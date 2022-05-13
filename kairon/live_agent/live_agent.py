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
    def from_bot(cls, bot: Text, raise_error: bool = False):
        """
        Fetches live agent implementation from bot id.

        :param bot: bot id
        :param raise_error: raise error if not agent configuration found. False, by default.
        """
        from kairon.live_agent.factory import LiveAgentFactory

        try:
            config = LiveAgentsProcessor.get_config(bot, mask_characters=False)
            return LiveAgentFactory.get_agent(config["agent_type"], config["config"])
        except DoesNotExist:
            if raise_error:
                raise AppException("Live agent system not configured")
