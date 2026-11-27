from typing import Text, Dict, Any

from kairon.shared.actions.utils import ActionUtility
from loguru import logger
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.actions.models import ActionType
from kairon.shared.voice.utils import VoiceUtils
from kairon.shared.data.constant import STATUSES
from kairon.shared.request_context import get_request_id


class ActionVoiceDisconnect(ActionsBase):
    """Send a disconnect signal to the voice channel to terminate the call.

    Add this action to any flow node where the call should end gracefully (e.g. after the bot's goodbye).
    The voice channel finishes playing the bot's reply and then hangs up: Twilio answers with a ``<Hangup>``
    instruction, the Exotel stream closes its websocket. On any conversation that is not positively a voice call
    (web chat sends no channel name, WhatsApp, Slack, ...) there is no call to end, so the action does nothing, and
    the hang-up signal never reaches the user as a message.
    """

    def __init__(self, bot: Text, name: Text):
        """Initialize VoiceDisconnect action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """The disconnect action has no configuration."""
        return {}

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any], **kwargs):
        status = STATUSES.SUCCESS.value
        exception = None
        bot_response = {"disconnect": True}
        try:
            if not VoiceUtils.is_voice_conversation(tracker):
                bot_response = "skipped: not a voice conversation"
            else:
                dispatcher.utter_custom_json({"disconnect": True})
        except Exception as e:
            logger.exception(e)
            exception = str(e)
            status = STATUSES.FAIL.value
            ActionUtility.trigger_action_failure_mail(slot_values=tracker.current_slot_values(), bot_name=self.bot,
                                                      action_name=self.name,
                                                      user_query_history=tracker.latest_message.get('text'))
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
                bot_response=str(bot_response),
                status=status,
                user_msg=tracker.latest_message.get("text"),
                trigger_info=TriggerInfo(**trigger_info_data),
                request_id=get_request_id()
            ).save()
        return {}
