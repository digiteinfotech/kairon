from datetime import date
from kairon.exceptions import AppException
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.data_objects import ConversationsHistoryDeleteLogs
from mongoengine import Q, DoesNotExist
from datetime import datetime, timedelta
from loguru import logger


class HistoryDeletionLogProcessor:
    """This Class contains logic for conversations history deletion log processor"""

    @staticmethod
    def add_log(bot: str, user: str, till_date: date = None, status: str = None,
                exception: str = None, sender_id: str = None):

        try:
            doc = ConversationsHistoryDeleteLogs.objects(bot=bot).filter(
                Q(status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(status__ne=EVENT_STATUS.FAIL.value)).get()
        except DoesNotExist:
            doc = ConversationsHistoryDeleteLogs(
                bot=bot,
                user=user,
                start_timestamp=datetime.utcnow(),
                sender_id=sender_id
            )
        doc.status = status
        if exception:
            doc.exception = exception
        if till_date:
            doc.till_date = till_date
        if status in {EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value}:
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
            ConversationsHistoryDeleteLogs.objects(bot=bot).filter(
                Q(status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(status__ne=EVENT_STATUS.FAIL.value)).get()

            if raise_exception:
                raise AppException("Event already in progress! Check logs.")
            in_progress = True
        except DoesNotExist as e:
            logger.error(e)
        return in_progress

    @staticmethod
    def get_logs(bot: str, start_idx: int = 0, page_size: int = 10):
        """
        Get all logs for history deletion event.
        @param bot: bot id.
        @param start_idx: start index
        @param page_size: page size
        @return: list of logs.
        """
        for log in ConversationsHistoryDeleteLogs.objects(bot=bot).order_by("-start_timestamp").skip(start_idx).limit(page_size):
            log = log.to_mongo().to_dict()
            log.pop('_id')
            yield log

    @staticmethod
    def delete_enqueued_event_log(bot: str):
        latest_log = ConversationsHistoryDeleteLogs.objects(bot=bot).order_by('-id').first()
        if latest_log and latest_log.status == EVENT_STATUS.ENQUEUED.value:
            latest_log.delete()
