import json
from typing import List, Any, Text, Dict

import requests

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.factory import WhatsappFactory
from kairon.exceptions import AppException
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.channels.broadcast.data_extraction import MessageBroadcastUsingDataExtraction
from kairon.shared.chat.notifications.constants import MessageBroadcastLogType
from kairon.shared.chat.notifications.processor import MessageBroadcastProcessor
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import ChannelTypes, ActorType
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.processor import MongoProcessor
from loguru import logger
from mongoengine import DoesNotExist


class WhatsappBroadcast(MessageBroadcastUsingDataExtraction):

    def get_recipients(self, data: Any, **kwargs):
        eval_log = None

        if not Utility.check_empty_string(self.config.get('pyscript')):
            logger.debug("Skipping get_recipients as pyscript exists!")
            return

        expr = self.config["recipients_config"]["recipients"]
        expr_type = self.config["recipients_config"]["recipient_type"]
        try:
            if expr_type == "static":
                recipients = [number.strip() for number in expr.split(',')]
            else:
                recipients, eval_log = ActionUtility.evaluate_script(expr, data)
        except Exception as e:
            raise AppException(f"Failed to evaluate {expr_type} recipients expression: {e}")
        if not isinstance(recipients, List):
            raise AppException(f"recipients evaluated to unexpected data type: {recipients}")
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, recipients=recipients,
            status=EVENT_STATUS.EVALUATE_RECIPIENTS.value, evaluation_log=eval_log
        )
        return recipients

    def send(self, recipients: List, data: Any, **kwargs):
        if Utility.check_empty_string(self.config.get('pyscript')):
            self.__send_using_configuration(recipients, data)
        else:
            self.__send_using_pyscript()

    def __send_using_pyscript(self):
        from kairon.shared.concurrency.orchestrator import ActorOrchestrator

        script = self.config['pyscript']
        timeout = self.config.get('pyscript_timeout', 10)
        channel_client = self.__get_client()
        failure_cnt = 0
        total = 0

        def send_msg(template_id: Text, recipient, language_code: Text = "en", components: Dict = None, namespace: Text = None):
            nonlocal failure_cnt
            nonlocal total

            response = channel_client.send_template_message(template_id, recipient, language_code, components, namespace)
            status = "Failed" if response.get("errors") else "Success"
            total += 1
            if status == "Failed":
                failure_cnt = failure_cnt + 1

            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.send.value, self.reference_id, api_response=response,
                status=status, recipient=recipient, template_params=components
            )
            return response

        def log(**kwargs):
            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.self.value, self.reference_id, **kwargs
            )

        script_variables = ActorOrchestrator.run(
            ActorType.pyscript_runner.value, source_code=script, timeout=timeout,
            predefined_objects={"requests": requests, "json": json, "send_msg": send_msg, "log": log}
        )
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, failure_cnt=failure_cnt, total=total,
            **script_variables
        )

    def __send_using_configuration(self, recipients: List, data: Any):
        channel_client = self.__get_client()
        total = len(recipients)

        for i, template_config in enumerate(self.config['template_config']):
            failure_cnt = 0
            template_id = template_config["template_id"]
            namespace = template_config.get("namespace")
            lang = template_config["language"]
            template_params = self._get_template_parameters(template_config, data)

            # if there's no template body, pass params as None for all recipients
            template_params = template_params if template_params else [template_params] * len(recipients)
            num_msg = len(list(zip(recipients, template_params)))
            evaluation_log = {
                f"Template {i + 1}": f"There are {total} recipients and {len(template_params)} template bodies. "
                                     f"Sending {num_msg} messages to {num_msg} recipients."
            }

            for recipient, t_params in zip(recipients, template_params):
                recipient = str(recipient) if recipient else ""
                if not Utility.check_empty_string(recipient):
                    response = channel_client.send_template_message(template_id, recipient, lang, t_params, namespace=namespace)
                    status = "Failed" if response.get("errors") else "Success"
                    if status == "Failed":
                        failure_cnt = failure_cnt + 1
                    MessageBroadcastProcessor.add_event_log(
                        self.bot, MessageBroadcastLogType.send.value, self.reference_id, api_response=response,
                        status=status, recipient=recipient, template_params=t_params
                    )
            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.common.value, self.reference_id, failure_cnt=failure_cnt, total=total,
                **evaluation_log
            )

    def __get_client(self):
        try:
            bot_settings = MongoProcessor.get_bot_settings(self.bot, self.user)
            channel_config = ChatDataProcessor.get_channel_config(ChannelTypes.WHATSAPP.value, self.bot, mask_characters=False)
            access_token = channel_config["config"].get('api_key') or channel_config["config"].get('access_token')
            channel_client = WhatsappFactory.get_client(bot_settings["whatsapp"])
            channel_client = channel_client(access_token, config=channel_config)
            return channel_client
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException(f"Whatsapp channel config not found!")
