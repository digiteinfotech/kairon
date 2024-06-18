import ujson as json
from typing import List, Text, Dict

import pymongo
import requests
from uuid6 import uuid7

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
            recipients = [f"91{number}" if len(number) == 10 else number for number in recipients]
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

    def __send_using_pyscript(self):
        from kairon.shared.concurrency.orchestrator import ActorOrchestrator

        script = self.config['pyscript']
        timeout = self.config.get('pyscript_timeout', 60)
        channel_client = self.__get_client()
        client = self.__get_db_client()

        def send_msg(template_id: Text, recipient, language_code: Text = "en", components: Dict = None, namespace: Text = None):
            recipient = f"91{recipient}" if len(recipient) == 10 else recipient
            response = channel_client.send_template_message(template_id, recipient, language_code, components, namespace)
            status = "Failed" if response.get("error") else "Success"
            raw_template = self.__get_template(template_id, language_code)

            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.send.value, self.reference_id, api_response=response,
                status=status, recipient=recipient, template_params=components, template=raw_template,
                event_id=self.event_id, template_name=template_id
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

    def __send_using_configuration(self, recipients: List):
        channel_client = self.__get_client()
        total = len(recipients)
        db_client = self.__get_db_client()

        for i, template_config in enumerate(self.config['template_config']):
            failure_cnt = 0
            template_id = template_config["template_id"]
            namespace = template_config.get("namespace")
            lang = template_config["language"]
            template_params = self._get_template_parameters(template_config)
            raw_template = self.__get_template(template_id, lang)

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
                    response = channel_client.send_template_message(template_id, recipient, lang, t_params, namespace=namespace)
                    status = "Failed" if response.get("errors") else "Success"
                    if status == "Failed":
                        failure_cnt = failure_cnt + 1

                    MessageBroadcastProcessor.add_event_log(
                        self.bot, MessageBroadcastLogType.send.value, self.reference_id, api_response=response,
                        status=status, recipient=recipient, template_params=t_params, template=raw_template,
                        event_id=self.event_id, template_name=template_id
                    )
            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.common.value, self.reference_id, failure_cnt=failure_cnt, total=total,
                event_id=self.event_id, **evaluation_log
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

    def __get_template(self, name: Text, language: Text):
        for template in BSP360Dialog(self.bot, self.user).list_templates(**{"business_templates.name": name}):
            if template.get("language") == language:
                return template.get("components")

    def __log_broadcast_in_conversation_history(self, template_id, contact: Text, template_params, template, mongo_client):
        import time

        mongo_client.insert_one({
            "type": "broadcast", "sender_id": contact, "conversation_id": uuid7().hex, "timestamp": time.time(),
            "data": {"name":template_id, "template": template, "template_params": template_params}
        })

    def __get_db_client(self):
        config = Utility.get_local_db()
        client = pymongo.MongoClient(
            host=config['host'], username=config.get('username'), password=config.get('password'),
            authSource=config['options'].get("authSource") if config['options'].get("authSource") else "admin"
        )
        db = client.get_database(config['db'])
        coll = db.get_collection(self.bot)
        return coll
