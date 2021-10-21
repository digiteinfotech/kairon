from datetime import datetime

from loguru import logger
from mongoengine import Q, DoesNotExist

from kairon.exceptions import AppException
from kairon.shared.data.constant import EVENT_STATUS
from kairon.test.data_objects import ModelTestingLogs


class ModelTestingLogProcessor:

    @staticmethod
    def add_initiation_log(bot: str, user: str, run_e2e: bool, event_status=EVENT_STATUS.INITIATED.value):
        ModelTestingLogs(
            run_on_test_stories=run_e2e,
            bot=bot,
            user=user,
            start_timestamp=datetime.utcnow(),
            event_status=event_status
        ).save()

    @staticmethod
    def update_log_with_test_results(bot: str, user: str, run_e2e: bool = None, event_status: str = None,
                                     stories=None, nlu=None,
                                     exception: str = None
                                     ):
        try:
            doc = ModelTestingLogs.objects(bot=bot).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value)).get()
        except DoesNotExist:
            doc = ModelTestingLogs(
                bot=bot,
                user=user,
                start_timestamp=datetime.utcnow(),
            )
        if run_e2e:
            doc.run_on_test_stories = run_e2e
        if event_status:
            doc.event_status = event_status
        if event_status in {EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value}:
            doc.end_timestamp = datetime.utcnow()
        if event_status == EVENT_STATUS.COMPLETED.value:
            doc.status = 'PASSED'
        if stories:
            doc.stories = stories
            if stories.get('failed_stories'):
                doc.status = 'FAILURE'
        if nlu:
            doc.nlu = nlu
            if nlu.get("intent_evaluation") and nlu["intent_evaluation"].get('errors'):
                doc.status = 'FAILURE'
            if nlu.get("response_selection_evaluation") and nlu["response_selection_evaluation"].get('errors'):
                doc.status = 'FAILURE'
            if nlu.get("entity_evaluation"):
                for extractor_used in nlu["entity_evaluation"]:
                    if extractor_used.get('error'):
                        doc.status = 'FAILURE'
                        break
        if exception:
            doc.exception = exception
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
            ModelTestingLogs.objects(bot=bot).filter(
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
        from kairon import Utility

        today = datetime.today()
        today_start = today.replace(hour=0, minute=0, second=0)
        doc_count = ModelTestingLogs.objects(
            bot=bot, start_timestamp__gte=today_start
        ).count()
        if doc_count >= Utility.environment['model']["test"]["limit_per_day"]:
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
        for log in ModelTestingLogs.objects(bot=bot).order_by("-start_timestamp"):
            log = log.to_mongo().to_dict()
            log.pop('_id')
            log.pop('bot')
            yield log
