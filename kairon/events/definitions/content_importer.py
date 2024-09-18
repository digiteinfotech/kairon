import asyncio
import os
from typing import Text

from kairon import Utility
from loguru import logger
from kairon.events.definitions.base import EventsBase
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.content_importer.content_processor import ContentImporterLogProcessor
from kairon.shared.data.processor import MongoProcessor


class DocContentImporterEvent(EventsBase):
    """
    Event to validate and process document content (e.g., CSV files).
    This event will validate and import the content if validation succeeds.
    """

    def __init__(self, bot: Text, user: Text, table_name: Text, **kwargs):
        """
        Initialise event.
        """
        self.bot = bot
        self.user = user
        self.table_name = table_name
        self.overwrite = kwargs.get("overwrite", False)

    def validate(self, **kwargs):
        """
        Validates if an event is already running for that particular bot and
        checks if the event trigger limit has been exceeded.
        If the document content (CSV) was uploaded, it is validated and logged.
        """
        doc_content = kwargs.get("doc_content")
        is_data_uploaded = kwargs.get("is_data_uploaded", False)
        ContentImporterLogProcessor.is_limit_exceeded(self.bot)
        ContentImporterLogProcessor.is_event_in_progress(self.bot)
        is_event_data = True
        if is_data_uploaded:
            is_event_data = MongoProcessor().validate_schema_and_log(self.bot, self.user, doc_content,
                                                                                 self.table_name)
        return is_event_data

    def enqueue(self):
        """
        Send event to event server
        """
        overwrite = '--overwrite' if self.overwrite is True else ''
        payload = {
            'bot': self.bot,
            'user': self.user,
            'event_type': EventClass.content_importer,
            'table_name': self.table_name,
            'overwrite': overwrite
        }
        ContentImporterLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.ENQUEUED.value)
        try:
            Utility.request_event_server(EventClass.content_importer, payload)
        except Exception as e:
            ContentImporterLogProcessor.delete_enqueued_event_log(self.bot)
            content_dir = os.path.join('doc_content_upload_records', self.bot)
            Utility.delete_directory(content_dir, True)
            raise e

    def execute(self, **kwargs):
        """
        Execute the document content import event.
        """
        from kairon.importer.content_importer import ContentImporter

        path = None
        validation_status = 'Failure'
        try:
            file_received = ContentImporterLogProcessor.get_file_received_for_latest_event(self.bot)
            path = Utility.get_latest_file('doc_content_upload_records', self.bot)
            ContentImporterLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.VALIDATING.value)
            content_importer = ContentImporter(path, self.bot, self.user, file_received,self.table_name,self.overwrite)
            original_row_count, summary = content_importer.validate()
            if len(summary) == original_row_count:
                initiate_import = False
                status = 'Failure'
            else:
                initiate_import = True
                status = 'Partial_Success' if summary else 'Success'
            ContentImporterLogProcessor.add_log(self.bot, self.user, validation_errors = summary, status=status,
                                                       event_status=EVENT_STATUS.SAVE.value)
            if initiate_import:
                content_importer.import_data()
            ContentImporterLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.COMPLETED.value)
        except Exception as e:
            logger.error(str(e))
            ContentImporterLogProcessor.add_log(self.bot, self.user,
                                                exception=str(e),
                                                status=validation_status,
                                                event_status=EVENT_STATUS.FAIL.value)
        finally:
            if path:
                Utility.delete_directory(path)



