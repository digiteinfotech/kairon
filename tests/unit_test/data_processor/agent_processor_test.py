import os
import shutil
from unittest import mock
from unittest.mock import patch

import bson
import pytest
from mongoengine import connect
from rasa.core.lock_store import InMemoryLockStore
from redis.client import Redis

from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.model_processor import ModelProcessor
from kairon.shared.utils import Utility
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
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        bot = bson.ObjectId().__str__()
        pytest.bot = bot
        model_path = os.path.join('models', bot)
        if not os.path.exists(model_path):
            os.mkdir(model_path)
        model_file = train(
            domain='tests/testing_data/model_tester/domain.yml',
            config='tests/testing_data/model_tester/config.yml',
            training_files=['tests/testing_data/model_tester/nlu_with_entities/nlu.yml',
                            'tests/testing_data/model_tester/training_stories_success/stories.yml'],
            output=model_path,
            core_additional_arguments={"augmentation_factor": 100},
            force_training=True
        ).model
        ModelProcessor.set_training_status(
            bot=bot,
            user="test",
            status=EVENT_STATUS.DONE.value,
            model_path=model_file,
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
        model = AgentProcessor.cache_provider.get(pytest.bot)
        assert model
        assert not Utility.check_empty_string(model.model_ver)
        assert isinstance(model.lock_store, InMemoryLockStore)

    def test_reload_model_with_lock_store_config(self, mock_agent_properties):

        with patch.dict(Utility.environment['lock_store'], {'url': 'rediscloud', "password": "password", "port": 6999, "db": 5}):
            AgentProcessor.reload(pytest.bot)
            model = AgentProcessor.cache_provider.get(pytest.bot)
            assert model
            assert not Utility.check_empty_string(model.model_ver)
            assert isinstance(model.lock_store.red, Redis)
            assert model.lock_store.key_prefix == f'{pytest.bot}:lock:'
            assert model.lock_store.red.connection_pool.connection_kwargs == {'db': 5, 'username': None,
                                                                                      'password': 'password',
                                                                                      'socket_timeout': 10,
                                                                                      'encoding': 'utf-8',
                                                                                      'encoding_errors': 'strict',
                                                                                      'decode_responses': False,
                                                                                      'retry_on_timeout': False,
                                                                                      'health_check_interval': 0,
                                                                                      'client_name': None,
                                                                                      'host': 'rediscloud',
                                                                                      'port': 6999,
                                                                                      'socket_connect_timeout': None,
                                                                                      'socket_keepalive': None,
                                                                                      'socket_keepalive_options': None}

        with patch.dict(Utility.environment['lock_store'], {'url': 'rediscloud'}):
            AgentProcessor.reload(pytest.bot)
            model = AgentProcessor.cache_provider.get(pytest.bot)
            assert model
            assert not Utility.check_empty_string(model.model_ver)
            assert isinstance(model.lock_store.red, Redis)
            assert model.lock_store.key_prefix == f'{pytest.bot}:lock:'
            assert model.lock_store.red.connection_pool.connection_kwargs == {'db': 1, 'username': None,
                                                                                      'password': None,
                                                                                      'socket_timeout': 10,
                                                                                      'encoding': 'utf-8',
                                                                                      'encoding_errors': 'strict',
                                                                                      'decode_responses': False,
                                                                                      'retry_on_timeout': False,
                                                                                      'health_check_interval': 0,
                                                                                      'client_name': None,
                                                                                      'host': 'rediscloud',
                                                                                      'port': 6379,
                                                                                      'socket_connect_timeout': None,
                                                                                      'socket_keepalive': None,
                                                                                      'socket_keepalive_options': None}

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
        model = AgentProcessor.get_agent(pytest.bot)
        assert model
        assert len(list(ModelProcessor.get_training_history(pytest.bot))) == 1
        assert not Utility.check_empty_string(model.model_ver)

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

    @mock.patch("kairon.chat.agent_processor.AgentProcessor.reload", autospec=True)
    @mock.patch("kairon.shared.data.model_processor.ModelProcessor.get_latest_model_version")
    def test_get_agent_after_new_model_training(self, mock_get_latest_model_version, mock_reload):
        mock_get_latest_model_version.return_value = "v1.tar.zip"
        assert AgentProcessor.get_agent(pytest.bot)
        mock_reload.assert_called_once()
