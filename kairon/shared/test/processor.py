import json
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
        from kairon.shared.utils import Utility

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
    def get_logs(bot: str, log_type: str = None, reference_id: str = None, start_idx: int = 0, page_size: int = 10):
        """
        Get all logs for data importer event.
        @param reference_id: test reference_id
        @param bot: bot id.
        @param log_type: log data type: 'stories', 'nlu'
        @param start_idx: start index in list field
        @param page_size: number of rows from start index
        @return: list of logs.
        """
        from kairon.shared.utils import Utility

        if not (Utility.check_empty_string(log_type) and Utility.check_empty_string(reference_id)):
            logs = ModelTestingLogProcessor.get_by_id_and_type(reference_id, bot, log_type, start_idx, page_size)
        else:
            logs = ModelTestingLogProcessor.get_all(bot)
        return logs

    @staticmethod
    def get_all(bot: str):
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
                '_id': 0, 'reference_id': '$_id',
                'data': {'$filter': {'input': '$data', 'as': 'data', 'cond': {'$ne': ['$$data.type', 'common']}}},
                'status': 1, 'event_status': 1, 'exception': 1, 'start_timestamp': 1, 'end_timestamp': 1}},
            {"$sort": {"start_timestamp": -1}}]))

    @staticmethod
    def get_by_id_and_type(reference_id: str, bot: str, log_type: str, start_idx: int = 0, page_size: int = 10):
        """
        Get all logs for data importer event.
        @param reference_id: test reference_id
        @param bot: bot id.
        @param log_type: log data type: 'stories', 'nlu'
        @param start_idx: start index in list field
        @param page_size: number of rows from start index
        @return: list of logs.
        """
        logs = []
        filtered_data = ModelTestingLogs.objects(reference_id=reference_id, bot=bot, type=log_type)
        if log_type == 'stories' and filtered_data:
            filtered_data = filtered_data.get()
            logs = filtered_data.data.get('failed_stories', [])[start_idx:start_idx+page_size]
            fail_cnt = filtered_data.data.get('conversation_accuracy', {}).get('failure_count', 0)
            logs = {'errors': logs, 'total': fail_cnt}
            if fail_cnt:
                logs = json.dumps(logs)
                logs = json.loads(logs)
        elif log_type == 'nlu' and filtered_data:
            filtered_data = filtered_data.get()
            intent_evaluation_logs = filtered_data.data.get('intent_evaluation', {}).get('errors', [])[start_idx:start_idx+page_size]
            entity_evaluation_logs = filtered_data.data.get('entity_evaluation', {}).get('errors', [])[start_idx:start_idx+page_size]
            response_selection_evaluation_logs = filtered_data.data.get('response_selection_evaluation', {}).get('errors', [])[start_idx:start_idx+page_size]
            intent_evaluation_fail_cnt = filtered_data.data.get('intent_evaluation', {}).get('failure_count', 0)
            entity_evaluation_fail_cnt = filtered_data.data.get('entity_evaluation', {}).get('failure_count', 0)
            response_selection_evaluation_fail_cnt = filtered_data.data.get('response_selection_evaluation', {}).get('failure_count', 0)
            logs = {
                "intent_evaluation": {'errors': intent_evaluation_logs, 'total': intent_evaluation_fail_cnt},
                "entity_evaluation": {'errors': entity_evaluation_logs, 'total': entity_evaluation_fail_cnt},
                "response_selection_evaluation": {
                    'errors': response_selection_evaluation_logs, 'total': response_selection_evaluation_fail_cnt
                }
            }
            if intent_evaluation_fail_cnt or entity_evaluation_fail_cnt or response_selection_evaluation_fail_cnt:
                logs = json.dumps(logs)
                logs = json.loads(logs)
        return logs

    @staticmethod
    def delete_enqueued_event_log(bot: str):
        """
        Deletes latest log if it is present in enqueued state.
        """
        latest_log = ModelTestingLogs.objects(bot=bot).order_by('-id').first()
        if latest_log and latest_log.event_status == EVENT_STATUS.ENQUEUED.value:
            latest_log.delete()

