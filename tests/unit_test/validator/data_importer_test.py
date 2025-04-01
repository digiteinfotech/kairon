import os
import shutil
import tempfile
import uuid
from unittest.mock import Mock

import pytest
from mongoengine import connect
from rasa.shared.core.domain import Domain
from rasa.shared.core.training_data.story_reader.yaml_story_reader import KEY_STORIES, KEY_RULES, KEY_RULE_CONDITION, \
    KEY_RULE_FOR_CONVERSATION_START
from rasa.shared.core.training_data.structures import StoryStep

from kairon.exceptions import AppException
from kairon.importer.data_importer import DataImporter
from kairon.shared.data.constant import REQUIREMENTS
from kairon.shared.data.model_data_imporer import CustomStoryGraph, KYAMLStoryReader, KRasaFileImporter, \
    KYAMLStoryWriter, KRuleParser, CustomStoryStepBuilder, CustomRuleStep
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import FlowTagType
from kairon.shared.utils import Utility


def pytest_namespace():
    return {'tmp_dir': None}


class TestDataImporter:

    @pytest.fixture(scope='session', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        tmp_dir = tempfile.mkdtemp()
        pytest.tmp_dir = tmp_dir
        yield None
        shutil.rmtree(tmp_dir)

    @pytest.mark.asyncio
    async def test_validate_success(self):
        path = 'tests/testing_data/validator/valid'
        importer = DataImporter(path, 'test_data_import', 'test', REQUIREMENTS.copy(), False, False)
        summary, component_count = await importer.validate()
        assert not summary.get('intents')
        assert not summary.get('stories')
        assert not summary.get('utterances')
        assert not summary.get('http_actions')
        assert not summary.get('training_examples')
        assert not summary.get('domain')
        assert not summary.get('config')
        assert not summary.get('exception')

    @pytest.mark.asyncio
    async def test_validate_invalid_domain(self):
        path = 'tests/testing_data/validator/invalid_domain'
        importer = DataImporter(path, 'test_data_import', 'test', REQUIREMENTS.copy(), False, False)
        with pytest.raises(AppException, match='Failed to load domain.yml. Error: \'Duplicate entities in domain. '
                                               'These entities occur more than once in the domain: \'location\'.\''):
            await importer.validate()

    @pytest.mark.asyncio
    async def test_validate_all_including_http_actions(self):
        path = 'tests/testing_data/validator/valid'
        http_actions = 'tests/testing_data/error/actions.yml'
        bot = 'test_data_import'
        user = 'test'
        bot_home = os.path.join(pytest.tmp_dir, bot, str(uuid.uuid4()))
        shutil.copytree(path, bot_home)
        shutil.copy2(http_actions, bot_home)
        importer = DataImporter(bot_home, bot, user, REQUIREMENTS.copy(), False, False)
        summary, component_count = await importer.validate()
        assert not summary.get('intents')
        assert not summary.get('stories')
        assert not summary.get('utterances')
        assert len(summary.get('http_action')) == 3
        summary.get('http_action')[0] = {'action_performanceUser1000@digite.com': " Required fields {'request_method'} not found."}
        assert not summary.get('training_examples')
        assert not summary.get('domain')
        assert not summary.get('config')
        assert not summary.get('exception')

    @pytest.mark.asyncio
    async def test_validate_failure(self):
        path = 'tests/testing_data/validator/common_training_examples'
        importer = DataImporter(path, 'test_data_import', 'test', REQUIREMENTS.copy())
        summary, component_count = await importer.validate()
        assert not summary.get('intents')
        assert not summary.get('stories')
        assert not summary.get('utterances')
        assert not summary.get('http_actions')
        assert summary.get('training_examples')
        assert not summary.get('domain')
        assert not summary.get('config')
        assert not summary.get('exception')

    @pytest.mark.asyncio
    async def test_validate_exception(self):
        path = 'tests/testing_data/validator/invalid_yaml'
        importer = DataImporter(path, 'test_data_import', 'test', REQUIREMENTS.copy())
        with pytest.raises(AppException):
            await importer.validate()

    @pytest.mark.asyncio
    async def test_validate_invalid_path(self):
        path = 'tests/testing_data/validator/invalid_path'
        importer = DataImporter(path, 'test_data_import', 'test', REQUIREMENTS.copy())
        with pytest.raises(AppException):
            await importer.validate()

    @pytest.mark.asyncio
    async def test_import_data(self):
        path = 'tests/testing_data/validator/valid'
        bot = 'test_data_import'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user,
                                REQUIREMENTS - {"http_actions", "chat_client_config"}, True, True)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 7
        assert len(list(processor.fetch_responses(bot))) == 3
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_import_data_with_valid_data(self):
        path = 'tests/testing_data/validator/valid_data'
        bot = 'test_data_import_with_valid_data'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user,
                                REQUIREMENTS - {"http_actions", "chat_client_config"}, True, True)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 7
        assert len(list(processor.fetch_responses(bot))) == 4
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 4

    @pytest.mark.asyncio
    async def test_import_data_with_actions(self):
        path = 'tests/testing_data/validator/valid_data'
        actions = 'tests/testing_data/valid_yml/actions.yml'
        bot = 'test_data_import_with_valid_data'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        shutil.copy2(actions, test_data_path)
        importer = DataImporter(test_data_path, bot, user,
                                REQUIREMENTS - {"http_actions", "chat_client_config"}, True, False)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 7
        assert len(list(processor.fetch_responses(bot))) == 4
        assert len(processor.fetch_actions(bot)) == 16
        assert len(processor.fetch_rule_block_names(bot)) == 4

    @pytest.mark.asyncio
    async def test_import_data_with_multiflow(self):
        path = 'tests/testing_data/multiflow_stories/valid_with_multiflow'
        bot = 'test_data_import_multiflow'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user,
                                REQUIREMENTS - {"http_actions", "chat_client_config"}, True, True)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 17
        assert len(list(processor.fetch_responses(bot))) == 7
        assert len(processor.fetch_actions(bot)) == 3
        assert len(processor.fetch_rule_block_names(bot)) == 3
        assert len(processor.fetch_multiflow_stories(bot)) == 2

    @pytest.mark.asyncio
    async def test_import_data_append(self):
        path = 'tests/testing_data/validator/append'
        bot = 'test_data_import'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user,
                                REQUIREMENTS - {"http_actions", "chat_client_config"}, True, False)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert 'location' in processor.fetch_intents(bot)
        assert 'affirm' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 4
        assert len(list(processor.fetch_training_examples(bot))) == 13
        assert len(list(processor.fetch_responses(bot))) == 6
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_import_data_dont_save(self):
        path = 'tests/testing_data/validator/common_training_examples'
        bot = 'test_data_import'
        bot_2 = 'test_data_import_bot'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user, set(), False)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        intents = processor.fetch_intents(bot)
        assert 'greet' in intents
        assert 'deny' in intents
        assert 'location' in intents
        assert 'affirm' in intents
        assert len(processor.fetch_stories(bot)) == 4
        assert len(list(processor.fetch_training_examples(bot))) == 13
        assert len(list(processor.fetch_responses(bot))) == 6
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 3

        assert len(processor.fetch_intents(bot_2)) == 0
        assert len(processor.fetch_stories(bot_2)) == 0
        assert len(list(processor.fetch_training_examples(bot_2))) == 0
        assert len(list(processor.fetch_responses(bot_2))) == 0
        assert len(processor.fetch_actions(bot_2)) == 0
        assert len(processor.fetch_rule_block_names(bot_2)) == 0

    @pytest.mark.asyncio
    async def test_import_data_validation_failed(self):
        path = 'tests/testing_data/validator/common_training_examples'
        bot = 'test_data_import_bot'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user, REQUIREMENTS.copy(), True)
        summary, component_count = await importer.validate()
        assert not summary.get('intents')
        assert not summary.get('stories')
        assert not summary.get('utterances')
        assert not summary.get('http_actions')
        assert summary.get('training_examples')
        assert not summary.get('domain')
        assert not summary.get('config')
        assert not summary.get('exception')

        importer.validator.intents = []
        importer.import_data()

        processor = MongoProcessor()
        assert len(processor.fetch_intents(bot)) == 0
        assert len(processor.fetch_stories(bot)) == 0
        assert len(list(processor.fetch_training_examples(bot))) == 0
        assert len(list(processor.fetch_responses(bot))) == 0
        assert len(processor.fetch_actions(bot)) == 0




def test_custom_rule_step():
    step = CustomRuleStep()
    assert step.flow_tags == [FlowTagType.chatbot_flow.value]


def test_custom_story_step_builder():
    builder = CustomStoryStepBuilder(name="test_story", source_name="test.yml")
    builder.is_rule = True
    steps = builder._next_story_steps()
    assert len(steps) == 1
    assert steps[0].flow_tags == [FlowTagType.chatbot_flow.value]


def test_k_rule_parser():
    parser = KRuleParser(Mock(), "test.yml")
    parser._new_rule_part("test_rule", "test.yml", ["custom_flow"])
    assert parser.current_step_builder.flow_tags == ["custom_flow"]


def test_custom_story_graph():
    story_step = Mock(spec=StoryStep)
    story_step.id = "step1"
    story_step.flow_tags = ["tag1"]

    dummy_start = Mock()
    dummy_start.name = "START"
    story_step.start_checkpoints = [dummy_start]

    dummy_end = Mock()
    dummy_end.name = "END"
    story_step.end_checkpoints = [dummy_end]

    graph = CustomStoryGraph([story_step])
    assert "tag1" in graph.flow_tags


def test_kyaml_story_reader():
    reader = KYAMLStoryReader(Mock(), "test.yml")
    dummy_builder = type("DummyBuilder", (), {})()
    dummy_builder.flow_tags = []
    reader.current_step_builder = dummy_builder
    reader._parse_metadata({"metadata": {"flow_tags": ["tag1"]}})
    assert reader.current_step_builder.flow_tags == ["tag1"]


def test_krasa_file_importer(monkeypatch):
    importer = KRasaFileImporter()
    importer._story_files = ["test.yml"]
    importer.get_domain = Mock()
    dummy_yaml = "stories:\n- story: test\n  steps: []"
    monkeypatch.setattr("rasa.shared.utils.io.read_file", lambda filename, encoding='utf-8': dummy_yaml)
    monkeypatch.setattr("rasa.shared.utils.validation.validate_yaml_schema", lambda s, f: None)
    importer.get_stories()


def test_kyaml_story_writer():
    writer = KYAMLStoryWriter()
    rule_step = Mock()
    rule_step.block_name = "rule1"
    rule_step.get_rules_condition = Mock(return_value=[])
    rule_step.get_rules_events = Mock(return_value=[])
    rule_step.flow_tags = ["tag1"]
    result = writer.process_rule_step(rule_step)
    assert result["metadata"]["flow_tags"] == ["tag1"]

def test_custom_rule_step_custom_flow_tags():
    custom_tags = ["custom1", "custom2"]
    step = CustomRuleStep(flow_tags=custom_tags)
    assert step.flow_tags == custom_tags



def test_custom_story_step_builder_default_flow_tags():
    builder = CustomStoryStepBuilder(name="default_story", source_name="default.yml")
    assert builder.flow_tags == [FlowTagType.chatbot_flow.value]


def test_k_rule_parser_new_part(monkeypatch):
    parser = KRuleParser(Mock(), "test.yml")
    # Bypass adding current stories.
    parser._add_current_stories_to_result = lambda: None

    # Capture rule conditions and snippet action calls.
    conditions_captured = []

    def capture_conditions(conds):
        nonlocal conditions_captured
        conditions_captured = conds

    parser._parse_rule_conditions = capture_conditions

    snippet_called = False

    def call_snippet():
        nonlocal snippet_called
        snippet_called = True

    parser._parse_rule_snippet_action = call_snippet

    item = {
        "metadata": {"flow_tags": ["tag_new"]},
        KEY_RULE_CONDITION: ["cond1", "cond2"],
        KEY_RULE_FOR_CONVERSATION_START: False,
    }
    parser._new_part("rule_test", item)
    assert parser.current_step_builder.flow_tags == ["tag_new"]
    assert conditions_captured == ["cond1", "cond2"]
    assert snippet_called is True



def test_custom_story_graph_multiple_steps():
    step1 = Mock(spec=StoryStep)
    step1.id = "s1"
    step1.flow_tags = ["tag1"]
    dummy_start1 = Mock()
    dummy_start1.name = "START"
    dummy_end1 = Mock()
    dummy_end1.name = "END1"
    step1.start_checkpoints = [dummy_start1]
    step1.end_checkpoints = [dummy_end1]

    step2 = Mock(spec=StoryStep)
    step2.id = "s2"
    step2.flow_tags = ["tag2"]
    dummy_start2 = Mock()
    dummy_start2.name = "START2"
    dummy_end2 = Mock()
    dummy_end2.name = "END2"
    step2.start_checkpoints = [dummy_start2]
    step2.end_checkpoints = [dummy_end2]

    graph = CustomStoryGraph([step1, step2])
    assert "tag1" in graph.flow_tags
    assert "tag2" in graph.flow_tags


def test_kyaml_story_reader_parse_step_string(monkeypatch):
    reader = KYAMLStoryReader(Mock(), "test.yml")
    warning_msg = None

    def fake_raise_warning(msg, docs=None):
        nonlocal warning_msg
        warning_msg = msg

    monkeypatch.setattr("rasa.shared.utils.io.raise_warning", fake_raise_warning)
    monkeypatch.setattr(reader, "_get_item_title", lambda: "Test Title")
    monkeypatch.setattr(reader, "_get_docs_link", lambda: "http://dummy.docs.link")

    reader._parse_step("unexpected string step")
    assert warning_msg is not None
    assert "unexpected step" in warning_msg


def test_kyaml_story_reader_read_from_parsed_yaml(monkeypatch):
    dummy_step = Mock(spec=StoryStep)
    dummy_step.id = "dummy"
    dummy_start = Mock()
    dummy_start.name = "dummy_start"
    dummy_end = Mock()
    dummy_end.name = "dummy_end"
    dummy_step.start_checkpoints = [dummy_start]
    dummy_step.end_checkpoints = [dummy_end]

    class FakeParser:
        def __init__(self, reader):
            self.reader = reader

        def parse_data(self, data):
            pass

        def get_steps(self):
            return [dummy_step]

        @classmethod
        def from_reader(cls, reader):
            return cls(reader)

    monkeypatch.setattr("kairon.shared.data.model_data_imporer.StoryParser", FakeParser)
    monkeypatch.setattr("kairon.shared.data.model_data_imporer.KRuleParser", FakeParser)
    monkeypatch.setattr("rasa.shared.utils.validation.validate_training_data_format_version",
                        lambda content, source: True)
    reader = KYAMLStoryReader(Mock(), "test.yml")
    reader.story_steps = []
    parsed_content = {
        KEY_STORIES: [{"story": "dummy", "steps": []}],
        KEY_RULES: [{"rule": "dummy", "steps": []}],
    }
    steps = reader.read_from_parsed_yaml(parsed_content)
    assert steps.count(dummy_step) == 2



def test_kyaml_story_writer_dump(monkeypatch, tmp_path):
    writer = KYAMLStoryWriter()
    dummy_step = Mock(spec=StoryStep)
    dummy_step.block_name = "rule1"
    dummy_step.get_rules_condition = lambda: []
    dummy_step.get_rules_events = lambda: []
    dummy_step.flow_tags = ["tag1"]
    writer.stories_to_yaml = lambda steps, is_test: {KEY_STORIES: [{"story": "dummy"}]}
    target_file = tmp_path / "output.yml"
    writer.dump(str(target_file), [dummy_step], is_appendable=False, is_test_story=True)
    content = target_file.read_text(encoding="utf-8")
    assert "dummy" in content



def test_krasa_file_importer_exclusion(monkeypatch):
    def fake_read_from_file(filename):
        dummy_step = Mock(spec=StoryStep)
        dummy_step.id = "dummy"
        dummy_start = Mock()
        dummy_start.name = "dummy_start"
        dummy_end = Mock()
        dummy_end.name = "dummy_end"
        dummy_step.start_checkpoints = [dummy_start]
        dummy_step.end_checkpoints = [dummy_end]
        return [dummy_step] * 10

    monkeypatch.setattr("kairon.shared.data.model_data_imporer.KYAMLStoryReader.read_from_file", lambda self, f: fake_read_from_file(f))
    story_files = ["file1.yml", "file2.yml"]
    dummy_domain = Domain(
        intents=[],
        entities=[],
        slots=[],
        responses={},
        action_names=[],
        forms={},
        data={}
    )
    steps = KRasaFileImporter.load_data_from_files(story_files, dummy_domain, exclusion_percentage=50)
    assert len(steps) == 10
