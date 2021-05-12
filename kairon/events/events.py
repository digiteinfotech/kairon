import os
from typing import Text

from loguru import logger
from requests import exceptions

from kairon.utils import Utility
from kairon.data_processor.constant import EVENT_STATUS
from kairon.data_processor.data_importer_log_processor import DataImporterLogProcessor
from kairon.events.actions.data_importer import DataImporter


class Events:
    """
    Class to trigger events.
    """

    @staticmethod
    async def trigger_data_importer(bot: Text, user: Text, save_data: bool, overwrite: bool = True):
        """
        Triggers data importer event which validates and imports data into kairon.
        @param bot: bot id.
        @param user: kairon username.
        @param save_data: Flag to import data into kairon. If set to false, then only validation is run.
                        Otherwise, both validation and import is done.
        @param overwrite: Overwrite existing data(if set to true) or append (if set to false).
        @return:
        """
        validation_status = 'Failure'
        path = None
        try:
            if Utility.environment.get('model') and Utility.environment['model'].get('data_importer') and \
                    Utility.environment['model']['data_importer'].get('event_url'):
                import_flag = '--import-data' if save_data else ''
                overwrite_flag = '--overwrite' if overwrite else ''
                json = {'BOT': bot, 'USER': user, "IMPORT_DATA": import_flag, "OVERWRITE": overwrite_flag}
                Utility.http_request("POST",
                                     Utility.environment['model']['data_importer'].get('event_url'),
                                     None, user, json)
                DataImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.TASKSPAWNED.value)
            else:
                path = Utility.get_latest_file(os.path.join('training_data', bot))
                DataImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.PARSE.value)

                data_importer = DataImporter(path, bot, user, save_data, overwrite)
                DataImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.VALIDATING.value)

                summary = await data_importer.validate()
                is_data_valid = all([not summary[key] for key in summary.keys()])
                validation_status = 'Success' if is_data_valid else 'Failure'
                DataImporterLogProcessor.add_log(bot, user, summary,
                                                 validation_status=validation_status,
                                                 event_status=EVENT_STATUS.SAVE.value)

                data_importer.import_data()
                DataImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.COMPLETED.value)
        except exceptions.ConnectionError as e:
            logger.error(str(e))
            DataImporterLogProcessor.add_log(bot, user,
                                             exception='Failed to trigger the event.',
                                             validation_status=validation_status,
                                             event_status=EVENT_STATUS.FAIL.value)

        except Exception as e:
            logger.error(str(e))
            DataImporterLogProcessor.add_log(bot, user,
                                             exception=str(e),
                                             validation_status=validation_status,
                                             event_status=EVENT_STATUS.FAIL.value)
        if path:
            Utility.delete_directory(path)
