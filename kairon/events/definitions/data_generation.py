from typing import Text
from loguru import logger
from augmentation.story_suggester.training_data_generator import WebsiteTrainingDataGenerator
from kairon.api.models import TrainingDataGeneratorStatusModel
from kairon.events.definitions.base import EventsBase
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.data.constant import EVENT_STATUS, TRAINING_DATA_SOURCE_TYPE
from kairon.shared.data.training_data_generation_processor import TrainingDataGenerationProcessor
from kairon.shared.constants import EventClass


class DataGenerationEvent(EventsBase):
    """
    Event to create Training data from website link provided by user
    """
    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise the event
        """
        self.bot = bot
        self.user = user
        self.website_url = kwargs.get('website_url')

    def validate(self):
        """
        Validates if an event is already running for that particular bot and also
        whether the event trigger limit has exceeded.
        """
        if Utility.check_empty_string(self.website_url):
            raise AppException("website_url cannot be empty")
        TrainingDataGenerationProcessor.check_data_generation_limit(self.bot)
        TrainingDataGenerationProcessor.is_in_progress(self.bot)

    def enqueue(self):
        """
        Send event to event server
        """
        payload = {
            "bot": self.bot, "user": self.user, "website_url": self.website_url
        }
        TrainingDataGenerationProcessor.set_status(bot=self.bot,
                                                   user=self.user, status=EVENT_STATUS.ENQUEUED.value,
                                                   source_type=TRAINING_DATA_SOURCE_TYPE.WEBSITE.value,
                                                   document_path=self.website_url)
        try:
            Utility.request_event_server(EventClass.data_generator, payload)
        except Exception as e:
            TrainingDataGenerationProcessor.delete_enqueued_event_log(self.bot)
            raise e

    def execute(self, **kwargs):
        """
        Execute event
        """
        try:
            TrainingDataGenerationProcessor.set_status(bot=self.bot,
                                                       user=self.user, status=EVENT_STATUS.INPROGRESS.value,
                                                       source_type=TRAINING_DATA_SOURCE_TYPE.WEBSITE.value,
                                                       document_path=self.website_url)

            generator = WebsiteTrainingDataGenerator(self.website_url)
            training_data = generator.get_training_data()
            story_data = TrainingDataGeneratorStatusModel()
            story_data.response = training_data
            story_data.status = EVENT_STATUS.COMPLETED
            TrainingDataGenerationProcessor.retrieve_response_and_set_status(story_data, self.bot, self.user)

        except Exception as e:
            logger.error(str(e))
            TrainingDataGenerationProcessor.set_status(bot=self.bot,
                                                       user=self.user, status=EVENT_STATUS.FAIL.value,
                                                       source_type=TRAINING_DATA_SOURCE_TYPE.WEBSITE.value,
                                                       document_path=self.website_url, exception=str(e))
