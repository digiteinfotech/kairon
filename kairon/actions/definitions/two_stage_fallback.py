from typing import Text

from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.shared.data.constant import DEFAULT_NLU_FALLBACK_RESPONSE, DEFAULT_NLU_FALLBACK_UTTERANCE_NAME
from kairon.shared.data.processor import MongoProcessor
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.actions.models import ActionType


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
        pass

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
        tracker.get_intent_of_latest_message()
        intent_ranking = tracker.latest_message.get("intent_ranking")
        if intent_ranking and intent_ranking[1:4]:
            suggested_intents = []
            mongo_processor = MongoProcessor()
            for intent in intent_ranking[1:4]:
                try:
                    example = next(mongo_processor.get_training_examples(intent["name"], self.bot))
                    suggested_intents.append(example['text'])
                except Exception:
                    pass
            dispatcher.utter_message(buttons=suggested_intents)
            bot_response = suggested_intents
        else:
            dispatcher.utter_template(DEFAULT_NLU_FALLBACK_UTTERANCE_NAME, tracker)
            bot_response = DEFAULT_NLU_FALLBACK_RESPONSE
        ActionServerLogs(
            type=ActionType.two_stage_fallback.value,
            intent=tracker.get_intent_of_latest_message(),
            action=self.name,
            sender=tracker.sender_id,
            bot=tracker.get_slot("bot"),
            exception=exception,
            bot_response=str(bot_response),
            status=status
        ).save()
        return {}
