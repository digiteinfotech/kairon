import pytest
from kairon.exceptions import AppException
from kairon.multilingual.processor import MultilingualTranslator
from kairon.shared.actions.data_objects import ZendeskAction, EmailActionConfig
from kairon.shared.multilingual.utils.translator import Translator
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.actions.models import ActionType
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility
import os
from mongoengine import connect
from kairon.shared.account.data_objects import Bot
from google.cloud.translate_v3 import TranslationServiceClient
from google.oauth2 import service_account
from unittest.mock import patch
from mongomock import MongoClient


class TestMultilingualProcessor:

    @pytest.fixture(autouse=True, scope="class")
    async def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())
        Utility.environment['multilingual']['service_account_creds']['type'] = "service_account"

        pytest.bot = Bot(name="test", account=1, user="test_user").save()

        yield None

    @pytest.mark.asyncio
    async def test_create_multilingual_bot(self, monkeypatch):
        mp = MongoProcessor()
        s_lang = "en"
        d_lang = "es"

        def _mock_service_client(*args, **kwargs):
            class MockServiceClient:

                def translate_text(*args, **kwargs):
                    text = kwargs["request"]["contents"]

                    class TranslationResponse:

                        class Translations:
                            translated_text = None

                            def __init__(self, sentence):
                                self.translated_text = sentence

                        translations = []

                        def __init__(self, text_list):
                            for t in text_list:
                                self.translations.append(self.Translations('TRANSLATED_' + t))

                    return TranslationResponse(text)

            return MockServiceClient()

        bot = Bot(name="test_bot", account=1, user="test_user")
        await (mp.save_from_path("./tests/testing_data/yml_training_files",
                                 bot="test_bot", user="test_user"))

        with patch('zenpy.Zenpy') as mock:
            ZendeskAction(
                name='zendesk_action', bot="test_bot", user="test_user", subdomain='digite751', user_name='test@digite.com',
                api_token={"value": "ASDFGHJKL"}, subject='new user detected', response='Successfully created').save()

            with patch("google.oauth2.service_account.Credentials", autospec=True):
                with patch("google.cloud.translate_v3.TranslationServiceClient.__new__") as mocked_new:
                    mocked_new.side_effect = _mock_service_client

                    multilingual_translator = MultilingualTranslator(account=bot.account, user=bot.user)
                    destination_bot = multilingual_translator.create_multilingual_bot(base_bot_id="test_bot",
                                                                                      base_bot_name=bot.name,
                                                                                      s_lang=s_lang, d_lang=d_lang,
                                                                                      translate_responses=True,
                                                                                      translate_actions=True)

        base_domain = mp.load_domain(bot="test_bot")
        new_domain = mp.load_domain(bot=destination_bot)

        # Checking domain
        for key, response in base_domain.responses.items():
            for i, utter in enumerate(response):
                if utter.get('text'):
                    assert 'TRANSLATED_' + utter['text'] == new_domain.responses[key][i]['text']

        base_nlu = mp.load_nlu(bot="test_bot")
        new_nlu = mp.load_nlu(bot=destination_bot)

        # Checking nlu
        for i, example in enumerate(base_nlu.training_examples):
            assert 'TRANSLATED_' + example.data['text'] == new_nlu.training_examples[i].data['text']

        base_actions = mp.load_action_configurations(bot="test_bot")
        new_actions = mp.load_action_configurations(bot=destination_bot)

        # Checking actions
        # http_action
        for i, action in enumerate(base_actions[ActionType.http_action]):
            assert 'TRANSLATED_' + action['response'].get('value') == new_actions[ActionType.http_action][i]['response'].get('value')
        # email_action
        for i, action in enumerate(base_actions[ActionType.email_action]):
            assert 'TRANSLATED_' + action['response'] == new_actions[ActionType.email_action][i]['response']
        # jira_action
        for i, action in enumerate(base_actions[ActionType.jira_action]):
            assert 'TRANSLATED_' + action['response'] == new_actions[ActionType.jira_action][i]['response']
        # zendesk_action
        for i, action in enumerate(base_actions[ActionType.zendesk_action]):
            assert 'TRANSLATED_' + action['response'] == new_actions[ActionType.zendesk_action][i]['response']
        # pipedrive_leads_action
        for i, action in enumerate(base_actions[ActionType.pipedrive_leads_action]):
            assert 'TRANSLATED_' + action['response'] == new_actions[ActionType.pipedrive_leads_action][i]['response']
        # google_search_action
        for i, action in enumerate(base_actions[ActionType.google_search_action]):
            assert 'TRANSLATED_' + action['failure_response'] == new_actions[ActionType.google_search_action][i]['failure_response']
        # form_validation_action
        for i, action in enumerate(base_actions[ActionType.form_validation_action]):
            assert 'TRANSLATED_' + action['valid_response'] == new_actions[ActionType.form_validation_action][i]['valid_response']
        for i, action in enumerate(base_actions[ActionType.form_validation_action]):
            assert 'TRANSLATED_' + action['invalid_response'] == new_actions[ActionType.form_validation_action][i]['invalid_response']

        assert mp.load_config(bot=destination_bot)
        assert mp.load_stories(bot=destination_bot)
        assert mp.get_rules_for_training(bot=destination_bot)

        new_bot = AccountProcessor.get_bot(destination_bot)
        assert new_bot["metadata"] == {'source_language': s_lang, 'language': d_lang, 'source_bot_id': 'test_bot'}

    @pytest.mark.asyncio
    async def test_create_multilingual_bot_without_actions(self, monkeypatch):
        mp = MongoProcessor()
        s_lang = "en"
        d_lang = "es"

        def _mock_service_client(*args, **kwargs):
            class MockServiceClient:

                def translate_text(*args, **kwargs):
                    text = kwargs["request"]["contents"]

                    class TranslationResponse:

                        class Translations:
                            translated_text = None

                            def __init__(self, sentence):
                                self.translated_text = sentence

                        translations = []

                        def __init__(self, text_list):
                            for t in text_list:
                                self.translations.append(self.Translations('TRANSLATED_' + t))

                    return TranslationResponse(text)

            return MockServiceClient()

        bot = Bot(name="test_bot", account=1, user="test_user")
        await (mp.save_from_path("./tests/testing_data/yml_training_files",
                                 bot="test_bot", user="test_user"))

        with patch("google.oauth2.service_account.Credentials", autospec=True):
            with patch("google.cloud.translate_v3.TranslationServiceClient.__new__") as mocked_new:
                mocked_new.side_effect = _mock_service_client

                multilingual_translator = MultilingualTranslator(account=bot.account, user=bot.user)
                destination_bot = multilingual_translator.create_multilingual_bot(base_bot_id="test_bot",
                                                                                  base_bot_name=bot.name,
                                                                                  s_lang=s_lang, d_lang=d_lang,
                                                                                  translate_responses=True,
                                                                                  translate_actions=False)

        base_domain = mp.load_domain(bot="test_bot")
        new_domain = mp.load_domain(bot=destination_bot)

        # Checking domain
        for key, response in base_domain.responses.items():
            for i, utter in enumerate(response):
                if utter.get('text'):
                    assert 'TRANSLATED_' + utter['text'] == new_domain.responses[key][i]['text']

        base_nlu = mp.load_nlu(bot="test_bot")
        new_nlu = mp.load_nlu(bot=destination_bot)

        # Checking nlu
        for i, example in enumerate(base_nlu.training_examples):
            assert 'TRANSLATED_' + example.data['text'] == new_nlu.training_examples[i].data['text']

        base_actions = mp.load_action_configurations(bot="test_bot")
        new_actions = mp.load_action_configurations(bot=destination_bot)

        # Checking actions
        # http_action
        for i, action in enumerate(base_actions[ActionType.http_action]):
            assert action['response'].get('value') == new_actions[ActionType.http_action][i]['response'].get('value')
        # email_action
        for i, action in enumerate(base_actions[ActionType.email_action]):
            assert action['response'] == new_actions[ActionType.email_action][i]['response']
        # jira_action
        for i, action in enumerate(base_actions[ActionType.jira_action]):
            assert action['response'] == new_actions[ActionType.jira_action][i]['response']
        # zendesk_action
        for i, action in enumerate(base_actions[ActionType.zendesk_action]):
            assert action['response'] == new_actions[ActionType.zendesk_action][i]['response']
        # pipedrive_leads_action
        for i, action in enumerate(base_actions[ActionType.pipedrive_leads_action]):
            assert action['response'] == new_actions[ActionType.pipedrive_leads_action][i]['response']
        # google_search_action
        for i, action in enumerate(base_actions[ActionType.google_search_action]):
            assert action['failure_response'] == new_actions[ActionType.google_search_action][i]['failure_response']
        # form_validation_action
        for i, action in enumerate(base_actions[ActionType.form_validation_action]):
            assert action['valid_response'] == new_actions[ActionType.form_validation_action][i]['valid_response']
        for i, action in enumerate(base_actions[ActionType.form_validation_action]):
            assert action['invalid_response'] == new_actions[ActionType.form_validation_action][i]['invalid_response']

        assert mp.load_config(bot=destination_bot)
        assert mp.load_stories(bot=destination_bot)
        assert mp.get_rules_for_training(bot=destination_bot)

        new_bot = AccountProcessor.get_bot(destination_bot)
        assert new_bot["metadata"] == {'source_language': s_lang, 'language': d_lang, 'source_bot_id': 'test_bot'}

    @pytest.mark.asyncio
    async def test_create_multilingual_bot_without_responses(self, monkeypatch):
        mp = MongoProcessor()
        s_lang = "en"
        d_lang = "es"

        def _mock_service_client(*args, **kwargs):
            class MockServiceClient:

                def translate_text(*args, **kwargs):
                    text = kwargs["request"]["contents"]

                    class TranslationResponse:

                        class Translations:
                            translated_text = None

                            def __init__(self, sentence):
                                self.translated_text = sentence

                        translations = []

                        def __init__(self, text_list):
                            for t in text_list:
                                self.translations.append(self.Translations('TRANSLATED_' + t))

                    return TranslationResponse(text)

            return MockServiceClient()

        bot = Bot(name="test_bot", account=1, user="test_user")
        await (mp.save_from_path("./tests/testing_data/yml_training_files",
                                 bot="test_bot", user="test_user"))

        with patch('kairon.shared.utils.SMTP', autospec=True):
            EmailActionConfig(
                action_name="email_action",
                smtp_url="test.localhost",
                smtp_port=293,
                smtp_password={"value": "test"},
                from_email={"value": "from_email", "parameter_type": "slot"},
                subject="test",
                to_email={"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
                response="Validated",
                bot="test_bot",
                user="test_user"
            ).save()

            with patch('zenpy.Zenpy'):
                ZendeskAction(
                    name='zendesk_action', bot="test_bot", user="test_user", subdomain='digite751', user_name='test@digite.com',
                    api_token={"value": 'ASDFGHJKL'}, subject='new user detected', response='Successfully created').save()

                with patch("google.oauth2.service_account.Credentials", autospec=True):
                    with patch("google.cloud.translate_v3.TranslationServiceClient.__new__") as mocked_new:
                        mocked_new.side_effect = _mock_service_client

                        multilingual_translator = MultilingualTranslator(account=bot.account, user=bot.user)
                        destination_bot = multilingual_translator.create_multilingual_bot(base_bot_id="test_bot",
                                                                                          base_bot_name=bot.name,
                                                                                          s_lang=s_lang, d_lang=d_lang,
                                                                                          translate_responses=False,
                                                                                          translate_actions=True)

        base_domain = mp.load_domain(bot="test_bot")
        new_domain = mp.load_domain(bot=destination_bot)

        # Checking domain
        for key, response in base_domain.responses.items():
            for i, utter in enumerate(response):
                if utter.get('text'):
                    assert utter['text'] == new_domain.responses[key][i]['text']

        base_nlu = mp.load_nlu(bot="test_bot")
        new_nlu = mp.load_nlu(bot=destination_bot)

        # Checking nlu
        for i, example in enumerate(base_nlu.training_examples):
            assert 'TRANSLATED_' + example.data['text'] == new_nlu.training_examples[i].data['text']

        base_actions = mp.load_action_configurations(bot="test_bot")
        new_actions = mp.load_action_configurations(bot=destination_bot)

        # Checking actions
        # http_action
        for i, action in enumerate(base_actions[ActionType.http_action]):
            assert 'TRANSLATED_' + action['response'].get('value') == new_actions[ActionType.http_action][i]['response'].get('value')
        # email_action
        for i, action in enumerate(base_actions[ActionType.email_action]):
            assert 'TRANSLATED_' + action['response'] == new_actions[ActionType.email_action][i]['response']
        # jira_action
        for i, action in enumerate(base_actions[ActionType.jira_action]):
            assert 'TRANSLATED_' + action['response'] == new_actions[ActionType.jira_action][i]['response']
        # zendesk_action
        for i, action in enumerate(base_actions[ActionType.zendesk_action]):
            assert 'TRANSLATED_' + action['response'] == new_actions[ActionType.zendesk_action][i]['response']
        # pipedrive_leads_action
        for i, action in enumerate(base_actions[ActionType.pipedrive_leads_action]):
            assert 'TRANSLATED_' + action['response'] == new_actions[ActionType.pipedrive_leads_action][i]['response']
        # google_search_action
        for i, action in enumerate(base_actions[ActionType.google_search_action]):
            assert 'TRANSLATED_' + action['failure_response'] == new_actions[ActionType.google_search_action][i]['failure_response']
        # form_validation_action
        for i, action in enumerate(base_actions[ActionType.form_validation_action]):
            assert 'TRANSLATED_' + action['valid_response'] == new_actions[ActionType.form_validation_action][i]['valid_response']
        for i, action in enumerate(base_actions[ActionType.form_validation_action]):
            assert 'TRANSLATED_' + action['invalid_response'] == new_actions[ActionType.form_validation_action][i]['invalid_response']

        assert mp.load_config(bot=destination_bot)
        assert mp.load_stories(bot=destination_bot)
        assert mp.get_rules_for_training(bot=destination_bot)

        new_bot = AccountProcessor.get_bot(destination_bot)
        assert new_bot["metadata"] == {'source_language': s_lang, 'language': d_lang, 'source_bot_id': 'test_bot'}

    @pytest.mark.asyncio
    async def test_create_multilingual_bot_without_responses_and_actions(self, monkeypatch):
        mp = MongoProcessor()
        s_lang = "en"
        d_lang = "es"

        def _mock_service_client(*args, **kwargs):
            class MockServiceClient:

                def translate_text(*args, **kwargs):
                    text = kwargs["request"]["contents"]

                    class TranslationResponse:

                        class Translations:
                            translated_text = None

                            def __init__(self, sentence):
                                self.translated_text = sentence

                        translations = []

                        def __init__(self, text_list):
                            for t in text_list:
                                self.translations.append(self.Translations('TRANSLATED_' + t))

                    return TranslationResponse(text)

            return MockServiceClient()

        bot = Bot(name="test_bot", account=1, user="test_user")
        await (mp.save_from_path("./tests/testing_data/yml_training_files",
                                 bot="test_bot", user="test_user"))

        with patch("google.oauth2.service_account.Credentials", autospec=True):
            with patch("google.cloud.translate_v3.TranslationServiceClient.__new__") as mocked_new:
                mocked_new.side_effect = _mock_service_client

                multilingual_translator = MultilingualTranslator(account=bot.account, user=bot.user)
                destination_bot = multilingual_translator.create_multilingual_bot(base_bot_id="test_bot",
                                                                                  base_bot_name=bot.name,
                                                                                  s_lang=s_lang, d_lang=d_lang,
                                                                                  translate_responses=False,
                                                                                  translate_actions=False)

        base_domain = mp.load_domain(bot="test_bot")
        new_domain = mp.load_domain(bot=destination_bot)

        # Checking domain
        for key, response in base_domain.responses.items():
            for i, utter in enumerate(response):
                if utter.get('text'):
                    assert utter['text'] == new_domain.responses[key][i]['text']

        base_nlu = mp.load_nlu(bot="test_bot")
        new_nlu = mp.load_nlu(bot=destination_bot)

        # Checking nlu
        for i, example in enumerate(base_nlu.training_examples):
            assert 'TRANSLATED_' + example.data['text'] == new_nlu.training_examples[i].data['text']

        base_actions = mp.load_action_configurations(bot="test_bot")
        new_actions = mp.load_action_configurations(bot=destination_bot)

        # Checking actions
        # http_action
        for i, action in enumerate(base_actions[ActionType.http_action]):
            assert action['response'].get('value') == new_actions[ActionType.http_action][i]['response'].get('value')
        # email_action
        for i, action in enumerate(base_actions[ActionType.email_action]):
            assert action['response'] == new_actions[ActionType.email_action][i]['response']
        # jira_action
        for i, action in enumerate(base_actions[ActionType.jira_action]):
            assert action['response'] == new_actions[ActionType.jira_action][i]['response']
        # zendesk_action
        for i, action in enumerate(base_actions[ActionType.zendesk_action]):
            assert action['response'] == new_actions[ActionType.zendesk_action][i]['response']
        # pipedrive_leads_action
        for i, action in enumerate(base_actions[ActionType.pipedrive_leads_action]):
            assert action['response'] == new_actions[ActionType.pipedrive_leads_action][i]['response']
        # google_search_action
        for i, action in enumerate(base_actions[ActionType.google_search_action]):
            assert action['failure_response'] == new_actions[ActionType.google_search_action][i]['failure_response']
        # form_validation_action
        for i, action in enumerate(base_actions[ActionType.form_validation_action]):
            assert action['valid_response'] == new_actions[ActionType.form_validation_action][i]['valid_response']
        for i, action in enumerate(base_actions[ActionType.form_validation_action]):
            assert action['invalid_response'] == new_actions[ActionType.form_validation_action][i]['invalid_response']

        assert mp.load_config(bot=destination_bot)
        assert mp.load_stories(bot=destination_bot)
        assert mp.get_rules_for_training(bot=destination_bot)

        new_bot = AccountProcessor.get_bot(destination_bot)
        assert new_bot["metadata"] == {'source_language': s_lang, 'language': d_lang, 'source_bot_id': 'test_bot'}

    def test_create_multilingual_bot_loading_nlu_fail(self, monkeypatch):
        s_lang = "en"
        d_lang = "es"

        def _mock_raise_exception(*args, **kwargs):
            raise Exception(f"Creation failed")

        monkeypatch.setattr(MongoProcessor, "load_nlu", _mock_raise_exception)

        multilingual_translator = MultilingualTranslator(account=pytest.bot.account, user=pytest.bot.user)

        start_bot_count = Bot.objects(status=True).count()
        with pytest.raises(AppException):
            destination_bot = multilingual_translator.create_multilingual_bot(base_bot_id=pytest.bot.id,
                                                                              base_bot_name=pytest.bot.name,
                                                                              s_lang=s_lang, d_lang=d_lang,
                                                                              translate_responses=False,
                                                                              translate_actions=False)
            assert not destination_bot

        assert start_bot_count == Bot.objects(status=True).count()

    @pytest.mark.asyncio
    async def test_create_multilingual_bot_translation_fail(self, monkeypatch):
        mp = MongoProcessor()
        s_lang = "en"
        d_lang = "es"

        def _mock_translate(*args, **kwargs):
            raise Exception("translation failed")

        bot = Bot(name="test_bot", account=1, user="test_user")
        await (mp.save_from_path("./tests/testing_data/yml_training_files",
                                 bot="test_bot", user="test_user"))

        monkeypatch.setattr(TranslationServiceClient, "translate_text", _mock_translate)

        multilingual_translator = MultilingualTranslator(account=bot.account, user=bot.user)

        start_bot_count = Bot.objects(status=True).count()
        with pytest.raises(AppException):
            destination_bot = multilingual_translator.create_multilingual_bot(base_bot_id="test_bot",
                                                                              base_bot_name=bot.name,
                                                                              s_lang=s_lang, d_lang=d_lang,
                                                                              translate_responses=False,
                                                                              translate_actions=False)
            assert not destination_bot

        assert start_bot_count == Bot.objects(status=True).count()

    @pytest.mark.asyncio
    async def test_create_multilingual_bot_save_files_fail(self, monkeypatch):
        mp = MongoProcessor()
        s_lang = "en"
        d_lang = "es"

        def _mock_delete_domain(*args, **kwargs):
            raise Exception("file saving failed")

        def _mock_service_client(*args, **kwargs):
            class MockServiceClient:

                def translate_text(*args, **kwargs):
                    text = kwargs["request"]["contents"]

                    class TranslationResponse:

                        class Translations:
                            translated_text = None

                            def __init__(self, sentence):
                                self.translated_text = sentence

                        translations = []

                        def __init__(self, text_list):
                            for t in text_list:
                                self.translations.append(self.Translations('TRANSLATED_' + t))

                    return TranslationResponse(text)

            return MockServiceClient()

        bot = Bot(name="test_bot", account=1, user="test_user")
        await (mp.save_from_path("./tests/testing_data/yml_training_files",
                                 bot="test_bot", user="test_user"))

        start_bot_count = Bot.objects(status=True).count()

        monkeypatch.setattr(MongoProcessor, "delete_domain", _mock_delete_domain)
        with pytest.raises(AppException):
            with patch("google.oauth2.service_account.Credentials", autospec=True):
                with patch("google.cloud.translate_v3.TranslationServiceClient.__new__") as mocked_new:
                    mocked_new.side_effect = _mock_service_client

                    multilingual_translator = MultilingualTranslator(account=bot.account, user=bot.user)
                    destination_bot = multilingual_translator.create_multilingual_bot(base_bot_id="test_bot",
                                                                                      base_bot_name=bot.name,
                                                                                      s_lang=s_lang, d_lang=d_lang,
                                                                                      translate_responses=False,
                                                                                      translate_actions=False)
                    assert not destination_bot

        assert start_bot_count == Bot.objects(status=True).count()

    def test_create_multilingual_bot_empty_data(self, monkeypatch):
        s_lang = "en"
        d_lang = "es"

        def _mock_translate(*args, **kwargs):
            raise Exception("Translation triggerd on empty data")

        monkeypatch.setattr(Translator, "translate_text_bulk", _mock_translate)

        multilingual_translator = MultilingualTranslator(account=pytest.bot.account, user=pytest.bot.user)
        destination_bot = multilingual_translator.create_multilingual_bot(base_bot_id=pytest.bot.id,
                                                                          base_bot_name=pytest.bot.name,
                                                                          s_lang=s_lang, d_lang=d_lang,
                                                                          translate_responses=True,
                                                                          translate_actions=True)
        assert destination_bot

    def test_create_multilingual_bot_iterable_name(self):

        existing_bot = AccountProcessor.add_bot(name="test_hi", account=1, user="test_user")
        s_lang = "en"
        d_lang = "hi"
        multilingual_translator = MultilingualTranslator(account=pytest.bot.account, user=pytest.bot.user)
        destination_bot = multilingual_translator.create_multilingual_bot(base_bot_id=pytest.bot.id,
                                                                          base_bot_name=pytest.bot.name,
                                                                          s_lang=s_lang, d_lang=d_lang,
                                                                          translate_responses=True,
                                                                          translate_actions=True)
        new_bot = AccountProcessor.get_bot(destination_bot)
        assert new_bot['name'] == existing_bot['name'] + '_' + '1'

    def test_get_languages(self):

        def _mock_service_client(*args, **kwargs):

            class MockServiceClient:

                def get_supported_languages(*args, **kwargs):

                    class LanguageResponse:

                        class Language:
                            language_code = "en"

                            def __init__(self):
                                self.language_code = "en"

                        languages = []

                        def __init__(self):
                            self.languages.append(self.Language())

                    return LanguageResponse()

            return MockServiceClient()

        with patch("google.oauth2.service_account.Credentials", autospec=True):
            with patch("google.cloud.translate_v3.TranslationServiceClient.__new__") as mocked_new:
                mocked_new.side_effect = _mock_service_client

                supported_languages = Translator.get_supported_languages()
                assert supported_languages == ["en"]

    def test_translation_call_fail(self, monkeypatch):

        def _mock_service_account(*args, **kwargs):
            raise AppException("Service account creation failed")

        monkeypatch.setattr(service_account.Credentials, "from_service_account_info", _mock_service_account)

        with pytest.raises(AppException):
            translated_text = Translator.translate_text_bulk(['translation text'], 'en', 'es')

            assert not translated_text
