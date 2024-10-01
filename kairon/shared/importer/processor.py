from datetime import datetime

from loguru import logger
from mongoengine import Q, DoesNotExist

from kairon.shared.actions.models import ActionType
from kairon.shared.data.constant import EVENT_STATUS
from kairon.exceptions import AppException
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.importer.data_objects import ValidationLogs, TrainingComponentLog, DomainLog


class DataImporterLogProcessor:
    """
    Data processor to log data importer event.
    """

    @staticmethod
    def add_log(bot: str, user: str, is_data_uploaded: bool = False, files_received: list = None,
                exception: str = None, status: str = None, event_status: str = EVENT_STATUS.INITIATED.value):
        """
        Adds/updated log for data importer event.
        @param bot: bot id.
        @param user: kairon username.
        @component_count: count of training data components.
        @param files_received: files received for upload.
        @param is_data_uploaded: Was the data uploaded or was the event triggered on existing kairon data.
        @param exception: Exception occurred during event.
        @param status: Validation success or failure.
        @param event_status: Event success or failed due to any error during validation or import.
        @return:
        """
        try:
            doc = ValidationLogs.objects(bot=bot).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value)).get()
        except DoesNotExist:
            doc = ValidationLogs(
                is_data_uploaded=is_data_uploaded,
                files_received=files_received,
                bot=bot,
                user=user,
                start_timestamp=datetime.utcnow(),
            )
        doc.event_status = event_status
        if exception:
            doc.exception = exception
        if status:
            doc.status = status
        if event_status in {EVENT_STATUS.FAIL.value, EVENT_STATUS.COMPLETED.value}:
            doc.end_timestamp = datetime.utcnow()
        doc.save()

    @staticmethod
    def update_summary(bot: str, user: str, component_count: dict, summary: dict, status: str = None,
                       event_status: str = EVENT_STATUS.COMPLETED.value):
        """
        Adds/updated log for data importer event.
        @param bot: bot id.
        @param user: kairon username.
        @param component_count: count of training data components.
        @param summary: validation summary (errors in intents, stories, training examples, responses).
        @param status: Validation success or failure.
        @param event_status: Event success or failed due to any error during validation or import.
        @return:
        """
        try:
            doc = ValidationLogs.objects(bot=bot).filter(
                Q(event_status__ne=EVENT_STATUS.COMPLETED.value) &
                Q(event_status__ne=EVENT_STATUS.FAIL.value)).get()
        except DoesNotExist:
            doc = ValidationLogs(
                bot=bot,
                user=user,
                start_timestamp=datetime.utcnow(),
            )
        doc.intents = TrainingComponentLog(count=component_count['intents'], data=summary.get('intents'))
        doc.utterances = TrainingComponentLog(count=component_count['utterances'], data=summary.get('utterances'))
        doc.stories = TrainingComponentLog(count=component_count['stories'], data=summary.get('stories'))
        doc.training_examples = TrainingComponentLog(count=component_count['training_examples'], data=summary.get('training_examples'))
        doc.config = TrainingComponentLog(data=summary.get('config'))
        doc.rules = TrainingComponentLog(count=component_count['rules'], data=summary.get('rules'))
        action_summary = [{'type': f"{s}s", 'count': component_count.get(s), 'data': summary.get(s)} for s in
                          summary.keys() if s in {f'{a_type.value}' for a_type in ActionType}]
        doc.multiflow_stories = TrainingComponentLog(count=component_count.get('multiflow_stories'),
                                                     data=summary.get('multiflow_stories'))
        doc.bot_content = TrainingComponentLog(data=summary.get('bot_content'))
        doc.user_actions = TrainingComponentLog(count=component_count.get('user_actions'),
                                                data=summary.get('user_actions'))
        doc.actions = action_summary
        doc.domain = DomainLog(
            intents_count=component_count['domain'].get('intents'),
            actions_count=component_count['domain'].get('actions'),
            slots_count=component_count['domain'].get('slots'),
            utterances_count=component_count['domain'].get('utterances'),
            forms_count=component_count['domain'].get('forms'),
            entities_count=component_count['domain'].get('entities'),
            data=summary.get('domain'))

        doc.event_status = event_status
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

        today_start = today.replace(hour=0, minute=0, second=0)
        doc_count = ValidationLogs.objects(
            bot=bot, start_timestamp__gte=today_start
        ).count()
        if doc_count >= BotSettings.objects(bot=bot).get().data_importer_limit_per_day:
            if raise_exception:
                raise AppException("Daily limit exceeded.")
            else:
                return True
        else:
            return False

    @staticmethod
    def get_logs(bot: str, start_idx: int = 0, page_size: int = 10):
        """
        Get all logs for data importer event.
        @param bot: bot id.
        @param start_idx: start index
        @param page_size: page size
        @return: list of logs.
        """
        for log in ValidationLogs.objects(bot=bot).order_by("-start_timestamp").skip(start_idx).limit(page_size):
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

    @staticmethod
    def delete_enqueued_event_log(bot: str):
        """
        Deletes latest log if it is present in enqueued state.
        """
        latest_log = ValidationLogs.objects(bot=bot).order_by('-id').first()
        if latest_log and latest_log.event_status == EVENT_STATUS.ENQUEUED.value:
            latest_log.delete()
