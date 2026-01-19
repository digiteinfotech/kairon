from typing import Dict, Text

from uuid6 import uuid7
from datetime import datetime
from croniter import croniter, CroniterBadCronError
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

            cron_exp = request_data.get("cron_exp")
            run_at = request_data.get("run_at")

            if cron_exp:
                KScheduler().add_job(event_class=event_type, event_id=event_id,
                                          task_type=TASK_TYPE.EVENT.value, cron_exp=cron_exp,
                                          data=request_data["data"], timezone=request_data.get("timezone"))
                message = "Recurring Event Scheduled!"
            elif run_at:
                KScheduler().add_one_time_job(event_class=event_type, event_id=event_id,
                                              task_type=TASK_TYPE.EVENT.value, run_at=run_at,
                                              data=request_data["data"], timezone=request_data.get("timezone"))
                message = "One-time Event Scheduled!"
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
        task_type = TASK_TYPE.EVENT.value
        data = request_data["data"]

        cron_exp = request_data.get("cron_exp")
        run_at = request_data.get("run_at")
        timezone = request_data.get("timezone")

        KScheduler().update_job(
            event_id=event_id,
            task_type=task_type,
            event_class=event_type,
            data=data,
            cron_exp=cron_exp,
            run_at=run_at,
            timezone=timezone
        )
        return None, 'Scheduled event updated!'

    @staticmethod
    def schedule_channel_mail_reading(bot: str):
        from kairon.shared.channels.mail.processor import MailProcessor
        import pytz
        IST = pytz.timezone("Asia/Kolkata")

        try:
            mail_processor = MailProcessor(bot)
            interval = mail_processor.config.get("interval", "*/30 * * * *")

            event_id = mail_processor.state.event_id
            if event_id:
                KScheduler().update_job(event_id,
                                        TASK_TYPE.EVENT,
                                        cron_exp=interval,
                                        event_class=EventClass.mail_channel_read_mails, data={"bot": bot, "user": mail_processor.bot_settings.user}, timezone=IST)
            else:
                event_id = uuid7().hex
                mail_processor.update_event_id(event_id)
                KScheduler().add_job(event_id,
                                     TASK_TYPE.EVENT,
                                     interval,
                                     EventClass.mail_channel_read_mails, {"bot": bot, "user": mail_processor.bot_settings.user}, timezone=IST)
        except Exception as e:
            raise AppException(f"Failed to schedule mail reading for bot {bot}. Error: {str(e)}")

    @staticmethod
    def validate_cron(cron_expr, min_interval_minutes, check_occurrences=2):
        """
        Validate that a cron expression respects a minimum interval between runs.

        Args:
            cron_expr (str): Cron schedule string.
            min_interval_minutes (float): Minimum interval between runs in minutes.
            check_occurrences (int): How many upcoming occurrences to check.

        Returns:
            tuple: (bool, message)
        """
        base = datetime.now()

        try:
            itr = croniter(cron_expr, base)
        except CroniterBadCronError:
            raise AppException("Invalid cron expression")

        prev = itr.get_next(datetime)

        for _ in range(check_occurrences):
            nxt = itr.get_next(datetime)
            diff = (nxt - prev).total_seconds() / 60
            if diff < min_interval_minutes:
                raise AppException(f"Minimum time interval should be greater than equal to {min_interval_minutes} minutes")

            prev = nxt

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
