import ast
from abc import ABC
from typing import Text, Dict, Any

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.channels.broadcast.base import MessageBroadcastBase
from kairon.shared.chat.notifications.constants import MessageBroadcastLogType
from kairon.shared.chat.notifications.processor import MessageBroadcastProcessor
from kairon.shared.data.constant import EVENT_STATUS


class MessageBroadcastUsingDataExtraction(MessageBroadcastBase, ABC):

    def __init__(self, bot: Text, user: Text, config: Dict, reference_id: Text = None):
        self.bot = bot
        self.user = user
        self.config = config
        self.reference_id = reference_id

    @classmethod
    def from_config(cls, config: Dict, reference_id: Text = None):
        return cls(config["bot"], config["user"], config, reference_id)

    def pull_data(self):
        data = {}
        extraction_log = {}
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, status=EVENT_STATUS.TRIGGERED_API.value
        )
        if self.config.get('data_extraction_config'):
            url = self.config["data_extraction_config"]["url"]
            method = self.config["data_extraction_config"]["method"]
            headers = self.config["data_extraction_config"].get("headers")
            data = Utility.execute_http_request(method, url, headers=headers)
            extraction_log['url'] = url
            extraction_log['headers'] = headers
            extraction_log['method'] = method
            extraction_log['api_response'] = data
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, data_extraction=extraction_log,
            status=EVENT_STATUS.DATA_EXTRACTED.value
        )
        return data

    def _get_template_parameters(self, template_config: Dict, data: Any):
        eval_log = None
        template_params = template_config.get("data")
        try:
            if template_params:
                if template_config["template_type"] == "dynamic":
                    template_params, eval_log = ActionUtility.evaluate_script(template_params, data)
                else:
                    template_params = ast.literal_eval(template_params)
        except Exception as e:
            raise AppException(f"Failed to evaluate {template_config['template_type']} template expression: {str(e)}")
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, template_params=template_params,
            status=EVENT_STATUS.EVALUATE_TEMPLATE.value, evaluation_log=eval_log
        )
        return template_params
