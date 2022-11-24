from abc import ABC
from typing import Text

from mongoengine import DoesNotExist

from kairon.exceptions import AppException
from kairon.live_agent.base import LiveAgentBase
from kairon.shared.live_agent.processor import LiveAgentsProcessor


class LiveAgent(LiveAgentBase, ABC):
    """
    Class overriding LiveAgentBase class and provides implementation for
    fetching live agent implementation.
    """

    @classmethod
    def from_bot(cls, bot: Text):
        """
        Fetches live agent implementation from bot id.

        :param bot: bot id

        """
        from kairon.live_agent.factory import LiveAgentFactory

        config = LiveAgentsProcessor.get_config(bot, mask_characters=False)
        return LiveAgentFactory.get_agent(config["agent_type"], config["config"])
