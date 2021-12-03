import os
from typing import Text

from loguru import logger
from requests import exceptions

from kairon.shared.data.constant import EVENT_STATUS
from kairon.importer.data_importer import DataImporter
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.utils import Utility
from kairon.shared.test.processor import ModelTestingLogProcessor
from kairon.test.test_models import ModelTester


class EventsTrigger:
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
        event_url = Utility.get_event_url("DATA_IMPORTER")
        try:
            if not Utility.check_empty_string(event_url):
                import_flag = '--import-data' if save_data else ''
                overwrite_flag = '--overwrite' if overwrite else ''
                env_var = {'BOT': bot, 'USER': user, "IMPORT_DATA": import_flag, "OVERWRITE": overwrite_flag}
                event_request = Utility.build_event_request(env_var)
                Utility.http_request("POST",
                                     Utility.environment['model']['data_importer'].get('event_url'),
                                     None, user, event_request)
                DataImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.TASKSPAWNED.value)
            else:
                path = Utility.get_latest_file(os.path.join('training_data', bot))
                files_received = DataImporterLogProcessor.get_files_received_for_latest_event(bot)
                DataImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.PARSE.value)
                data_importer = DataImporter(path, bot, user, files_received, save_data, overwrite)
                DataImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.VALIDATING.value)

                summary, component_count = await data_importer.validate()
                initiate_import = Utility.is_data_import_allowed(summary, bot, user)
                status = 'Success' if initiate_import else 'Failure'
                DataImporterLogProcessor.update_summary(bot, user, component_count, summary,
                                                        status=status,
                                                        event_status=EVENT_STATUS.SAVE.value)

                if initiate_import:
                    data_importer.import_data()
                DataImporterLogProcessor.add_log(bot, user, event_status=EVENT_STATUS.COMPLETED.value)
        except exceptions.ConnectionError as e:
            logger.error(str(e))
            DataImporterLogProcessor.add_log(bot, user,
                                             exception=f'Failed to trigger the event. {e}',
                                             status=validation_status,
                                             event_status=EVENT_STATUS.FAIL.value)

        except Exception as e:
            logger.error(str(e))
            DataImporterLogProcessor.add_log(bot, user,
                                             exception=str(e),
                                             status=validation_status,
                                             event_status=EVENT_STATUS.FAIL.value)
        if path:
            Utility.delete_directory(path)

    @staticmethod
    def trigger_model_testing(bot: Text, user: Text, run_e2e: bool = False):
        """
        Triggers model testing event.
        @param bot: bot id.
        @param user: kairon username.
        @param run_e2e: if true, tests are run on test stories. e2e test run in case of rasa is when intent predictions
        are also done as part of core model testing.
        @return:
        """
        try:
            event_url = Utility.get_event_url("TESTING")
            if not Utility.check_empty_string(event_url):
                env_var = {'BOT': bot, 'USER': user}
                event_request = Utility.build_event_request(env_var)
                Utility.http_request("POST",
                                     event_url,
                                     None, user, event_request)
                ModelTestingLogProcessor.log_test_result(bot, user,
                                                         event_status=EVENT_STATUS.TASKSPAWNED.value)
            else:
                ModelTestingLogProcessor.log_test_result(bot, user, event_status=EVENT_STATUS.INPROGRESS.value)
                nlu_results, stories_results = ModelTester.run_tests_on_model(bot, run_e2e)
                ModelTestingLogProcessor.log_test_result(bot, user, stories_result=stories_results,
                                                         nlu_result=nlu_results,
                                                         event_status=EVENT_STATUS.COMPLETED.value)
        except exceptions.ConnectionError as e:
            logger.error(str(e))
            ModelTestingLogProcessor.log_test_result(bot, user, exception=f'Failed to trigger the event. {e}',
                                                     event_status=EVENT_STATUS.FAIL.value)

        except Exception as e:
            logger.error(str(e))
            ModelTestingLogProcessor.log_test_result(bot, user, exception=str(e), event_status=EVENT_STATUS.FAIL.value)
