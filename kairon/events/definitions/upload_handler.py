import os
from typing import Text
from kairon import Utility
from kairon.events.definitions.base import EventsBase
from kairon.shared.constants import EventClass, UploadHandlerClass
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.upload_handler.upload_handler_log_processor import UploadHandlerLogProcessor
from kairon.upload_handlers.definitions.factory import UploadHandlerFactory
from loguru import logger

class UploadHandler(EventsBase):
    """
    Validates and processes data before importing it
    to CRUD
    """

    def __init__(self, bot: Text, user: Text, type: Text, **kwargs):
        """
        Initialise event.
        """
        file_uploader = UploadHandlerFactory.get_instance(type)
        if type == UploadHandlerClass.crud_data:
            self.upload_handler = file_uploader(
                bot=bot,
                user=user,
                type=type,
                overwrite=kwargs.get("overwrite", False),
                collection_name=kwargs.get("collection_name")
            )


    def validate(self, **kwargs):
        """
        Validates if an event is already running for that particular bot and
        checks if the event trigger limit has been exceeded.
        Then, preprocesses the received request
        """
        file_content = kwargs.get("file_content")
        is_event_data = True
        is_event_data = self.upload_handler.validate(file_content=file_content)
        return is_event_data

    def enqueue(self, **kwargs):
        """
        Send event to event server
        """

        payload=self.upload_handler.create_payload(**kwargs)
        UploadHandlerLogProcessor.add_log(bot=self.upload_handler.bot, user=self.upload_handler.user, event_status=EVENT_STATUS.ENQUEUED.value)
        try:
            Utility.request_event_server(EventClass.upload_file_handler, payload)
        except Exception as e:
            logger.error(str(e))
            UploadHandlerLogProcessor.add_log(bot=self.upload_handler.bot, user=self.upload_handler.user, exception=str(e),
                                              event_status=EVENT_STATUS.FAIL.value)
            content_dir = os.path.join('file_content_upload_records', self.upload_handler.bot)
            Utility.delete_directory(content_dir, True)
            raise e

    def execute(self, **kwargs):
        """
        Execute the file content import event.
        """
        self.upload_handler.execute(**kwargs)
