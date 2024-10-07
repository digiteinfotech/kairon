import os
import re
import shutil
import tempfile
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from unittest.mock import patch, MagicMock
from urllib.parse import urlencode
from kairon.shared.utils import Utility, MailUtility

Utility.load_system_metadata()

import numpy as np
import pandas as pd
import pytest
import requests
import responses
import ujson as json
from fastapi import UploadFile
from mongoengine import connect
from mongoengine.queryset.visitor import Q
from password_strength.tests import Special, Uppercase, Numbers, Length
from rasa.shared.core.constants import RULE_SNIPPET_ACTION_NAME
from rasa.shared.core.events import UserUttered, ActionExecuted
from rasa.shared.core.training_data.structures import StoryStep, Checkpoint, RuleStep
from websockets import InvalidStatusCode

from kairon.chat.converters.channels.response_factory import ConverterFactory
from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
from kairon.chat.converters.channels.telegram import TelegramResponseConverter
from kairon.exceptions import AppException
from kairon.shared.augmentation.utils import AugmentationUtils
from kairon.shared.constants import GPT3ResourceTypes, LLMResourceProvider
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.audit.processor import AuditDataProcessor
from kairon.shared.data.constant import DEFAULT_SYSTEM_PROMPT, STORY_EVENT
from kairon.shared.data.data_objects import EventConfig, Slots, LLMSettings, DemoRequestLogs
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.utils import DataUtility
from kairon.shared.models import TemplateType
from kairon.shared.verification.email import QuickEmailVerification


class TestUtility:
    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_email_configuration()
        connect(
            **Utility.mongoengine_connection(Utility.environment["database"]["url"])
        )
        pytest.bot = "test"
        yield None
        shutil.rmtree(os.path.join("training_data", pytest.bot))

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
        shutil.copytree("tests/testing_data/yml_training_files", bot_data_home_dir)
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_files"
        shutil.rmtree(tmp_dir)

    @pytest.fixture()
    def resource_validate_no_training_files(self):
        bot_data_home_dir = tempfile.mkdtemp()
        os.mkdir(os.path.join(bot_data_home_dir, "data"))
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_no_training_files"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_unzip_and_validate(self):
        data_path = "tests/testing_data/yml_training_files"
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, "test")
        shutil.make_archive(zip_file, "zip", data_path)
        pytest.zip = UploadFile(
            filename="test.zip", file=BytesIO(open(zip_file + ".zip", "rb").read())
        )
        yield "resource_unzip_and_validate"
        os.remove(zip_file + ".zip")

    def test_copy_model_file_to_directory(self):
        input_file_path = "tests/testing_data/model/20210512-172208.tar.gz"
        output_path = "tests/testing_data/test_dir"

        if os.path.exists(output_path):
            shutil.rmtree(output_path)

        model_file = Utility.copy_model_file_to_directory(input_file_path, output_path)

        copied_file_path = os.path.join(output_path, model_file)
        assert os.path.exists(copied_file_path)
        assert os.path.isfile(copied_file_path)
        shutil.rmtree(output_path)

    @pytest.fixture()
    def resource_unzip_and_validate_exception(self):
        data_path = "tests/testing_data/yml_training_files/data"
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, "test")
        shutil.make_archive(zip_file, "zip", data_path)
        pytest.zip = UploadFile(
            filename="test.zip", file=BytesIO(open(zip_file + ".zip", "rb").read())
        )
        yield "resource_unzip_and_validate_exception"
        os.remove(zip_file + ".zip")

    @pytest.fixture()
    def resource_validate_no_training_files_delete_dir(self):
        bot_data_home_dir = tempfile.mkdtemp()
        os.mkdir(os.path.join(bot_data_home_dir, "data"))
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_no_training_files_delete_dir"

    @pytest.fixture()
    def resource_validate_only_stories_and_nlu(self):
        bot_data_home_dir = tempfile.mkdtemp()
        shutil.copytree(
            "tests/testing_data/yml_training_files/data/",
            os.path.join(bot_data_home_dir, "data"),
        )
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_only_stories_and_nlu"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_validate_only_http_actions(self):
        bot_data_home_dir = tempfile.mkdtemp()
        shutil.copy2(
            "tests/testing_data/yml_training_files/actions.yml", bot_data_home_dir
        )
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_only_http_actions"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_validate_only_multiflow_stories(self):
        bot_data_home_dir = tempfile.mkdtemp()
        shutil.copy2(
            "tests/testing_data/yml_training_files/multiflow_stories.yml",
            bot_data_home_dir,
        )
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_validate_only_multiflow_stories"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_validate_only_domain(self):
        bot_data_home_dir = tempfile.mkdtemp()
        shutil.copy2(
            "tests/testing_data/yml_training_files/domain.yml", bot_data_home_dir
        )
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_resource_validate_only_domain"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_validate_only_config(self):
        bot_data_home_dir = tempfile.mkdtemp()
        shutil.copy2(
            "tests/testing_data/yml_training_files/config.yml", bot_data_home_dir
        )
        pytest.bot_data_home_dir = bot_data_home_dir
        yield "resource_resource_validate_only_config"
        shutil.rmtree(bot_data_home_dir)

    @pytest.fixture()
    def resource_save_and_validate_training_files(self):
        config_path = "tests/testing_data/yml_training_files/config.yml"
        domain_path = "tests/testing_data/yml_training_files/domain.yml"
        nlu_path = "tests/testing_data/yml_training_files/data/nlu.yml"
        stories_path = "tests/testing_data/yml_training_files/data/stories.yml"
        http_action_path = "tests/testing_data/yml_training_files/actions.yml"
        rules_path = "tests/testing_data/yml_training_files/data/rules.yml"
        pytest.config = UploadFile(
            filename="config.yml", file=BytesIO(open(config_path, "rb").read())
        )
        pytest.domain = UploadFile(
            filename="domain.yml", file=BytesIO(open(domain_path, "rb").read())
        )
        pytest.nlu = UploadFile(
            filename="nlu.yml", file=BytesIO(open(nlu_path, "rb").read())
        )
        pytest.stories = UploadFile(
            filename="stories.yml", file=BytesIO(open(stories_path, "rb").read())
        )
        pytest.http_actions = UploadFile(
            filename="actions.yml", file=BytesIO(open(http_action_path, "rb").read())
        )
        pytest.rules = UploadFile(
            filename="rules.yml", file=BytesIO(open(rules_path, "rb").read())
        )
        pytest.non_nlu = UploadFile(
            filename="non_nlu.yml", file=BytesIO(open(rules_path, "rb").read())
        )
        yield "resource_save_and_validate_training_files"

    @pytest.mark.asyncio
    async def test_save_training_files(self):
        nlu_content = "## intent:greet\n- hey\n- hello".encode()
        stories_content = (
            "## greet\n* greet\n- utter_offer_help\n- action_restart".encode()
        )
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        rules_content = "rules:\n\n- rule: Only say `hello` if the user provided a location\n  condition:\n  - slot_was_set:\n    - location: true\n  steps:\n  - intent: greet\n  - action: utter_greet\n".encode()
        http_action_content = "http_actions:\n- action_name: action_performanceUsers1000@digite.com\n  auth_token: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  http_url: http://www.alphabet.com\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response: json\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        rules = UploadFile(filename="rules.yml", file=BytesIO(rules_content))
        http_action = UploadFile(
            filename="actions.yml", file=BytesIO(http_action_content)
        )
        training_file_loc = await DataUtility.save_training_files(
            nlu, domain, config, stories, rules, http_action
        )
        assert os.path.exists(training_file_loc["nlu"])
        assert os.path.exists(training_file_loc["config"])
        assert os.path.exists(training_file_loc["stories"])
        assert os.path.exists(training_file_loc["domain"])
        assert os.path.exists(training_file_loc["rules"])
        assert os.path.exists(training_file_loc["http_action"])
        assert os.path.exists(training_file_loc["root"])

    def test_read_faq_csv(self):
        content = "Question, Response\nWhat is Digite?, IT Company\n".encode()
        file = UploadFile(filename="file.csv", file=BytesIO(content))
        df = Utility.read_faq(file)
        assert not df.empty

    def test_read_faq_xlsx(self):
        content = "Question, Response\nWhat is Digite?, IT Company\n".encode()
        file = UploadFile(
            filename="upload.xlsx",
            file=(open("tests/testing_data/upload_faq/upload.xlsx", "rb")),
        )
        df = Utility.read_faq(file)
        assert not df.empty

    def test_read_faq_invalid(self):
        content = "How are you?".encode()
        file = UploadFile(filename="file.arff", file=BytesIO(content))
        with pytest.raises(AppException, match="Invalid file type!"):
            Utility.read_faq(file)

    def test_save_faq_training_files_none(self):
        with pytest.raises(
            AppException,
            match="Invalid file type! Only csv and xlsx files are supported.",
        ):
            Utility.validate_faq_training_file([])

        with pytest.raises(
            AppException,
            match="Invalid file type! Only csv and xlsx files are supported.",
        ):
            Utility.validate_faq_training_file(None)

    def test_validate_faq_training_file(self):
        content = "Question, Response\nWhat is Digite?, IT Company\n".encode()
        file = UploadFile(filename="file.csv", file=BytesIO(content))
        required_headers = {"questions", "answer"}
        with pytest.raises(
            AppException,
            match=f"Required columns {required_headers} not present in file.",
        ):
            Utility.validate_faq_training_file(file)

    def test_save_faq_training_files_csv(self):
        csv_content = "Question, Answer,\nWhat is Digite?, IT Company\n".encode()
        file = UploadFile(filename="abc.csv", file=BytesIO(csv_content))
        bot_data_home_dir = Utility.save_faq_training_files(pytest.bot, file)
        assert os.path.exists(os.path.join(bot_data_home_dir, file.filename))

    def test_save_faq_training_files_xlsx(self):
        xlsx_content = "Question, Answer,\nWhat is Digite?, IT Company\n".encode()
        file = UploadFile(filename="abc.xlsx", file=BytesIO(xlsx_content))
        bot_data_home_dir = Utility.save_faq_training_files(pytest.bot, file)
        assert os.path.exists(os.path.join(bot_data_home_dir, file.filename))

    def test_get_duplicate_values(self):
        df = pd.read_csv("tests/testing_data/upload_faq/validate.csv")
        column_name = "Questions"
        duplicates = DataUtility.get_duplicate_values(df, column_name)
        assert duplicates == {"What day is it?"}
        column_name = "Answer"
        duplicates = DataUtility.get_duplicate_values(df, column_name)
        assert duplicates == {" Indeed it is!", " It is Thursday"}

    def test_get_duplicate_values_empty(self):
        content = "Questions, Answer\n ".encode()
        file = UploadFile(filename="filename.csv", file=BytesIO(content))
        with pytest.raises(AppException, match="No data found in the file!"):
            Utility.validate_faq_training_file(file)

    def test_get_keywords(self):
        paragraph = "What is Digite?"
        raise_err = False
        token = AugmentationUtils.get_keywords(paragraph)
        assert Utility.check_empty_string(token[0][0]) == False

    def test_check_character_limit_success(self):
        name = "supercalifragilisticexpialidociousalwaysworks"
        result = Utility.check_character_limit(value=name)
        assert result is True

    def test_check_character_limit_failure(self):
        name = "supercalifragilisticexpialidociousalwaysworksmorethan60characters"
        result = Utility.check_character_limit(value=name)
        assert result is False

    @pytest.mark.asyncio
    async def test_upload_and_save(self):
        nlu_content = "## intent:greet\n- hey\n- hello".encode()
        stories_content = (
            "## greet\n* greet\n- utter_offer_help\n- action_restart".encode()
        )
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.yml", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        training_file_loc = await DataUtility.save_training_files(
            nlu, domain, config, stories, None
        )
        assert os.path.exists(training_file_loc["nlu"])
        assert os.path.exists(training_file_loc["config"])
        assert os.path.exists(training_file_loc["stories"])
        assert os.path.exists(training_file_loc["domain"])
        assert not training_file_loc.get("rules")
        assert not training_file_loc.get("http_action")
        assert os.path.exists(training_file_loc["root"])

    @pytest.mark.asyncio
    async def test_write_training_data(self):
        from kairon.shared.data.processor import MongoProcessor

        processor = MongoProcessor()
        await (
            processor.save_from_path(
                "./tests/testing_data/yml_training_files",
                bot="test_load_from_path_yml_training_files",
                user="testUser",
            )
        )
        training_data = processor.load_nlu("test_load_from_path_yml_training_files")
        story_graph = processor.load_stories("test_load_from_path_yml_training_files")
        domain = processor.load_domain("test_load_from_path_yml_training_files")
        config = processor.load_config("test_load_from_path_yml_training_files")
        http_action = processor.load_http_action(
            "test_load_from_path_yml_training_files"
        )
        training_data_path = Utility.write_training_data(
            training_data, domain, config, story_graph, None, http_action
        )
        multiflow_stories = processor.load_multiflow_stories_yaml(
            "test_load_from_path_yml_training_files"
        )
        training_data_path = Utility.write_training_data(
            training_data,
            domain,
            config,
            story_graph,
            None,
            http_action,
            None,
            multiflow_stories,
        )
        assert os.path.exists(training_data_path)

    def test_write_training_data_with_rules(self):
        from kairon.shared.data.processor import MongoProcessor

        processor = MongoProcessor()
        training_data = processor.load_nlu("test_load_from_path_yml_training_files")
        story_graph = processor.load_stories("test_load_from_path_yml_training_files")
        domain = processor.load_domain("test_load_from_path_yml_training_files")
        config = processor.load_config("test_load_from_path_yml_training_files")
        http_action = processor.load_http_action(
            "test_load_from_path_yml_training_files"
        )
        rules = processor.get_rules_for_training(
            "test_load_from_path_yml_training_files"
        )
        training_data_path = Utility.write_training_data(
            training_data, domain, config, story_graph, rules, http_action
        )
        assert os.path.exists(training_data_path)

    def test_read_yaml(self):
        path = "tests/testing_data/yml_training_files/actions.yml"
        content = Utility.read_yaml(path)
        assert len(content["http_action"]) == 5

    def test_read_yaml_multiflow_story(self):
        path = "tests/testing_data/yml_training_files/multiflow_stories.yml"
        content = Utility.read_yaml(path)
        assert len(content["multiflow_story"]) == 1

    def test_read_yaml_not_found_exception(self):
        path = "tests/testing_data/yml_training_files/path_not_found.yml"
        with pytest.raises(AppException):
            Utility.read_yaml(path, True)

    def test_read_yaml_not_found(self):
        path = "tests/testing_data/yml_training_files/path_not_found.yml"
        assert not Utility.read_yaml(path, False)

    def test_replace_file_name(self):
        msg = "Invalid /home/digite/kairon/domain.yaml:\n Error found in /home/digite/kairon/domain.yaml at line 6"
        output = Utility.replace_file_name(msg, "/home")
        assert output == "Invalid domain.yaml:\n Error found in domain.yaml at line 6"

    def test_replace_file_name_key_not_in_msg(self):
        msg = "Invalid domain.yaml:\n Error found in domain.yaml at line 6"
        output = Utility.replace_file_name(msg, "/home")
        assert output == "Invalid domain.yaml:\n Error found in domain.yaml at line 6"

    def test_make_dirs(self, resource_make_dirs):
        path = os.path.join(pytest.temp_path, str(uuid.uuid4()))
        Utility.make_dirs(path)
        assert os.path.exists(path)

    def test_get_action_url(self, monkeypatch):
        actual = Utility.get_action_url({})
        assert actual.url == "http://kairon.localhost:5055/webhook"
        actual = Utility.get_action_url(
            {"action_endpoint": {"url": "http://action-server:5055/webhook"}}
        )
        assert actual.url == "http://action-server:5055/webhook"
        monkeypatch.setitem(Utility.environment["action"], "url", None)
        actual = Utility.get_action_url({})
        assert actual is None

    def test_make_dirs_exception(self, resource_make_dirs):
        assert os.path.exists(pytest.temp_path)
        with pytest.raises(AppException) as e:
            Utility.make_dirs(pytest.temp_path, True)
        assert str(e).__contains__("Directory exists!")

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

    def test_validate_files(self, resource_validate_files):
        requirements = DataUtility.validate_and_get_requirements(
            pytest.bot_data_home_dir
        )
        assert not requirements

    def test_validate_path_not_found(self):
        with pytest.raises(AppException):
            DataUtility.validate_and_get_requirements("/tests/path_not_found")

    def test_validate_no_files(self, resource_validate_no_training_files):
        with pytest.raises(AppException):
            DataUtility.validate_and_get_requirements(pytest.bot_data_home_dir)
        assert os.path.exists(pytest.bot_data_home_dir)

    def test_validate_no_files_delete_dir(
        self, resource_validate_no_training_files_delete_dir
    ):
        with pytest.raises(AppException):
            DataUtility.validate_and_get_requirements(pytest.bot_data_home_dir, True)
        assert not os.path.exists(pytest.bot_data_home_dir)

    def test_validate_only_stories_and_nlu(
        self, resource_validate_only_stories_and_nlu
    ):
        requirements = DataUtility.validate_and_get_requirements(
            pytest.bot_data_home_dir, True
        )
        assert {
            "actions",
            "config",
            "domain",
            "chat_client_config",
            "multiflow_stories",
            "bot_content",
        } == requirements

    def test_validate_only_http_actions(self, resource_validate_only_http_actions):
        requirements = DataUtility.validate_and_get_requirements(
            pytest.bot_data_home_dir, True
        )
        assert {
            "rules",
            "domain",
            "config",
            "stories",
            "nlu",
            "chat_client_config",
            "multiflow_stories",
            "bot_content",
        } == requirements

    def test_validate_only_multiflow_stories(
        self, resource_validate_only_multiflow_stories
    ):
        requirements = DataUtility.validate_and_get_requirements(
            pytest.bot_data_home_dir, True
        )
        assert {
            "actions",
            "config",
            "stories",
            "chat_client_config",
            "nlu",
            "rules",
            "domain",
            "bot_content",
        } == requirements

    def test_validate_only_domain(self, resource_validate_only_domain):
        requirements = DataUtility.validate_and_get_requirements(
            pytest.bot_data_home_dir, True
        )
        assert {
            "rules",
            "actions",
            "config",
            "stories",
            "nlu",
            "chat_client_config",
            "multiflow_stories",
            "bot_content",
        } == requirements

    def test_validate_only_config(self, resource_validate_only_config):
        requirements = DataUtility.validate_and_get_requirements(
            pytest.bot_data_home_dir, True
        )
        assert {
            "rules",
            "actions",
            "domain",
            "stories",
            "nlu",
            "chat_client_config",
            "multiflow_stories",
            "bot_content",
        } == requirements

    @pytest.mark.asyncio
    async def test_unzip_and_validate(self, resource_unzip_and_validate):
        unzip_path = await DataUtility.save_training_files_as_zip(
            pytest.bot, pytest.zip
        )
        assert os.path.exists(unzip_path)

    @pytest.mark.asyncio
    async def test_unzip_and_validate_exception(
        self, resource_unzip_and_validate_exception
    ):
        unzip_path = await DataUtility.save_training_files_as_zip(
            pytest.bot, pytest.zip
        )
        assert os.path.exists(unzip_path)

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_zip(
        self, resource_unzip_and_validate
    ):
        bot_data_home_dir = await DataUtility.save_uploaded_data(
            pytest.bot, [pytest.zip]
        )
        assert os.path.exists(os.path.join(bot_data_home_dir, "domain.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "data", "nlu.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "data", "rules.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "data", "stories.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "config.yml"))

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_no_files_received(self):
        with pytest.raises(AppException) as e:
            await DataUtility.save_uploaded_data(pytest.bot, [])
        assert str(e).__contains__("No files received!")

        with pytest.raises(AppException) as e:
            await DataUtility.save_uploaded_data(pytest.bot, None)
        assert str(e).__contains__("No files received!")

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_2_files_only(
        self, resource_save_and_validate_training_files
    ):
        bot_data_home_dir = await DataUtility.save_uploaded_data(
            pytest.bot, [pytest.domain, pytest.nlu]
        )
        assert os.path.exists(os.path.join(bot_data_home_dir, "domain.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "data", "nlu.yml"))

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files(
        self, resource_save_and_validate_training_files
    ):
        training_files = [
            pytest.config,
            pytest.domain,
            pytest.nlu,
            pytest.stories,
            pytest.rules,
            pytest.http_actions,
        ]
        bot_data_home_dir = await DataUtility.save_uploaded_data(
            pytest.bot, training_files
        )
        assert os.path.exists(os.path.join(bot_data_home_dir, "domain.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "data", "nlu.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "config.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "data", "stories.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "actions.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "data", "rules.yml"))

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_no_rules_and_http_actions(
        self, resource_save_and_validate_training_files
    ):
        training_files = [pytest.config, pytest.domain, pytest.nlu, pytest.stories]
        bot_data_home_dir = await DataUtility.save_uploaded_data(
            pytest.bot, training_files
        )
        assert os.path.exists(os.path.join(bot_data_home_dir, "domain.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "data", "nlu.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "config.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "data", "stories.yml"))

    @pytest.mark.asyncio
    async def test_save_and_validate_training_files_invalid(
        self, resource_save_and_validate_training_files
    ):
        training_files = [pytest.config, pytest.domain, pytest.non_nlu, pytest.stories]
        bot_data_home_dir = await DataUtility.save_uploaded_data(
            pytest.bot, training_files
        )
        assert not os.path.exists(
            os.path.join(bot_data_home_dir, "data", "non_nlu.yml")
        )
        assert not os.path.exists(os.path.join(bot_data_home_dir, "non_nlu.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "domain.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "config.yml"))
        assert os.path.exists(os.path.join(bot_data_home_dir, "data", "stories.yml"))

    def test_build_event_request(self):
        request = {"BOT": "mood_bot", "USER": "bot_user"}
        request_body = Utility.build_lambda_payload(request)
        assert isinstance(request_body, list)
        assert request_body[0]["name"] == "BOT"
        assert request_body[0]["value"] == "mood_bot"
        assert request_body[1]["name"] == "USER"
        assert request_body[1]["value"] == "bot_user"
        assert len(request_body) == 2

    def test_build_event_request_empty(self):
        request_body = Utility.build_lambda_payload({})
        assert isinstance(request_body, list)
        assert not request_body

    def test_download_csv(self):
        file_path, temp_path = Utility.download_csv([{"test": "test_val"}], None)
        assert file_path.endswith(".csv")
        assert "tmp" in str(temp_path).lower()

    def test_download_csv_error_message(self):
        with pytest.raises(AppException) as e:
            Utility.download_csv([], "error_message")
        assert str(e).__contains__("error_message")

    def test_extract_db_config_without_login(self):
        config = Utility.extract_db_config("mongodb://localhost/test")
        assert config["db"] == "test"
        assert config["username"] is None
        assert config["password"] is None
        assert config["host"] == "mongodb://localhost"
        assert len(config["options"]) == 0

    def test_extract_db_config_with_login(self):
        config = Utility.extract_db_config(
            "mongodb://admin:admin@localhost/test?authSource=admin"
        )
        assert config["db"] == "test"
        assert config["username"] == "admin"
        assert config["password"] == "admin"
        assert config["host"] == "mongodb://localhost"
        assert "authSource" in config["options"]

    def test_get_event_server_url_not_found(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["events"], "server_url", None)
        with pytest.raises(AppException, match="Event server url not found"):
            Utility.get_event_server_url()

    def test_get_event_server_url(self):
        assert Utility.get_event_server_url() == "http://localhost:5001"

    def test_is_model_file_exists(self):
        assert not Utility.is_model_file_exists("invalid_bot", False)
        with pytest.raises(
            AppException, match="No model trained yet. Please train a model to test"
        ):
            Utility.is_model_file_exists("invalid_bot")

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_password_reset(self, validate_and_send_mail_mock):
        mail_type = "password_reset"
        email = "sampletest@gmail.com"
        first_name = "sample"

        Utility.email_conf["email"]["templates"]["password_reset"] = (
            open("template/emails/passwordReset.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"]["password_reset"]
        base_url = Utility.environment["app"]["frontend_url"]
        expected_body = (
            expected_body.replace("FIRST_NAME", first_name.capitalize())
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "password_reset_subject"
        ]

        await MailUtility.format_and_send_mail(
            mail_type=mail_type, email=email, first_name=first_name
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_password_reset_confirmation(
        self, validate_and_send_mail_mock
    ):
        mail_type = "password_reset_confirmation"
        email = "sampletest@gmail.com"
        first_name = "sample"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["password_reset_confirmation"] = (
            open("template/emails/passwordResetConfirmation.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"][
            "password_reset_confirmation"
        ]
        expected_body = expected_body.replace("FIRST_NAME", first_name).replace(
            "USER_EMAIL", email
        ).replace("BASE_URL", base_url)
        expected_subject = Utility.email_conf["email"]["templates"][
            "password_changed_subject"
        ]

        await MailUtility.format_and_send_mail(
            mail_type=mail_type, email=email, first_name=first_name
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_verification(self, validate_and_send_mail_mock):
        mail_type = "verification"
        email = "sampletest@gmail.com"
        first_name = "sample"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["verification"] = (
            open("template/emails/verification.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"]["verification"]
        expected_body = (
            expected_body.replace("FIRST_NAME", first_name.capitalize())
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "confirmation_subject"
        ]
        await MailUtility.format_and_send_mail(
            mail_type=mail_type, email=email, first_name=first_name
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_verification_confirmation(self, validate_and_send_mail_mock):
        mail_type = "verification_confirmation"
        email = "sampletest@gmail.com"
        first_name = "sample"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["verification_confirmation"] = (
            open("template/emails/verificationConfirmation.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"][
            "verification_confirmation"
        ]
        expected_body = (
            expected_body.replace("FIRST_NAME", first_name.capitalize())
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
        )
        expected_subject = Utility.email_conf["email"]["templates"]["confirmed_subject"]

        await MailUtility.format_and_send_mail(
            mail_type=mail_type, email=email, first_name=first_name
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_add_member(self, validate_and_send_mail_mock):
        mail_type = "add_member"
        email = "sampletest@gmail.com"
        first_name = "sample"
        url = "https://www.testurl.com"
        bot_name = "test_bot"
        role = "test_role"
        accessor_name = "buddy"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["add_member_invitation"] = (
            open("template/emails/memberAddAccept.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"][
            "add_member_invitation"
        ]
        expected_body = (
            expected_body.replace("BOT_NAME", bot_name)
            .replace("BOT_OWNER_NAME", first_name.capitalize())
            .replace("ACCESS_TYPE", role)
            .replace("ACCESS_URL", url)
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("VERIFICATION_LINK", url)
            .replace("BASE_URL", base_url)
            .replace("INVITED_PERSON_NAME", accessor_name)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "add_member_subject"
        ]
        expected_subject = expected_subject.replace("BOT_NAME", bot_name)

        await MailUtility.format_and_send_mail(
            mail_type=mail_type,
            email=email,
            first_name=first_name,
            url=url,
            bot_name=bot_name,
            role=role,
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_add_member_confirmation(self, validate_and_send_mail_mock):
        mail_type = "add_member_confirmation"
        email = "sampletest@gmail.com"
        accessor_name = "sample"
        bot_name = "test_bot"
        role = "test_role"
        accessor_email = "test@gmail.com"
        member_confirm = "test_name"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["add_member_confirmation"] = (
            open("template/emails/memberAddConfirmation.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"][
            "add_member_confirmation"
        ]
        expected_body = (
            expected_body.replace("BOT_NAME", bot_name)
            .replace("ACCESS_TYPE", role)
            .replace("INVITED_PERSON_NAME", accessor_name.capitalize())
            .replace("FIRST_NAME", member_confirm)
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "add_member_confirmation_subject"
        ]
        expected_subject = expected_subject.replace(
            "INVITED_PERSON_NAME", accessor_name.capitalize()
        )

        await MailUtility.format_and_send_mail(
            mail_type=mail_type,
            email=email,
            bot_name=bot_name,
            role=role,
            first_name=member_confirm,
            accessor_email=accessor_email,
            member_confirm=member_confirm,
            accessor_name=accessor_name
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_update_role_member_mail(self, validate_and_send_mail_mock):
        mail_type = "update_role_member_mail"
        email = "sampletest@gmail.com"
        first_name = "sample"
        bot_name = "test_bot"
        new_role = "test_role"
        status = "test_status"
        modifier_name = "test_name"
        member_name = "test_name"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["update_role"] = (
            open("template/emails/memberUpdateRole.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"]["update_role"]
        expected_body = (
            expected_body.replace(
                "MAIL_BODY_HERE",
                Utility.email_conf["email"]["templates"][
                    "update_role_member_mail_body"
                ],
            )
            .replace("BOT_NAME", bot_name)
            .replace("NEW_ROLE", new_role)
            .replace("STATUS", status)
            .replace("MODIFIER_NAME", modifier_name.capitalize())
            .replace("FIRST_NAME", first_name.capitalize())
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
            .replace("ACCESS_TYPE", new_role)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "update_role_subject"
        ]
        expected_subject = expected_subject.replace("BOT_NAME", bot_name)

        await MailUtility.format_and_send_mail(
            mail_type=mail_type,
            email=email,
            first_name=first_name,
            status=status,
            bot_name=bot_name,
            new_role=new_role,
            member_name=member_name,
            modifier_name=modifier_name
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_update_role_owner_mail(self, validate_and_send_mail_mock):
        mail_type = "update_role_owner_mail"
        email = "sampletest@gmail.com"
        first_name = "sample"
        bot_name = "test_bot"
        new_role = "test_role"
        status = "test_status"
        owner_name = "test_name"
        member_email = "test@gmail.com"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["update_role"] = (
            open("template/emails/memberUpdateRole.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"]["update_role"]
        expected_body = (
            expected_body.replace(
                "MAIL_BODY_HERE",
                Utility.email_conf["email"]["templates"]["update_role_owner_mail_body"],
            )
            .replace("MEMBER_EMAIL", member_email)
            .replace("BOT_NAME", bot_name)
            .replace("NEW_ROLE", new_role)
            .replace("STATUS", status)
            .replace("MODIFIER_NAME", first_name.capitalize())
            .replace("FIRST_NAME", owner_name.capitalize())
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "update_role_subject"
        ]
        expected_subject = expected_subject.replace("BOT_NAME", bot_name)

        await MailUtility.format_and_send_mail(
            mail_type=mail_type,
            email=email,
            first_name=first_name,
            status=status,
            bot_name=bot_name,
            new_role=new_role,
            owner_name=owner_name,
            member_email=member_email,
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_transfer_ownership_mail(self, validate_and_send_mail_mock):
        mail_type = "transfer_ownership_mail"
        email = "sampletest@gmail.com"
        first_name = "sample"
        bot_name = "test_bot"
        new_role = "test_role"
        member_email = "test@gmail.com"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["update_role"] = (
            open("template/emails/memberUpdateRole.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"]["update_role"]
        expected_body = (
            expected_body.replace(
                "MAIL_BODY_HERE",
                Utility.email_conf["email"]["templates"][
                    "transfer_ownership_mail_body"
                ],
            )
            .replace("MEMBER_EMAIL", member_email)
            .replace("BOT_NAME", bot_name)
            .replace("NEW_ROLE", new_role)
            .replace("MODIFIER_NAME", first_name.capitalize())
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "update_role_subject"
        ]
        expected_subject = expected_subject.replace("BOT_NAME", bot_name)

        await MailUtility.format_and_send_mail(
            mail_type=mail_type,
            email=email,
            first_name=first_name,
            bot_name=bot_name,
            new_role=new_role,
            member_email=member_email,
            new_owner_mail=member_email
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_password_generated(self, validate_and_send_mail_mock):
        mail_type = "password_generated"
        email = "sampletest@gmail.com"
        first_name = "sample"
        password = "test@123"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["password_generated"] = (
            open("template/emails/passwordGenerated.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"]["password_generated"]
        expected_body = (
            expected_body.replace("PASSWORD", password)
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "password_generated_subject"
        ]

        await MailUtility.format_and_send_mail(
            mail_type=mail_type, email=email, first_name=first_name, password=password
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_untrusted_login(self, validate_and_send_mail_mock):
        mail_type = "untrusted_login"
        email = "sampletest@gmail.com"
        first_name = "sample"
        url = "https://www.testurl.com"
        geo_location = {"City": "Mumbai", "Network": "CATO"}
        reset_password_url = Utility.email_conf["app"]["url"] + "/reset_password"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["untrusted_login"] = (
            open("template/emails/untrustedLogin.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"]["untrusted_login"]
        expected_geo_location = (
            "<li>first_name: sample</li><li>url: https://www.testurl.com</li>"
            "<li>City: Mumbai</li><li>Network: CATO</li>"
        )
        expected_body = (
            expected_body.replace("GEO_LOCATION", expected_geo_location)
            .replace("TRUST_DEVICE_URL", url)
            .replace("RESET_PASSWORD_URL", reset_password_url)
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("VERIFICATION_LINK", url)
            .replace("BASE_URL", base_url)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "untrusted_login_subject"
        ]

        await MailUtility.format_and_send_mail(
            mail_type=mail_type,
            email=email,
            first_name=first_name,
            url=url,
            **geo_location,
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_add_trusted_device(self, validate_and_send_mail_mock):
        mail_type = "add_trusted_device"
        email = "sampletest@gmail.com"
        first_name = "sample"
        geo_location = {"City": "Mumbai", "Network": "CATO"}
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["add_trusted_device"] = (
            open("template/emails/untrustedLogin.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"]["add_trusted_device"]
        expected_geo_location = (
            "<li>first_name: sample</li><li>url: None</li>"
            "<li>City: Mumbai</li><li>Network: CATO</li>"
        )
        expected_body = (
            expected_body.replace("GEO_LOCATION", expected_geo_location)
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "add_trusted_device"
        ]

        await MailUtility.format_and_send_mail(
            mail_type=mail_type, email=email, first_name=first_name, **geo_location
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_book_a_demo(self, validate_and_send_mail_mock):
        mail_type = "book_a_demo"
        email = "sample.test@gmail.com"
        first_name = "sample"
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "58.0.127.89"}
        base_url = Utility.environment["app"]["frontend_url"]
        data = {
            "first_name": "sample",
            "last_name": "test",
            "email": "sample.test@gmail.com",
            "phone": "+919876543210",
            "message": "Thank You",
            "recaptcha_response": "Svw2mPVxM0SkO4_2yxTcDQQ7iKNUDeDhGf4l6C2i"
        }
        Utility.email_conf["email"]["templates"]["custom_text_mail"] = (
            open("template/emails/custom_text_mail.html", "rb").read().decode()
        )
        user_details = (
            "Hi,<br>Following demo has been requested for Kairon:<br><li>first_name: sample</li>"
            "<li>last_name: test</li><li>email: sample.test@gmail.com</li><li>phone: +919876543210</li>" \
            "<li>message: Thank You</li>" \
            "<li>recaptcha_response: Svw2mPVxM0SkO4_2yxTcDQQ7iKNUDeDhGf4l6C2i</li>"
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "book_a_demo_subject"
        ]
        expected_body = Utility.email_conf["email"]["templates"]["custom_text_mail"]
        expected_body = (
            expected_body.replace("CUSTOM_TEXT", user_details)
            .replace("SUBJECT", expected_subject)
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
        )

        await MailUtility.format_and_send_mail(
            mail_type=mail_type,
            email=email,
            first_name=first_name,
            request=request,
            data=data,
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )
        demo_request_logs = DemoRequestLogs.objects(first_name="sample", last_name="test",
                                                    email="sample.test@gmail.com").get().to_mongo().to_dict()
        assert demo_request_logs['first_name'] == "sample"
        assert demo_request_logs['last_name'] == "test"
        assert demo_request_logs['email'] == "sample.test@gmail.com"
        assert demo_request_logs['phone'] == "+919876543210"
        assert demo_request_logs['status'] == "request_received"
        assert demo_request_logs['message'] == "Thank You"
        assert demo_request_logs['recaptcha_response'] == "Svw2mPVxM0SkO4_2yxTcDQQ7iKNUDeDhGf4l6C2i"

    @pytest.mark.asyncio
    async def test_trigger_email(self):
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock:
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

            await MailUtility.trigger_email(
                [to_email],
                subject,
                body,
                content_type=content_type,
                smtp_url=smtp_url,
                smtp_port=smtp_port,
                sender_email=sender_email,
                smtp_userid=smtp_userid,
                smtp_password=smtp_password,
                tls=tls,
            )

            mbody = MIMEText(body, content_type)
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender_email
            msg["To"] = to_email
            msg.attach(mbody)

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().connect"
            assert {} == kwargs

            host, port = args
            assert host == smtp_url
            assert port == port

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().login"
            assert {} == kwargs

            from_email, password = args
            assert from_email == sender_email
            assert password == smtp_password

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().sendmail"
            assert {} == kwargs

            assert args[0] == sender_email
            assert args[1] == [to_email]
            assert str(args[2]).__contains__(subject)
            assert str(args[2]).__contains__(body)

    @pytest.mark.asyncio
    async def test_trigger_email_tls(self):
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock:
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

            await MailUtility.trigger_email(
                [to_email],
                subject,
                body,
                content_type=content_type,
                smtp_url=smtp_url,
                smtp_port=smtp_port,
                sender_email=sender_email,
                smtp_userid=smtp_userid,
                smtp_password=smtp_password,
                tls=tls,
            )

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().connect"
            assert {} == kwargs

            host, port = args
            assert host == smtp_url
            assert port == port

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().starttls"
            assert {} == kwargs

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().login"
            assert {} == kwargs

            from_email, password = args
            assert from_email == sender_email
            assert password == smtp_password

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().sendmail"
            assert {} == kwargs

            assert args[0] == sender_email
            assert args[1] == [to_email]
            assert str(args[2]).__contains__(subject)
            assert str(args[2]).__contains__(body)

    @pytest.mark.asyncio
    async def test_trigger_email_using_smtp_userid(self):
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock:
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

            await MailUtility.trigger_email(
                [to_email],
                subject,
                body,
                content_type=content_type,
                smtp_url=smtp_url,
                smtp_port=smtp_port,
                sender_email=sender_email,
                smtp_userid=smtp_userid,
                smtp_password=smtp_password,
                tls=tls,
            )

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().connect"
            assert {} == kwargs

            host, port = args
            assert host == smtp_url
            assert port == port

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().starttls"
            assert {} == kwargs

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().login"
            assert {} == kwargs

            from_email, password = args
            assert from_email == smtp_userid
            assert password == smtp_password

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().sendmail"
            assert {} == kwargs

            assert args[0] == sender_email
            assert args[1] == [to_email]
            assert str(args[2]).__contains__(subject)
            assert str(args[2]).__contains__(body)

    def test_validate_smtp_valid(self):
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock:
            assert Utility.validate_smtp("localhost", 25)

    def test_validate_smtp_invalid(self):
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock:
            mock.return_value = Exception()
            assert not Utility.validate_smtp("dummy.test.com", 467)

    @pytest.mark.asyncio
    async def test_trigger_smtp(self):
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock:
            content_type = "html"
            to_email = "test@demo.com"
            subject = "Test"
            body = "Test"
            smtp_url = "changeit"
            sender_email = "changeit@changeit.com"
            smtp_password = "changeit"
            smtp_port = 587

            await MailUtility.trigger_smtp(
                to_email, subject, body, content_type=content_type
            )

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().connect"
            assert {} == kwargs

            host, port = args
            assert host == smtp_url
            assert port == smtp_port

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().starttls"
            assert {} == kwargs

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().login"
            assert {} == kwargs

            from_email, password = args
            assert from_email == sender_email
            assert password == smtp_password

            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().sendmail"
            assert {} == kwargs

            assert args[0] == sender_email
            assert args[1] == [to_email]
            assert str(args[2]).__contains__(subject)
            assert str(args[2]).__contains__(body)

    @pytest.mark.asyncio
    async def test_websocket_request(self):
        url = "ws://localhost/events/bot_id"
        msg = "hello"
        with patch("kairon.shared.utils.connect", autospec=True) as mock:
            await Utility.websocket_request(url, msg)
            mock.assert_called_with(url)

    @pytest.mark.asyncio
    async def test_websocket_request_connect_exception(self):
        from websockets.datastructures import Headers

        url = "ws://localhost/events/bot_id"
        msg = "hello"

        def _mock_websocket_connect_exception(*args, **kwargs):
            raise InvalidStatusCode(404, headers=Headers())

        with patch("kairon.shared.utils.connect", autospec=True) as mock:
            mock.side_effect = _mock_websocket_connect_exception
            with pytest.raises(InvalidStatusCode):
                await Utility.websocket_request(url, msg)

    def test_execute_http_request_connection_error(self):
        def __mock_connection_error(*args, **kwargs):
            raise requests.exceptions.ConnectTimeout()

        with patch("kairon.shared.utils.requests.request") as mocked:
            mocked.side_effect = __mock_connection_error
            with pytest.raises(
                AppException, match="Failed to connect to service: localhost"
            ):
                Utility.execute_http_request("POST", "http://localhost:2000/endpoint")

    def test_execute_http_request_exception(self):
        def __mock_connection_error(*args, **kwargs):
            raise Exception("Server not found")

        with patch("kairon.shared.utils.requests.sessions.Session.request") as mocked:
            mocked.side_effect = __mock_connection_error
            with pytest.raises(
                AppException, match="Failed to execute the url: Server not found"
            ):
                Utility.execute_http_request("POST", "http://test.com/endpoint")

    def test_execute_http_request_invalid_request(self):
        with pytest.raises(AppException, match="Invalid request method!"):
            Utility.execute_http_request("OPTIONS", "http://test.com/endpoint")

    @responses.activate
    def test_execute_http_request_empty_error_msg(self):
        responses.add(
            "POST", "https://app.chatwoot.com/public/api/v1/accounts", status=404
        )
        with pytest.raises(AppException, match="err_msg cannot be empty"):
            Utility.execute_http_request(
                "POST",
                "https://app.chatwoot.com/public/api/v1/accounts",
                validate_status=True,
            )

    @responses.activate
    def test_execute_http_request_with_error_msg(self):
        expected_response = {
            'meta': {
                '360dialog_trace_id': 'TOZFYLoh3xrUq2FsREQ',
                'developer_message': 'Invalid payload ({"error":{"message":"Invalid parameter","type":"OAuthException","code":100,"error_data":{"blame_field_specs":[["name"]]},"error_subcode":2388046,"is_transient":false,"error_user_title":"Name Format is Incorrect","error_user_msg":"The message template name can only have lowercase letters and underscores.","fbtrace_id":"AtxupgaxIrZVghWRHupbKzl"}})', 'error': '{"error":{"message":"Invalid parameter","type":"OAuthException","code":100,"error_data":{"blame_field_specs":[["name"]]},"error_subcode":2388046,"is_transient":false,"error_user_title":"Name Format is Incorrect","error_user_msg":"The message template name can only have lowercase letters and underscores.","fbtrace_id":"AtxupgaxIrZVghWRHupbKzl"}}',
                'http_code': 400,
                'success': False
            }
        }
        responses.add(
            "POST", "https://waba-v2.360dialog.io/v1/configs/templates", status=400, json=expected_response
        )

        with pytest.raises(AppException, match=re.escape('Failed to add template: Bad Request: Invalid payload ({"error":{"message":"Invalid parameter","type":"OAuthException","code":100,"error_data":{"blame_field_specs":[["name"]]},"error_subcode":2388046,"is_transient":false,"error_user_title":"Name Format is Incorrect","error_user_msg":"The message template name can only have lowercase letters and underscores.","fbtrace_id":"AtxupgaxIrZVghWRHupbKzl"}})')):
            Utility.execute_http_request(
                "POST",
                "https://waba-v2.360dialog.io/v1/configs/templates",
                validate_status=True, expected_status_code=201, err_msg="Failed to add template: "
            )

    @responses.activate
    def test_execute_http_request_with_invalid_response_object(self):
        expected_response = "Invalid Parameter"
        responses.add(
            "POST", "https://waba-v2.360dialog.io/v1/configs/templates", status=400, json=expected_response
        )

        with pytest.raises(AppException, match="Failed to add template: Bad Request"):
            Utility.execute_http_request(
                "POST",
                "https://waba-v2.360dialog.io/v1/configs/templates",
                validate_status=True, expected_status_code=201, err_msg="Failed to add template: "
            )

    def test_get_masked_value_empty(self):
        assert None is Utility.get_masked_value(None)
        assert "" == Utility.get_masked_value("")
        assert "  " == Utility.get_masked_value("  ")

    def test_get_masked_value_len_less_than_4(self):
        assert Utility.get_masked_value("test") == "****"

    def test_get_masked_value_len_more_from_left(self, monkeypatch):
        monkeypatch.setitem(
            Utility.environment["security"], "unmasked_char_strategy", "from_left"
        )
        assert Utility.get_masked_value("teststring") == "te********"

    def test_get_masked_value_mask_strategy_from_right(self, monkeypatch):
        monkeypatch.setitem(
            Utility.environment["security"], "unmasked_char_strategy", "from_right"
        )
        assert Utility.get_masked_value("teststring") == "********ng"

    def test_get_masked_value_from_mask_strategy_not_set(self, monkeypatch):
        monkeypatch.setitem(
            Utility.environment["security"], "unmasked_char_strategy", None
        )
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
        element_resolver = ElementTransformerOps("image", "hangouts")
        response = element_resolver.message_extractor(input_json, "image")
        expected_output = {
            "type": "image",
            "URL": "https://i.imgur.com/nFL91Pc.jpeg",
            "caption": "Dog Image",
        }
        assert expected_output == response

    def test_message_extractor_hangout_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        element_resolver = ElementTransformerOps("link", "hangouts")
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
        element_resolver = ElementTransformerOps("link", "hangouts")
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
        message_tmp = ElementTransformerOps.getChannelConfig("hangouts", "image")
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        element_resolver = ElementTransformerOps("image", "hangouts")
        extract_response = element_resolver.message_extractor(input_json, "image")
        response = ElementTransformerOps.replace_strategy(
            message_tmp, extract_response, "hangouts", "image"
        )
        expected_output = "{'cards': [{'sections': [{'widgets': [{'textParagraph': {'text': 'Dog Image'}}, {'image': {'imageUrl': 'https://i.imgur.com/nFL91Pc.jpeg', 'onClick': {'openLink': {'url': 'https://i.imgur.com/nFL91Pc.jpeg'}}}}]}]}]}"
        assert expected_output == str(response).strip()

    def test_hangout_replace_strategy_no_channel(self):
        message_tmp = None
        extract_response = None
        with pytest.raises(
            Exception, match="Element key mapping missing for hangout_fake or image"
        ):
            ElementTransformerOps.replace_strategy(
                message_tmp, extract_response, "hangout_fake", "image"
            )

    def test_hangout_replace_strategy_no_type(self):
        message_tmp = None
        extract_response = None
        with pytest.raises(
            Exception, match="Element key mapping missing for hangout or image_fake"
        ):
            ElementTransformerOps.replace_strategy(
                message_tmp, extract_response, "hangout", "image_fake"
            )

    def test_image_transformer_hangout_image(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        elementops = ElementTransformerOps("image", "hangouts")
        response = elementops.image_transformer(input_json)
        expected_output = "{'cards': [{'sections': [{'widgets': [{'textParagraph': {'text': 'Dog Image'}}, {'image': {'imageUrl': 'https://i.imgur.com/nFL91Pc.jpeg', 'onClick': {'openLink': {'url': 'https://i.imgur.com/nFL91Pc.jpeg'}}}}]}]}]}"
        assert expected_output == str(response).strip()

    def test_link_transformer_hangout_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        element_resolver = ElementTransformerOps("link", "hangouts")
        response = element_resolver.link_transformer(input_json)
        output = str(response)
        expected_output = (
            "{'text': 'This is <http://www.google.com|GoogleLink> use for search'}"
        )
        assert expected_output == output

    def test_link_transformer_messenger(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter

        messenger = MessengerResponseConverter("link", "messenger")
        response = messenger.link_transformer(input_json)
        output = response.get("text")
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
        assert telegram is None

    @pytest.mark.asyncio
    async def test_messageConverter_hangout_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        hangout = ConverterFactory.getConcreteInstance("link", "hangouts")
        response = await hangout.messageConverter(input_json)
        expected_output = json_data.get("hangout_link_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_hangout_image(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        hangout = ConverterFactory.getConcreteInstance("image", "hangouts")
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
        datalist = [
            {"name": "testadmin", "bot": 123},
            {"name": "testadmin1", "bot": 100},
        ]
        for item in json_generator:
            assert item in datalist

    def test_json_generator_nolist(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("json_generator_nolist")
        json_generator = ElementTransformerOps.json_generator(input_json)
        datalist = [{"name": "testadmin", "bot": 123}]
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
        string_response = ElementTransformerOps.convertjson_to_link_format(
            json_generator
        )
        assert (
            "This is <http://www.google.com|GoogleLink> use for search"
            == string_response
        )

    def test_convertjson_to_link_format_no_display(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        json_generator = ElementTransformerOps.json_generator(input_json)
        string_response = ElementTransformerOps.convertjson_to_link_format(
            json_generator, False
        )
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
            messenger.message_extractor(input_json, "link")

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
            telegram.message_extractor(input_json, "link")

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
            whatsapp.message_extractor(input_json, "link")

    @pytest.mark.asyncio
    async def test_messageConverter_hangout_video(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        hangout = ConverterFactory.getConcreteInstance("video", "hangouts")
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
        element_resolver = ElementTransformerOps("video", "hangouts")
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
        elementops = ElementTransformerOps("video", "hangouts")
        response = elementops.video_transformer(input_json)
        expected_output = {"text": "https://www.youtube.com/watch?v=YFbCaahCWQ0"}
        assert expected_output == response

    def test_save_and_publish_auditlog_action_save(self, monkeypatch):
        def publish_auditlog(*args, **kwargs):
            return None

        monkeypatch.setattr(AuditDataProcessor, "publish_auditlog", publish_auditlog)
        bot = "publish_auditlog"
        user = "testuser"
        event_config = EventConfig(
            bot=bot, user=user, ws_url="http://localhost:5000/event_url"
        )
        kwargs = {"action": "save"}
        AuditDataProcessor.save_and_publish_auditlog(
            event_config, "EventConfig", **kwargs
        )
        count = AuditLogData.objects(
            attributes=[{"key": "bot", "value": bot}], user=user, action="save"
        ).count()
        assert count == 1

    def test_save_and_publish_auditlog_action_save_another(self, monkeypatch):
        def publish_auditlog(*args, **kwargs):
            return None

        monkeypatch.setattr(AuditDataProcessor, "publish_auditlog", publish_auditlog)
        bot = "publish_auditlog"
        user = "testuser"
        event_config = EventConfig(
            bot=bot,
            user=user,
            ws_url="http://localhost:5000/event_url",
            headers="{'Autharization': '123456789'}",
            method="GET",
        )
        kwargs = {"action": "save"}
        AuditDataProcessor.save_and_publish_auditlog(
            event_config, "EventConfig", **kwargs
        )
        count = AuditLogData.objects(
            attributes=[{"key": "bot", "value": bot}], user=user, action="save"
        ).count()
        assert count == 2

    def test_save_and_publish_auditlog_action_update(self, monkeypatch):
        def publish_auditlog(*args, **kwargs):
            return None

        monkeypatch.setattr(AuditDataProcessor, "publish_auditlog", publish_auditlog)
        bot = "publish_auditlog"
        user = "testuser"
        event_config = EventConfig(
            bot=bot,
            user=user,
            ws_url="http://localhost:5000/event_url",
            headers="{'Autharization': '123456789'}",
        )
        kwargs = {"action": "update"}
        AuditDataProcessor.save_and_publish_auditlog(
            event_config, "EventConfig", **kwargs
        )
        count = AuditLogData.objects(
            attributes=[{"key": "bot", "value": bot}], user=user, action="update"
        ).count()
        assert count == 1

    def test_save_and_publish_auditlog_total_count(self, monkeypatch):
        def publish_auditlog(*args, **kwargs):
            return None

        monkeypatch.setattr(AuditDataProcessor, "publish_auditlog", publish_auditlog)
        bot = "publish_auditlog"
        user = "testuser"
        event_config = EventConfig(
            bot=bot,
            user=user,
            ws_url="http://localhost:5000/event_url",
            headers="{'Autharization': '123456789'}",
        )
        kwargs = {"action": "update"}
        AuditDataProcessor.save_and_publish_auditlog(
            event_config, "EventConfig", **kwargs
        )
        count = AuditLogData.objects(
            attributes=[{"key": "bot", "value": bot}], user=user
        ).count()
        assert count >= 3

    def test_save_and_publish_auditlog_total_count_with_event_url(self, monkeypatch):
        def execute_http_request(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "execute_http_request", execute_http_request)
        bot = "publish_auditlog"
        user = "testuser"
        event_config = EventConfig(
            bot=bot,
            user=user,
            ws_url="http://localhost:5000/event_url",
            headers="{'Autharization': '123456789'}",
        )
        kwargs = {"action": "update"}
        AuditDataProcessor.save_and_publish_auditlog(
            event_config, "EventConfig", **kwargs
        )
        count = AuditLogData.objects(
            attributes=[{"key": "bot", "value": bot}], user=user
        ).count()
        assert count >= 2

    @responses.activate
    def test_publish_auditlog(self):
        bot = "publish_auditlog"
        user = "secret_user"
        config = {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
            "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",
            "client_id": "3396830255712.3396861654876869879",
            "client_secret": "cf92180a7634d90bf42a217408376878",
        }
        auditlog_data = {
            "attributes": [{"key": "bot", "value": bot}],
            "user": user,
            "action": "update",
            "entity": "Channels",
            "data": config,
        }

        event_url = "http://publish_log.com/consume"
        EventConfig(
            bot=bot,
            user=user,
            ws_url="http://publish_log.com/consume",
            headers={"Autharization": "123456789"},
            method="GET",
        ).save()

        responses.add(
            responses.POST,
            event_url,
            json='{"message": "Auditlog saved on remote server"}',
            status=200,
        )

        AuditDataProcessor.publish_auditlog(AuditLogData(**auditlog_data))
        count = AuditLogData.objects(
            attributes=[{"key": "bot", "value": bot}], user=user
        ).count()
        assert count == 1

    @pytest.mark.asyncio
    async def test_messageConverter_messenger_button_one(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_one")
        messenger = ConverterFactory.getConcreteInstance("button", "messenger")
        response = await messenger.messageConverter(input_json)
        expected_output = json_data.get("messenger_button_op_one")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_messenger_quick_reply_one(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("quick_reply_one")
        messenger = ConverterFactory.getConcreteInstance("quick_reply", "messenger")
        response = await messenger.messageConverter(input_json)
        expected_output = json_data.get("messenger_quick_reply_op_one")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_messenger_quick_reply_two(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("quick_reply_two")
        messenger = ConverterFactory.getConcreteInstance("quick_reply", "messenger")
        response = await messenger.messageConverter(input_json)
        expected_output = json_data.get("messenger_quick_reply_op_two")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_messenger_quick_reply_three(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("quick_reply_three")
        messenger = ConverterFactory.getConcreteInstance("quick_reply", "messenger")
        response = await messenger.messageConverter(input_json)
        expected_output = json_data.get("messenger_quick_reply_op_three")
        assert expected_output == response

    def test_quick_reply_transformer_messenger_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("quick_reply_three")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter
        messenger = MessengerResponseConverter("quick_reply", "messenger_fake")
        with pytest.raises(Exception):
            messenger.quick_reply_transformer(input_json)

    @pytest.mark.asyncio
    async def test_message_converter_quick_reply_messenger_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("quick_reply_three")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter
        messenger = MessengerResponseConverter("quick_reply", "messenger_fail")
        with pytest.raises(Exception):
            await messenger.messageConverter(input_json)

    @pytest.mark.asyncio
    async def test_messageConverter_messenger_button_two(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_two")
        messenger = ConverterFactory.getConcreteInstance("button", "messenger")
        response = await messenger.messageConverter(input_json)
        expected_output = json_data.get("messenger_button_op_two")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_messenger_button_three(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_three")
        messenger = ConverterFactory.getConcreteInstance("button", "messenger")
        response = await messenger.messageConverter(input_json)
        expected_output = json_data.get("messenger_button_op_three")
        assert expected_output == response

    def test_button_transformer_messenger_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_one")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter
        messenger = MessengerResponseConverter("button", "messenger_fake")
        with pytest.raises(Exception):
            messenger.link_transformer(input_json)

    @pytest.mark.asyncio
    async def test_messageConverter_button_messenger_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_two")
        from kairon.chat.converters.channels.messenger import MessengerResponseConverter
        messenger = MessengerResponseConverter("button", "messenger_fail")
        with pytest.raises(Exception):
            await messenger.messageConverter(input_json)

    @pytest.mark.asyncio
    async def test_messageConverter_whatsapp_button_two(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_two")
        whatsapp = ConverterFactory.getConcreteInstance("button", "whatsapp")
        response = await whatsapp.messageConverter(input_json)
        expected_output = json_data.get("whatsapp_button_op_two")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_whatsapp_button_three(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_three")
        whatsapp = ConverterFactory.getConcreteInstance("button", "whatsapp")
        response = await whatsapp.messageConverter(input_json)
        expected_output = json_data.get("whatsapp_button_op_three")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_whatsapp_button_one(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_one")
        whatsapp = ConverterFactory.getConcreteInstance("button", "whatsapp")
        response = await whatsapp.messageConverter(input_json)
        expected_output = json_data.get("whatsapp_button_op_one")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_whatsapp_button_one_failure(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_one")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter

        whatsapp = WhatsappResponseConverter("button", "whatsapp_failed")
        with pytest.raises(Exception):
            await whatsapp.messageConverter(input_json)

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

    def test_get_templates_type_story_dict(self):
        story = {
            "name": "share_ticket_count_323",
            "steps": [
                {"name": "share_ticket_count_323", "type": "INTENT"},
                {"name": "utter_share_ticket_count_323", "type": "BOT"},
            ],
            "type": "RULE",
        }
        assert DataUtility.get_template_type(story) == TemplateType.QNA.value

        story["type"] = "STORY"
        assert DataUtility.get_template_type(story) == TemplateType.CUSTOM.value

    def test_get_templates_type_rule_dict(self):
        story = {
            "name": "share_ticket_count_323",
            "steps": [
                {"name": RULE_SNIPPET_ACTION_NAME, "type": "ACTION"},
                {"name": "share_ticket_count_323", "type": "INTENT"},
                {"name": "utter_share_ticket_count_323", "type": "BOT"},
            ],
            "type": "RULE",
        }
        assert DataUtility.get_template_type(story) == TemplateType.QNA.value

        story["type"] = "STORY"
        assert DataUtility.get_template_type(story) == TemplateType.CUSTOM.value

    def test_get_templates_type_story_step_and_rule_step(self):
        intent = {
            STORY_EVENT.NAME.value: "share_ticket_count_323",
            STORY_EVENT.CONFIDENCE.value: 1.0,
        }
        events = [
            UserUttered(text=None, intent=intent),
            ActionExecuted(action_name="utter_share_ticket_count_323"),
        ]
        story = RuleStep(
            block_name="ticket_count",
            start_checkpoints=[Checkpoint("START")],
            end_checkpoints=[],
            events=events,
        )
        assert DataUtility.get_template_type(story) == TemplateType.QNA.value

        story_one = StoryStep(
            block_name="ticket_count",
            start_checkpoints=[Checkpoint("START")],
            end_checkpoints=[],
            events=events,
        )
        assert DataUtility.get_template_type(story_one) == TemplateType.CUSTOM.value

    def test_get_templates_type_rule_step_with_rule_snippet_action(self):
        intent = {
            STORY_EVENT.NAME.value: "share_ticket_count_323",
            STORY_EVENT.CONFIDENCE.value: 1.0,
        }
        events = [
            ActionExecuted(action_name=RULE_SNIPPET_ACTION_NAME),
            UserUttered(text=None, intent=intent),
            ActionExecuted(action_name="utter_share_ticket_count_323"),
        ]
        story = RuleStep(
            block_name="ticket_count",
            start_checkpoints=[Checkpoint("START")],
            end_checkpoints=[],
            events=events,
        )
        assert DataUtility.get_template_type(story) == TemplateType.QNA.value

        events_two = [
            UserUttered(text=None, intent=intent),
            ActionExecuted(action_name="utter_share_ticket_count_323"),
        ]
        story_two = StoryStep(
            block_name="ticket_count_two",
            start_checkpoints=[Checkpoint("START")],
            end_checkpoints=[],
            events=events_two,
        )
        assert DataUtility.get_template_type(story_two) == TemplateType.CUSTOM.value

    def test_get_templates_type_custom(self):
        story = {
            "name": "share_ticket_count_323",
            "steps": [
                {"name": "share_ticket_count_323", "type": "INTENT"},
                {"name": "utter_share_ticket_count_323", "type": "BOT"},
                {"name": "utter_share_ticket_count_324", "type": "BOT"},
            ],
            "type": "STORY",
        }
        assert DataUtility.get_template_type(story) == TemplateType.CUSTOM.value

    def test_getConcreteInstance_msteams(self):
        from kairon.chat.converters.channels.msteams import MSTeamsResponseConverter

        msteams = ConverterFactory.getConcreteInstance("link", "msteams")
        assert isinstance(msteams, MSTeamsResponseConverter)

    @pytest.mark.asyncio
    async def test_messageConverter_msteams_link(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        msteams = ConverterFactory.getConcreteInstance("link", "msteams")
        response = await msteams.messageConverter(input_json)
        expected_output = json_data.get("msteams_link_op")
        assert expected_output == response.get("text")

    @pytest.mark.asyncio
    async def test_messageConverter_msteams_image(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        msteams = ConverterFactory.getConcreteInstance("image", "msteams")
        response = await msteams.messageConverter(input_json)
        expected_output = json_data.get("msteams_image_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_msteams_button(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_one")
        msteams = ConverterFactory.getConcreteInstance("button", "msteams")
        response = await msteams.messageConverter(input_json)
        expected_output = json_data.get("msteams_button_one_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_msteams_three_button(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_three")
        msteams = ConverterFactory.getConcreteInstance("button", "msteams")
        response = await msteams.messageConverter(input_json)
        expected_output = json_data.get("msteams_button_three_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_msteams_two_button(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_two")
        msteams = ConverterFactory.getConcreteInstance("button", "msteams")
        response = await msteams.messageConverter(input_json)
        expected_output = json_data.get("msteams_button_two_op")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_messageConverter_msteams_multilinks(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("multi_link")
        msteams = ConverterFactory.getConcreteInstance("link", "msteams")
        response = await msteams.messageConverter(input_json)
        expected_output = json_data.get("msteams_multilink_op")
        assert expected_output == response.get("text")

    @pytest.mark.asyncio
    async def test_message_extractor_msteams_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link_wrong_json")
        from kairon.chat.converters.channels.msteams import MSTeamsResponseConverter

        msteams = MSTeamsResponseConverter("link", "msteams")
        with pytest.raises(Exception):
            print(f"{msteams.message_type} {msteams.channel_type}")
            await msteams.messageConverter(input_json)

    def test_link_transformer_msteams_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link_wrong_json")
        from kairon.chat.converters.channels.msteams import MSTeamsResponseConverter

        msteams = MSTeamsResponseConverter("link", "msteams")
        with pytest.raises(Exception):
            msteams.link_transformer(input_json)

    @pytest.mark.asyncio
    async def test_video_transformer_msteams_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        msteams = ConverterFactory.getConcreteInstance("video", "msteams")
        response = await msteams.messageConverter(input_json)
        expected_output = json_data.get("msteams_video_op")
        assert expected_output == response.get("text")

    @pytest.mark.parametrize(
        "testing_password,results,err_msg",
        [
            ("TEST@2", [Length(8)], "Password length must be 8"),
            ("TESTING123", [Special(1)], "Missing 1 special letter"),
            ("testing@123", [Uppercase(1)], "Missing 1 uppercase letter"),
            ("TESTING@test", [Numbers(1)], "Missing 1 number"),
            (
                "TestingTest",
                [Numbers(1), Special(1)],
                "Missing 1 number\nMissing 1 special letter",
            ),
        ],
    )
    @patch("kairon.shared.utils.Utility.password_policy.test")
    def test_valid_password(
        self, mock_password_policy_test, testing_password, results, err_msg
    ):
        mock_password_policy_test.return_value = results
        with pytest.raises(AppException) as error:
            Utility.valid_password(password=testing_password)
        assert str(error.value) == err_msg
        mock_password_policy_test.assert_called_once_with(testing_password)

    def test_valid_password_with_correct_password(self):
        testing_password = "TESTING@123"
        assert Utility.valid_password(password=testing_password) is None

    def test_is_exist_without_base_fields(self):
        with pytest.raises(
            AppException, match="Field bot is required to check if document exist"
        ):
            assert Utility.is_exist(Slots, raise_error=False)

    def test_is_exist_with_raise_error_false(self):
        from kairon.shared.data.processor import MongoProcessor

        processor = MongoProcessor()
        processor.add_slot(
            {"name": "test", "type": "text", "influence_conversation": True},
            bot="testRaise",
            user="test",
        )
        assert Utility.is_exist(Slots, raise_error=False, bot="testRaise")

    def test_is_exist_with_raise_error_true_without_exp_message(self):
        from kairon.shared.data.processor import MongoProcessor

        processor = MongoProcessor()
        processor.add_slot(
            {"name": "test", "type": "text", "influence_conversation": True},
            bot="test_utils",
            user="test",
        )
        with pytest.raises(AppException, match="Exception message cannot be empty"):
            Utility.is_exist(Slots, raise_error=True, bot="test_utils")

    def test_is_exist_with_raise_error_true_with_exp_message(self):
        err_msg = "Testing Error Message"
        from kairon.shared.data.processor import MongoProcessor

        processor = MongoProcessor()
        processor.add_slot(
            {"name": "test1", "type": "text", "influence_conversation": True},
            bot="test_utils",
            user="test",
        )
        with pytest.raises(AppException, match=err_msg):
            Utility.is_exist(
                Slots, raise_error=True, exp_message=err_msg, bot="test_utils"
            )

    @pytest.mark.parametrize(
        "is_raise_error,expected_output", [(True, None), (False, False)]
    )
    def test_is_exist_with_zero_docs(self, is_raise_error, expected_output):
        assert (
            Utility.is_exist(
                Slots,
                raise_error=is_raise_error,
                exp_message="Testing",
                name__iexact="random",
                bot="test",
            )
            is expected_output
        )

    def test_is_exist(self):
        bot = "5f50fd0a56b698ca10d35d2e"
        user = "test_user"
        slot = "location"
        Slots(name=slot, type="text", bot=bot, user=user).save()
        assert (
            Utility.is_exist(
                Slots, raise_error=False, name=slot, type="text", bot=bot, user=user
            )
            is True
        )

    def test_is_exist_query_with_raise_error_false(self):
        assert (
            Utility.is_exist_query(
                Slots, raise_error=False, query=(Q(name="bot") & Q(status=True))
            )
            is True
        )

    def test_is_exist_query_with_raise_error_true_without_exp_message(self):
        with pytest.raises(AppException) as error:
            Utility.is_exist_query(
                Slots, raise_error=True, query=(Q(name="bot") & Q(status=True))
            )
        assert str(error.value) == "Exception message cannot be empty"

    def test_is_exist_query_with_raise_error_true_with_exp_message(self):
        err_msg = "Testing Error Message"
        with pytest.raises(AppException) as error:
            Utility.is_exist_query(
                Slots,
                raise_error=True,
                query=(Q(name="bot") & Q(status=True)),
                exp_message=err_msg,
            )
        assert str(error.value) == err_msg

    @pytest.mark.parametrize(
        "is_raise_error,expected_output", [(False, False), (True, None)]
    )
    def test_is_exist_query_with_zero_docs(self, is_raise_error, expected_output):
        assert (
            Utility.is_exist_query(
                Slots,
                raise_error=is_raise_error,
                query=(Q(name="random") & Q(status=True)),
            )
            is expected_output
        )

    def test_is_exist_query(self):
        bot = "5f50fd0a56b698ca10d35d2e"
        user = "test_user"
        slot = "location"
        Slots(name=slot, type="text", bot=bot, user=user).save()
        assert (
            Utility.is_exist_query(
                Slots, raise_error=False, query=(Q(name=slot) & Q(bot=bot))
            )
            is True
        )

    def test_special_match(self):
        assert Utility.special_match(strg="Testing@123") is True

    def test_special_match_without_special_character(self):
        assert Utility.special_match(strg="Testing123") is False

    def test_load_json_file(self):
        testing_path = "./template/chat-client/default-config.json"
        expected_output = {
            "name": "kairon",
            "buttonType": "button",
            "welcomeMessage": "Hello! How are you?",
            "container": "#root",
            "userType": "custom",
            "userStorage": "ls",
            "whitelist": ["*"],
            "live_agent_enabled": False,
            "styles": {
                "headerStyle": {
                    "backgroundColor": "#2b3595",
                    "color": "#ffffff",
                    "height": "60px",
                },
                "botStyle": {
                    "backgroundColor": "#e0e0e0",
                    "color": "#000000",
                    "iconSrc": "",
                    "fontFamily": "'Roboto', sans-serif",
                    "fontSize": "14px",
                    "showIcon": "false",
                },
                "userStyle": {
                    "backgroundColor": "#2b3595",
                    "color": "#ffffff",
                    "iconSrc": "",
                    "fontFamily": "'Roboto', sans-serif",
                    "fontSize": "14px",
                    "showIcon": "false",
                },
                "buttonStyle": {"color": "#ffffff", "backgroundColor": "#2b3595"},
                "containerStyles": {
                    "height": "500px",
                    "width": "350px",
                    "background": "#ffffff",
                },
            },
            "headerClassName": "",
            "containerClassName": "",
            "chatContainerClassName": "",
            "userClassName": "",
            "botClassName": "",
            "formClassName": "",
            "openButtonClassName": "",
            "multilingual": {"enable": False, "bots": []},
        }
        config = Utility.load_json_file(path=testing_path)
        assert config == expected_output

    def test_load_json_file_with_incorrect_path_raise_exception(self):
        testing_path = "./template/chat-client/testing.json"
        with pytest.raises(AppException) as error:
            Utility.load_json_file(path=testing_path)
        assert str(error.value) == "file not found"

    def test_get_channels(self):
        expected_channels = [
            "msteams",
            "slack",
            "telegram",
            "business_messages",
            "hangouts",
            "messenger",
            "instagram",
            "whatsapp",
            "line"
        ]
        channels = Utility.get_channels()
        assert channels == expected_channels

    def test_get_channels_with_no_channels(self, monkeypatch):
        expected_channels = []
        monkeypatch.setitem(Utility.system_metadata, "channels", [])
        channels = Utility.get_channels()
        assert channels == expected_channels

    def test_convertdatetime_with_timezone(self):
        from datetime import datetime, timezone

        dateformat = "%Y-%m-%d %H:%M:%S"
        current_utcnow = datetime(2023, 2, 12, 8, 00, 00, tzinfo=timezone.utc)
        result = Utility.convert_utcdate_with_timezone(
            current_utcnow, "Asia/Kolkata", dateformat
        )
        assert result == datetime(2023, 2, 12, 13, 30)

    def test_verify_email_disable(self):
        Utility.verify_email("test@test.com")

    @responses.activate
    def test_verify_email_enable_disposable_email(self):
        email = "test@test.com"
        api_key = "test"
        with patch.dict(
            Utility.environment,
            {
                "verify": {
                    "email": {"type": "quickemail", "key": api_key, "enable": True}
                }
            },
        ):
            verification = QuickEmailVerification()
            responses.add(
                responses.GET,
                verification.url
                + "?"
                + urlencode({"apikey": verification.key, "email": email}),
                json={
                    "result": "valid",
                    "reason": "rejected_email",
                    "disposable": "true",
                    "accept_all": "false",
                    "role": "false",
                    "free": "false",
                    "email": "test@test.com",
                    "user": "test",
                    "domain": "quickemailverification.com",
                    "mx_record": "us2.mx1.mailhostbox.com",
                    "mx_domain": "mailhostbox.com",
                    "safe_to_send": "false",
                    "did_you_mean": "",
                    "success": "true",
                    "message": None,
                },
            )
            with pytest.raises(AppException, match="Invalid or disposable Email!"):
                Utility.verify_email(email)

    @responses.activate
    def test_verify_email_enable_invalid_email(self):
        email = "test@test.com"
        api_key = "test"
        with patch.dict(
            Utility.environment,
            {
                "verify": {
                    "email": {"type": "quickemail", "key": api_key, "enable": True}
                }
            },
        ):
            verification = QuickEmailVerification()
            responses.add(
                responses.GET,
                verification.url
                + "?"
                + urlencode({"apikey": verification.key, "email": email}),
                json={
                    "result": "invalid",
                    "reason": "rejected_email",
                    "disposable": "false",
                    "accept_all": "false",
                    "role": "false",
                    "free": "false",
                    "email": "test@test.com",
                    "user": "test",
                    "domain": "quickemailverification.com",
                    "mx_record": "us2.mx1.mailhostbox.com",
                    "mx_domain": "mailhostbox.com",
                    "safe_to_send": "false",
                    "did_you_mean": "",
                    "success": "true",
                    "message": None,
                },
            )
            with pytest.raises(AppException, match="Invalid or disposable Email!"):
                Utility.verify_email(email)

    @responses.activate
    def test_verify_email_enable_valid_email(self):
        email = "test@test.com"
        api_key = "test"
        with patch.dict(
            Utility.environment,
            {
                "verify": {
                    "email": {"type": "quickemail", "key": api_key, "enable": True}
                }
            },
        ):
            verification = QuickEmailVerification()
            responses.add(
                responses.GET,
                verification.url
                + "?"
                + urlencode({"apikey": verification.key, "email": email}),
                json={
                    "result": "valid",
                    "reason": "rejected_email",
                    "disposable": "false",
                    "accept_all": "false",
                    "role": "false",
                    "free": "false",
                    "email": "test@test.com",
                    "user": "test",
                    "domain": "quickemailverification.com",
                    "mx_record": "us2.mx1.mailhostbox.com",
                    "mx_domain": "mailhostbox.com",
                    "safe_to_send": "false",
                    "did_you_mean": "",
                    "success": "true",
                    "message": None,
                },
            )
            Utility.verify_email(email)

    def test_get_llm_hyperparameters(self):
        hyperparameters = Utility.get_llm_hyperparameters("openai")
        assert hyperparameters == {
            "temperature": 0.0,
            "max_tokens": 300,
            "model": "gpt-4o-mini",
            "top_p": 0.0,
            "n": 1,
            "stop": None,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "logit_bias": {},
        }

    def test_get_llm_hyperparameters_not_found(self, monkeypatch):
        with pytest.raises(
            AppException, match="Could not find any hyperparameters for gemini LLM."
        ):
            Utility.get_llm_hyperparameters("gemini")

    def test_get_client_ip_with_request_client(self):
        request = MagicMock()
        request.headers = {}
        request.client.host = "58.0.127.89"
        ip = Utility.get_client_ip(request)
        assert "58.0.127.89" == ip


    @pytest.mark.asyncio
    async def test_messageConverter_whatsapp_dropdown(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("whatsapp_drop_down_input")
        whatsapp = ConverterFactory.getConcreteInstance("dropdown", "whatsapp")
        response = await whatsapp.messageConverter(input_json)
        expected_output = json_data.get("whatsapp_drop_down_output")
        print(f"expected {expected_output}..{response}")
        assert expected_output == response

    def test_dropdown_transformer_whatsapp(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("whatsapp_drop_down_input")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter

        whatsapp = WhatsappResponseConverter("dropdown", "whatsapp")
        response = whatsapp.dropdown_transformer(input_json)
        expected_output = json_data.get("whatsapp_drop_down_output")
        assert expected_output == response

    def test_dropdown_transformer_whatsapp_with_intent_and_slot_blank_values(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("whatsapp_drop_down_blank_input")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter

        whatsapp = WhatsappResponseConverter("dropdown", "whatsapp")
        response = whatsapp.dropdown_transformer(input_json)
        expected_output = json_data.get("whatsapp_drop_down_blank_output")
        assert expected_output == response

    def test_dropdown_transformer_whatsapp_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("whatsapp_drop_down_input_exception")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter

        whatsapp = WhatsappResponseConverter("dropdown", "whatsapp")
        with pytest.raises(Exception):
            whatsapp.dropdown_transformer(input_json)

    def test_dropdown_transformer_header_input_whatsapp(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("whatsapp_drop_down_header_input")
        from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter

        whatsapp = WhatsappResponseConverter("dropdown", "whatsapp")
        response = whatsapp.dropdown_transformer(input_json)
        expected_output = json_data.get("whatsapp_drop_down_header_output")
        assert expected_output == response

    def test_is_picklable_for_mongo(self):
        assert Utility.is_picklable_for_mongo({"bot": "test_bot"})

    def test_is_picklable_for_mongo_failure(self):
        assert not Utility.is_picklable_for_mongo({"requests": requests})
        assert not Utility.is_picklable_for_mongo({"utility": Utility})
        assert not Utility.is_picklable_for_mongo(
            {"is_picklable_for_mongo": Utility.is_picklable_for_mongo}
        )

    def test_button_transformer_telegram_single_button(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_one")
        telegram = TelegramResponseConverter("button", "telegram")
        response = telegram.button_transformer(input_json)
        expected_output = json_data.get("telegram_button_op_one")
        assert expected_output == response

    def test_button_transformer_telegram_multi_buttons(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_three")
        telegram = TelegramResponseConverter("button", "telegram")
        response = telegram.button_transformer(input_json)
        expected_output = json_data.get("telegram_button_op_multi")
        assert expected_output == response

    @pytest.mark.asyncio
    async def test_button_transformer_telegram_messageConverter(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_three")
        telegram = ConverterFactory.getConcreteInstance("button", "telegram")
        response = await telegram.messageConverter(input_json)
        expected_output = json_data.get("telegram_button_op_multi")
        assert expected_output == response

    def test_button_transformer_telegram_exception(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("button_one_exception")
        telegram = TelegramResponseConverter("button", "telegram")
        with pytest.raises(Exception):
            telegram.button_transformer(input_json)

    def test_copy_pretrained_model(self):
        import tarfile
        import tempfile

        tempdir = tempfile.TemporaryDirectory().name

        bot = "copy_bot"
        output_path = f"models/{bot}"
        Utility.copy_pretrained_model(bot, "Hi-Hello-GPT")
        model_file = Utility.get_latest_file(output_path)
        with tarfile.open(model_file, "r:gz") as model:
            members = model.getnames()
            assert all(item in members for item in ["components", "metadata.json"])
            model.extractall(tempdir)

            metadata = json.load(open(f"{tempdir}/metadata.json"))
            domain = Utility.read_yaml(
                f"{tempdir}/components/domain_provider/domain.yml"
            )

            assert domain["slots"]["bot"]["initial_value"] == bot
            assert metadata["domain"]["slots"]["bot"]["initial_value"] == bot

    def test_link_transformer_line(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("link")
        from kairon.chat.converters.channels.line import LineResponseConverter

        line = LineResponseConverter("link", "line")
        response = line.link_transformer(input_json)
        output = str(response)
        expected_output = """{'type': 'text', 'text': 'This is http://www.google.com use for search'}"""
        assert expected_output == output

    def test_video_transformer_line(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("video")
        from kairon.chat.converters.channels.line import LineResponseConverter

        line = LineResponseConverter("video", "line")
        response = line.video_transformer(input_json)
        expected_output = {'type': 'video', 'originalContentUrl': 'https://www.youtube.com/watch?v=YFbCaahCWQ0', 'previewImageUrl': 'https://www.learntotrade.com.ph/assets-lttph/uploads/2016/04/video-preview-pic.jpg'}
        assert expected_output == response

    def test_image_transformer_line(self):
        json_data = json.load(open("tests/testing_data/channel_data/channel_data.json"))
        input_json = json_data.get("image")
        from kairon.chat.converters.channels.line import LineResponseConverter

        line = LineResponseConverter("image", "line")
        response = line.image_transformer(input_json)
        expected_output = {'type': 'image', 'originalContentUrl': 'https://i.imgur.com/nFL91Pc.jpeg', 'previewImageUrl': 'https://i.imgur.com/nFL91Pc.jpeg'}
        assert expected_output == response

    def test_getConcreteInstance_line(self):
        from kairon.chat.converters.channels.line import LineResponseConverter

        line = ConverterFactory.getConcreteInstance("link", "line")
        assert isinstance(line, LineResponseConverter)



    @pytest.fixture
    def bot_setting_dict(self):
        return {
            "live_agent_enabled": True
        }

    @pytest.fixture
    def bot(self):
        return "sample_bot"

    def test_is_live_agent_enabled_true(self, bot, bot_setting_dict):
        with patch('kairon.shared.data.data_objects.BotSettings.objects') as mock_objects:
            mock_get = mock_objects.return_value.get
            mock_get.return_value.to_mongo.return_value.to_dict.return_value = bot_setting_dict

            processor = MongoProcessor();
            assert processor.is_live_agent_enabled(bot, False) == True

    def test_is_live_agent_enabled_false(self, bot):
        bot_setting_dict = {"live_agent_enabled": False}

        with patch('kairon.shared.data.data_objects.BotSettings.objects') as mock_objects:
            mock_get = mock_objects.return_value.get
            mock_get.return_value.to_mongo.return_value.to_dict.return_value = bot_setting_dict
            processor = MongoProcessor()
            assert processor.is_live_agent_enabled(bot) == False

    def test_is_live_agent_enabled_no_bot_setting(self, bot):
        with patch('kairon.shared.data.data_objects.BotSettings.objects') as mock_objects:
            mock_get = mock_objects.return_value.get
            mock_get.return_value.to_mongo.return_value.to_dict.return_value = {}
            processor = MongoProcessor()
            assert processor.is_live_agent_enabled(bot) == False

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_first_name_add_member_email_template(self, validate_and_send_mail_mock):
        mail_type = "add_member"
        email = "sampletest@gmail.com"
        first_name = "sample"
        bot_name = "test_bot"
        role = "test_role"
        access_url = "http://localhost:3000"
        bot_owner_name = "Sample"
        accessor_email = "test@gmail.com"
        accessor_name = "buddy"
        member_confirm = "test_name"
        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["add_member"] = (
            open("template/emails/memberAddAccept.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"][
            "add_member"
        ]
        expected_body = (
            expected_body.replace("BOT_NAME", bot_name)
            .replace("ACCESS_TYPE", role)
            .replace("FIRST_NAME", first_name)
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)
            .replace("ACCESS_URL", access_url)
            .replace("BOT_OWNER_NAME", bot_owner_name)
            .replace("INVITED_PERSON_NAME", accessor_name)
        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "add_member_subject"
        ]
        expected_subject = expected_subject.replace(
            "BOT_NAME", bot_name
        )

        await MailUtility.format_and_send_mail(
            mail_type=mail_type,
            email=email,
            first_name=first_name,
            bot_name=bot_name,
            role=role,
            accessor_email=accessor_email,
            member_confirm=member_confirm,
            url=base_url,
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )

    @pytest.mark.asyncio
    @patch("kairon.shared.utils.MailUtility.validate_and_send_mail", autospec=True)
    async def test_handle_first_name_member_update_email_template(self, validate_and_send_mail_mock):
        mail_type = "update_role_member_mail"
        email = "sampletest@gmail.com"
        first_name = "sample"
        bot_name = "test_bot"
        new_role = "test_role"
        status = "test_status"
        member_email = "test@gmail.com"
        modifier_name = "test_name"

        base_url = Utility.environment["app"]["frontend_url"]
        Utility.email_conf["email"]["templates"]["update_role_member_mail"] = (
            open("template/emails/memberUpdateRole.html", "rb").read().decode()
        )
        expected_body = Utility.email_conf["email"]["templates"]["update_role_member_mail"]
        expected_body = (
            expected_body.replace(
                "MAIL_BODY_HERE",
                Utility.email_conf["email"]["templates"]["update_role_member_mail_body"],
            )
            .replace("MEMBER_EMAIL", member_email)
            .replace("BOT_NAME", bot_name)
            .replace("NEW_ROLE", new_role)
            .replace("ACCESS_TYPE", new_role)
            .replace("STATUS", status)
            .replace("MODIFIER_NAME", modifier_name.capitalize())
            .replace("FIRST_NAME", first_name.capitalize())
            .replace("USER_EMAIL", email)
            .replace("BASE_URL", base_url)

        )
        expected_subject = Utility.email_conf["email"]["templates"][
            "update_role_subject"
        ]
        expected_subject = expected_subject.replace("BOT_NAME", bot_name)
        await MailUtility.format_and_send_mail(
            mail_type=mail_type,
            email=email,
            first_name=first_name,
            status=status,
            bot_name=bot_name,
            new_role=new_role,
            member_email=member_email,
            base_url=base_url,
            modifier_name=modifier_name
        )
        validate_and_send_mail_mock.assert_called_once_with(
            email, expected_subject, expected_body
        )