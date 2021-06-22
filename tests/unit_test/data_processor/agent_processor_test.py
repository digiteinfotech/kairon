import os
import shutil

import pytest

from kairon import Utility
from kairon.data_processor.agent_processor import AgentProcessor
from kairon.data_processor.processor import MongoProcessor
from kairon.exceptions import AppException


class TestAgentProcessor:

    @pytest.fixture(autouse=True)
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        bot = 'agent_testing_user'
        pytest.bot = bot
        model_path = os.path.join('models', bot)
        os.mkdir(model_path)
        shutil.copy('tests/testing_data/model/20210512-172208.tar.gz', model_path)
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
        assert str(e).__contains__("Bot has not been trained yet !")

    def test_get_agent_not_exists(self):
        with pytest.raises(AppException) as e:
            AgentProcessor.get_agent('test_user')
        assert str(e).__contains__("Bot has not been trained yet !")

    def test_get_agent(self):
        assert AgentProcessor.get_agent(pytest.bot)

    def test_get_agent_not_cached(self, mock_agent_properties):
        AgentProcessor.cache_provider = Utility.create_cache()
        assert AgentProcessor.get_agent(pytest.bot)
