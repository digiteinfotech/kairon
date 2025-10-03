import time
from datetime import datetime
from typing import Text, Dict

from bson import ObjectId
from loguru import logger

from kairon.events.definitions.scheduled_base import ScheduledEventsBase
from kairon.exceptions import AppException
from kairon.shared.channels.broadcast.factory import MessageBroadcastFactory
from kairon.shared.chat.broadcast.constants import MessageBroadcastLogType
from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
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
        bot_settings = MongoProcessor.get_bot_settings(self.bot, self.user)
        if bot_settings['notification_scheduling_limit'] <= \
                len(list(MessageBroadcastProcessor.list_settings(self.bot, timestamp__gt=date_today))):
            raise AppException("Notification scheduling limit reached!")

    def validate_retry_broadcast(self, event_id: Text):
        bot_settings = MongoProcessor.get_bot_settings(self.bot, self.user)
        config = MessageBroadcastProcessor.get_settings(event_id, self.bot, is_resend=True)

        if bot_settings['retry_broadcasting_limit'] <= config["retry_count"]:
            raise AppException("Retry Broadcasting limit reached!")

    def execute(self, event_id: Text, **kwargs):
        """
        Execute the event.
        """
        config = None
        reference_id = None
        status = EVENT_STATUS.INITIATED.value
        exception = None
        is_resend = kwargs.get('is_resend', "False") == "True"
        try:
            config, reference_id = self.__retrieve_config(event_id, is_resend)
            broadcast = MessageBroadcastFactory.get_instance(config["connector_type"]).from_config(config, event_id,
                                                                                                   reference_id)
            if is_resend:
                config = broadcast.resend_broadcast()
            else:
                config = MessageBroadcastProcessor.update_retry_count(event_id, self.bot, self.user, retry_count=0)
                recipients = broadcast.get_recipients()
                broadcast.send(recipients)
            status = EVENT_STATUS.COMPLETED.value
        except Exception as e:
            logger.exception(e)
            exception = str(e)
            status = EVENT_STATUS.FAIL.value
        finally:
            time.sleep(5)
            MessageBroadcastProcessor.insert_status_received_on_channel_webhook(reference_id, config["name"],
                                                                                config["retry_count"])
            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.common.value, reference_id, status=status, exception=exception
            )
            if config and not config.get("scheduler_config"):
                MessageBroadcastProcessor.delete_task(event_id, self.bot, False)

    def _trigger_async(self, config: Dict):
        msg_broadcast_id = None
        try:
            msg_broadcast_id = MessageBroadcastProcessor.add_scheduled_task(self.bot, self.user, config)
            payload = {'bot': self.bot, 'user': self.user, "event_id": msg_broadcast_id, "is_resend": "False"}
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
            timezone = config["scheduler_config"]["timezone"]
            payload = {'bot': self.bot, 'user': self.user, "event_id": msg_broadcast_id, "is_resend": "False"}
            Utility.request_event_server(EventClass.message_broadcast, payload, is_scheduled=True, cron_exp=cron_exp,
                                         timezone=timezone)
            return msg_broadcast_id
        except Exception as e:
            logger.error(e)
            if msg_broadcast_id:
                MessageBroadcastProcessor.delete_task(msg_broadcast_id, self.bot)
            raise AppException(e)

    def _add_one_time_schedule(self, config: Dict):
        msg_broadcast_id = None
        if not config.get("one_time_scheduler_config") or not config["one_time_scheduler_config"].get("run_at"):
            raise AppException("one_time_scheduler_config with run_at is required!")
        try:
            run_at = config["one_time_scheduler_config"].get("run_at")
            if isinstance(run_at, str):
                run_at = datetime.fromisoformat(run_at.replace("Z", "+00:00"))

            elif isinstance(run_at, (int, float)):
                run_at = datetime.fromtimestamp(run_at)
            config["one_time_scheduler_config"]["run_at"] = run_at
            msg_broadcast_id = MessageBroadcastProcessor.add_scheduled_task(self.bot, self.user, config)
            run_at = config["one_time_scheduler_config"].get("run_at")
            timezone = config["one_time_scheduler_config"].get("timezone", "UTC")

            payload = {
                'bot': self.bot,
                'user': self.user,
                "event_id": msg_broadcast_id,
                "is_resend": "False",
            }
            Utility.request_event_server(
                EventClass.message_broadcast,
                payload,
                is_scheduled=True,
                timezone=timezone,
                run_at = run_at.isoformat()
            )
            return msg_broadcast_id
        except Exception as e:
            logger.error(e)
            if msg_broadcast_id:
                MessageBroadcastProcessor.delete_task(msg_broadcast_id, self.bot)
            raise AppException(e)


    def _resend_broadcast(self, msg_broadcast_id: Text):
        try:
            payload = {'bot': self.bot, 'user': self.user,
                       "event_id": msg_broadcast_id, "is_resend": "True"}
            Utility.request_event_server(EventClass.message_broadcast, payload)
            return msg_broadcast_id
        except Exception as e:
            logger.error(e)
            raise e

    def _update_schedule(self, msg_broadcast_id: Text, config: Dict):
        settings_updated = False
        current_settings = {}
        try:
            if not config.get("scheduler_config") and not config.get("one_time_scheduler_config"):
                raise AppException("scheduler_config or one_time_scheduler_config is required!")

            current_settings = MessageBroadcastProcessor.get_settings(msg_broadcast_id, self.bot)
            MessageBroadcastProcessor.update_scheduled_task(msg_broadcast_id, self.bot, self.user, config)
            settings_updated = True

            payload = {
                "bot": self.bot,
                "user": self.user,
                "event_id": msg_broadcast_id,
                "is_resend": "False"
            }

            if config.get("scheduler_config"):
                scheduler_config = config["scheduler_config"]
                cron_exp = scheduler_config.get("schedule")
                timezone = scheduler_config.get("timezone")

                if not cron_exp:
                    raise AppException("schedule (cron expression) must be provided for scheduler_config")

                Utility.request_event_server(
                    EventClass.message_broadcast,
                    payload,
                    method="PUT",
                    is_scheduled=True,
                    cron_exp=cron_exp,
                    timezone=timezone
                )

            elif config.get("one_time_scheduler_config"):
                one_time_config = config["one_time_scheduler_config"]
                run_at = one_time_config.get("run_at")
                if isinstance(run_at, str):
                    run_at = datetime.fromisoformat(run_at.replace("Z", "+00:00"))

                elif isinstance(run_at, (int, float)):
                    run_at = datetime.fromtimestamp(run_at)

                config["one_time_scheduler_config"]["run_at"] = run_at
                run_at = config["one_time_scheduler_config"].get("run_at")
                timezone = config["one_time_scheduler_config"].get("timezone", "UTC")

                Utility.request_event_server(
                    EventClass.message_broadcast,
                    payload,
                    method="PUT",
                    is_scheduled=True,
                    run_at=run_at.isoformat(),
                    timezone=timezone
                )

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
            Utility.delete_scheduled_event(msg_broadcast_id)
            MessageBroadcastProcessor.delete_task(msg_broadcast_id, self.bot)
        except Exception as e:
            logger.error(e)
            raise e

    def __retrieve_config(self, event_id: Text, is_resend: bool):

        reference_id = MessageBroadcastProcessor.get_reference_id_from_broadcasting_logs(event_id) \
            if is_resend else ObjectId().__str__()
        config = MessageBroadcastProcessor.get_settings(event_id, self.bot, is_resend=is_resend)
        bot_settings = MongoProcessor.get_bot_settings(self.bot, self.user)
        config["pyscript_timeout"] = bot_settings["dynamic_broadcast_execution_timeout"]
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, reference_id, user=self.user, config=config,
            status=EVENT_STATUS.INPROGRESS.value, event_id=event_id, is_new_log=True, is_resend=is_resend
        )
        return config, reference_id
