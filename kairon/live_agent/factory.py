from typing import Dict, Text

from kairon.exceptions import AppException
from kairon.live_agent.chatwoot import ChatwootLiveAgent


class LiveAgentFactory:

    """
    Factory to get live agent implementation.
    """

    agent_systems = {
        "chatwoot": ChatwootLiveAgent
    }

    @staticmethod
    def get_agent(agent_type: Text, config: Dict):
        """
        Fetches live agent implementation.

        :param agent_type: one of supported types - chatwoot.
        :param config: agent configuration as dict.
        """
        if not LiveAgentFactory.agent_systems.get(agent_type):
            raise AppException('Agent system not supported')
        return LiveAgentFactory.agent_systems[agent_type].from_config(config)
