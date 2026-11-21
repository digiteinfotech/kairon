from tests.unit_test.data_processor.data_processor_support import *  # noqa: F403
from tests.unit_test.data_processor.data_processor_support import fast_rasa_training

class TestAgentProcessor:

    def test_get_agent(self, monkeypatch):
        from kairon.chat.agent_processor import AgentProcessor

        def mongo_store(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
        agent = AgentProcessor.get_agent("tests")
        assert isinstance(agent, Agent)

    def test_get_agent_from_cache(self):
        from kairon.chat.agent_processor import AgentProcessor

        agent = AgentProcessor.get_agent("tests")
        assert isinstance(agent, Agent)

    def test_get_agent_from_cache_does_not_exists(self):
        from kairon.chat.agent_processor import AgentProcessor

        with pytest.raises(AppException):
            agent = AgentProcessor.get_agent("test")
            assert isinstance(agent, Agent)
