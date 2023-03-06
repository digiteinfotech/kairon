import datetime
import json
from typing import Text

from loguru import logger
from pymongo.errors import ServerSelectionTimeoutError
from rasa.core.channels import UserMessage
from rasa.core.tracker_store import TrackerStore

from .agent_processor import AgentProcessor
from .constants import WABA_GENERATE_KEY, WABA_AUTH_TOKEN, WABA_SET_WEBHOOK, API_HEADER_KEY, GET_WABA_TEMPLATE, \
    GET_WABA_ACCOUNT
from .. import Utility
from ..live_agent.factory import LiveAgentFactory
from ..shared.actions.utils import ActionUtility
from ..shared.chat.processor import ChatDataProcessor
from ..shared.live_agent.processor import LiveAgentsProcessor
from ..shared.metering.constants import MetricType
from ..shared.metering.metering_processor import MeteringProcessor
from pymongo.collection import Collection

class ChatUtils:

    @staticmethod
    async def chat(data: Text, account: int, bot: Text, user: Text, is_integration_user: bool = False):
        model = AgentProcessor.get_agent(bot)
        msg = UserMessage(data, sender_id=user, metadata={"is_integration_user": is_integration_user, "bot": bot,
                                                          "account": account, "channel_type": "chat_client"})
        chat_response = await model.handle_message(msg)
        ChatUtils.__attach_agent_handoff_metadata(account, bot, user, chat_response, model.tracker_store)
        return chat_response

    @staticmethod
    def reload(bot: Text):
        AgentProcessor.reload(bot)

    @staticmethod
    def __attach_agent_handoff_metadata(account: int, bot: Text, sender_id: Text, bot_predictions, tracker):
        metadata = {'initiate': False, 'type': None, "additional_properties": None}
        exception = None
        should_initiate_handoff = False
        try:
            config = LiveAgentsProcessor.get_config(bot, mask_characters=False, raise_error=False)
            if config:
                metadata["type"] = config["agent_type"]
                should_initiate_handoff = ChatUtils.__should_initiate_handoff(bot_predictions, config)
                if should_initiate_handoff:
                    metadata["initiate"] = True
                    live_agent = LiveAgentFactory.get_agent(config["agent_type"], config["config"])
                    metadata["additional_properties"] = live_agent.initiate_handoff(bot, sender_id)
                    businessdata = live_agent.getBusinesshours(config, metadata["additional_properties"]["inbox_id"])
                    if businessdata is not None and businessdata.get("working_hours_enabled"):
                        is_business_hours_enabled = businessdata.get("working_hours_enabled")
                        if is_business_hours_enabled:
                            current_utcnow = datetime.datetime.utcnow()
                            workingstatus = live_agent.validate_businessworkinghours(businessdata, current_utcnow)
                            if not workingstatus:
                                metadata.update({"businessworking":businessdata["out_of_office_message"]})
                                metadata["initiate"] = False
                                bot_predictions["agent_handoff"] = metadata
                                should_initiate_handoff = False
                                return metadata
                    message_trail = ChatUtils.__retrieve_conversation(tracker, sender_id)
                    live_agent.send_conversation_log(message_trail, metadata["additional_properties"]["destination"])
        except Exception as e:
            logger.exception(e)
            exception = str(e)
            metadata['initiate'] = False
        finally:
            if not Utility.check_empty_string(exception) or should_initiate_handoff:
                MeteringProcessor.add_metrics(
                    bot, account, MetricType.agent_handoff, sender_id=sender_id,
                    agent_type=metadata.get("type"), bot_predictions=bot_predictions, exception=exception
                )

        bot_predictions["agent_handoff"] = metadata
        return metadata

    @staticmethod
    def __retrieve_conversation(tracker, sender_id: Text):
        events = TrackerStore.serialise_tracker(tracker.retrieve(sender_id))
        events = json.loads(events)
        _, message_trail = ActionUtility.prepare_message_trail(events.get("events"))
        return message_trail

    @staticmethod
    def __should_initiate_handoff(bot_predictions, agent_handoff_config):
        predicted_intent = bot_predictions["nlu"]["intent"]["name"]
        print(bot_predictions["action"])
        predicted_action = [action.get("action_name") for action in bot_predictions["action"]]
        trigger_on_intent = predicted_intent in set(agent_handoff_config.get("trigger_on_intents", []))
        trigger_on_action = len(set(predicted_action).intersection(set(agent_handoff_config.get("trigger_on_actions", [])))) > 0
        return agent_handoff_config["override_bot"] or trigger_on_intent or trigger_on_action

    @staticmethod
    def get_last_session_conversation(bot: Text, sender_id: Text):

        """
        List conversation events in last session.

        :param bot: bot id
        :param sender_id: user id
        :return: list of conversation events
        """

        events = []
        message = None

        try:
            host = Utility.environment['database']['url']
            db = Utility.environment['database']['test_db']
            client = Utility.create_mongo_client(host)
            with client as client:
                db = client.get_database(db)
                conversations = db.get_collection(bot)
                last_session = ChatUtils.get_last_session(conversations, sender_id)
                if not last_session:
                    return events, message
                events = list(conversations.aggregate([
                    {"$match": {"sender_id": sender_id, "event.timestamp": {"$gt": last_session['event']['timestamp']}}},
                    {"$match": {"event.event": {"$in": ["session_started", "user", "bot"]}}},
                    {"$project": {"sender_id": 1, "event.event": 1, "event.timestamp": 1, "event.text": 1,
                                  "event.data": 1}},
                    {"$group": {"_id": "$sender_id", "events": {"$push": "$event"}}},
                ]))
                print(events)
                if events:
                    events = events[0]['events']
        except ServerSelectionTimeoutError as e:
            logger.error(e)
            message = f'Failed to retrieve conversation: {e}'
        except Exception as e:
            logger.error(e)
            message = f'Failed to retrieve conversation: {e}'
        return events, message

    @staticmethod
    def get_last_session(conversations: Collection, sender_id: Text):
        last_session = list(conversations.aggregate([
            {"$match": {"sender_id": sender_id, "event.event": "session_started"}},
            {"$group": {"_id": "$sender_id", "event": {"$last": "$event"}}},
        ]))
        return last_session[0] if last_session else None

    @staticmethod
    def get_partners_auth_token():
        base_url_hub = Utility.environment["waba_partner"]["base_url_hub"]
        partner_username = Utility.environment["waba_partner"]["partner_username"]
        partner_password = Utility.environment["waba_partner"]["partner_password"]

        token_url = base_url_hub + WABA_AUTH_TOKEN
        request_body = {
            "username": partner_username,
            "password": partner_password
        }
        resp = Utility.execute_http_request(request_method="POST", http_url=token_url, request_body=request_body)
        return resp.get("token_type") + " " + resp.get("access_token")

    @staticmethod
    def generate_waba_key(channel_id: Text):
        base_url_hub = Utility.environment["waba_partner"]["base_url_hub"]
        partner_id = Utility.environment["waba_partner"]["partner_id"]
        url = base_url_hub + WABA_GENERATE_KEY.format(partner_id=partner_id, channel_id=channel_id)

        headers = {"Authorization": ChatUtils.get_partners_auth_token()}
        resp = Utility.execute_http_request(request_method="POST", http_url=url, headers=headers)

        api_key = resp.get("api_key")
        return api_key

    @staticmethod
    def get_waba_account_id(channel_id: Text):
        base_url_hub = Utility.environment["waba_partner"]["base_url_hub"]
        partner_id = Utility.environment["waba_partner"]["partner_id"]

        url = base_url_hub + GET_WABA_ACCOUNT.format(partner_id=partner_id, channel_id=channel_id)

        headers = {"Authorization": ChatUtils.get_partners_auth_token()}
        resp = Utility.execute_http_request(request_method="GET", http_url=url, headers=headers)

        return resp.get("partner_channels", {})[0].get("waba_account", {}).get("id")

    @staticmethod
    def set_webhook_url(api_key: Text, webhook_url: Text):
        base_url_waba = Utility.environment["waba_partner"]["base_url_waba"]

        waba_webhook_url = base_url_waba + WABA_SET_WEBHOOK
        headers = {API_HEADER_KEY: api_key}
        request_body = {"url": webhook_url}
        resp = Utility.execute_http_request(request_method="POST", http_url=waba_webhook_url,
                                            request_body=request_body, headers=headers)
        return resp.get("url")

    @staticmethod
    def post_process(bot, user):

        config = ChatDataProcessor.get_channel_config("waba_partner", bot, mask_characters=False)
        channel_id = config.get("config", {}).get("channel_id")

        api_key = ChatUtils.generate_waba_key(channel_id)
        waba_account_id = ChatUtils.get_waba_account_id(channel_id)
        payload = {"api_key": api_key, "waba_account_id": waba_account_id}

        webhook_url = ChatUtils.update_waba_channel_config(config, payload, bot, user)

        return ChatUtils.set_webhook_url(api_key, webhook_url)

    @staticmethod
    def update_waba_channel_config(config, payload, bot, user):
        conf = config["config"]
        conf.update(payload)
        config["config"] = conf
        return ChatDataProcessor.save_channel_config(config, bot, user)

    @staticmethod
    def get_waba_template(bot, template_id):
        config = ChatDataProcessor.get_channel_config("waba_partner", bot, mask_characters=False)
        waba_account_id = config.get("config").get("waba_account_id")
        base_url_hub = Utility.environment["waba_partner"]["base_url_hub"]
        partner_id = config.get("partner_id", Utility.environment["waba_partner"]["partner_id"])
        template_url = GET_WABA_TEMPLATE.format(partner_id=partner_id, template_id=template_id,
                                                waba_account_id=waba_account_id)

        headers = {"Authorization": ChatUtils.get_partners_auth_token()}
        url = base_url_hub + template_url
        resp = Utility.execute_http_request(request_method="GET", http_url=url, headers=headers)
        templace_data = resp.get("waba_templates")[0]

        template = {"namespace": templace_data.get("namespace"), "name": templace_data.get("name"),
                    "language": {"policy": "deterministic", "code": templace_data.get("language"), }}

        components = list()
        for component in templace_data.get("components", {}):
            comp = {"type": component.get("type").lower()}
            param_list = []
            for param in component.get("example", {}).get("body_text"):
                param_list.append({})
            comp["parameters"] : []
        return template