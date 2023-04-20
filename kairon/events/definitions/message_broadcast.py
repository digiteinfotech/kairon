from datetime import datetime
from typing import Text, Dict

from loguru import logger

from kairon.events.definitions.scheduled_base import ScheduledEventsBase
from kairon.exceptions import AppException
from kairon.shared.channels.broadcast.factory import MessageBroadcastFactory
from kairon.shared.chat.notifications.constants import MessageBroadcastLogType
from kairon.shared.chat.notifications.data_objects import MessageBroadcastSettings
from kairon.shared.chat.notifications.processor import MessageBroadcastProcessor
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility


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
            broadcast = MessageBroadcastFactory.get_instance(config["connector_type"]).from_config(config, reference_id)
            data = broadcast.pull_data()
            recipients = broadcast.get_recipients(data)
            broadcast.send(recipients, data)
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

    def __retrieve_config(self, doc_id: Text):
        config = MessageBroadcastProcessor.get_settings(doc_id, self.bot)
        reference_id = MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, user=self.user, config=config,
            status=EVENT_STATUS.INPROGRESS.value, broadcast_id=doc_id
        )
        return reference_id, config
