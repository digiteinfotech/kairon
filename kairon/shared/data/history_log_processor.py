from kairon.exceptions import AppException
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.data_objects import ConversationsHistoryDeleteLogs
from mongoengine import Q, DoesNotExist
from datetime import datetime, timedelta
from loguru import logger


class HistoryDeletionLogProcessor:
    """
    This Class contains logic for conversations history deletion log processor
    """

    @staticmethod
    def add_log(bot: str, user: str, month: int = None, status: str = None, exception: str = None):

        try:
            doc = ConversationsHistoryDeleteLogs.objects(bot=bot, user=user).filter(
                Q(status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(status__ne=EVENT_STATUS.FAIL.value)).get()
        except DoesNotExist:
            doc = ConversationsHistoryDeleteLogs(
                bot=bot,
                user=user,
                start_timestamp=datetime.utcnow()
            )
        doc.status = status
        if exception:
            doc.exception = exception
        if month:
            doc.month = HistoryDeletionLogProcessor.get_datetime_previous_month(month)
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
    def get_datetime_previous_month(month: int):
        start_time = datetime.now() - timedelta(month * 30, seconds=0, minutes=0, hours=0)
        return start_time
