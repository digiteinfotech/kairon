from datetime import datetime

from bson import ObjectId
from loguru import logger
from mongoengine import Q, DoesNotExist
from kairon.shared.content_importer.data_objects import ContentValidationLogs
from kairon.shared.data.constant import EVENT_STATUS
from kairon.exceptions import AppException
from kairon.shared.data.data_objects import BotSettings


class ContentImporterLogProcessor:
    """
    Log processor for content importer event.
    """

    @staticmethod
    def add_log(bot: str, user: str, table: str = "", is_data_uploaded: bool = False, file_received: str = None,
                validation_errors: dict = None, exception: str = None, status: str = None, event_status: str = EVENT_STATUS.INITIATED.value):
        """
        Adds or updates log for content importer event.
        @param bot: bot id.
        @param user: kairon username.
        @param table: table name.
        @param file_received: files received for upload.
        @param is_data_uploaded: Was the data uploaded or was the event triggered on existing kairon data.
        @param validation_errors: Dictionary containing any validation errors encountered
        @param exception: Exception occurred during event.
        @param status: Validation success or failure.
        @param event_status: Event success or failed due to any error during validation or import.
        @return:
        """
        try:
            doc = ContentValidationLogs.objects(bot=bot).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value)).get()
        except DoesNotExist:
            doc = ContentValidationLogs(
                is_data_uploaded=is_data_uploaded,
                file_received=file_received,
                bot=bot,
                user=user,
                table=table,
                start_timestamp=datetime.utcnow(),
                event_id=str(ObjectId())
            )
        doc.event_status = event_status
        if exception:
            doc.exception = exception
        if status:
            doc.status = status
        if validation_errors:
            doc.validation_errors = validation_errors
        if event_status in {EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value}:
            doc.end_timestamp = datetime.utcnow()
        doc.save()

    @staticmethod
    def is_event_in_progress(bot: str, raise_exception=True):
        """
        Checks if event is in progress.
        @param bot: bot id
        @param raise_exception: Raise exception if event is in progress.
        @return: boolean flag.
        """
        in_progress = False
        try:
            ContentValidationLogs.objects(bot=bot).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value) &
                Q(event_status__ne=EVENT_STATUS.ABORTED.value)).get()

            if raise_exception:
                raise AppException("Event already in progress! Check logs.")
            in_progress = True
        except DoesNotExist as e:
            logger.error(e)
        return in_progress

    @staticmethod
    def is_limit_exceeded(bot: str, raise_exception=True):
        """
        Checks if daily event triggering limit exceeded.
        @param bot: bot id.
        @param raise_exception: Raise exception if limit is reached.
        @return: boolean flag
        """
        today = datetime.today()

        today_start = today.replace(hour=0, minute=0, second=0)
        doc_count = ContentValidationLogs.objects(
            bot=bot, start_timestamp__gte=today_start
        ).count()
        if doc_count >= BotSettings.objects(bot=bot).get().content_importer_limit_per_day:
            if raise_exception:
                raise AppException("Daily limit exceeded.")
            else:
                return True
        else:
            return False

    @staticmethod
    def get_logs(bot: str, start_idx: int = 0, page_size: int = 10):
        """
        Get all logs for content importer event.
        @param bot: bot id.
        @param start_idx: start index
        @param page_size: page size
        @return: list of logs.
        """
        for log in ContentValidationLogs.objects(bot=bot).order_by("-start_timestamp").skip(start_idx).limit(page_size):
            log = log.to_mongo().to_dict()
            log.pop('_id')
            log.pop('bot')
            log.pop('user')
            yield log

    @staticmethod
    def get_file_received_for_latest_event(bot: str):
        """
        Fetch set of files received for latest event.
        @param bot: bot id.
        """
        file_received = next(ContentImporterLogProcessor.get_logs(bot)).get("file_received")
        return file_received

    @staticmethod
    def get_event_id_for_latest_event(bot: str):
        """
        Fetch event_id for latest event.
        @param bot: bot id.
        """
        event_id = next(ContentImporterLogProcessor.get_logs(bot)).get("event_id")
        return event_id

    @staticmethod
    def delete_enqueued_event_log(bot: str):
        """
        Deletes latest log if it is present in enqueued state.
        """
        latest_log = ContentValidationLogs.objects(bot=bot).order_by('-id').first()
        if latest_log and latest_log.event_status == EVENT_STATUS.ENQUEUED.value:
            latest_log.delete()
