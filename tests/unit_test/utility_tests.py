import glob
import os
import shutil
import tempfile
from datetime import datetime
from io import BytesIO
import pytest
from fastapi import UploadFile
from mongoengine import connect

from kairon.exceptions import AppException
from kairon.utils import Utility


class TestUtility:

    @pytest.fixture(autouse=True, scope="session")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment["database"]['url'])
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
        bot_data_home_dir = os.path.join(tempfile.mkdtemp(), str(datetime.now()))
        shutil.copytree('tests/testing_data/yml_training_files', bot_data_home_dir)
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_files"
        shutil.rmtree(bot_data_home_dir)

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
        os.remove(zip_file+'.zip')

    @pytest.fixture()
    def resource_unzip_and_validate_exception(self):
        data_path = 'tests/testing_data/yml_training_files/data'
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.make_archive(zip_file, 'zip', data_path)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_unzip_and_validate_exception"
        os.remove(zip_file+'.zip')

    @pytest.fixture()
    def resource_validate_no_training_files_delete_dir(self):
        bot_data_home_dir = tempfile.mkdtemp()
        os.mkdir(os.path.join(bot_data_home_dir, 'data'))
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_no_training_files_delete_dir"

    @pytest.fixture()
    def resource_save_and_validate_training_files(self):
        config_path = 'tests/testing_data/yml_training_files/config.yml'
        domain_path = 'tests/testing_data/yml_training_files/domain.yml'
        nlu_path = 'tests/testing_data/yml_training_files/data/nlu.yml'
        stories_path = 'tests/testing_data/yml_training_files/data/stories.yml'
        http_action_path = 'tests/testing_data/yml_training_files/http_action.yml'
        rules_path = 'tests/testing_data/yml_training_files/data/rules.yml'
        pytest.config = UploadFile(filename="config.yml", file=BytesIO(open(config_path, 'rb').read()))
        pytest.domain = UploadFile(filename="domain.yml", file=BytesIO(open(domain_path, 'rb').read()))
        pytest.nlu = UploadFile(filename="nlu.yml", file=BytesIO(open(nlu_path, 'rb').read()))
        pytest.stories = UploadFile(filename="stories.yml", file=BytesIO(open(stories_path, 'rb').read()))
        pytest.http_actions = UploadFile(filename="http_action.yml", file=BytesIO(open(http_action_path, 'rb').read()))
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
        http_action = UploadFile(filename="http_action.yml", file=BytesIO(http_action_content))
        training_file_loc = await Utility.save_training_files(nlu, domain, config, stories, rules, http_action)
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
        training_file_loc = await Utility.save_training_files(nlu, domain, config, stories, None)
        assert os.path.exists(training_file_loc['nlu'])
        assert os.path.exists(training_file_loc['config'])
        assert os.path.exists(training_file_loc['stories'])
        assert os.path.exists(training_file_loc['domain'])
        assert not training_file_loc.get('rules')
        assert not training_file_loc.get('http_action')
        assert os.path.exists(training_file_loc['root'])

    @pytest.mark.asyncio
    async def test_write_training_data(self):
        from kairon.data_processor.processor import MongoProcessor
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
        from kairon.data_processor.processor import MongoProcessor
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
        path = 'tests/testing_data/yml_training_files/http_action.yml'
        content = Utility.read_yaml(path)
        assert len(content['http_actions']) == 5

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
        path = os.path.join(pytest.temp_path, str(datetime.now()))
        Utility.make_dirs(path)
        assert os.path.exists(path)

    def test_make_dirs_exception(self, resource_make_dirs):
        assert os.path.exists(pytest.temp_path)
        with pytest.raises(AppException) as e:
            Utility.make_dirs(pytest.temp_path, True)
        assert str(e).__contains__('Directory exists!')

    def test_make_dirs_path_already_exists(self, resource_make_dirs):
        assert os.path.exists(pytest.temp_path)
        assert not Utility.make_dirs(pytest.temp_path)

    def test_validate_files(self, resource_validate_files):
        assert not Utility.validate_files(pytest.bot_data_home_dir)

    def test_get_interpreter_with_no_model(self):
        actual = Utility.get_interpreter("test.tar.gz")
        assert actual is None

    def test_delete_old_models(self):
        folder = "models/tests"
        file = Utility.get_latest_file(folder)
        Utility.move_old_models(folder, file)
        assert len(list(glob.glob(folder+'/*.tar.gz'))) == 1

    def test_validate_path_not_found(self):
        with pytest.raises(AppException):
            Utility.validate_files('/tests/path_not_found')

    def test_validate_no_files(self, resource_validate_no_training_files):
        with pytest.raises(AppException):
            Utility.validate_files(pytest.bot_data_home_dir)
        assert os.path.exists(pytest.bot_data_home_dir)

    def test_validate_no_files_delete_dir(self, resource_validate_no_training_files_delete_dir):
        with pytest.raises(AppException):
            Utility.validate_files(pytest.bot_data_home_dir, True)
        assert not os.path.exists(pytest.bot_data_home_dir)

    @pytest.mark.asyncio
    async def test_unzip_and_validate(self, resource_unzip_and_validate):
        assert not await Utility.unzip_and_validate(pytest.bot, pytest.zip)

    @pytest.mark.asyncio
    async def test_unzip_and_validate_exception(self, resource_unzip_and_validate_exception):
        with pytest.raises(AppException):
            await Utility.unzip_and_validate(pytest.bot, pytest.zip)

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_zip(self, resource_unzip_and_validate):
        assert not await Utility.save_and_validate_training_files(pytest.bot, [pytest.zip])

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_no_files_received(self):
        with pytest.raises(AppException) as e:
            await Utility.save_and_validate_training_files(pytest.bot, [])
        assert str(e).__contains__("No files received!")

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files(self, resource_save_and_validate_training_files):
        training_files = [pytest.config, pytest.domain, pytest.nlu, pytest.stories, pytest.rules, pytest.http_actions]
        assert not await Utility.save_and_validate_training_files(pytest.bot, training_files)

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_no_rules_and_http_actions(self, resource_save_and_validate_training_files):
        training_files = [pytest.config, pytest.domain, pytest.nlu, pytest.stories]
        assert not await Utility.save_and_validate_training_files(pytest.bot, training_files)

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_invalid(self, resource_save_and_validate_training_files):
        training_files = [pytest.config, pytest.domain, pytest.non_nlu, pytest.stories]
        with pytest.raises(AppException):
            await Utility.save_and_validate_training_files(pytest.bot, training_files)
