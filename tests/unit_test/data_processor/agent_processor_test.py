import os
import shutil

import pytest

from kairon import Utility
from kairon.chat.agent_processor import AgentProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.exceptions import AppException
from elasticmock import elasticmock


class TestAgentProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        from rasa import train

        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        bot = 'agent_testing_user'
        pytest.bot = bot
        model_path = os.path.join('models', bot)
        os.mkdir(model_path)
        train(
            domain='tests/testing_data/model_tester/domain.yml',
            config='tests/testing_data/model_tester/config.yml',
            training_files=['tests/testing_data/model_tester/nlu_with_entities/nlu.yml',
                            'tests/testing_data/model_tester/training_stories_success/stories.yml'],
            output=model_path,
            core_additional_arguments={"augmentation_factor": 100},
            force_training=True
        )
        yield None
        shutil.rmtree(model_path)

    @pytest.fixture()
    def mock_agent_properties(self, monkeypatch):
        def _return_none(*args, **kwargs):
            return None

        monkeypatch.setattr(MongoProcessor, "get_endpoints", _return_none)
        monkeypatch.setattr(Utility, "get_action_url", _return_none)
        monkeypatch.setattr(MongoProcessor, "load_domain", _return_none)
        monkeypatch.setattr(Utility, "get_local_mongo_store", _return_none)
        monkeypatch.setattr(MongoProcessor, "get_endpoints", _return_none)

    def test_reload(self, mock_agent_properties):
        assert not AgentProcessor.cache_provider.get(pytest.bot)

        AgentProcessor.reload(pytest.bot)
        assert AgentProcessor.cache_provider.get(pytest.bot)

    def test_reload_exception(self, mock_agent_properties):
        assert not AgentProcessor.cache_provider.get('test_user')

        with pytest.raises(AppException) as e:
            AgentProcessor.reload('test_user')
        assert str(e).__contains__("Bot has not been trained yet!")

    def test_get_agent_not_exists(self):
        with pytest.raises(AppException) as e:
            AgentProcessor.get_agent('test_user')
        assert str(e).__contains__("Bot has not been trained yet!")

    def test_get_agent(self):
        assert AgentProcessor.get_agent(pytest.bot)

    def test_get_agent_not_cached(self, mock_agent_properties):
        assert AgentProcessor.get_agent(pytest.bot)

    def test_get_agent_custom_metric_apm_disabled(self, mock_agent_properties):
        assert AgentProcessor.get_agent(pytest.bot)
        assert AgentProcessor.cache_provider.len() >= 1

    @elasticmock
    def test_get_agent_custom_metric_apm_enabled(self, monkeypatch):

        monkeypatch.setitem(Utility.environment["elasticsearch"], 'enable', True)
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'service_name', "kairon")
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'apm_server_url', "http://localhost:8082")

        assert AgentProcessor.get_agent(pytest.bot)
        assert AgentProcessor.cache_provider.len() >= 1
