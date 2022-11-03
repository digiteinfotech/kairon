from typing import Text
from loguru import logger


from kairon.events.definitions.base import EventsBase
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.data.constant import EVENT_STATUS, TrainingDataSourceType
from kairon.shared.data.data_objects import TrainingDataGeneratorResponse
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.training_data_generation_processor import TrainingDataGenerationProcessor
from kairon.shared.constants import EventClass, DataGeneratorCliTypes


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
        self.depth = kwargs.get('depth') or 0

    def validate(self):
        """
        Validates if an event is already running for that particular bot and also
        whether the event trigger limit has exceeded.
        """
        if Utility.check_empty_string(self.website_url):
            raise AppException("website_url cannot be empty")
        depth_search_limit = MongoProcessor().get_bot_settings(
            self.bot, self.user)['website_data_generator_depth_search_limit']
        if not isinstance(self.depth, int) or self.depth < 0 or self.depth > depth_search_limit:
            raise AppException(f"depth should be between 0 and {depth_search_limit}")
        TrainingDataGenerationProcessor.check_data_generation_limit(self.bot)
        TrainingDataGenerationProcessor.is_in_progress(self.bot)

    def enqueue(self):
        """
        Send event to event server
        """
        payload = {
            "bot": self.bot, "user": self.user, "type": DataGeneratorCliTypes.from_website.value,
            "website_url": self.website_url, "depth": self.depth
        }
        TrainingDataGenerationProcessor.set_status(bot=self.bot,
                                                   user=self.user, status=EVENT_STATUS.ENQUEUED.value,
                                                   source_type=TrainingDataSourceType.website.value,
                                                   document_path=self.website_url)
        try:
            Utility.request_event_server(EventClass.data_generator, payload)
        except Exception as e:
            TrainingDataGenerationProcessor.delete_enqueued_event_log(self.bot)
            raise e

    def execute(self, **kwargs):
        """
        Execute the event.
        """
        from augmentation.story_generator.factory import TrainingDataGeneratorFactory

        try:
            TrainingDataGenerationProcessor.set_status(
                bot=self.bot, user=self.user, status=EVENT_STATUS.INPROGRESS.value,
                source_type=TrainingDataSourceType.website.value, document_path=self.website_url
            )
            generator = TrainingDataGeneratorFactory.get_instance(TrainingDataSourceType.website.value)(
                self.website_url, self.depth)
            training_data = generator.extract()
            training_data = [TrainingDataGeneratorResponse(**t_data) for t_data in training_data]
            TrainingDataGenerationProcessor.set_status(
                self.bot, self.user, EVENT_STATUS.COMPLETED.value, response=training_data
            )
        except Exception as e:
            logger.error(str(e))
            TrainingDataGenerationProcessor.set_status(bot=self.bot,
                                                       user=self.user, status=EVENT_STATUS.FAIL.value,
                                                       source_type=TrainingDataSourceType.website.value,
                                                       document_path=self.website_url, exception=str(e))
