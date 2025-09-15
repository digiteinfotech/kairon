from typing import Text, Dict, Any

from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import KAIRON_USER_MSG_ENTITY
from kairon.shared.data.constant import DEFAULT_NLU_FALLBACK_UTTERANCE_NAME, STATUSES
from kairon.shared.data.processor import MongoProcessor
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, KaironTwoStageFallbackAction, TriggerInfo
from kairon.shared.actions.models import ActionType
from loguru import logger

from kairon.shared.data.utils import DataUtility


class ActionTwoStageFallback(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Two stage fallback action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Action does not have any configuration saved in the current implementation.
        """
        try:
            action = KaironTwoStageFallbackAction.objects(bot=self.bot, name=self.name, status=True).get().to_mongo().to_dict()
            logger.debug("kairon_two_stage_fallback_action_config: " + str(action))
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("Two stage fallback action config not found")
        return action

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any], **kwargs):
        """
        Retrieves top intents that were predicted apart
        from nlu fallback and fetches one training example for that intent.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        action_call = kwargs.get('action_call', {})

        status = STATUSES.SUCCESS.value
        exception = None
        action_config = self.retrieve_config()
        intent_ranking = tracker.latest_message.get("intent_ranking")
        text_recommendations = action_config['text_recommendations']
        trigger_rules = action_config.get('trigger_rules')
        latest_user_msg = tracker.latest_message.get('text')
        recommendations = []
        mongo_processor = MongoProcessor()
        if text_recommendations and text_recommendations.get("count"):
            if text_recommendations.get("use_intent_ranking"):
                for intent in intent_ranking[1: 1 + text_recommendations["count"]]:
                    try:
                        example = next(mongo_processor.get_training_examples(intent["name"], self.bot))
                        text = DataUtility.extract_text_and_entities(example['text'])[0]
                        recommendations.append({"text": text, "payload": text})
                    except Exception as e:
                        exception = str(e)
                        logger.exception(e)
            else:
                for result in list(mongo_processor.search_training_examples(latest_user_msg, self.bot, text_recommendations["count"])):
                    recommendations.append({"text": result.get("text"), "payload": result.get("text")})
        if trigger_rules:
            for rule in trigger_rules:
                btn = {}
                if rule.get('is_dynamic_msg'):
                    btn['payload'] = f'/{rule["payload"]}{{"{KAIRON_USER_MSG_ENTITY}": "{latest_user_msg}"}}'
                elif not ActionUtility.is_empty(rule.get('message')):
                    btn['payload'] = f'/{rule["payload"]}{{"{KAIRON_USER_MSG_ENTITY}": "{rule.get("message")}"}}'
                else:
                    btn['payload'] = f"/{rule['payload']}"
                btn['text'] = rule['text']
                recommendations.append(btn)
        if recommendations:
            dispatcher.utter_message(buttons=recommendations, text=action_config.get('fallback_message'))
        else:
            dispatcher.utter_message(response=DEFAULT_NLU_FALLBACK_UTTERANCE_NAME)
        trigger_info_data = action_call.get('trigger_info') or {}
        trigger_info_obj = TriggerInfo(**trigger_info_data)
        ActionServerLogs(
            type=ActionType.two_stage_fallback.value,
            intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
            action=self.name,
            sender=tracker.sender_id,
            bot=tracker.get_slot("bot"),
            exception=exception,
            bot_response=str(recommendations),
            status=status,
            user_msg=tracker.latest_message.get('text'),
                trigger_info=trigger_info_obj
        ).save()
        return {}
