import os
from io import BytesIO

import pytest
from fastapi import UploadFile
from mongoengine import connect

from kairon.utils import Utility


class TestUtility:

    @pytest.fixture(autouse=True, scope="session")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment["database"]['url'])

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

