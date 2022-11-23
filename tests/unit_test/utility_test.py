import os
import shutil
import tempfile
import uuid
from io import BytesIO
from unittest import mock

import pytest
import requests
import responses
from fastapi import UploadFile
from mongoengine import connect
from websockets import InvalidStatusCode
from websockets.datastructures import Headers

from kairon.exceptions import AppException
from kairon.shared.augmentation.utils import AugmentationUtils
from kairon.shared.data.base_data import AuditLogData
from kairon.shared.data.data_objects import EventConfig
from kairon.shared.data.utils import DataUtility
from kairon.shared.utils import Utility
from unittest.mock import patch
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
from kairon.chat.converters.channels.response_factory import ConverterFactory
import json


class TestUtility:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_email_configuration()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        pytest.bot = 'test'
        yield None
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.fixture()
    def resource_make_dirs(self):
        path = tempfile.mkdtemp()
        pytest.temp_path = path
        yield "resource"
        shutil.rmtree(path)

    @pytest.fixture()
    def resource_validate_files(self):
        tmp_dir = tempfile.mkdtemp()
        bot_data_home_dir = os.path.join(tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/yml_training_files', bot_data_home_dir)
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_files"
        shutil.rmtree(tmp_dir)

    @pytest.fixture()
    def resource_validate_no_training_files(self):
        bot_data_home_dir = tempfile.mkdtemp()
        os.mkdir(os.path.join(bot_data_home_dir, 'data'))
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_no_training_files"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_unzip_and_validate(self):
        data_path = 'tests/testing_data/yml_training_files'
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.make_archive(zip_file, 'zip', data_path)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_unzip_and_validate"
        os.remove(zip_file + '.zip')

    @pytest.fixture()
    def resource_unzip_and_validate_exception(self):
        data_path = 'tests/testing_data/yml_training_files/data'
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.make_archive(zip_file, 'zip', data_path)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_unzip_and_validate_exception"
        os.remove(zip_file + '.zip')

    @pytest.fixture()
    def resource_validate_no_training_files_delete_dir(self):
        bot_data_home_dir = tempfile.mkdtemp()
        os.mkdir(os.path.join(bot_data_home_dir, 'data'))
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_no_training_files_delete_dir"

    @pytest.fixture()
    def resource_validate_only_stories_and_nlu(self):
        bot_data_home_dir = tempfile.mkdtemp()
        shutil.copytree('tests/testing_data/yml_training_files/data/', os.path.join(bot_data_home_dir, 'data'))
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_only_stories_and_nlu"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_validate_only_http_actions(self):
        bot_data_home_dir = tempfile.mkdtemp()
        shutil.copy2('tests/testing_data/yml_training_files/actions.yml', bot_data_home_dir)
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_only_http_actions"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_validate_only_domain(self):
        bot_data_home_dir = tempfile.mkdtemp()
        shutil.copy2('tests/testing_data/yml_training_files/domain.yml', bot_data_home_dir)
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_resource_validate_only_domain"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_validate_only_config(self):
        bot_data_home_dir = tempfile.mkdtemp()
        shutil.copy2('tests/testing_data/yml_training_files/config.yml', bot_data_home_dir)
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_resource_validate_only_config"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_save_and_validate_training_files(self):
        config_path = 'tests/testing_data/yml_training_files/config.yml'
        domain_path = 'tests/testing_data/yml_training_files/domain.yml'
        nlu_path = 'tests/testing_data/yml_training_files/data/nlu.yml'
        stories_path = 'tests/testing_data/yml_training_files/data/stories.yml'
        http_action_path = 'tests/testing_data/yml_training_files/actions.yml'
        rules_path = 'tests/testing_data/yml_training_files/data/rules.yml'
        pytest.config = UploadFile(filename="config.yml", file=BytesIO(open(config_path, 'rb').read()))
        pytest.domain = UploadFile(filename="domain.yml", file=BytesIO(open(domain_path, 'rb').read()))
        pytest.nlu = UploadFile(filename="nlu.yml", file=BytesIO(open(nlu_path, 'rb').read()))
        pytest.stories = UploadFile(filename="stories.yml", file=BytesIO(open(stories_path, 'rb').read()))
        pytest.http_actions = UploadFile(filename="actions.yml", file=BytesIO(open(http_action_path, 'rb').read()))
        pytest.rules = UploadFile(filename="rules.yml", file=BytesIO(open(rules_path, 'rb').read()))
        pytest.non_nlu = UploadFile(filename="non_nlu.yml", file=BytesIO(open(rules_path, 'rb').read()))
        yield "resource_save_and_validate_training_files"

    @pytest.mark.asyncio
    async def test_save_training_files(self):
        nlu_content = "## intent:greet\n- hey\n- hello".encode()
        stories_content = "## greet\n* greet\n- utter_offer_help\n- action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        rules_content = "rules:\n\n- rule: Only say `hello` if the user provided a location\n  condition:\n  - slot_was_set:\n    - location: true\n  steps:\n  - intent: greet\n  - action: utter_greet\n".encode()
        http_action_content = "http_actions:\n- action_name: action_performanceUsers1000@digite.com\n  auth_token: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  http_url: http://www.alphabet.com\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response: json\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.md", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        rules = UploadFile(filename="rules.yml", file=BytesIO(rules_content))
        http_action = UploadFile(filename="actions.yml", file=BytesIO(http_action_content))
        training_file_loc = await DataUtility.save_training_files(nlu, domain, config, stories, rules, http_action)
        assert os.path.exists(training_file_loc['nlu'])
        assert os.path.exists(training_file_loc['config'])
        assert os.path.exists(training_file_loc['stories'])
        assert os.path.exists(training_file_loc['domain'])
        assert os.path.exists(training_file_loc['rules'])
        assert os.path.exists(training_file_loc['http_action'])
        assert os.path.exists(training_file_loc['root'])

    @pytest.mark.asyncio
    async def test_upload_and_save(self):
        nlu_content = "## intent:greet\n- hey\n- hello".encode()
        stories_content = "## greet\n* greet\n- utter_offer_help\n- action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.md", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        training_file_loc = await DataUtility.save_training_files(nlu, domain, config, stories, None)
        assert os.path.exists(training_file_loc['nlu'])
        assert os.path.exists(training_file_loc['config'])
        assert os.path.exists(training_file_loc['stories'])
        assert os.path.exists(training_file_loc['domain'])
        assert not training_file_loc.get('rules')
        assert not training_file_loc.get('http_action')
        assert os.path.exists(training_file_loc['root'])

    @pytest.mark.asyncio
    async def test_write_training_data(self):
        from kairon.shared.data.processor import MongoProcessor
        processor = MongoProcessor()
        await (
            processor.save_from_path(
                "./tests/testing_data/yml_training_files", bot="test_load_from_path_yml_training_files", user="testUser"
            )
        )
        training_data = processor.load_nlu("test_load_from_path_yml_training_files")
        story_graph = processor.load_stories("test_load_from_path_yml_training_files")
        domain = processor.load_domain("test_load_from_path_yml_training_files")
        config = processor.load_config("test_load_from_path_yml_training_files")
        http_action = processor.load_http_action("test_load_from_path_yml_training_files")
        training_data_path = Utility.write_training_data(training_data, domain, config, story_graph, None, http_action)
        assert os.path.exists(training_data_path)

    def test_write_training_data_with_rules(self):
        from kairon.shared.data.processor import MongoProcessor
        processor = MongoProcessor()
        training_data = processor.load_nlu("test_load_from_path_yml_training_files")
        story_graph = processor.load_stories("test_load_from_path_yml_training_files")
        domain = processor.load_domain("test_load_from_path_yml_training_files")
        config = processor.load_config("test_load_from_path_yml_training_files")
        http_action = processor.load_http_action("test_load_from_path_yml_training_files")
        rules = processor.get_rules_for_training("test_load_from_path_yml_training_files")
        training_data_path = Utility.write_training_data(training_data, domain, config, story_graph, rules, http_action)
        assert os.path.exists(training_data_path)

    def test_read_yaml(self):
        path = 'tests/testing_data/yml_training_files/actions.yml'
        content = Utility.read_yaml(path)
        assert len(content['http_action']) == 5

    def test_read_yaml_not_found_exception(self):
        path = 'tests/testing_data/yml_training_files/path_not_found.yml'
        with pytest.raises(AppException):
            Utility.read_yaml(path, True)

    def test_read_yaml_not_found(self):
        path = 'tests/testing_data/yml_training_files/path_not_found.yml'
        assert not Utility.read_yaml(path, False)

    def test_replace_file_name(self):
        msg = "Invalid /home/digite/kairon/domain.yaml:\n Error found in /home/digite/kairon/domain.yaml at line 6"
        output = Utility.replace_file_name(msg, '/home')
        assert output == "Invalid domain.yaml:\n Error found in domain.yaml at line 6"

    def test_replace_file_name_key_not_in_msg(self):
        msg = "Invalid domain.yaml:\n Error found in domain.yaml at line 6"
        output = Utility.replace_file_name(msg, '/home')
        assert output == "Invalid domain.yaml:\n Error found in domain.yaml at line 6"

    def test_make_dirs(self, resource_make_dirs):
        path = os.path.join(pytest.temp_path, str(uuid.uuid4()))
        Utility.make_dirs(path)
        assert os.path.exists(path)

    def test_get_action_url(self, monkeypatch):
        actual = Utility.get_action_url({})
        assert actual.url == "http://localhost:5055/webhook"
        actual = Utility.get_action_url({"action_endpoint": {"url": "http://action-server:5055/webhook"}})
        assert actual.url == "http://action-server:5055/webhook"
        monkeypatch.setitem(Utility.environment['action'], "url", None)
        actual = Utility.get_action_url({})
        assert actual is None

    def test_make_dirs_exception(self, resource_make_dirs):
        assert os.path.exists(pytest.temp_path)
        with pytest.raises(AppException) as e:
            Utility.make_dirs(pytest.temp_path, True)
        assert str(e).__contains__('Directory exists!')

    def test_make_dirs_path_already_exists(self, resource_make_dirs):
        assert os.path.exists(pytest.temp_path)
        assert not Utility.make_dirs(pytest.temp_path)

    def test_prepare_nlu_text_with_entities(self):
        expected = "n=[8](n), p=1[8](n), k=2[8](n) ec=[14](ec), ph=[3](p)"
        text, entities = DataUtility.extract_text_and_entities(expected)
        actual = DataUtility.prepare_nlu_text(text, entities)
        assert expected == actual

    def test_prepare_nlu_text(self):
        expected = "India is beautiful"
        text, entities = DataUtility.extract_text_and_entities(expected)
        actual = DataUtility.prepare_nlu_text(text, entities)
        assert expected == actual

    def test_get_interpreter_with_no_model(self):
        actual = DataUtility.get_interpreter("test.tar.gz")
        assert actual is None

    def test_validate_files(self, resource_validate_files):
        requirements = DataUtility.validate_and_get_requirements(pytest.bot_data_home_dir)
        assert not requirements

    def test_initiate_apm_client_disabled(self):
        assert not Utility.initiate_apm_client_config()

    def test_initiate_apm_client_enabled(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'enable', True)
        assert not Utility.initiate_apm_client_config()

    def test_initiate_apm_client_server_url_not_present(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'enable', True)
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'apm_server_url', None)

        assert not Utility.initiate_apm_client_config()

    def test_initiate_apm_client_service_url_not_present(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'enable', True)
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'apm_server_url', None)
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'service_name', None)

        assert not Utility.initiate_apm_client_config()

    def test_initiate_apm_client_env_not_present(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'enable', True)
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'env_type', None)

        assert Utility.initiate_apm_client_config() is None

    def test_initiate_apm_client_with_url_present(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'enable', True)
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'service_name', "kairon")
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'apm_server_url', "http://localhost:8082")

        client = Utility.initiate_apm_client_config()
        assert client == {"SERVER_URL": "http://localhost:8082",
                          "SERVICE_NAME": "kairon",
                          'ENVIRONMENT': "development"}

        monkeypatch.setitem(Utility.environment["elasticsearch"], 'secret_token', "12345")

        client = Utility.initiate_apm_client_config()
        assert client == {"SERVER_URL": "http://localhost:8082",
                          "SERVICE_NAME": "kairon",
                          'ENVIRONMENT': "development",
                          "SECRET_TOKEN": "12345"}

    def test_validate_path_not_found(self):
        with pytest.raises(AppException):
            DataUtility.validate_and_get_requirements('/tests/path_not_found')

    def test_validate_no_files(self, resource_validate_no_training_files):
        with pytest.raises(AppException):
            DataUtility.validate_and_get_requirements(pytest.bot_data_home_dir)
        assert os.path.exists(pytest.bot_data_home_dir)

    def test_validate_no_files_delete_dir(self, resource_validate_no_training_files_delete_dir):
        with pytest.raises(AppException):
            DataUtility.validate_and_get_requirements(pytest.bot_data_home_dir, True)
        assert not os.path.exists(pytest.bot_data_home_dir)

    def test_validate_only_stories_and_nlu(self, resource_validate_only_stories_and_nlu):
        requirements = DataUtility.validate_and_get_requirements(pytest.bot_data_home_dir, True)
        assert {'actions', 'config', 'domain'} == requirements

    def test_validate_only_http_actions(self, resource_validate_only_http_actions):
        requirements = DataUtility.validate_and_get_requirements(pytest.bot_data_home_dir, True)
        assert {'rules', 'domain', 'config', 'stories', 'nlu'} == requirements

    def test_validate_only_domain(self, resource_validate_only_domain):
        requirements = DataUtility.validate_and_get_requirements(pytest.bot_data_home_dir, True)
        assert {'rules', 'actions', 'config', 'stories', 'nlu'} == requirements

    def test_validate_only_config(self, resource_validate_only_config):
        requirements = DataUtility.validate_and_get_requirements(pytest.bot_data_home_dir, True)
        assert {'rules', 'actions', 'domain', 'stories', 'nlu'} == requirements

    @pytest.mark.asyncio
    async def test_unzip_and_validate(self, resource_unzip_and_validate):
        unzip_path = await DataUtility.save_training_files_as_zip(pytest.bot, pytest.zip)
        assert os.path.exists(unzip_path)

    @pytest.mark.asyncio
    async def test_unzip_and_validate_exception(self, resource_unzip_and_validate_exception):
        unzip_path = await DataUtility.save_training_files_as_zip(pytest.bot, pytest.zip)
        assert os.path.exists(unzip_path)

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_zip(self, resource_unzip_and_validate):
        bot_data_home_dir = await DataUtility.save_uploaded_data(pytest.bot, [pytest.zip])
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_no_files_received(self):
        with pytest.raises(AppException) as e:
            await DataUtility.save_uploaded_data(pytest.bot, [])
        assert str(e).__contains__("No files received!")

        with pytest.raises(AppException) as e:
            await DataUtility.save_uploaded_data(pytest.bot, None)
        assert str(e).__contains__("No files received!")

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_2_files_only(self, resource_save_and_validate_training_files):
        bot_data_home_dir = await DataUtility.save_uploaded_data(pytest.bot, [pytest.domain, pytest.nlu])
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files(self, resource_save_and_validate_training_files):
        training_files = [pytest.config, pytest.domain, pytest.nlu, pytest.stories, pytest.rules, pytest.http_actions]
        bot_data_home_dir = await DataUtility.save_uploaded_data(pytest.bot, training_files)
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_no_rules_and_http_actions(self,
                                                                              resource_save_and_validate_training_files):
        training_files = [pytest.config, pytest.domain, pytest.nlu, pytest.stories]
        bot_data_home_dir = await DataUtility.save_uploaded_data(pytest.bot, training_files)
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_invalid(self, resource_save_and_validate_training_files):
        training_files = [pytest.config, pytest.domain, pytest.non_nlu, pytest.stories]
        bot_data_home_dir = await DataUtility.save_uploaded_data(pytest.bot, training_files)
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'non_nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'non_nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))

    def test_build_event_request(self):
        request = {'BOT': 'mood_bot', "USER": "bot_user"}
        request_body = Utility.build_lambda_payload(request)
        assert isinstance(request_body, list)
        assert request_body[0]['name'] == 'BOT'
        assert request_body[0]['value'] == 'mood_bot'
        assert request_body[1]['name'] == 'USER'
        assert request_body[1]['value'] == 'bot_user'
        assert len(request_body) == 2

    def test_build_event_request_empty(self):
        request_body = Utility.build_lambda_payload({})
        assert isinstance(request_body, list)
        assert not request_body

    def test_download_csv(self):
        file_path, temp_path = Utility.download_csv([{"test": "test_val"}], None)
        assert file_path.endswith(".csv")
        assert "tmp" in str(temp_path).lower()

    def test_download_csv_no_data(self):
        with pytest.raises(AppException) as e:
            Utility.download_csv([], None)
        assert str(e).__contains__("No data available")

    def test_download_csv_error_message(self):
        with pytest.raises(AppException) as e:
            Utility.download_csv([], "error_message")
        assert str(e).__contains__("error_message")

    def test_extract_db_config_without_login(self):
        config = Utility.extract_db_config("mongodb://localhost/test")
        assert config['db'] == "test"
        assert config['username'] is None
        assert config['password'] is None
        assert config['host'] == "mongodb://localhost"
        assert len(config["options"]) == 0

    def test_extract_db_config_with_login(self):
        config = Utility.extract_db_config("mongodb://admin:admin@localhost/test?authSource=admin")
        assert config['db'] == "test"
        assert config['username'] == "admin"
        assert config['password'] == "admin"
        assert config['host'] == "mongodb://localhost"
        assert "authSource" in config['options']

    def test_get_event_server_url_not_found(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['events'], 'server_url', None)
        with pytest.raises(AppException, match="Event server url not found"):
            Utility.get_event_server_url()

    def test_get_event_server_url(self):
        assert Utility.get_event_server_url() == 'http://localhost:5001'

    def test_is_model_file_exists(self):
        assert not Utility.is_model_file_exists('invalid_bot', False)
        with pytest.raises(AppException, match='No model trained yet. Please train a model to test'):
            Utility.is_model_file_exists('invalid_bot')

    @pytest.mark.asyncio
    async def test_trigger_email(self):
        with patch('kairon.shared.utils.SMTP', autospec=True) as mock:
            content_type = "html"
            to_email = "test@demo.com"
            subject = "Test"
            body = "Test"
            smtp_url = "localhost"
            smtp_port = 293
            sender_email = "dummy@test.com"
            smtp_password = "test"
            smtp_userid = None
            tls = False

            await Utility.trigger_email([to_email],
                                        subject,
                                        body,
                                        content_type=content_type,
                                        smtp_url=smtp_url,
                                        smtp_port=smtp_port,
                                        sender_email=sender_email,
                                        smtp_userid=smtp_userid,
                                        smtp_password=smtp_password,
                                        tls=tls)

            mbody = MIMEText(body, content_type)
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = sender_email
            msg['To'] = to_email
            msg.attach(mbody)

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().connect'
            assert {} == kwargs

            host, port = args
            assert host == smtp_url
            assert port == port

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().login'
            assert {} == kwargs

            from_email, password = args
            assert from_email == sender_email
            assert password == smtp_password

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().sendmail'
            assert {} == kwargs

            assert args[0] == sender_email
            assert args[1] == [to_email]
            assert str(args[2]).__contains__(subject)
            assert str(args[2]).__contains__(body)

    @pytest.mark.asyncio
    async def test_trigger_email_tls(self):
        with patch('kairon.shared.utils.SMTP', autospec=True) as mock:
            content_type = "html"
            to_email = "test@demo.com"
            subject = "Test"
            body = "Test"
            smtp_url = "localhost"
            smtp_port = 293
            sender_email = "dummy@test.com"
            smtp_password = "test"
            smtp_userid = None
            tls = True

            await Utility.trigger_email([to_email],
                                        subject,
                                        body,
                                        content_type=content_type,
                                        smtp_url=smtp_url,
                                        smtp_port=smtp_port,
                                        sender_email=sender_email,
                                        smtp_userid=smtp_userid,
                                        smtp_password=smtp_password,
                                        tls=tls)

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().connect'
            assert {} == kwargs

            host, port = args
            assert host == smtp_url
            assert port == port

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().starttls'
            assert {} == kwargs

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().login'
            assert {} == kwargs

            from_email, password = args
            assert from_email == sender_email
            assert password == smtp_password

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().sendmail'
            assert {} == kwargs

            assert args[0] == sender_email
            assert args[1] == [to_email]
            assert str(args[2]).__contains__(subject)
            assert str(args[2]).__contains__(body)

    @pytest.mark.asyncio
    async def test_trigger_email_using_smtp_userid(self):
        with patch('kairon.shared.utils.SMTP', autospec=True) as mock:
            content_type = "html"
            to_email = "test@demo.com"
            subject = "Test"
            body = "Test"
            smtp_url = "localhost"
            smtp_port = 293
            sender_email = "dummy@test.com"
            smtp_password = "test"
            smtp_userid = "test_user"
            tls = True

            await Utility.trigger_email([to_email],
                                        subject,
                                        body,
                                        content_type=content_type,
                                        smtp_url=smtp_url,
                                        smtp_port=smtp_port,
                                        sender_email=sender_email,
                                        smtp_userid=smtp_userid,
                                        smtp_password=smtp_password,
                                        tls=tls)

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().connect'
            assert {} == kwargs

            host, port = args
            assert host == smtp_url
            assert port == port

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().starttls'
            assert {} == kwargs

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().login'
            assert {} == kwargs

            from_email, password = args
            assert from_email == smtp_userid
            assert password == smtp_password

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().sendmail'
            assert {} == kwargs

            assert args[0] == sender_email
            assert args[1] == [to_email]
            assert str(args[2]).__contains__(subject)
            assert str(args[2]).__contains__(body)

    def test_validate_smtp_valid(self):
        with patch('kairon.shared.utils.SMTP', autospec=True) as mock:
            assert Utility.validate_smtp("localhost", 25)

    def test_validate_smtp_invalid(self):
        with patch('kairon.shared.utils.SMTP', autospec=True) as mock:
            mock.return_value = Exception()
            assert not Utility.validate_smtp("dummy.test.com", 467)

    @pytest.mark.asyncio
    async def test_trigger_smtp(self):
        with patch('kairon.shared.utils.SMTP', autospec=True) as mock:
            content_type = "html"
            to_email = "test@demo.com"
            subject = "Test"
            body = "Test"
            smtp_url = "changeit"
            sender_email = "changeit@changeit.com"
            smtp_password = "changeit"
            smtp_port = 587

            await Utility.trigger_smtp(to_email,
                                        subject,
                                        body,
                                        content_type=content_type)

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().connect'
            assert {} == kwargs

            host, port = args
            assert host == smtp_url
            assert port == smtp_port

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().starttls'
            assert {} == kwargs

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().login'
            assert {} == kwargs

            from_email, password = args
            assert from_email == sender_email
            assert password == smtp_password

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == '().sendmail'
            assert {} == kwargs

            assert args[0] == sender_email
            assert args[1] == [to_email]
            assert str(args[2]).__contains__(subject)
            assert str(args[2]).__contains__(body)

    @pytest.mark.asyncio
    async def test_websocket_request(self):
        url = 'ws://localhost/events/bot_id'
        msg = 'hello'
        with patch('kairon.shared.utils.connect', autospec=True) as mock:
            await Utility.websocket_request(url, msg)
            mock.assert_called_with(url)

    @pytest.mark.asyncio
    async def test_websocket_request_connect_exception(self):
        url = 'ws://localhost/events/bot_id'
        msg = 'hello'

        def _mock_websocket_connect_exception(*args, **kwargs):
            raise InvalidStatusCode(404, Headers())

        with patch('kairon.shared.utils.connect', autospec=True) as mock:
            mock.side_effect = _mock_websocket_connect_exception
            with pytest.raises(InvalidStatusCode):
                await Utility.websocket_request(url, msg)

    def test_execute_http_request_connection_error(self):
        def __mock_connection_error(*args, **kwargs):
            raise requests.exceptions.ConnectTimeout()
        with mock.patch("kairon.shared.utils.requests.request") as mocked:
            mocked.side_effect = __mock_connection_error
            with pytest.raises(AppException, match='Failed to connect to service: test.com'):
                Utility.execute_http_request("POST", "http://test.com/endpoint")

    def test_execute_http_request_exception(self):
        def __mock_connection_error(*args, **kwargs):
            raise Exception("Server not found")
        with mock.patch("kairon.shared.utils.requests.request") as mocked:
            mocked.side_effect = __mock_connection_error
            with pytest.raises(AppException, match='Failed to execute the url: Server not found'):
                Utility.execute_http_request("POST", "http://test.com/endpoint")

    def test_execute_http_request_invalid_request(self):
        with pytest.raises(AppException, match="Invalid request method!"):
            Utility.execute_http_request("OPTIONS", "http://test.com/endpoint")

    @responses.activate
    def test_execute_http_request_empty_error_msg(self):
        responses.add(
            "POST",
            "https://app.chatwoot.com/public/api/v1/accounts",
            status=404
        )
        with pytest.raises(AppException, match="err_msg cannot be empty"):
            Utility.execute_http_request("POST", "https://app.chatwoot.com/public/api/v1/accounts", validate_status=True)

    def test_get_masked_value_empty(self):
        assert None is Utility.get_masked_value(None)
        assert "" == Utility.get_masked_value("")
        assert "  " == Utility.get_masked_value("  ")

    def test_get_masked_value_len_less_than_4(self):
        assert Utility.get_masked_value("test") == "****"

    def test_get_masked_value_len_more_from_left(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['security'], "unmasked_char_strategy", "from_left")
        assert Utility.get_masked_value("teststring") == "te********"

    def test_get_masked_value_mask_strategy_from_right(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['security'], "unmasked_char_strategy", "from_right")
        assert Utility.get_masked_value("teststring") == "********ng"

    def test_get_masked_value_from_mask_strategy_not_set(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['security'], "unmasked_char_strategy", None)
        assert Utility.get_masked_value("teststring") == "**********"

    def test_getChannelConfig(self):
        configdata = ElementTransformerOps.getChannelConfig("slack", "image")
        assert configdata

    def test_getChannelConfig_negative(self):
        configdata = ElementTransformerOps.getChannelConfig("slack", "image_negative")
        assert not configdata

    def test_getChannelConfig_no_channel(self):
        with pytest.raises(AppException):
            ElementTransformerOps.getChannelConfig("nochannel", "image")

    def test_message_extractor_hangout_image(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        element_resolver = ElementTransformerOps("image", "hangout")
        response = element_resolver.message_extractor(input_json, "image")
        expected_output = {"type": "image", "URL": "https://i.imgur.com/nFL91Pc.jpeg",
                           "caption": "Dog Image"}
        assert expected_output == response

    def test_message_extractor_hangout_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        element_resolver = ElementTransformerOps("link", "hangout")
        response = element_resolver.message_extractor(input_json, "link")
        output = response.get("data")
        expected_output = "This is <http://www.google.com|GoogleLink> use for search"
        assert expected_output == output

    def test_message_extractor_slack_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        element_resolver = ElementTransformerOps("link", "slack")
        response = element_resolver.message_extractor(input_json, "link")
        output = response.get("data")
        expected_output = "This is <http://www.google.com|GoogleLink> use for search"
        assert expected_output == output

    def test_message_extractor_messenger_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter
        messenger = MessengerResponseConverter("link", "messenger")
        response = messenger.message_extractor(input_json, "link")
        output = response.get("data")
        expected_output = "This is http://www.google.com use for search"
        assert expected_output == output

    def test_message_extractor_telegram_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.telegram import TelegramResponseConverter
        telegram = TelegramResponseConverter("link", "telegram")
        response = telegram.message_extractor(input_json, "link")
        output = response.get("data")
        expected_output = "This is http://www.google.com use for search"
        assert expected_output == output

    def test_message_extractor_whatsapp_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
        whatsapp = WhatsappResponseConverter("link", "whatsapp")
        response = whatsapp.message_extractor(input_json, "link")
        output = response.get("data")
        expected_output = "This is http://www.google.com use for search"
        assert expected_output == output

    def test_message_extractor_hangout_multi_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("multi_link")
        element_resolver = ElementTransformerOps("link", "hangout")
        response = element_resolver.message_extractor(input_json, "link")
        output = response.get("data")
        expected_output = "This is <http://www.google.com|GoogleLink> use for search and you can also see news on <https://www.indiatoday.in/|Indiatoday> and slatejs details on <https://www.slatejs.org/examples/richtext|SlateJS>"
        assert expected_output.strip() == output

    def test_message_extractor_whatsapp_multi_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("multi_link")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
        whatsapp = WhatsappResponseConverter("link", "whatsapp")
        response = whatsapp.message_extractor(input_json, "link")
        output = response.get("data")
        expected_output = "This is http://www.google.com use for search and you can also see news on https://www.indiatoday.in/ and slatejs details on https://www.slatejs.org/examples/richtext"
        assert expected_output.strip() == output

    def test_message_extractor_hangout_only_link_no_text(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("only_link")
        element_resolver = ElementTransformerOps("link", "hangout")
        response = element_resolver.message_extractor(input_json, "link")
        output = response.get("data")
        expected_output = "<http://www.google.com|GoogleLink>"
        assert expected_output.strip() == output

    def test_message_extractor_whatsapp_only_link_no_text(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("only_link")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
        whatsapp = WhatsappResponseConverter("link", "whatsapp")
        response = whatsapp.message_extractor(input_json, "link")
        output = response.get("data")
        expected_output = "http://www.google.com"
        assert expected_output.strip() == output

    def test_hangout_replace_strategy_image(self):
        message_tmp = ElementTransformerOps.getChannelConfig("hangout", "image")
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        element_resolver = ElementTransformerOps("image", "hangout")
        extract_response = element_resolver.message_extractor(input_json, "image")
        response = ElementTransformerOps.replace_strategy(message_tmp, extract_response, "hangout", "image")
        expected_output = "{'cards': [{'sections': [{'widgets': [{'textParagraph': {'text': 'Dog Image'}}, {'image': {'imageUrl': 'https://i.imgur.com/nFL91Pc.jpeg', 'onClick': {'openLink': {'url': 'https://i.imgur.com/nFL91Pc.jpeg'}}}}]}]}]}"
        assert expected_output == str(response).strip()

    def test_hangout_replace_strategy_no_channel(self):
        message_tmp = None
        extract_response = None
        with pytest.raises(Exception, match="Element key mapping missing for hangout_fake or image"):
            ElementTransformerOps.replace_strategy(message_tmp, extract_response, "hangout_fake", "image")

    def test_hangout_replace_strategy_no_type(self):
        message_tmp = None
        extract_response = None
        with pytest.raises(Exception, match="Element key mapping missing for hangout or image_fake"):
            ElementTransformerOps.replace_strategy(message_tmp, extract_response, "hangout", "image_fake")

    def test_image_transformer_hangout_image(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        elementops = ElementTransformerOps("image", "hangout")
        response = elementops.image_transformer(input_json)
        expected_output = "{'cards': [{'sections': [{'widgets': [{'textParagraph': {'text': 'Dog Image'}}, {'image': {'imageUrl': 'https://i.imgur.com/nFL91Pc.jpeg', 'onClick': {'openLink': {'url': 'https://i.imgur.com/nFL91Pc.jpeg'}}}}]}]}]}"
        assert expected_output == str(response).strip()

    def test_link_transformer_hangout_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        element_resolver = ElementTransformerOps("link", "hangout")
        response = element_resolver.link_transformer(input_json)
        output = str(response)
        expected_output = "{'text': 'This is <http://www.google.com|GoogleLink> use for search'}"
        assert expected_output == output

    def test_link_transformer_messenger(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter
        messenger = MessengerResponseConverter("link", "messenger")
        response = messenger.link_transformer(input_json)
        output = response.get('text')
        expected_output = "This is http://www.google.com use for search"
        assert expected_output == output

    def test_link_transformer_whatsapp(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
        whatsapp = WhatsappResponseConverter("link", "whatsapp")
        response = whatsapp.link_transformer(input_json)
        output = str(response)
        expected_output = """{'preview_url': True, 'body': 'This is http://www.google.com use for search'}"""
        assert expected_output == output

    def test_link_transformer_telegram(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.telegram import TelegramResponseConverter
        telegram = TelegramResponseConverter("link", "telegram")
        response = telegram.link_transformer(input_json)
        output = str(response)
        expected_output = """{'text': 'This is http://www.google.com use for search', 'parse_mode': 'HTML', 'disable_web_page_preview': False, 'disable_notification': False, 'reply_to_message_id': 0}"""
        assert expected_output == output

    def test_getConcreteInstance_telegram(self):
        from kairon.chat.converters.channels.telegram import TelegramResponseConverter
        telegram = ConverterFactory.getConcreteInstance("link", "telegram")
        assert isinstance(telegram, TelegramResponseConverter)

    def test_getConcreteInstance_invalid_type(self):
        telegram = ConverterFactory.getConcreteInstance("link", "invalid")
        assert telegram == None

    @pytest.mark.asyncio
    async def test_messageConverter_hangout_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        hangout = ConverterFactory.getConcreteInstance("link", "hangout")
        response = await hangout.messageConverter(input_json)
        expected_output = json_data.get("hangout_link_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_hangout_image(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        hangout = ConverterFactory.getConcreteInstance("image", "hangout")
        response = await hangout.messageConverter(input_json)
        expected_output = json_data.get("hangout_image_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_slack_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        slack = ConverterFactory.getConcreteInstance("link", "slack")
        response = await slack.messageConverter(input_json)
        expected_output = json_data.get("slack_link_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_slack_image(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        slack = ConverterFactory.getConcreteInstance("image", "slack")
        response = await slack.messageConverter(input_json)
        expected_output = json_data.get("slack_image_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_messenger_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        messenger = ConverterFactory.getConcreteInstance("link", "messenger")
        response = await messenger.messageConverter(input_json)
        expected_output = json_data.get("messenger_link_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_messenger_image(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        messenger = ConverterFactory.getConcreteInstance("image", "messenger")
        response = await messenger.messageConverter(input_json)
        expected_output = json_data.get("messenger_image_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_whatsapp_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        whatsapp = ConverterFactory.getConcreteInstance("link", "whatsapp")
        response = await whatsapp.messageConverter(input_json)
        expected_output = json_data.get("whatsapp_link_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_whatsapp_image(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        whatsapp = ConverterFactory.getConcreteInstance("image", "whatsapp")
        response = await whatsapp.messageConverter(input_json)
        expected_output = json_data.get("whatsapp_image_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_telegram_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        telegram = ConverterFactory.getConcreteInstance("link", "telegram")
        response = await telegram.messageConverter(input_json)
        expected_output = json_data.get("telegram_link_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_telegram_image(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        telegram = ConverterFactory.getConcreteInstance("image", "telegram")
        response = await telegram.messageConverter(input_json)
        expected_output = json_data.get("telegram_image_op")
        assert expected_output == response

    def test_json_generator(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("json_generator")
        json_generator = ElementTransformerOps.json_generator(input_json)
        datalist = [{"name": "testadmin","bot": 123}, {"name": "testadmin1", "bot": 100}]
        for item in json_generator:
            assert item in datalist

    def test_json_generator_nolist(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("json_generator_nolist")
        json_generator = ElementTransformerOps.json_generator(input_json)
        datalist = [{"name": "testadmin","bot": 123}]
        for item in json_generator:
            assert item in datalist

    def test_json_generator_nodata(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("json_generator_nodata")
        json_generator = ElementTransformerOps.json_generator(input_json)
        with pytest.raises(StopIteration):
            json_generator.__next__()

    def test_json_generator_instance(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("json_generator")
        json_generator = ElementTransformerOps.json_generator(input_json)
        import types
        assert isinstance(json_generator, types.GeneratorType)

    def test_convertjson_to_link_format(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        json_generator = ElementTransformerOps.json_generator(input_json)
        string_response = ElementTransformerOps.convertjson_to_link_format(json_generator)
        assert "This is <http://www.google.com|GoogleLink> use for search" == string_response

    def test_convertjson_to_link_format_no_display(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        json_generator = ElementTransformerOps.json_generator(input_json)
        string_response = ElementTransformerOps.convertjson_to_link_format(json_generator, False)
        assert "This is http://www.google.com use for search" == string_response

    @pytest.mark.asyncio
    async def test_messageConverter_hangout_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.hangout import HangoutResponseConverter
        hangout = HangoutResponseConverter("link", "hangout_fail")
        with pytest.raises(Exception):
            await hangout.messageConverter(input_json)

    @pytest.mark.asyncio
    async def test_messageConverter_slack_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.slack import SlackMessageConverter
        slack = SlackMessageConverter("link", "slack_fail")
        with pytest.raises(Exception):
            await slack.messageConverter(input_json)

    @pytest.mark.asyncio
    async def test_messageConverter_messenger_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter
        messenger = MessengerResponseConverter("link", "messenger_fail")
        with pytest.raises(Exception):
            await messenger.messageConverter(input_json)

    def test_link_transformer_messenger_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter
        messenger = MessengerResponseConverter("link", "messenger_fake")
        with pytest.raises(Exception):
            messenger.link_transformer(input_json)

    def test_message_extractor_messenger_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link_wrong_json")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter
        messenger = MessengerResponseConverter("link", "messenger")
        with pytest.raises(Exception):
            messenger.message_extractor(input_json,"link")

    @pytest.mark.asyncio
    async def test_messageConverter_telegram_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.telegram import TelegramResponseConverter
        telegram = TelegramResponseConverter("link", "messenger_fail")
        with pytest.raises(Exception):
            await telegram.messageConverter(input_json)

    def test_link_transformer_telegram_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.telegram import TelegramResponseConverter
        telegram = TelegramResponseConverter("link", "messenger_fake")
        with pytest.raises(Exception):
            telegram.link_transformer(input_json)

    def test_message_extractor_telegram_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link_wrong_json")
        from kairon.chat.converters.channels.telegram import TelegramResponseConverter
        telegram = TelegramResponseConverter("link", "messenger")
        with pytest.raises(Exception):
            telegram.message_extractor(input_json,"link")

    @pytest.mark.asyncio
    async def test_messageConverter_whatsapp_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
        whatsapp = WhatsappResponseConverter("link", "messenger_fail")
        with pytest.raises(Exception):
            await whatsapp.messageConverter(input_json)

    def test_link_transformer_whatsapp_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
        whatsapp = WhatsappResponseConverter("link", "messenger_fake")
        with pytest.raises(Exception):
            whatsapp.link_transformer(input_json)

    def test_message_extractor_whatsapp_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link_wrong_json")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
        whatsapp = WhatsappResponseConverter("link", "messenger")
        with pytest.raises(Exception):
            whatsapp.message_extractor(input_json,"link")

    @pytest.mark.asyncio
    async def test_messageConverter_hangout_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        hangout = ConverterFactory.getConcreteInstance("video", "hangout")
        response = await hangout.messageConverter(input_json)
        expected_output = json_data.get("hangout_video_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_slack_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        hangout = ConverterFactory.getConcreteInstance("video", "slack")
        response = await hangout.messageConverter(input_json)
        expected_output = json_data.get("slack_video_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_messenger_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        hangout = ConverterFactory.getConcreteInstance("video", "messenger")
        response = await hangout.messageConverter(input_json)
        expected_output = json_data.get("messenger_video_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_whatsapp_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        hangout = ConverterFactory.getConcreteInstance("video", "whatsapp")
        response = await hangout.messageConverter(input_json)
        expected_output = json_data.get("whatsapp_video_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_telegram_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        hangout = ConverterFactory.getConcreteInstance("video", "telegram")
        response = await hangout.messageConverter(input_json)
        expected_output = json_data.get("telegram_video_op")
        assert expected_output == response

    def test_message_extractor_slack_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        element_resolver = ElementTransformerOps("video", "slack")
        response = element_resolver.message_extractor(input_json, "video")
        output = response.get("data")
        expected_output = "https://www.youtube.com/watch?v=YFbCaahCWQ0"
        assert expected_output == output

    def test_message_extractor_hangout_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        element_resolver = ElementTransformerOps("video", "hangout")
        response = element_resolver.message_extractor(input_json, "video")
        output = response.get("data")
        expected_output = "https://www.youtube.com/watch?v=YFbCaahCWQ0"
        assert expected_output == output

    def test_message_extractor_messenger_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter
        messenger = MessengerResponseConverter("link", "messenger")
        response = messenger.message_extractor(input_json, "video")
        output = response.get("data")
        expected_output = "https://www.youtube.com/watch?v=YFbCaahCWQ0"
        assert expected_output == output

    def test_message_extractor_whatsapp_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
        whatsapp = WhatsappResponseConverter("link", "messenger")
        response = whatsapp.message_extractor(input_json, "video")
        output = response.get("data")
        expected_output = "https://www.youtube.com/watch?v=YFbCaahCWQ0"
        assert expected_output == output

    def test_message_extractor_telegram_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        from kairon.chat.converters.channels.telegram import TelegramResponseConverter
        telegram = TelegramResponseConverter("video", "telegram")
        response = telegram.message_extractor(input_json, "video")
        output = response.get("data")
        expected_output = "https://www.youtube.com/watch?v=YFbCaahCWQ0"
        assert expected_output == output

    def test_video_transformer_hangout_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        elementops = ElementTransformerOps("video", "hangout")
        response = elementops.video_transformer(input_json)
        expected_output = {"text": "https://www.youtube.com/watch?v=YFbCaahCWQ0"}
        assert expected_output == response

    def test_save_and_publish_auditlog_action_save(self, monkeypatch):
        def publish_auditlog(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "publish_auditlog", publish_auditlog)
        bot = "tests"
        user = "testuser"
        event_config = EventConfig(bot=bot,
                                   user=user,
                                   ws_url="http://localhost:5000/event_url")
        kwargs = {"action": "save"}
        Utility.save_and_publish_auditlog(event_config, "EventConfig", **kwargs)
        count = AuditLogData.objects(bot=bot, user=user, action="save").count()
        assert count == 1

    def test_save_and_publish_auditlog_action_save_another(self, monkeypatch):
        def publish_auditlog(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "publish_auditlog", publish_auditlog)
        bot = "tests"
        user = "testuser"
        event_config = EventConfig(bot=bot,
                                   user=user,
                                   ws_url="http://localhost:5000/event_url",
                                   headers="{'Autharization': '123456789'}",
                                   method="GET")
        kwargs = {"action": "save"}
        Utility.save_and_publish_auditlog(event_config, "EventConfig", **kwargs)
        count = AuditLogData.objects(bot=bot, user=user, action="save").count()
        assert count == 2

    def test_save_and_publish_auditlog_action_update(self, monkeypatch):
        def publish_auditlog(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "publish_auditlog", publish_auditlog)
        bot = "tests"
        user = "testuser"
        event_config = EventConfig(bot=bot,
                                   user=user,
                                   ws_url="http://localhost:5000/event_url",
                                   headers="{'Autharization': '123456789'}")
        kwargs = {"action": "update"}
        Utility.save_and_publish_auditlog(event_config, "EventConfig", **kwargs)
        count = AuditLogData.objects(bot=bot, user=user, action="update").count()
        assert count == 1

    def test_save_and_publish_auditlog_total_count(self, monkeypatch):
        def publish_auditlog(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "publish_auditlog", publish_auditlog)
        bot = "tests"
        user = "testuser"
        event_config = EventConfig(bot=bot,
                                   user=user,
                                   ws_url="http://localhost:5000/event_url",
                                   headers="{'Autharization': '123456789'}")
        kwargs = {"action": "update"}
        Utility.save_and_publish_auditlog(event_config, "EventConfig", **kwargs)
        count = AuditLogData.objects(bot=bot, user=user).count()
        assert count >= 3

    def test_save_and_publish_auditlog_total_count_with_event_url(self, monkeypatch):
        def execute_http_request(*args, **kwargs):
            return None
        monkeypatch.setattr(Utility, "execute_http_request", execute_http_request)
        bot = "tests"
        user = "testuser"
        event_config = EventConfig(bot=bot,
                                   user=user,
                                   ws_url="http://localhost:5000/event_url",
                                   headers="{'Autharization': '123456789'}")
        kwargs = {"action": "update"}
        Utility.save_and_publish_auditlog(event_config, "EventConfig", **kwargs)
        count = AuditLogData.objects(bot=bot, user=user).count()
        assert count >= 3

    def test_positive_case(self):
        result = AugmentationUtils.generate_synonym("good")
        assert len(result) == 3 and "good" not in result

    def test_positive_case_with_6_synonyms(self):
        result = AugmentationUtils.generate_synonym("good", 6)
        assert len(result) == 6 and "good" not in result

    def test_empty_case(self):
        result = AugmentationUtils.generate_synonym("")
        assert result == []

    def test_more_synonyms(self):
        result = AugmentationUtils.generate_synonym("good", 100)
        assert len(result) >= 1 and "good" not in result