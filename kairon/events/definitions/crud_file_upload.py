from typing import Text
from kairon import Utility
from kairon.importer.file_importer import FileImporter
from kairon.shared.data.collection_processor import DataProcessor
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.upload_handler.upload_handler_log_processor import UploadHandlerLogProcessor
from loguru import logger
from kairon.upload_handlers.definitions.base import UploadHandlerBase


class CrudFileUploader(UploadHandlerBase):
    """
    Validates data
    """

    def __init__(self, bot: Text, user: Text, type : Text, **kwargs):
        """
        Initialise event.
        """
        overwrite = kwargs.get("overwrite", False)
        collection_name = kwargs.get("collection_name", "")
        self.bot = bot
        self.user = user
        self.type = type
        self.overwrite = overwrite
        self.collection_name = collection_name

    def validate(self, **kwargs):
        """
        Validates if an event is already running for that particular bot and
        checks if the event trigger limit has been exceeded.
        Then, preprocesses the received request
        """

        file_content = kwargs.get("file_content")
        UploadHandlerLogProcessor.is_limit_exceeded(self.bot)
        UploadHandlerLogProcessor.is_event_in_progress(self.bot, self.collection_name)
        UploadHandlerLogProcessor.add_log(bot=self.bot, user=self.user, file_name=file_content.filename, type=self.type, collection_name=self.collection_name, is_uploaded=True, event_status=EVENT_STATUS.INITIATED.value)
        is_event_data = MongoProcessor().file_upload_validate_schema_and_log(bot=self.bot, user=self.user, file_content=file_content, type=self.type, collection_name=self.collection_name)
        return is_event_data

    def create_payload(self, **kwargs):
        return {
            "bot": kwargs.get('bot'),
            "user": kwargs.get('user'),
            "type": kwargs.get('type'),
            "collection_name": kwargs.get('collection_name'),
            "overwrite": kwargs.get('overwrite')
        }

    def execute(self, **kwargs):
        """
        Execute the file content import event.
        """
        path = None
        validation_status = 'Failure'
        try:
            file_received = UploadHandlerLogProcessor.get_latest_event_file_name(self.bot)
            path = Utility.get_latest_file('file_content_upload_records', self.bot)
            UploadHandlerLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.SAVE.value)
            file_importer = FileImporter(path, self.bot, self.user, file_received, self.collection_name, self.overwrite)
            collection_data=file_importer.preprocess()
            if self.overwrite:
                DataProcessor.delete_collection(self.bot, self.collection_name)
            file_importer.import_data(collection_data)
            validation_status = 'Success'
            UploadHandlerLogProcessor.add_log(self.bot, self.user, status=validation_status, event_status=EVENT_STATUS.COMPLETED.value)
        except Exception as e:
            logger.error(str(e))
            UploadHandlerLogProcessor.add_log(self.bot, self.user,
                                                exception=str(e),
                                                status=validation_status,
                                                event_status=EVENT_STATUS.COMPLETED.value)
        finally:
            if path:
                Utility.delete_directory(path)
