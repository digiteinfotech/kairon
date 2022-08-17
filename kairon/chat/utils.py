import json
from typing import Text

from loguru import logger
from pymongo.errors import ServerSelectionTimeoutError
from rasa.core.tracker_store import TrackerStore

from .agent_processor import AgentProcessor
from .. import Utility
from ..live_agent.factory import LiveAgentFactory
from ..shared.actions.utils import ActionUtility
from ..shared.end_user_metrics.constants import MetricTypes
from ..shared.end_user_metrics.processor import EndUserMetricsProcessor
from ..shared.live_agent.processor import LiveAgentsProcessor


class ChatUtils:

    @staticmethod
    async def chat(data: Text, bot: Text, user: Text):
        model = AgentProcessor.get_agent(bot)
        chat_response = await model.handle_text(data, sender_id=user)
        ChatUtils.__attach_agent_handoff_metadata(bot, user, chat_response, model.tracker_store)
        return chat_response

    @staticmethod
    def reload(bot: Text):
        AgentProcessor.reload(bot)

    @staticmethod
    def __attach_agent_handoff_metadata(bot: Text, sender_id: Text, bot_predictions, tracker):
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
                    message_trail = ChatUtils.__retrieve_conversation(tracker, sender_id)
                    live_agent.send_conversation_log(message_trail, metadata["additional_properties"]["destination"])
        except Exception as e:
            logger.exception(e)
            exception = str(e)
            metadata['initiate'] = False
        finally:
            if not Utility.check_empty_string(exception) or should_initiate_handoff:
                EndUserMetricsProcessor.add_log(
                    MetricTypes.agent_handoff.value, sender_id, bot,
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
        predicted_action = bot_predictions["action"]
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
        host = Utility.environment['database']['url']
        db = Utility.environment['database']['test_db']
        events = []
        message = None
        client = Utility.create_mongo_client(host)
        with client as client:
            try:
                db = client.get_database(db)
                conversations = db.get_collection(bot)
                events = list(conversations.aggregate([
                    {"$match": {"sender_id": sender_id}},
                    {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                    {"$match": {"events.event": {"$in": ["session_started", "user", "bot"]}}},
                    {"$project": {"sender_id": 1, "events.event": 1, "events.timestamp": 1, "events.text": 1}},
                    {"$group": {"_id": "$sender_id", "events": {"$push": "$events"},
                                "all_events": {"$push": "$events"}}},
                    {"$unwind": {"path": "$events", "includeArrayIndex": "arrayIndex"}},
                    {"$match": {"events.event": "session_started"}},
                    {"$group": {"_id": "$sender_id", "events": {"$push": "$arrayIndex"},
                                "allevents": {"$first": '$all_events'}}},
                    {"$project": {"lastindex": {"$last": "$events"}, "allevents": 1}},
                    {"$project": {"events": {"$slice": ["$allevents", "$lastindex", {"$size": '$allevents'}]}}},
                ]))
                if events:
                    events = events[0]['events']
            except ServerSelectionTimeoutError as e:
                logger.error(e)
                message = f'Failed to retrieve conversation: {e}'
            except Exception as e:
                logger.error(e)
                message = f'Failed to retrieve conversation: {e}'
            return events, message
