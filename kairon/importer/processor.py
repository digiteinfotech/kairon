from datetime import datetime

from loguru import logger
from mongoengine import Q, DoesNotExist

from kairon.data_processor.constant import EVENT_STATUS
from .data_objects import ValidationLogs
from kairon.utils import Utility
from kairon.exceptions import AppException


class DataImporterLogProcessor:
    """
    Data processor to log data importer event.
    """

    @staticmethod
    def add_log(bot: str, user: str, summary: dict = None, is_data_uploaded: bool = True, files_received: list = None,
                exception: str = None, status: str = None, event_status: str = EVENT_STATUS.INITIATED.value):
        """
        Adds/updated log for data importer event.
        @param bot: bot id.
        @param user: kairon username.
        @param files_received: files received for upload.
        @param summary: validation summary (errors in intents, stories, training examples, responses).
        @param is_data_uploaded: Was the data uploaded or was the event triggered on existing kairon data.
        @param exception: Exception occurred during event.
        @param status: Validation success or failure.
        @param event_status: Event success or failed due to any error during validation or import.
        @return:
        """
        try:
            doc = ValidationLogs.objects(bot=bot, user=user).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value)).get()
        except DoesNotExist as e:
            logger.error(str(e))
            logger.info("Adding new log.")
            doc = ValidationLogs(
                is_data_uploaded=is_data_uploaded,
                files_received=files_received,
                bot=bot,
                user=user,
                start_timestamp=datetime.utcnow(),
            )
        if summary:
            doc.intents = summary.get('intents')
            doc.utterances = summary.get('utterances')
            doc.stories = summary.get('stories')
            doc.training_examples = summary.get('training_examples')
            doc.domain = summary.get('domain')
            doc.config = summary.get('config')
            doc.http_actions = summary.get('http_actions')
        doc.event_status = event_status
        if exception:
            doc.exception = exception
        if status:
            doc.status = status
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
            ValidationLogs.objects(bot=bot).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value)).get()

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
        @param raise_exception: Raise exception if event is in progress.
        @return: boolean flag
        """
        today = datetime.today()

        today_start = today.replace(hour=0, minute=0, second=0)
        doc_count = ValidationLogs.objects(
            bot=bot, start_timestamp__gte=today_start
        ).count()
        if doc_count >= Utility.environment['model']["data_importer"]["limit_per_day"]:
            if raise_exception:
                raise AppException("Daily limit exceeded.")
            else:
                return True
        else:
            return False

    @staticmethod
    def get_logs(bot: str):
        """
        Get all logs for data importer event.
        @param bot: bot id.
        @return: list of logs.
        """
        for log in ValidationLogs.objects(bot=bot).order_by("-start_timestamp"):
            log = log.to_mongo().to_dict()
            log.pop('_id')
            log.pop('bot')
            log.pop('user')
            yield log

    @staticmethod
    def get_files_received_for_latest_event(bot: str):
        """
        Fetch set of files received for latest event.
        @param bot: bot id.
        """
        files_received = next(DataImporterLogProcessor.get_logs(bot)).get("files_received")
        files_received = set(files_received) if files_received else set()
        return files_received
