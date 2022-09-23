from typing import Text

from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.shared.actions.exception import ActionFailure
from kairon.shared.data.processor import MongoProcessor
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, KaironTwoStageFallbackAction
from kairon.shared.actions.models import ActionType
from loguru import logger

from kairon.shared.data.utils import DataUtility


class ActionTwoStageFallback(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Email action.

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

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker):
        """
        Retrieves top intents that were predicted apart
        from nlu fallback and fetches one training example for that intent.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        :return: Dict containing slot name as keys and their values.
        """
        status = "SUCCESS"
        exception = None
        action_config = self.retrieve_config()
        intent_ranking = tracker.latest_message.get("intent_ranking")
        num_text_recommendations = action_config['num_text_recommendations']
        trigger_rules = action_config.get('trigger_rules')
        suggested_intents = []
        if num_text_recommendations and intent_ranking:
            mongo_processor = MongoProcessor()
            for intent in intent_ranking[1: 1+num_text_recommendations]:
                try:
                    example = next(mongo_processor.get_training_examples(intent["name"], self.bot))
                    text = DataUtility.extract_text_and_entities(example['text'])[0]
                    suggested_intents.append({"text": text, "payload": text})
                except Exception as e:
                    exception = str(e)
                    logger.exception(e)
        if trigger_rules:
            for rule in trigger_rules:
                rule['payload'] = f"/{rule['payload']}"
                suggested_intents.append(rule)
        dispatcher.utter_message(buttons=suggested_intents)
        ActionServerLogs(
            type=ActionType.two_stage_fallback.value,
            intent=tracker.get_intent_of_latest_message(),
            action=self.name,
            sender=tracker.sender_id,
            bot=tracker.get_slot("bot"),
            exception=exception,
            bot_response=str(suggested_intents),
            status=status
        ).save()
        return {}
