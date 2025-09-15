import ujson as json
from datetime import datetime

from bson import ObjectId
from loguru import logger
from mongoengine import Q, DoesNotExist

from kairon.exceptions import AppException
from kairon.shared.data.constant import EVENT_STATUS, ModelTestingLogType, STATUSES
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.test.data_objects import ModelTestingLogs


class ModelTestingLogProcessor:

    @staticmethod
    def log_test_result(bot: str, user: str, is_augmented: bool = False, event_status: str = None,
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
        if is_augmented:
            common_data.is_augmented = is_augmented
        if event_status:
            common_data.event_status = event_status
        if event_status in {EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value}:
            common_data.end_timestamp = datetime.utcnow()
        if event_status == EVENT_STATUS.COMPLETED.value:
            common_data.status = 'PASSED'
        if stories_result:
            common_data.status = STATUSES.FAIL.value if stories_result.get('failed_stories') else STATUSES.SUCCESS.value
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
                common_data.status = STATUSES.FAIL.value
            if nlu_result.get("response_selection_evaluation") and nlu_result["response_selection_evaluation"].get('errors'):
                common_data.status = STATUSES.FAIL.value
            if nlu_result.get("entity_evaluation"):
                for extractor_evaluation in nlu_result["entity_evaluation"].values():
                    if extractor_evaluation.get('errors'):
                        common_data.status = STATUSES.FAIL.value
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
        @param raise_exception: Raise exception if event is in progress.
        @return: boolean flag
        """

        today = datetime.today()
        initiated_today = today.replace(hour=0, minute=0, second=0)
        doc_count = ModelTestingLogs.objects(
            bot=bot, type='common', start_timestamp__gte=initiated_today
        ).count()
        if doc_count >= BotSettings.objects(bot=bot).get().test_limit_per_day:
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

        if not Utility.check_empty_string(log_type) and not Utility.check_empty_string(reference_id):
            logs, row_count = ModelTestingLogProcessor.get_by_id_and_type(reference_id, bot, log_type, start_idx, page_size)
        else:
            logs, row_count = ModelTestingLogProcessor.get_all(bot, start_idx, page_size)
        return logs, row_count

    @staticmethod
    def get_all(bot: str, start_idx: int = 0, page_size: int = 10):
        """
        Get all logs for data importer event.
        @param bot: bot id.
        @return: list of logs.
        @param start_idx: start index in list field
        @param page_size: number of rows from start index
        """
        processor = MongoProcessor()
        kwargs = {'type': 'common'}
        logs = list(ModelTestingLogs.objects(bot=bot).aggregate([
            {"$set": {"data.type": "$type"}},
            {'$group': {'_id': '$reference_id', 'bot': {'$first': '$bot'}, 'user': {'$first': '$user'},
                        'status': {'$first': '$status'},
                        'event_status': {'$first': '$event_status'}, 'data': {'$push': '$data'},
                        'exception': {'$first': '$exception'},
                        'start_timestamp': {'$first': '$start_timestamp'},
                        'end_timestamp': {'$first': '$end_timestamp'},
                        'is_augmented': {'$first': '$is_augmented'}}},
            {'$project': {
                '_id': 0, 'reference_id': '$_id',
                'data': {'$filter': {'input': '$data', 'as': 'data', 'cond': {'$ne': ['$$data.type', 'common']}}},
                'status': 1, 'event_status': 1, 'exception': 1, 'start_timestamp': 1, 'end_timestamp': 1,
                'is_augmented': 1
            }},
            {"$sort": {"start_timestamp": -1}}]))[start_idx:start_idx+page_size]
        row_count = processor.get_row_count(ModelTestingLogs, bot, **kwargs)
        return logs, row_count

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
        row_count = 0
        filter_log_type = 'stories' if log_type == 'stories' else 'nlu'
        filtered_data = ModelTestingLogs.objects(reference_id=reference_id, bot=bot, type=filter_log_type)
        if log_type == ModelTestingLogType.stories.value and filtered_data:
            filtered_data = filtered_data.get()
            logs = filtered_data.data.get('failed_stories', [])[start_idx:start_idx+page_size]
            fail_cnt = filtered_data.data.get('conversation_accuracy', {}).get('failure_count', 0)
            success_cnt = filtered_data.data.get('conversation_accuracy', {}).get('success_count', 0)
            total_cnt = filtered_data.data.get('conversation_accuracy', {}).get('total_count', 0)
            logs = {'errors': logs, 'failure_count': fail_cnt, 'success_count': success_cnt, 'total_count': total_cnt}
            if fail_cnt:
                logs = json.dumps(logs)
                logs = json.loads(logs)
                row_count = fail_cnt
        elif log_type == ModelTestingLogType.nlu.value and filtered_data:
            intent_failures = []
            intent_failure_cnt, intent_success_cnt, intent_total_cnt = 0, 0, 0
            filtered_data = filtered_data.get()
            if filtered_data.data.get('intent_evaluation'):
                intent_failure_cnt = filtered_data.data['intent_evaluation'].get('failure_count') or 0
                intent_success_cnt = filtered_data.data['intent_evaluation'].get('success_count') or 0
                intent_total_cnt = filtered_data.data['intent_evaluation'].get('total_count') or 0
                if filtered_data.data['intent_evaluation'].get('errors'):
                    intent_failures = filtered_data.data['intent_evaluation']['errors'][start_idx:start_idx+page_size]
            logs = {
                "intent_evaluation": {'errors': intent_failures, 'failure_count': intent_failure_cnt,
                                      'success_count': intent_success_cnt, 'total_count': intent_total_cnt}
            }
            if intent_failure_cnt:
                logs = json.dumps(logs)
                logs = json.loads(logs)
                row_count = intent_failure_cnt
        elif log_type in {ModelTestingLogType.entity_evaluation_with_diet_classifier.value,
                          ModelTestingLogType.entity_evaluation_with_regex_entity_extractor.value} and filtered_data:
            entity_failures = []
            entity_failure_cnt, entity_success_cnt, entity_total_cnt = 0, 0, 0
            filtered_data = filtered_data.get()
            key = 'DIETClassifier' if log_type == 'entity_evaluation_with_diet_classifier' else 'RegexEntityExtractor'
            if filtered_data.data.get('entity_evaluation') and filtered_data.data['entity_evaluation'].get(key):
                entity_failure_cnt = filtered_data.data['entity_evaluation'][key]['failure_count'] or 0
                entity_success_cnt = filtered_data.data['entity_evaluation'][key]['success_count'] or 0
                entity_total_cnt = filtered_data.data['entity_evaluation'][key]['total_count'] or 0
                if filtered_data.data['entity_evaluation'][key].get('errors'):
                    entity_failures = \
                        filtered_data.data['entity_evaluation'][key]['errors'][start_idx:start_idx+page_size]
            logs = {"entity_evaluation": {'errors': entity_failures, 'failure_count': entity_failure_cnt,
                                          'success_count': entity_success_cnt, 'total_count': entity_total_cnt}}
            if entity_failure_cnt:
                logs = json.dumps(logs)
                logs = json.loads(logs)
                row_count = entity_failure_cnt
        elif log_type == ModelTestingLogType.response_selection_evaluation.value and filtered_data:
            response_selection_failures = []
            response_selection_failure_cnt, response_selection_success_cnt, response_selection_total_cnt = 0, 0, 0
            filtered_data = filtered_data.get()
            if filtered_data.data.get('response_selection_evaluation'):
                response_selection_failure_cnt = filtered_data.data['response_selection_evaluation']['failure_count'] or 0
                response_selection_success_cnt = filtered_data.data['response_selection_evaluation']['success_count'] or 0
                response_selection_total_cnt = filtered_data.data['response_selection_evaluation']['total_count'] or 0
                if filtered_data.data['response_selection_evaluation'].get('errors'):
                    response_selection_failures = \
                        filtered_data.data['response_selection_evaluation']['errors'][start_idx:start_idx+page_size]
            logs = {
                "response_selection_evaluation": {
                    'errors': response_selection_failures, 'failure_count': response_selection_failure_cnt,
                    'success_count': response_selection_success_cnt, 'total_count': response_selection_total_cnt
                }
            }
            if response_selection_failure_cnt:
                logs = json.dumps(logs)
                logs = json.loads(logs)
                row_count = response_selection_failure_cnt
        return logs, row_count

    @staticmethod
    def delete_enqueued_event_log(bot: str):
        """
        Deletes latest log if it is present in enqueued state.
        """
        latest_log = ModelTestingLogs.objects(bot=bot).order_by('-id').first()
        if latest_log and latest_log.event_status == EVENT_STATUS.ENQUEUED.value:
            latest_log.delete()

