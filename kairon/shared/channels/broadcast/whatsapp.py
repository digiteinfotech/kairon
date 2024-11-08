from datetime import datetime

import ujson as json
from typing import List, Text, Dict

import requests

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.factory import WhatsappFactory
from kairon.exceptions import AppException
from kairon.shared.channels.broadcast.from_config import MessageBroadcastFromConfig
from kairon.shared.channels.whatsapp.bsp.dialog360 import BSP360Dialog
from kairon.shared.chat.broadcast.constants import MessageBroadcastLogType, MessageBroadcastType
from kairon.shared.chat.broadcast.data_objects import MessageBroadcastLogs
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import ChannelTypes, ActorType
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.processor import MongoProcessor
from loguru import logger
from mongoengine import DoesNotExist


class WhatsappBroadcast(MessageBroadcastFromConfig):

    def get_recipients(self, **kwargs):
        eval_log = None

        if self.config["broadcast_type"] == MessageBroadcastType.dynamic.value:
            logger.debug("Skipping get_recipients as broadcast_type is dynamic!")
            return

        try:
            expr = self.config["recipients_config"]["recipients"]
            recipients = [number.strip() for number in expr.split(',')]
            recipients = list(set(recipients))
        except Exception as e:
            raise AppException(f"Failed to evaluate recipients: {e}")

        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, recipients=recipients,
            status=EVENT_STATUS.EVALUATE_RECIPIENTS.value, evaluation_log=eval_log, event_id=self.event_id
        )
        return recipients

    def send(self, recipients: List, **kwargs):
        if self.config["broadcast_type"] == MessageBroadcastType.static.value:
            self.__send_using_configuration(recipients)
        else:
            self.__send_using_pyscript()

    def __send_using_pyscript(self, **kwargs):
        from kairon.shared.concurrency.orchestrator import ActorOrchestrator

        script = self.config['pyscript']
        timeout = self.config.get('pyscript_timeout', 60)
        channel_client = self.__get_client()

        def send_msg(template_id: Text, recipient, language_code: Text = "en", components: Dict = None, namespace: Text = None):
            response = channel_client.send_template_message(template_id, recipient, language_code, components, namespace)
            status = "Failed" if response.get("error") else "Success"

            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.send.value, self.reference_id, api_response=response,
                status=status, recipient=recipient, template_params=components,
                event_id=self.event_id, template_name=template_id, language_code=language_code, namespace=namespace,
                retry_count=0
            )

            return response

        def log(**kwargs):
            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.self.value, self.reference_id, event_id=self.event_id, **kwargs
            )

        script_variables = ActorOrchestrator.run(
            ActorType.pyscript_runner.value, source_code=script, timeout=timeout,
            predefined_objects={"requests": requests, "json": json, "send_msg": send_msg, "log": log}
        )
        failure_cnt = MongoProcessor.get_row_count(MessageBroadcastLogs, self.bot, reference_id=self.reference_id, log_type=MessageBroadcastLogType.send, status="Failed")
        total = MongoProcessor.get_row_count(MessageBroadcastLogs, self.bot, reference_id=self.reference_id, log_type=MessageBroadcastLogType.send)

        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, failure_cnt=failure_cnt, total=total,
            event_id=self.event_id, **script_variables
        )

        template_name = self.config['template_name']
        language_code = self.config['language_code']

        raw_template, template_exception = self.__get_template(template_name, language_code)
        raw_template = raw_template if raw_template else []
        MessageBroadcastProcessor.update_broadcast_logs_with_template(
            self.reference_id, self.event_id, raw_template=raw_template,
            log_type=MessageBroadcastLogType.send.value, retry_count=0,
            template_exception=template_exception
        )

    def __send_using_configuration(self, recipients: List):
        channel_client = self.__get_client()
        total = len(recipients)

        for i, template_config in enumerate(self.config['template_config']):
            failure_cnt = 0
            template_id = template_config["template_id"]
            namespace = template_config.get("namespace")
            lang = template_config["language"]
            template_params = self._get_template_parameters(template_config)
            raw_template, template_exception = self.__get_template(template_id, lang)

            # if there's no template body, pass params as None for all recipients
            template_params = template_params * len(recipients) if template_params else [template_params] * len(recipients)
            num_msg = len(list(zip(recipients, template_params)))
            evaluation_log = {
                f"Template {i + 1}": f"There are {total} recipients and {len(template_params)} template bodies. "
                                     f"Sending {num_msg} messages to {num_msg} recipients."
            }

            for recipient, t_params in zip(recipients, template_params):
                recipient = str(recipient) if recipient else ""
                if not Utility.check_empty_string(recipient):
                    response = channel_client.send_template_message(template_id, recipient, lang, t_params,
                                                                    namespace=namespace)
                    status = "Failed" if response.get("errors") else "Success"
                    if status == "Failed":
                        failure_cnt = failure_cnt + 1

                    MessageBroadcastProcessor.add_event_log(
                        self.bot, MessageBroadcastLogType.send.value, self.reference_id, api_response=response,
                        status=status, recipient=recipient, template_params=t_params, template=raw_template,
                        event_id=self.event_id, template_name=template_id, language_code=lang, namespace=namespace,
                        retry_count=0, template_exception=template_exception
                    )
            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.common.value, self.reference_id, failure_cnt=failure_cnt, total=total,
                event_id=self.event_id, **evaluation_log
            )

    def resend_broadcast(self):
        config = MessageBroadcastProcessor.get_settings(self.event_id, self.bot, is_resend=True)
        retry_count = config["retry_count"]

        message_broadcast_logs = MessageBroadcastProcessor.extract_message_ids_from_broadcast_logs(
            self.reference_id, retry_count=retry_count
        )

        broadcast_logs = [log for log in message_broadcast_logs.values() if log["errors"]]
        codes_to_exclude = Utility.environment["channels"]["360dialog"]["error_codes"]
        required_logs = [log for log in broadcast_logs if log["errors"][0]["code"] not in codes_to_exclude]
        channel_client = self.__get_client()
        retry_count += 1
        failure_cnt = 0
        total = len(required_logs)
        skipped_count = len(broadcast_logs) - total
        template_name = required_logs[0]["template_name"]
        language_code = required_logs[0]["language_code"]
        template, template_exception = self.__get_template(template_name, language_code)

        for log in required_logs:
            template_id = log["template_name"]
            namespace = log["namespace"]
            language_code = log["language_code"]
            components = log["template_params"]
            recipient = log["recipient"]
            template = log.template if log.template else template
            response = channel_client.send_template_message(template_id, recipient, language_code, components,
                                                            namespace)
            status = "Failed" if response.get("error") else "Success"
            if status == "Failed":
                failure_cnt = failure_cnt + 1

            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.resend.value, self.reference_id, api_response=response,
                status=status, recipient=recipient, template_params=components, template=template,
                event_id=self.event_id, template_name=template_id, language_code=language_code, namespace=namespace,
                retry_count=retry_count, template_exception=template_exception
            )
        kwargs = {
            f"resend_count_{retry_count}": total,
            f"skipped_count_{retry_count}": skipped_count,
            f"retry_{retry_count}_timestamp": datetime.utcnow()
        }
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, **kwargs
        )
        config = MessageBroadcastProcessor.update_retry_count(self.event_id, self.bot, self.user,
                                                              retry_count=retry_count)

        return config

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

    def __get_template(self, name: Text, language: Text):
        template_exception = None
        template = []
        try:
            for template in BSP360Dialog(self.bot, self.user).list_templates(**{"business_templates.name": name}):
                if template.get("language") == language:
                    template = template.get("components")
                    break
            return template, template_exception
        except Exception as e:
            logger.exception(e)
            template_exception = str(e)
            return template, template_exception

