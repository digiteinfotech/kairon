import os
import pytest
from mongoengine import connect
from kairon import Utility
from kairon.shared.data.constant import EVENT_STATUS, REQUIREMENTS, COMPONENT_COUNT, STATUSES
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.multilingual.processor import MultilingualLogProcessor
from kairon.shared.multilingual.data_objects import BotReplicationLogs
from kairon.exceptions import AppException
from mongomock import MongoClient


class TestMultilingualLogProcessor:

    @pytest.fixture(scope='session', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_add_log(self):
        bot = 'test'
        user = 'test'

        MultilingualLogProcessor.add_log(source_bot=bot, user=user)
        log = BotReplicationLogs.objects(bot=bot).get().to_mongo().to_dict()

        assert not log.get('source_bot_name')
        assert not log.get('destination_bot')
        assert not log.get('s_lang')
        assert not log.get('d_lang')
        assert log.get('copy_type') == 'Translation'
        assert not log.get('account')
        assert log.get('translate_responses')
        assert not log.get('translate_actions')
        assert not log.get('exception')
        assert log.get('start_timestamp')
        assert not log.get('end_timestamp')
        assert not log.get('status')
        assert log.get('event_status') == EVENT_STATUS.INITIATED.value

    def test_add_log_exception(self):
        bot = 'test'
        user = 'test'

        MultilingualLogProcessor.add_log(bot, user, exception='Translation failed', status=STATUSES.FAIL.value,
                                         event_status=EVENT_STATUS.FAIL.value)
        log = BotReplicationLogs.objects(bot=bot).get().to_mongo().to_dict()

        assert not log.get('source_bot_name')
        assert not log.get('destination_bot')
        assert not log.get('s_lang')
        assert not log.get('d_lang')
        assert log.get('copy_type') == 'Translation'
        assert not log.get('account')
        assert log.get('translate_responses')
        assert not log.get('translate_actions')
        assert log.get('exception') == 'Translation failed'
        assert log.get('start_timestamp')
        assert log.get('end_timestamp')
        assert log.get('status') == STATUSES.FAIL.value
        assert log.get('event_status') == EVENT_STATUS.FAIL.value

    def test_add_log_success(self):
        bot = 'test'
        user = 'test'
        MultilingualLogProcessor.add_log(bot, user)
        MultilingualLogProcessor.add_log(bot, user,
                                         status=STATUSES.SUCCESS.value,
                                         event_status=EVENT_STATUS.COMPLETED.value)
        log = list(MultilingualLogProcessor.get_logs(bot))
        assert not log[0].get('source_bot_name')
        assert not log[0].get('destination_bot')
        assert not log[0].get('s_lang')
        assert not log[0].get('d_lang')
        assert log[0].get('copy_type') == 'Translation'
        assert not log[0].get('account')
        assert not log[0].get('exception')
        assert log[0].get('translate_responses')
        assert not log[0].get('translate_actions')
        assert log[0].get('start_timestamp')
        assert log[0].get('end_timestamp')
        assert log[0].get('status') == STATUSES.SUCCESS.value
        assert log[0].get('event_status') == EVENT_STATUS.COMPLETED.value

    def test_is_event_in_progress_false(self):
        bot = 'test'
        assert not MultilingualLogProcessor.is_event_in_progress(bot)

    def test_is_event_in_progress_true(self):
        bot = 'test'
        user = 'test'
        MultilingualLogProcessor.add_log(bot, user)
        assert MultilingualLogProcessor.is_event_in_progress(bot, False)

        with pytest.raises(AppException):
            MultilingualLogProcessor.is_event_in_progress(bot)

    def test_is_limit_exceeded_failure(self, monkeypatch):
        bot = 'test_bot'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.multilingual_limit_per_day = 0
        bot_settings.save()
        assert MultilingualLogProcessor.is_limit_exceeded(bot, False)

        with pytest.raises(AppException, match='Daily limit exceeded.'):
            MultilingualLogProcessor.is_limit_exceeded(bot)

    def test_is_limit_exceeded(self, monkeypatch):
        bot = 'test_bot'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.multilingual_limit_per_day = 5
        bot_settings.save()
        assert not MultilingualLogProcessor.is_limit_exceeded(bot)

    def test_get_logs(self):
        bot = 'test'
        logs = list(MultilingualLogProcessor.get_logs(bot))
        assert len(logs) == 3

    def test_update_log(self):
        bot = 'test'
        user = 'test'
        MultilingualLogProcessor.add_log(bot, user)
        log = next(MultilingualLogProcessor.get_logs(bot))
        assert not log.get('source_bot_name')
        assert not log.get('destination_bot')
        assert not log.get('s_lang')
        assert not log.get('d_lang')
        assert log.get('copy_type') == 'Translation'
        assert not log.get('account')
        assert not log.get('exception')
        assert log.get('translate_responses')
        assert not log.get('translate_actions')
        assert log.get('start_timestamp')
        assert not log.get('end_timestamp')
        assert not log.get('status')
        assert log.get('event_status') == EVENT_STATUS.INITIATED.value

        destination_bot = 'd_bot'
        MultilingualLogProcessor.update_summary(bot, user, destination_bot=destination_bot, status=STATUSES.SUCCESS.value)
        log = next(MultilingualLogProcessor.get_logs(bot))
        assert not log.get('source_bot_name')
        assert log.get('destination_bot') == 'd_bot'
        assert not log.get('s_lang')
        assert not log.get('d_lang')
        assert log.get('copy_type') == 'Translation'
        assert not log.get('account')
        assert not log.get('exception')
        assert log.get('translate_responses')
        assert not log.get('translate_actions')
        assert log.get('start_timestamp')
        assert log.get('end_timestamp')
        assert log.get('status') == STATUSES.SUCCESS.value
        assert log.get('event_status') == EVENT_STATUS.COMPLETED.value

    def test_update_log_create_new(self):
        bot = 'test'
        user = 'test'
        destination_bot = 'd_bot'
        MultilingualLogProcessor.update_summary(bot, user, destination_bot)
        log = next(MultilingualLogProcessor.get_logs(bot))
        assert not log.get('source_bot_name')
        assert log.get('destination_bot') == 'd_bot'
        assert not log.get('s_lang')
        assert not log.get('d_lang')
        assert log.get('copy_type') == 'Translation'
        assert not log.get('account')
        assert not log.get('exception')
        assert log.get('translate_responses')
        assert not log.get('translate_actions')
        assert log.get('start_timestamp')
        assert log.get('end_timestamp')
        assert not log.get('status')
        assert log.get('event_status') == EVENT_STATUS.COMPLETED.value
