from typing import Dict, Text

from uuid6 import uuid7

from kairon.events.executors.factory import ExecutorFactory
from kairon.events.scheduler.kscheduler import KScheduler
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import TASK_TYPE
from loguru import logger


class EventUtility:

    @staticmethod
    def add_job(event_type: Text, request_data: Dict, is_scheduled: bool):
        message = None
        if is_scheduled:
            response = None
            event_id = request_data["data"]["event_id"]
            KScheduler().add_job(event_class=event_type, event_id=event_id,
                                 task_type=TASK_TYPE.EVENT.value, **request_data)
            message = 'Event Scheduled!'
        else:
            response = ExecutorFactory.get_executor().execute_task(event_class=event_type,
                                                                   task_type=TASK_TYPE.EVENT.value,
                                                                   data=request_data["data"])
        return response, message

    @staticmethod
    def update_job(event_type: Text, request_data: Dict, is_scheduled: bool):
        if not is_scheduled:
            raise AppException("Updating non-scheduled event not supported!")

        event_id = request_data["data"]["event_id"]
        KScheduler().update_job(event_class=event_type, event_id=event_id, task_type=TASK_TYPE.EVENT.value,
                                **request_data)
        return None, 'Scheduled event updated!'

    @staticmethod
    def schedule_channel_mail_reading(bot: str):
        from kairon.shared.channels.mail.processor import MailProcessor

        try:
            mail_processor = MailProcessor(bot)
            interval = mail_processor.config.get("interval", 60)
            event_id = mail_processor.state.event_id
            if event_id:
                KScheduler().update_job(event_id,
                                        TASK_TYPE.EVENT,
                                        f"*/{interval} * * * *",
                                        EventClass.mail_channel_read_mails, {"bot": bot, "user": mail_processor.bot_settings.user})
            else:
                event_id = uuid7().hex
                mail_processor.update_event_id(event_id)
                KScheduler().add_job(event_id,
                                     TASK_TYPE.EVENT,
                                     f"*/{interval} * * * *",
                                     EventClass.mail_channel_read_mails, {"bot": bot, "user": mail_processor.bot_settings.user})
        except Exception as e:
            raise AppException(f"Failed to schedule mail reading for bot {bot}. Error: {str(e)}")

    @staticmethod
    def stop_channel_mail_reading(bot: str):
        from kairon.shared.channels.mail.processor import MailProcessor

        try:
            mail_processor = MailProcessor(bot)
            event_id = mail_processor.state.event_id
            if event_id:
                mail_processor.update_event_id(None)
                KScheduler().delete_job(event_id)
        except Exception as e:
            raise AppException(f"Failed to stop mail reading for bot {bot}. Error: {str(e)}")
