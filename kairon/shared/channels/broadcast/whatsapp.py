import asyncio
from datetime import datetime
from functools import partial

import ujson as json
from typing import List, Text, Dict

import requests

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.factory import WhatsappFactory
from kairon.exceptions import AppException
from kairon.shared.channels.broadcast.from_config import MessageBroadcastFromConfig
from kairon.shared.channels.whatsapp.bsp.dialog360 import BSP360Dialog
from kairon.shared.chat.agent.agent_flow import AgenticFlow
from kairon.shared.chat.broadcast.constants import MessageBroadcastLogType, MessageBroadcastType
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import ChannelTypes, ActorType
from kairon.shared.data.collection_processor import DataProcessor
from kairon.shared.data.constant import EVENT_STATUS, MEDIA_TYPES, STATUSES
from kairon.shared.data.processor import MongoProcessor
from loguru import logger
from mongoengine import DoesNotExist
from more_itertools import chunked


class WhatsappBroadcast(MessageBroadcastFromConfig):

    def get_recipients(self, **kwargs):
        eval_log = None

        if self.config["broadcast_type"] == MessageBroadcastType.dynamic.value:
            logger.debug("Skipping get_recipients as broadcast_type is dynamic!")
            return

        if self.config.get('collection_config'):
            logger.debug("Skipping get_recipients as collection_config is present!")
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
        elif self.config["broadcast_type"] == MessageBroadcastType.flow.value:
            self.__send_using_flow(recipients)
        else:
            self.__send_using_pyscript()

    async def send_template_message(self, template_id: Text, recipient, language_code: Text = "en", components: list = None,
                                 namespace: Text = None, flowname: Text = None):
        if not self.channel_client:
            self.channel_client = self.__get_client()

        if flowname:
            flow = AgenticFlow(self.bot)
            resps, _ = await flow.execute_rule(flowname, sender_id=recipient)
            if  resps:
                resp = resps[0]
                if txt := resp.get('text'):
                    components = json.loads(txt)
                elif custom := resp.get('custom'):
                    components = custom


        status_flag, status_code, response = await self.channel_client.send_template_message_async(template_id,
                                                                                              recipient,
                                                                                              language_code,
                                                                                              components,
                                                                                              namespace)
        status = STATUSES.FAIL.value if response.get("error") else STATUSES.SUCCESS.value

        if status == STATUSES.FAIL.value:
            return status_flag, status_code, response

        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.send.value, self.reference_id, api_response=response,
            status=status, recipient=recipient, template_params=components,
            event_id=self.event_id, template_name=template_id, language_code=language_code, namespace=namespace,
            retry_count=0, status_code=status_code
        )

        return status_flag, status_code, response

    async def send_template_message_retry(self, template_id: Text, recipient, retry_count, template, language_code: Text = "en",
                                    components: Dict = None,
                                    namespace: Text = None):
        if not self.channel_client:
            self.channel_client = self.__get_client()
        status_flag, status_code, response = await self.channel_client.send_template_message_async(template_id,
                                                                                                   recipient,
                                                                                                   language_code,
                                                                                                   components,
                                                                                                   namespace)
        status = STATUSES.FAIL.value if response.get("error") else STATUSES.SUCCESS.value

        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.resend.value, self.reference_id, api_response=response,
            status=status, recipient=recipient, template_params=components,
            event_id=self.event_id, template_name=template_id, language_code=language_code, namespace=namespace,
            retry_count=retry_count, status_code=status_code, template=template
        )

        return status_flag, status_code, response

    def log_failed_messages(self,
                                messages: list,
                                error_msg:str = "terminated broadcast",
                                broadcast_log_type:str = MessageBroadcastLogType.send.value,
                                ):
        retry_count = 0
        for message in messages:
            if broadcast_log_type == MessageBroadcastLogType.send.value:
                template_id, recipient, language_code, components, namespace = message
            else:
                template_id, recipient, retry_count, language_code, components, namespace = message
            MessageBroadcastProcessor.add_event_log(
                self.bot, broadcast_log_type, self.reference_id, api_response={"error": error_msg},
                status=STATUSES.FAIL.value, recipient=recipient, template_params=components,
                event_id=self.event_id, template_name=template_id, language_code=language_code, namespace=namespace,
                retry_count=retry_count, errors =[{'code':131026,
                                                   'title': "Message undeliverable",
                                                   'message':error_msg}]
            )

    def initiate_broadcast(self, message_list: list, is_resend: bool=False):
        batch_size = Utility.environment["broadcast"]["whatsapp_broadcast_batch_size"]
        rate_per_second = Utility.environment["broadcast"]["whatsapp_broadcast_rate_per_second"]
        max_batches_per_second = rate_per_second // batch_size

        last_time = datetime.utcnow()
        batches_sent_in_current_second = 0
        non_sent_recipients = []
        sent_count = 0
        done_till = 0
        total_count = len(message_list)

        for chunk in chunked(message_list, batch_size):
            tasks = []
            if is_resend:
                tasks = [self.send_template_message_retry(*msg) for msg in chunk]
            else:
                tasks = [self.send_template_message(*msg) for msg in chunk]
            async def run_async(tasks_to_run):
                failed_to_send_recipients = []
                results = await asyncio.gather(*tasks_to_run)
                fails = [not result[0] for result in results]
                for msg, fail in zip(chunk, fails):
                    if fail:
                        failed_to_send_recipients.append(msg[1])

                return  all(fails) , failed_to_send_recipients

            all_failed, failed_recipients  = asyncio.run(run_async(tasks))
            done_till += len(tasks)

            if all_failed:
                break
            non_sent_recipients.extend(failed_recipients)
            sent_count += len(tasks) - len(failed_recipients)
            MessageBroadcastProcessor.upsert_broadcast_progress_log(self.bot,
                                                                    self.reference_id,
                                                                    self.event_id,
                                                                    done_till,
                                                                    total_count)

            batches_sent_in_current_second += 1

            if batches_sent_in_current_second >= max_batches_per_second:
                current_time = datetime.utcnow()
                time_diff = (current_time - last_time).total_seconds()
                if time_diff < 1:
                    asyncio.run(asyncio.sleep(1 - time_diff))
                last_time = datetime.utcnow()
                batches_sent_in_current_second = 0

        failed_broadcast_log_type = MessageBroadcastLogType.resend.value if is_resend else MessageBroadcastLogType.send.value

        if done_till < len(message_list):
            self.log_failed_messages(message_list[done_till:], broadcast_log_type=failed_broadcast_log_type)

        return sent_count, non_sent_recipients

    def __send_using_pyscript(self, **kwargs):
        from kairon.shared.concurrency.orchestrator import ActorOrchestrator

        script = self.config['pyscript']
        timeout = self.config.get('pyscript_timeout', 60)
        self.messages_list = []
        self.recipients_list = []

        def send_msg(messages_list :list, recipients_list:list, template_id: Text, recipient, language_code: Text = "en",
                           components: Dict = None, namespace: Text = None):
            messages_list.append((template_id, recipient, language_code, components, namespace, None))
            recipients_list.append(recipient)
            return True

        def log(**kwargs):
            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.self.value, self.reference_id, event_id=self.event_id, **kwargs
            )

        script_variables = ActorOrchestrator.run(
            ActorType.pyscript_runner.value, source_code=script, timeout=timeout,
            predefined_objects={"requests": requests, "json": json, "send_msg": partial(send_msg, self.messages_list, self.recipients_list),
                                "log": log, "messages_list": self.messages_list, "recipients_list": self.recipients_list}
        )

        self.messages_list = script_variables.get("messages_list", [])
        self.recipients_list = script_variables.get("recipients_list", [])

        logger.info(f"Messages to be sent: {len(self.messages_list)}")
        self.has_error = False
        self.sent_count = 0
        self.nonsent_recipients = []

        self.sent_count, self.nonsent_recipients = self.initiate_broadcast(self.messages_list)


        failure_cnt = len(self.nonsent_recipients)
        total = len(self.recipients_list)

        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, failure_cnt=failure_cnt, total=total,
            event_id=self.event_id, nonsent_recipients=self.nonsent_recipients, **script_variables
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

    def __prepare_template_params(self, raw_template, template_id):
        collection_config = self.config.get("collection_config", {})
        collection_name = collection_config.get("collection")
        filters = collection_config.get("filters_list", [])
        field_mapping = collection_config.get("field_mapping", {}).get(template_id)
        number_field = collection_config.get("number_field")

        crud_data = DataProcessor.get_broadcast_collection_data(self.bot, collection_name, filters)

        example_map = {item.get("type"): item.get("example", {}) for item in raw_template}

        def _default_text(section_type: str, field_name: str) -> str:
            """Fetch default text value from example_map."""
            example = example_map.get(section_type, {})
            return (
                    example.get("header_text", [None])[0]
                    or (example.get("body_text", [[None]])[0][0])
                    or f"<{field_name}>"
            )

        def _default_media(section_type: str, param_type: str) -> str:
            """Fetch default media link from example_map."""
            example = example_map.get(section_type, {})
            return (
                    example.get("header_handle", [None])[0]
                    or (example.get("body_handle", [[None]])[0][0])
                    or example.get(param_type, {}).get("link", f"<{param_type}_link>")
            )

        def _map_field_value(value: str, record: dict, section_type: str, param_type: str) -> str:
            """Resolve placeholder {field} → actual value or default."""
            import re
            PLACEHOLDER_PATTERN = re.compile(r"^{(.+)}$")

            match = PLACEHOLDER_PATTERN.match(value)
            if not match:
                return value
            field_name = match.group(1)

            if param_type == "text":
                return record.get(field_name) or _default_text(section_type, field_name)
            if param_type in MEDIA_TYPES:
                media_link = record.get(field_name)
                return media_link or _default_media(section_type, param_type)
            return value

        def _build_param(param: dict, record: dict, section_type: str) -> dict:
            """Build a single parameter dict based on type."""
            param_type = param.get("type", "text")

            if param_type == "text" and "text" in param:
                text_val = param["text"]
                resolved = _map_field_value(text_val, record, section_type, "text")
                return {"type": "text", "text": str(resolved)}

            if param_type in MEDIA_TYPES and param_type in param:
                media_dict = param[param_type]

                if "id" in media_dict:
                    return {"type": param_type, param_type: {"id": media_dict["id"]}}

                if "link" in media_dict:
                    link_val = media_dict["link"]
                    resolved_link = _map_field_value(link_val, record, section_type, param_type)
                    return {"type": param_type, param_type: {"link": str(resolved_link)}}

            return param

        template_params, recipients = [], []

        for record in crud_data:
            record_params = [
                {
                    "type": comp["type"],
                    "parameters": [
                        _build_param(param, record, comp.get("type", "").upper())
                        for param in comp.get("parameters", [])
                    ],
                }
                for comp in field_mapping
            ]

            template_params.append(record_params)

            if mobile := record.get(number_field):
                recipients.append(mobile)

        return template_params, recipients

    def __send_using_configuration(self, recipients: List):

        for i, template_config in enumerate(self.config['template_config']):

            template_id = template_config["template_id"]
            namespace = template_config.get("namespace")
            lang = template_config["language"]
            raw_template, template_exception = self.__get_template(template_id, lang)

            if self.config.get('collection_config'):
                template_params, recipients = self.__prepare_template_params(raw_template, template_id)
            else:
                template_params = self._get_template_parameters(template_config)

                template_params = template_params * len(recipients) if template_params \
                    else [template_params] * len(recipients)

            total = len(recipients)
            num_msg = len(list(zip(recipients, template_params)))
            evaluation_log = {
                f"Template {i + 1}":
                    f"[{template_id}] There are {total} recipients and {len(template_params)} template bodies. "
                    f"Sending {num_msg} messages to {num_msg} recipients."
            }

            message_list = []

            for recipient, t_params in zip(recipients, template_params):
                recipient = str(recipient) if recipient else ""
                if not Utility.check_empty_string(recipient):

                    message_list.append((template_id, recipient, lang, t_params, namespace, None))

            _, non_sent_recipients = self.initiate_broadcast(message_list)
            failure_cnt = len(non_sent_recipients)

            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.common.value, self.reference_id, failure_cnt=failure_cnt, total=total,
                event_id=self.event_id, nonsent_recipients=non_sent_recipients,
                template_params=template_params, recipients=recipients, **evaluation_log
            )

            MessageBroadcastProcessor.update_broadcast_logs_with_template(
                self.reference_id, self.event_id, raw_template=raw_template,
                log_type=MessageBroadcastLogType.send.value, retry_count=0,
                template_exception=template_exception
            )

    def __send_using_flow(self, recipients: List, **kwargs):
        total = len(recipients)
        flowname = self.config.get("flowname")
        for i, template_config in enumerate(self.config['template_config']):
            template_id = template_config["template_id"]
            namespace = template_config.get("namespace")
            lang = template_config["language"]
            template_params = self._get_template_parameters(template_config)
            raw_template, template_exception = self.__get_template(template_id, lang)
            template_params = template_params * len(recipients) if template_params else [template_params] * len(
                recipients)
            num_msg = len(list(zip(recipients, template_params)))
            evaluation_log = {
                f"Template {i + 1}": f"There are {total} recipients and {len(template_params)} template bodies. "
                                     f"Sending {num_msg} messages to {num_msg} recipients."
            }

            message_list = []


            for recipient, t_params in zip(recipients, template_params):
                recipient = str(recipient) if recipient else ""
                if not Utility.check_empty_string(recipient):


                    message_list.append((template_id, recipient, lang, t_params, namespace, flowname))

            _, non_sent_recipients = self.initiate_broadcast(message_list)
            failure_cnt = len(non_sent_recipients)

            MessageBroadcastProcessor.add_event_log(
                self.bot, MessageBroadcastLogType.common.value, self.reference_id, failure_cnt=failure_cnt, total=total,
                event_id=self.event_id, nonsent_recipients=non_sent_recipients, **evaluation_log
            )

            MessageBroadcastProcessor.update_broadcast_logs_with_template(
                self.reference_id, self.event_id, raw_template=raw_template,
                log_type=MessageBroadcastLogType.send.value, retry_count=0,
                template_exception=template_exception
            )




    def resend_broadcast(self):
        config = MessageBroadcastProcessor.get_settings(self.event_id, self.bot, is_resend=True)
        retry_count = config["retry_count"]

        message_broadcast_logs = MessageBroadcastProcessor.extract_message_ids_from_broadcast_logs(
            self.reference_id, retry_count=retry_count
        )

        broadcast_logs = [log for log in message_broadcast_logs.values() if hasattr(log, "errors") and log.errors]

        codes_to_exclude = Utility.environment["channels"]["360dialog"]["error_codes"]
        required_logs = [log for log in broadcast_logs if log["errors"][0]["code"] not in codes_to_exclude]
        retry_count += 1
        total = len(required_logs)
        skipped_count = len(broadcast_logs) - total
        template_name = required_logs[0]["template_name"]
        language_code = required_logs[0]["language_code"]
        template, template_exception = self.__get_template(template_name, language_code)

        message_list = []

        for log in required_logs:
            template_id = log["template_name"]
            namespace = log["namespace"]
            language_code = log["language_code"]
            components = log["template_params"]
            recipient = log["recipient"]
            template = log.template if hasattr(log, "template") else template
            message_list.append((template_id, recipient, retry_count, template, language_code, components, namespace))

        status_count_key = f"retry_count_{retry_count}_status"
        MessageBroadcastProcessor.add_event_log(
            self.bot, MessageBroadcastLogType.common.value, self.reference_id, **{status_count_key: EVENT_STATUS.INPROGRESS.value}
        )

        try :
            _, non_sent_recipients = self.initiate_broadcast(message_list, is_resend=True)
            failure_cnt = len(non_sent_recipients)
            status = EVENT_STATUS.COMPLETED.value
        except Exception:
            failure_cnt = len(message_list)
            status = EVENT_STATUS.FAIL.value

        kwargs = {
            f"template_exception_{retry_count}": template_exception,
            f"template_{retry_count}": template,
            f"failure_count_{retry_count}": failure_cnt,
            f"resend_count_{retry_count}": total,
            f"skipped_count_{retry_count}": skipped_count,
            f"retry_{retry_count}_timestamp": datetime.utcnow(),
            f"retry_count_{retry_count}_status" : status,
            "retry_count": retry_count
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