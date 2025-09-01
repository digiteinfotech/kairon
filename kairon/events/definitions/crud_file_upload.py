from typing import Text
from kairon import Utility
from kairon.importer.file_importer import FileImporter
from kairon.shared.data.collection_processor import DataProcessor
from kairon.shared.data.constant import EVENT_STATUS, STATUSES
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.upload_handler.upload_handler_log_processor import UploadHandlerLogProcessor
from loguru import logger
from kairon.upload_handlers.definitions.base import UploadHandlerBase


class CrudFileUploader(UploadHandlerBase):
    """
    Validates data
    """

    def __init__(self, bot: Text, user: Text, upload_type : Text, **kwargs):
        """
        Initialise event.
        """
        overwrite = kwargs.get("overwrite", False)
        collection_name = kwargs.get("collection_name", "")
        self.bot = bot
        self.user = user
        self.upload_type = upload_type
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
        UploadHandlerLogProcessor.add_log(bot=self.bot, user=self.user, file_name=file_content.filename, upload_type=self.upload_type, collection_name=self.collection_name, is_uploaded=True, event_status=EVENT_STATUS.INITIATED.value)
        is_event_data = MongoProcessor().file_upload_validate_schema_and_log(bot=self.bot, user=self.user, file_content=file_content)
        return is_event_data

    def create_payload(self, **kwargs):
        return {
            "bot": kwargs.get('bot'),
            "user": kwargs.get('user'),
            "upload_type": kwargs.get('upload_type'),
            "collection_name": kwargs.get('collection_name'),
            "overwrite": kwargs.get('overwrite')
        }

    def execute(self, **kwargs):
        """
        Execute the file content import event.
        """
        path = None
        try:
            file_received = UploadHandlerLogProcessor.get_latest_event_file_name(self.bot)
            path = Utility.get_latest_file('file_content_upload_records', self.bot)
            UploadHandlerLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.SAVE.value)
            file_importer = FileImporter(path, self.bot, self.user, file_received, self.collection_name, self.overwrite)
            collection_data=file_importer.preprocess()
            if self.overwrite:
                DataProcessor.delete_collection(self.bot, self.collection_name)
            file_importer.import_data(collection_data)
            UploadHandlerLogProcessor.add_log(self.bot, self.user, status=STATUSES.SUCCESS.value, event_status=EVENT_STATUS.COMPLETED.value)
        except Exception as e:
            logger.error(str(e))
            UploadHandlerLogProcessor.add_log(self.bot, self.user,
                                                exception=str(e),
                                                status=STATUSES.FAIL.value,
                                                event_status=EVENT_STATUS.FAIL.value)
        finally:
            if path:
                Utility.delete_directory(path)
