import ast
from abc import ABC
from typing import Text, Dict

from kairon.exceptions import AppException
from kairon.shared.channels.broadcast.base import MessageBroadcastBase
from kairon.shared.chat.broadcast.constants import MessageBroadcastLogType
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.data.constant import EVENT_STATUS


class MessageBroadcastFromConfig(MessageBroadcastBase, ABC):

    def __init__(self, bot: Text, user: Text, config: Dict, event_id: Text, reference_id: Text):
        """
        event_id: This is unique for each broadcast config.
        reference_id: Identifies each running broadcast event and associated sent/custom logs uniquely among multiple
                    recurring broadcasts.
        """
        self.bot = bot
        self.user = user
        self.config = config
        self.event_id = event_id
        self.reference_id = reference_id
        self.channel_client = None

    @classmethod
    def from_config(cls, config: Dict, event_id: Text, reference_id: Text):
        return cls(config["bot"], config["user"], config, event_id, reference_id)

    def _get_template_parameters(self, template_config: Dict):
        template_params = template_config.get("data")

        try:
            if template_params:
                template_params = ast.literal_eval(template_params)
        except Exception as e:
            raise AppException(f"Failed to evaluate template: {str(e)}")
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, template_params=template_params,
            status=EVENT_STATUS.EVALUATE_TEMPLATE.value, event_id=self.event_id
        )
        return template_params
