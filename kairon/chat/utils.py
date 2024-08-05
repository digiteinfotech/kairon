import datetime
import os
from typing import Text, Dict

from loguru import logger
from pymongo.collection import Collection
from pymongo.errors import ServerSelectionTimeoutError
from rasa.core.channels import UserMessage
from rasa.core.tracker_store import SerializedTrackerAsDict

from .agent_processor import AgentProcessor
from .. import Utility
from ..live_agent.factory import LiveAgentFactory
from ..shared.account.activity_log import UserActivityLogger
from ..shared.actions.utils import ActionUtility
from ..shared.constants import UserActivityType
from ..shared.live_agent.processor import LiveAgentsProcessor
from ..shared.metering.constants import MetricType
from ..shared.metering.metering_processor import MeteringProcessor


class ChatUtils:
    @staticmethod
    async def chat(
        data: Text,
        account: int,
        bot: Text,
        user: Text,
        is_integration_user: bool = False,
        metadata: Dict = None,
    ):
        model = AgentProcessor.get_agent(bot)
        metadata = ChatUtils.get_metadata(account, bot, is_integration_user, metadata)
        msg = UserMessage(data, sender_id=user, metadata=metadata)
        chat_response = await AgentProcessor.handle_channel_message(bot, msg)
        if not chat_response:
            return {
                "success": True,
                "message": "user message delivered to live agent."
            }
        await ChatUtils.__attach_agent_handoff_metadata(
            account, bot, user, chat_response, model.tracker_store
        )
        return chat_response

    @staticmethod
    def reload(bot: Text, user: Text):
        exc = None
        status = "Success"
        try:
            AgentProcessor.reload(bot)
        except Exception as e:
            logger.error(e)
            exc = str(e)
            status = "Failed"
        finally:
            UserActivityLogger.add_log(
                a_type=UserActivityType.model_reload.value,
                email=user,
                bot=bot,
                data={
                    "username": user,
                    "process_id": os.getpid(),
                    "exception": exc,
                    "status": status,
                },
            )

    @staticmethod
    async def __attach_agent_handoff_metadata(
        account: int, bot: Text, sender_id: Text, bot_predictions, tracker
    ):
        metadata = {"initiate": False, "type": None, "additional_properties": None}
        exception = None
        should_initiate_handoff = False
        try:
            config = LiveAgentsProcessor.get_config(
                bot, mask_characters=False, raise_error=False
            )
            if config:
                metadata["type"] = config["agent_type"]
                should_initiate_handoff = ChatUtils.__should_initiate_handoff(
                    bot_predictions, config
                )
                if should_initiate_handoff:
                    metadata["initiate"] = True
                    live_agent = LiveAgentFactory.get_agent(
                        config["agent_type"], config["config"]
                    )
                    metadata["additional_properties"] = live_agent.initiate_handoff(
                        bot, sender_id
                    )
                    businessdata = live_agent.getBusinesshours(
                        config, metadata["additional_properties"]["inbox_id"]
                    )
                    if businessdata is not None and businessdata.get(
                        "working_hours_enabled"
                    ):
                        is_business_hours_enabled = businessdata.get(
                            "working_hours_enabled"
                        )
                        if is_business_hours_enabled:
                            current_utcnow = datetime.datetime.utcnow()
                            workingstatus = live_agent.validate_businessworkinghours(
                                businessdata, current_utcnow
                            )
                            if not workingstatus:
                                metadata.update(
                                    {
                                        "businessworking": businessdata[
                                            "out_of_office_message"
                                        ]
                                    }
                                )
                                metadata["initiate"] = False
                                bot_predictions["agent_handoff"] = metadata
                                should_initiate_handoff = False
                                return metadata
                    message_trail = await ChatUtils.__retrieve_conversation(
                        tracker, sender_id
                    )
                    live_agent.send_conversation_log(
                        message_trail, metadata["additional_properties"]["destination"]
                    )
        except Exception as e:
            logger.exception(e)
            exception = str(e)
            metadata["initiate"] = False
        finally:
            if not Utility.check_empty_string(exception) or should_initiate_handoff:
                MeteringProcessor.add_metrics(
                    bot,
                    account,
                    MetricType.agent_handoff,
                    sender_id=sender_id,
                    agent_type=metadata.get("type"),
                    bot_predictions=bot_predictions,
                    exception=exception,
                )

        bot_predictions["agent_handoff"] = metadata
        return metadata

    @staticmethod
    async def __retrieve_conversation(tracker, sender_id: Text):
        events = SerializedTrackerAsDict.serialise_tracker(
            await tracker.retrieve(sender_id)
        )
        _, message_trail = ActionUtility.prepare_message_trail(events.get("events"))
        return message_trail

    @staticmethod
    def __should_initiate_handoff(bot_predictions, agent_handoff_config):
        predicted_intent = bot_predictions["nlu"]["intent"]["name"]
        predicted_action = [
            action.get("action_name") for action in bot_predictions["action"]
        ]
        trigger_on_intent = predicted_intent in set(
            agent_handoff_config.get("trigger_on_intents", [])
        )
        trigger_on_action = (
            len(
                set(predicted_action).intersection(
                    set(agent_handoff_config.get("trigger_on_actions", []))
                )
            )
            > 0
        )
        return (
            agent_handoff_config["override_bot"]
            or trigger_on_intent
            or trigger_on_action
        )

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
            config = Utility.get_local_db()
            db_name = config.pop("db")
            client = Utility.create_mongo_client(config)
            with client as client:
                db = client.get_database(db_name)
                conversations = db.get_collection(bot)
                logger.debug(
                    f"Loading host: {config['host']}, db:{db.name}, collection: {bot},env: {Utility.environment['env']}"
                )
                last_session = ChatUtils.get_last_session(conversations, sender_id)
                print(last_session)
                logger.debug(f"last session: {last_session}")
                if not last_session:
                    return events, message
                events = list(
                    conversations.aggregate(
                        [
                            {
                                "$match": {
                                    "sender_id": sender_id,
                                    "timestamp": {
                                        "$gt": last_session["event"]["timestamp"]
                                    },
                                    "type": {
                                        "$in": ["flattened"]
                                    },
                                }
                            },
                            {
                                "$addFields": {"_id": {"$toString": "$_id"}}
                            },
                            {"$sort": {"timestamp": 1}},
                            {
                                "$group": {
                                  "_id": "$metadata.tabname",
                                  "events": {"$push": "$$ROOT"}
                                }
                            },
                            {
                                "$project": {
                                    "_id": 0,
                                    "tabname": "$_id",
                                    "events": "$events",
                                }
                            },
                        ]
                    )
                )
        except ServerSelectionTimeoutError as e:
            logger.info(e)
            message = f"Failed to retrieve conversation: {e}"
        except Exception as e:
            logger.info(e)
            message = f"Failed to retrieve conversation: {e}"
        return events, message

    @staticmethod
    def get_last_session(conversations: Collection, sender_id: Text):
        last_session = list(
            conversations.aggregate(
                [
                    {
                        "$match": {
                            "sender_id": sender_id,
                            "event.event": "session_started",
                        }
                    },
                    {"$sort": {"event.timestamp": 1}},
                    {"$group": {"_id": "$sender_id", "event": {"$last": "$event"}}},
                ]
            )
        )
        return last_session[0] if last_session else None

    @staticmethod
    def get_metadata(
        account: int,
        bot: Text,
        is_integration_user: bool = False,
        metadata: Dict = None,
    ):
        default_metadata = {
            "is_integration_user": is_integration_user,
            "bot": bot,
            "account": account,
            "channel_type": "chat_client",
        }
        if not metadata:
            metadata = {}
        if not metadata.get("tabname"):
            metadata["tabname"] = "default"
        metadata.update(default_metadata)
        return metadata







    @staticmethod
    def add_telemetry_metadata(x_telemetry_uid: Text, x_telemetry_sid: Text, metadata: Dict = None):
        if not metadata:
            metadata = {}
        if x_telemetry_uid and x_telemetry_sid:
            #TODO: validate x_telemetry_uid and x_session_id for the botid
            metadata["telemetry-uid"] = x_telemetry_uid
            metadata["telemetry-sid"] = x_telemetry_sid
        return metadata
