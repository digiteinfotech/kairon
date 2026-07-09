from typing import Text, Dict, Any

from loguru import logger
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.actions.models import ActionType
from kairon.shared.data.constant import STATUSES
from kairon.shared.request_context import get_request_id


class ActionVoiceDisconnect(ActionsBase):
    """
    Sends a disconnect signal to the voice output channel so the handler
    can terminate the call with a <Hangup> TwiML instruction.
    Add this action to any flow node where the call should end gracefully.
    """

    def __init__(self, bot: Text, name: Text):
        """
        Initialize VoiceDisconnect action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        return {}

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any], **kwargs):
        status = STATUSES.SUCCESS.value
        exception = None
        try:
            dispatcher.utter_custom_json({"disconnect": True})
        except Exception as e:
            logger.exception(e)
            exception = str(e)
            status = STATUSES.FAIL.value
        finally:
            trigger_info_data = kwargs.get('action_call', {}).get('trigger_info') or {}
            from kairon.shared.actions.data_objects import TriggerInfo
            ActionServerLogs(
                type=ActionType.kairon_voice_disconnect.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot=self.bot,
                exception=exception,
                bot_response=str({"disconnect": True}),
                status=status,
                user_msg=tracker.latest_message.get("text"),
                trigger_info=TriggerInfo(**trigger_info_data),
                request_id=get_request_id()
            ).save()
        return {}
