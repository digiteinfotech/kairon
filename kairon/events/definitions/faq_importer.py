import os
from typing import Text

from loguru import logger

from kairon.events.definitions.base import EventsBase
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.utils import Utility
from kairon.shared.data.utils import DataUtility


class FaqDataImporterEvent(EventsBase):
    """
    Event to validate faq csv/Excel file data and import it if validation succeeds.
    This same event is also used for validating existing data.
    """

    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise event.
        """
        self.bot = bot
        self.user = user

    def validate(self, **kwargs):
        """
        Validates if an event is already running for that particular bot and also
        whether the event trigger limit has exceeded.
        If the data was uploaded, then it is saved in 'faq_data' folder.
        """
        training_data_file = kwargs.get("training_data_file")
        DataImporterLogProcessor.is_limit_exceeded(self.bot)
        DataImporterLogProcessor.is_event_in_progress(self.bot)
        DataUtility.save_faq_training_files(self.bot, training_data_file)
        DataImporterLogProcessor.add_log(self.bot, self.user, is_data_uploaded=True, files_received=[training_data_file.filename])

    def enqueue(self):
        """
        Send event to event server.
        """
        payload = {'bot': self.bot, 'user': self.user}
        DataImporterLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.ENQUEUED.value)
        try:
            Utility.request_event_server(EventClass.faq_importer, payload)
        except Exception as e:
            DataImporterLogProcessor.delete_enqueued_event_log(self.bot)
            training_data_home_dir = os.path.join('training_data', self.bot)
            Utility.delete_directory(training_data_home_dir, True)
            raise AppException(e)

    def execute(self, **kwargs):
        """
        Execute the event.
        """

        path = os.path.join('training_data', self.bot)
        validation_status = 'Failure'
        processor = MongoProcessor()
        try:
            DataImporterLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.INPROGRESS.value)
            processor.delete_all_faq(self.bot)
            component_count, summary = processor.save_faq(self.bot, self.user)
            DataImporterLogProcessor.update_summary(self.bot, self.user, component_count, summary,
                                                    status='Success',
                                                    event_status=EVENT_STATUS.COMPLETED.value)
        except Exception as e:
            logger.error(str(e))
            DataImporterLogProcessor.add_log(self.bot, self.user,
                                             exception=str(e),
                                             status=validation_status,
                                             event_status=EVENT_STATUS.FAIL.value)
        finally:
            if os.path.exists(path):
                Utility.delete_directory(path)
