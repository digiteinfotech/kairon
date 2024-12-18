from typing import Text
from loguru import logger

from kairon import Utility
from kairon.events.definitions.base import EventsBase
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.test.processor import ModelTestingLogProcessor


class ModelTestingEvent(EventsBase):
    """
    Event to test a model on augmented data.
    """

    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise event.
        """
        self.bot = bot
        self.user = user
        self.run_e2e = kwargs.get('run_e2e', False)
        self.augment_data = kwargs.get('augment_data', True)

    def validate(self):
        """
        Validates if a model is trained for the bot,
        an event is already running for that particular bot and also
        whether the event trigger limit has exceeded.
        """
        Utility.is_model_file_exists(self.bot)
        ModelTestingLogProcessor.is_event_in_progress(self.bot)
        ModelTestingLogProcessor.is_limit_exceeded(self.bot)

    def enqueue(self):
        """
        Send event to event server.
        """
        try:
            augment_data = '--augment' if self.augment_data else ''
            payload = {'bot': self.bot, 'user': self.user, "augment_data": augment_data}
            ModelTestingLogProcessor.log_test_result(self.bot, self.user, self.augment_data,
                                                     event_status=EVENT_STATUS.ENQUEUED.value)
            Utility.request_event_server(EventClass.model_testing, payload)
        except Exception as e:
            ModelTestingLogProcessor.delete_enqueued_event_log(self.bot)
            raise e

    def execute(self, **kwargs):
        """
        Execute the event.
        """
        from kairon.test.test_models import ModelTester
        try:
            ModelTestingLogProcessor.log_test_result(self.bot, self.user, event_status=EVENT_STATUS.INPROGRESS.value)
            nlu_results, stories_results = ModelTester.run_tests_on_model(self.bot, self.run_e2e, self.augment_data)
            ModelTestingLogProcessor.log_test_result(self.bot, self.user, stories_result=stories_results,
                                                     nlu_result=nlu_results,
                                                     event_status=EVENT_STATUS.COMPLETED.value)
        except Exception as e:
            logger.exception(str(e))
            ModelTestingLogProcessor.log_test_result(self.bot, self.user, exception=str(e),
                                                     event_status=EVENT_STATUS.FAIL.value)
