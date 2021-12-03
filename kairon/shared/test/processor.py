from datetime import datetime

from bson import ObjectId
from loguru import logger
from mongoengine import Q, DoesNotExist

from kairon.exceptions import AppException
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.test.data_objects import ModelTestingLogs


class ModelTestingLogProcessor:

    @staticmethod
    def log_test_result(bot: str, user: str, event_status: str = None,
                        stories_result=None, nlu_result=None, exception: str = None):
        try:
            common_data = ModelTestingLogs.objects(bot=bot, type='common').filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value)).get()
        except DoesNotExist:
            common_data = ModelTestingLogs(
                reference_id=ObjectId().__str__(),
                type='common',
                bot=bot,
                user=user,
                start_timestamp=datetime.utcnow()
            )
        if event_status:
            common_data.event_status = event_status
        if event_status in {EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value}:
            common_data.end_timestamp = datetime.utcnow()
        if event_status == EVENT_STATUS.COMPLETED.value:
            common_data.status = 'PASSED'
        if stories_result:
            common_data.status = 'FAILURE' if stories_result.get('failed_stories') else 'SUCCESS'
            ModelTestingLogs(
                reference_id=common_data.reference_id,
                type='stories',
                bot=bot,
                user=user,
                data=stories_result
            ).save()

        if nlu_result:
            ModelTestingLogs(
                reference_id=common_data.reference_id,
                type='nlu',
                bot=bot,
                user=user,
                data=nlu_result
            ).save()
            if nlu_result.get("intent_evaluation") and nlu_result["intent_evaluation"].get('errors'):
                common_data.status = 'FAILURE'
            if nlu_result.get("response_selection_evaluation") and nlu_result["response_selection_evaluation"].get('errors'):
                common_data.status = 'FAILURE'
            if nlu_result.get("entity_evaluation"):
                for extractor_evaluation in nlu_result["entity_evaluation"].values():
                    if extractor_evaluation.get('errors'):
                        common_data.status = 'FAILURE'
                        break
        if exception:
            common_data.exception = exception
        common_data.save()

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
            ModelTestingLogs.objects(bot=bot, type='common').filter(
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
        initiated_today = today.replace(hour=0, minute=0, second=0)
        doc_count = ModelTestingLogs.objects(
            bot=bot, type='common', start_timestamp__gte=initiated_today
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
        return list(ModelTestingLogs.objects(bot=bot).aggregate([
            {"$set": {"data.type": "$type"}},
            {'$group': {'_id': '$reference_id', 'bot': {'$first': '$bot'}, 'user': {'$first': '$user'},
                        'status': {'$first': '$status'},
                        'event_status': {'$first': '$event_status'}, 'data': {'$push': '$data'},
                        'exception': {'$first': '$exception'},
                        'start_timestamp': {'$first': '$start_timestamp'},
                        'end_timestamp': {'$first': '$end_timestamp'}}},
            {'$project': {
                'data': {'$filter': {'input': '$data', 'as': 'data', 'cond': {'$ne': ['$$data.type', 'common']}}},
                'status': 1, 'event_status': 1, 'exception': 1, 'start_timestamp': 1, 'end_timestamp': 1}},
            {"$sort": {"start_timestamp": -1}}]))
