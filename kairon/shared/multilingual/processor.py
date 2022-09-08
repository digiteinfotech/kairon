from datetime import datetime

from loguru import logger
from mongoengine import Q, DoesNotExist

from kairon.shared.utils import Utility
from kairon.exceptions import AppException
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.multilingual.data_objects import BotReplicationLogs


class MultilingualLogProcessor:

    """Data processor to log multilingual translation event"""

    @staticmethod
    def add_log(source_bot: str, user: str, source_bot_name: str = None, s_lang: str = None, d_lang: str = None,
                account: int = None, translate_responses: bool = True, translate_actions: bool = False,
                exception: str = None, status: str = None, event_status: str = EVENT_STATUS.INITIATED.value):
        """
        Adds log for multilingual translation event
        :param source_bot: bot id of source bot
        :param source_bot_name: name of source bot
        :param s_lang: language of source bot
        :param d_lang: language of destination bot
        :param account: google cloud account number
        :param user: kairon username
        :param translate_actions: flag for translating actions
        :param translate_responses: flag for translating responses
        :param exception: Exception occurred during event
        :param status: Translation success or failure
        :param event_status: Event success or failed due to any error during translation
        :return:
        """
        try:
            doc = BotReplicationLogs.objects(bot=source_bot).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value)).get()
        except DoesNotExist:
            doc = BotReplicationLogs(
                source_bot_name=source_bot_name,
                s_lang=s_lang,
                d_lang=d_lang,
                bot=source_bot,
                user=user,
                account=account,
                translate_responses=translate_responses,
                translate_actions=translate_actions,
                start_timestamp=datetime.utcnow(),
            )
        doc.event_status = event_status
        if exception:
            doc.exception = exception
        if status:
            doc.status = status
        if source_bot_name:
            doc.source_bot_name = source_bot_name
        if s_lang:
            doc.s_lang = s_lang
        if event_status in {EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value}:
            doc.end_timestamp = datetime.utcnow()
        doc.save()

    @staticmethod
    def update_summary(source_bot: str, user: str, destination_bot: str, status: str = None,
                       event_status: str = EVENT_STATUS.COMPLETED.value):
        """
        Updates log for multilingual translation event
        :param source_bot: bot id of source bot
        :param user: kairon username
        :param destination_bot: bot id of destination bot
        :param status: Translation success or failure
        :param event_status: Event success or failed due to any error during translation
        :return:
        """
        try:
            doc = BotReplicationLogs.objects(bot=source_bot).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value)).get()
        except DoesNotExist:
            doc = BotReplicationLogs(
                bot=source_bot,
                user=user,
                start_timestamp=datetime.utcnow(),
            )

        doc.destination_bot = destination_bot

        doc.event_status = event_status
        if status:
            doc.status = status
        if event_status in {EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value}:
            doc.end_timestamp = datetime.utcnow()
        doc.save()

    @staticmethod
    def is_event_in_progress(source_bot: str, raise_exception=True):
        """
        Checks if event is in progress.
        @param source_bot: bot id for source bot
        @param raise_exception: Raise exception if event is in progress.
        @return: boolean flag.
        """
        in_progress = False
        try:
            BotReplicationLogs.objects(bot=source_bot).filter(
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
        doc_count = BotReplicationLogs.objects(
            bot=bot, start_timestamp__gte=today_start
        ).count()
        if doc_count >= Utility.environment["multilingual"]["limit_per_day"]:
            if raise_exception:
                raise AppException("Daily limit exceeded.")
            else:
                return True
        else:
            return False

    @staticmethod
    def get_logs(source_bot: str, start_idx: int = 0, page_size: int = 10):
        """
        Get all logs for data importer event.
        @param source_bot: bot id of source bot.
        @param start_idx: start index
        @param page_size: page size
        @return: list of logs.
        """
        for log in BotReplicationLogs.objects(bot=source_bot).order_by("-start_timestamp").skip(start_idx).limit(page_size):
            log = log.to_mongo().to_dict()
            log.pop('_id')
            log.pop('bot')
            log.pop('user')
            yield log

    @staticmethod
    def delete_enqueued_event_log(source_bot: str):
        """
        Deletes latest log if it is present in enqueued state.
        """
        latest_log = BotReplicationLogs.objects(bot=source_bot).order_by('-id').first()
        if latest_log and latest_log.event_status == EVENT_STATUS.ENQUEUED.value:
            latest_log.delete()
