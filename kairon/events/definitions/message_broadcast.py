import ast
from datetime import datetime
from typing import Text, Dict, List, Any

from loguru import logger
from mongoengine import DoesNotExist

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.factory import WhatsappFactory
from kairon.events.definitions.scheduled_base import ScheduledEventsBase
from kairon.exceptions import AppException
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.chat.notifications.constants import MessageBroadcastLogType
from kairon.shared.chat.notifications.data_objects import MessageBroadcastSettings
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.chat.notifications.processor import MessageBroadcastProcessor


class MessageBroadcastEvent(ScheduledEventsBase):
    """
    Event to trigger notifications instantly or schedule them.
    """

    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise event.
        """
        super(MessageBroadcastEvent, self).__init__()
        self.bot = bot
        self.user = user

    def validate(self):
        """
        Validates if a model is trained for the bot,
        an event is already running for that particular bot and also
        whether the event trigger limit has exceeded.
        """
        date_today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        bot_settings = MongoProcessor().get_bot_settings(self.bot, self.user)
        if bot_settings['notification_scheduling_limit'] <= \
                len(list(MessageBroadcastProcessor.list_settings(self.bot, timestamp__gt=date_today))):
            raise AppException("Notification scheduling limit reached!")

    def execute(self, event_id: Text, **kwargs):
        """
        Execute the event.
        """
        reference_id = None
        config = None
        status = EVENT_STATUS.FAIL.value
        exception = None
        try:
            reference_id, config = self.__retrieve_config(event_id)
            data = self.__pull_data(config, reference_id)
            recipients = self.__get_recipients(config, data, reference_id)
            self.__broadcast(recipients, config, data, reference_id)
            status = EVENT_STATUS.COMPLETED.value
        except Exception as e:
            logger.exception(e)
            exception = str(e)
        finally:
            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.common.value, reference_id=reference_id, status=status,
                broadcast_id=event_id, exception=exception
            )
            if config and not config.get("scheduler_config"):
                MessageBroadcastProcessor.delete_task(event_id, self.bot, False)

    def _trigger_async(self, config: Dict):
        msg_broadcast_id = None
        try:
            msg_broadcast_id = MessageBroadcastProcessor.add_scheduled_task(self.bot, self.user, config)
            payload = {'bot': self.bot, 'user': self.user, "event_id": msg_broadcast_id}
            Utility.request_event_server(EventClass.message_broadcast, payload)
            return msg_broadcast_id
        except Exception as e:
            logger.error(e)
            if msg_broadcast_id:
                MessageBroadcastProcessor.delete_task(msg_broadcast_id, self.bot)
            raise e

    def _add_schedule(self, config: Dict):
        msg_broadcast_id = None
        if not config.get("scheduler_config") or not config["scheduler_config"].get("schedule"):
            raise AppException("scheduler_config is required!")
        try:
            msg_broadcast_id = MessageBroadcastProcessor.add_scheduled_task(self.bot, self.user, config)
            cron_exp = config["scheduler_config"]["schedule"]
            payload = {'bot': self.bot, 'user': self.user, "event_id": msg_broadcast_id, "cron_exp": cron_exp}
            Utility.request_event_server(EventClass.message_broadcast, payload, is_scheduled=True)
            return msg_broadcast_id
        except Exception as e:
            logger.error(e)
            if msg_broadcast_id:
                MessageBroadcastProcessor.delete_task(msg_broadcast_id, self.bot)
            raise AppException(e)

    def _update_schedule(self, msg_broadcast_id: Text, config: Dict):
        settings_updated = False
        current_settings = {}
        if not config.get("scheduler_config") or not config["scheduler_config"].get("schedule"):
            raise AppException("scheduler_config is required!")
        try:
            current_settings = MessageBroadcastProcessor.get_settings(msg_broadcast_id, self.bot)
            MessageBroadcastProcessor.update_scheduled_task(msg_broadcast_id, self.bot, self.user, config)
            settings_updated = True
            cron_exp = config["scheduler_config"]["schedule"]
            payload = {'bot': self.bot, 'user': self.user, "event_id": msg_broadcast_id, "cron_exp": cron_exp}
            Utility.request_event_server(EventClass.message_broadcast, payload, method="PUT", is_scheduled=True)
        except Exception as e:
            logger.error(e)
            if settings_updated:
                MessageBroadcastProcessor.update_scheduled_task(msg_broadcast_id, self.bot, self.user, current_settings)
            raise e

    def delete_schedule(self, msg_broadcast_id: Text):
        try:
            if not Utility.is_exist(MessageBroadcastSettings, raise_error=False, bot=self.bot,
                                    id=msg_broadcast_id, status=True):
                raise AppException("Notification settings not found!")
            payload = {'bot': self.bot, 'user': self.user, "event_id": msg_broadcast_id}
            Utility.request_event_server(EventClass.message_broadcast, payload, method="DELETE", is_scheduled=True)
            MessageBroadcastProcessor.delete_task(msg_broadcast_id, self.bot)
        except Exception as e:
            logger.error(e)
            raise e

    def __pull_data(self, config: Dict, reference_id: Text):
        data = {}
        extraction_log = {}
        if config.get('data_extraction_config'):
            url = config["data_extraction_config"]["url"]
            method = config["data_extraction_config"]["method"]
            headers = config["data_extraction_config"].get("headers")
            data = Utility.execute_http_request(method, url, headers=headers)
            extraction_log['url'] = url
            extraction_log['headers'] = headers
            extraction_log['method'] = method
            extraction_log['api_response'] = data
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, reference_id, data_extraction=extraction_log,
            status=EVENT_STATUS.DATA_EXTRACTED.value
        )
        return data

    def __get_recipients(self, config: Dict, data: Any, reference_id: Text):
        eval_log = None
        if config["recipients_config"]["recipient_type"] == "static":
            recipients = [number.strip() for number in config["recipients_config"]["recipients"].split(',')]
        else:
            recipients, eval_log = ActionUtility.evaluate_script(config["recipients_config"]["recipients"], data)
            recipients = ast.literal_eval(recipients)
        if not isinstance(recipients, List):
            raise AppException(f"recipients evaluated to unexpected data type: {recipients}")
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, reference_id, recipients=recipients,
            status=EVENT_STATUS.EVALUATE_RECIPIENTS.value, evaluation_log=eval_log
        )
        return recipients

    def __get_template_parameters(self, template_config: Dict, data: Any, reference_id: Text):
        template_params = template_config.get("data")
        if template_params:
            if template_config["template_type"] == "dynamic":
                template_params = ActionUtility.evaluate_script(template_params, data)
            template_params = ast.literal_eval(template_params)
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, reference_id, template_params=template_params,
            status=EVENT_STATUS.EVALUATE_TEMPLATE.value
        )
        return template_params

    def __get_client(self, channel: Text):
        try:
            bot_settings = MongoProcessor.get_bot_settings(self.bot, self.user)
            channel_config = ChatDataProcessor.get_channel_config(channel, self.bot, mask_characters=False)
            access_token = channel_config["config"].get('api_key') or channel_config["config"].get('access_token')
            channel_client = WhatsappFactory.get_client(bot_settings["whatsapp"])
            channel_client = channel_client(access_token, config=channel_config)
            return channel_client
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException(f"{channel} channel config not found!")
    
    def __broadcast(self, recipients: List, config: Dict, data: Any, reference_id: Text):
        channel_client = self.__get_client(config['connector_type'])

        for template_config in config['template_config']:
            template_id = template_config["template_id"]
            namespace = template_config["namespace"]
            template_params = self.__get_template_parameters(template_config, data, reference_id)
            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.common.value, reference_id, status=EVENT_STATUS.BROADCAST_STARTED.value
            )

            for recipient in recipients:
                recipient = str(recipient) if recipient else ""
                if not Utility.check_empty_string(recipient):
                    response = channel_client.send_template_message(namespace, template_id, recipient, components=template_params)
                    status = "Failed" if response.get("errors") else "Success"
                    MessageBroadcastProcessor.add_event_log(
                        self.bot, MessageBroadcastLogType.send.value, reference_id, api_response=response, status=status,
                        recipient=recipient, template_params=template_params
                    )

    def __retrieve_config(self, doc_id: Text):
        config = MessageBroadcastProcessor.get_settings(doc_id, self.bot)
        reference_id = MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, user=self.user, config=config,
            status=EVENT_STATUS.INPROGRESS.value, broadcast_id=doc_id
        )
        return reference_id, config
