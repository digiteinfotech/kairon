from datetime import datetime
from loguru import logger
from mongoengine import Q, DoesNotExist
from kairon.exceptions import AppException
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.log_system.base import BaseLogHandler
from kairon.shared.upload_handler.data_objects import UploadHandlerLogs
from kairon.shared.data.constant import EVENT_STATUS
from typing import Text

class UploadHandlerLogProcessor:
    """
    Log processor for generic file uploads (CSV/XLSX or Media).
    """

    @staticmethod
    def add_log(
        bot: str,
        user: str,
        file_name: str = None,
        type: str = None,
        collection_name: str = None,
        is_uploaded: bool = False,
        upload_errors: dict = None,
        exception: str = None,
        status: str = None,
        event_status: str = EVENT_STATUS.INITIATED.value,
    ):
        try:
            doc = UploadHandlerLogs.objects(bot=bot).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value)
            ).get()
        except DoesNotExist:
            doc = UploadHandlerLogs(
                bot=bot,
                user=user,
                file_name=file_name,
                type=type,
                collection_name=collection_name,
                is_uploaded=is_uploaded,
                start_timestamp=datetime.utcnow()
            )

        doc.event_status = event_status
        if exception:
            doc.exception = exception
        if status:
            doc.status = status
        if upload_errors:
            doc.upload_errors = upload_errors
        if is_uploaded:
            doc.is_uploaded = True
        if event_status in {EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value}:
            doc.end_timestamp = datetime.utcnow()

        doc.save()

    @staticmethod
    def is_event_in_progress(bot: str, collection_name: Text, raise_exception=True):
        in_progress = False
        try:
            UploadHandlerLogs.objects(
                bot=bot,
                collection_name=collection_name  # new condition
            ).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value) &
                Q(event_status__ne=EVENT_STATUS.ABORTED.value)
            ).get()

            if raise_exception:
                raise AppException(
                    f"Upload already in progress for collection: {collection_name}. Check logs."
                )
            in_progress = True
        except DoesNotExist as e:
            logger.error(e)

        return in_progress

    @staticmethod
    def is_limit_exceeded(bot: str, raise_exception=True):
        today = datetime.today()
        today_start = today.replace(hour=0, minute=0, second=0)

        file_count = UploadHandlerLogs.objects(
            bot=bot, start_timestamp__gte=today_start
        ).count()
        if file_count >= BotSettings.objects(bot=bot).get().system_limits["file_upload_limit"]:
            if raise_exception:
                raise AppException("Daily upload limit exceeded.")
            return True
        return False

    @staticmethod
    def get_latest_event_file_name(bot: str):
        logs,count=BaseLogHandler.get_logs(bot, "file_upload")
        if not logs:
            return ""
        return logs[0].get("file_name", "")

    @staticmethod
    def delete_enqueued_event_log(bot: str):
        latest_log = UploadHandlerLogs.objects(bot=bot).order_by('-id').first()
        if latest_log and latest_log.event_status == EVENT_STATUS.ENQUEUED.value:
            latest_log.delete()
