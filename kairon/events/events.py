import os
from typing import Text

from loguru import logger
from requests import exceptions

from kairon.shared.account.processor import AccountProcessor
from kairon.shared.data.constant import EVENT_STATUS
from kairon.importer.data_importer import DataImporter
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.utils import Utility
from kairon.shared.test.processor import ModelTestingLogProcessor
from kairon.shared.multilingual.processor import MultilingualLogProcessor
from kairon.multilingual.processor import MultilingualProcessor
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

    @staticmethod
    def trigger_history_deletion(bot: Text, user: Text, month: int = 1, sender_id: Text = None):
        """
        Triggers model testing event.
        @param bot: bot id.
        @param user: kairon username.
        @param month: default is current month and max is last 6 months
        @param sender_id: sender id
        @return:
        """
        from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
        from kairon.history.processor import HistoryProcessor

        try:
            event_url = Utility.get_event_url("HISTORY_DELETION")
            if not Utility.check_empty_string(event_url):
                env_var = {'BOT': bot, 'USER': user, 'MONTH': month, 'SENDER_ID': sender_id}
                event_request = Utility.build_event_request(env_var)
                Utility.http_request("POST",
                                     event_url,
                                     None, user, event_request)
                HistoryDeletionLogProcessor.add_log(bot, user, month, status=EVENT_STATUS.TASKSPAWNED.value, sender_id=sender_id)
            else:
                HistoryDeletionLogProcessor.add_log(bot, user, month, status=EVENT_STATUS.INPROGRESS.value, sender_id=sender_id)
                if not Utility.check_empty_string(sender_id):
                    HistoryProcessor.delete_user_history(bot, sender_id, month)
                else:
                    HistoryProcessor.delete_bot_history(bot, month)
                HistoryDeletionLogProcessor.add_log(bot, user, status=EVENT_STATUS.COMPLETED.value, sender_id=sender_id)
        except exceptions.ConnectionError as e:
            logger.error(str(e))
            HistoryDeletionLogProcessor.add_log(bot, user, exception=f'Failed to trigger the event. {e}',
                                                status=EVENT_STATUS.FAIL.value)

        except Exception as e:
            logger.error(str(e))
            HistoryDeletionLogProcessor.add_log(bot, user, exception=str(e), status=EVENT_STATUS.FAIL.value)

    @staticmethod
    def trigger_multilingual_translation(bot: Text, user: Text, d_lang: Text,
                                         translate_responses: bool = True, translate_actions: bool = False):
        """
        Triggers multilingual translation event
        :param bot: bot id of source bot
        :param user: kairon username
        :param d_lang: language of destination bot
        :param translate_actions:
        :param translate_responses:
        :return:
        """
        translation_status = 'Failure'
        event_url = Utility.get_event_url("BOT_REPLICATION")
        # copy_type = "Translation"
        try:
            if not Utility.check_empty_string(event_url):
                env_var = {'SOURCE_BOT': bot, 'USER': user, 'D_LANG': d_lang,
                           'TRANSLATE_RESPONSES': translate_responses, 'TRANSLATE_ACTIONS': translate_actions}
                event_request = Utility.build_event_request(env_var)
                Utility.http_request("POST", event_url, None, user, event_request)
                MultilingualLogProcessor.add_log(source_bot=bot, user=user, d_lang=d_lang,
                                                 translate_responses=translate_responses,
                                                 translate_actions=translate_actions,
                                                 event_status=EVENT_STATUS.TASKSPAWNED.value)
            else:
                bot_info = AccountProcessor.get_bot(bot)
                account = bot_info['account']
                source_bot_name = bot_info['name']
                s_lang = bot_info['metadata']['language']

                multilingual_translator = MultilingualProcessor(account=account, user=user)

                MultilingualLogProcessor.add_log(source_bot=bot, user=user, source_bot_name=source_bot_name,
                                                 s_lang=s_lang, d_lang=d_lang, account=account,
                                                 translate_responses=translate_responses,
                                                 translate_actions=translate_actions,
                                                 event_status=EVENT_STATUS.TRIGGER_TRANSLATION.value)

                # translate bot and get new bot id
                destination_bot = multilingual_translator.create_multilingual_bot(base_bot_id=bot,
                                                                                  base_bot_name=source_bot_name,
                                                                                  s_lang=s_lang, d_lang=d_lang,
                                                                                  translate_responses=translate_responses,
                                                                                  translate_actions=translate_actions)

                translation_status = 'Success' if destination_bot else 'Failure'
                MultilingualLogProcessor.update_summary(bot, user, destination_bot=destination_bot,
                                                        status=translation_status,
                                                        event_status=EVENT_STATUS.COMPLETED.value)
        except exceptions.ConnectionError as e:
            logger.error(str(e))
            MultilingualLogProcessor.add_log(bot, user, exception=f'Failed to trigger the event. {e}',
                                             status=translation_status, event_status=EVENT_STATUS.FAIL.value)

        except Exception as e:
            logger.error(str(e))
            MultilingualLogProcessor.add_log(source_bot=bot, user=user, exception=str(e), status=translation_status,
                                             event_status=EVENT_STATUS.FAIL.value)
