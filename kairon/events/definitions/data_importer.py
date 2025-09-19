import asyncio
import os
import uuid
from typing import Text
from loguru import logger
from kairon import Utility
from kairon.events.definitions.base import EventsBase
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS, STATUSES
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.importer.processor import DataImporterLogProcessor


class TrainingDataImporterEvent(EventsBase):
    """
    Event to validate training data and import it if validation succeeds.
    This same event is also used for validating existing data.
    """

    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise event.
        """
        self.bot = bot
        self.user = user
        self.import_data = kwargs.get("import_data", False)
        self.overwrite = kwargs.get("overwrite", False)

    def validate(self, **kwargs):
        """
        Validates if an event is already running for that particular bot and also
        whether the event trigger limit has exceeded.
        If the data was uploaded, then it is saved in 'training_data' folder.
        """
        training_files = kwargs.get("training_files")
        is_data_uploaded = kwargs.get("is_data_uploaded", False)
        DataImporterLogProcessor.is_limit_exceeded(self.bot)
        DataImporterLogProcessor.is_event_in_progress(self.bot)
        if is_data_uploaded:
            is_event_data = asyncio.run(MongoProcessor().validate_and_log(self.bot, self.user, training_files, self.overwrite))
        else:
            Utility.make_dirs(os.path.join("training_data", self.bot, str(uuid.uuid4())))
            is_event_data = True
        return is_event_data

    def enqueue(self):
        """
        Send event to event server.
        """
        import_data = "--import-data" if self.import_data is True else ''
        overwrite = '--overwrite' if self.overwrite is True else ''
        payload = {'bot': self.bot, 'user': self.user, 'import_data': import_data, 'overwrite': overwrite, 'event_type': EventClass.data_importer}
        DataImporterLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.ENQUEUED.value)
        try:
            Utility.request_event_server(EventClass.data_importer, payload)
        except Exception as e:
            DataImporterLogProcessor.delete_enqueued_event_log(self.bot)
            training_data_home_dir = os.path.join('training_data', self.bot)
            Utility.delete_directory(training_data_home_dir, True)
            raise e

    def execute(self, **kwargs):
        """
        Execute the event.
        """
        from kairon.importer.data_importer import DataImporter

        path = None
        validation_status = STATUSES.FAIL.value
        try:
            path = Utility.get_latest_file(os.path.join('training_data', self.bot))
            files_received = DataImporterLogProcessor.get_files_received_for_latest_event(self.bot)
            DataImporterLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.PARSE.value)
            data_importer = DataImporter(path, self.bot, self.user, files_received, self.import_data, self.overwrite)
            DataImporterLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.VALIDATING.value)

            summary, component_count = asyncio.run(data_importer.validate())
            initiate_import = Utility.is_data_import_allowed(summary, self.bot, self.user)
            status = STATUSES.SUCCESS.value if initiate_import else STATUSES.FAIL.value
            DataImporterLogProcessor.update_summary(self.bot, self.user, component_count, summary,
                                                    status=status,
                                                    event_status=EVENT_STATUS.SAVE.value)

            if initiate_import:
                data_importer.import_data()
            DataImporterLogProcessor.add_log(self.bot, self.user, event_status=EVENT_STATUS.COMPLETED.value)
        except Exception as e:
            logger.error(str(e))
            DataImporterLogProcessor.add_log(self.bot, self.user,
                                             exception=str(e),
                                             status=validation_status,
                                             event_status=EVENT_STATUS.FAIL.value)
        finally:
            if path:
                Utility.delete_directory(path)
