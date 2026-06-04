import logging
from typing import Text

from mongoengine.errors import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, VoiceCallAction, TriggerInfo
from kairon.shared.chat.data_objects import ChannelLogs
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, ActionParameterType
from kairon.shared.data.constant import STATUSES
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import ChannelTypes, KaironSystemSlots
from kairon.shared.voice.factory import VoiceOutboundFactory

logger = logging.getLogger(__name__)


class ActionVoiceCall(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialise the voice call action handler.

        :param bot: bot ID
        :param name: voice call action name used to look up VoiceCallAction config
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        try:
            return VoiceCallAction.objects(
                bot=self.bot, name=self.name, status=True
            ).get().to_mongo().to_dict()
        except DoesNotExist:
            raise ActionFailure("No VoiceCallAction found for given action and bot")

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict, **kwargs):
        action_call = kwargs.get('action_call', {})
        status = STATUSES.SUCCESS.value
        exception = None

        action_config = self.retrieve_config()
        bot_response = action_config.get("response") or "I'm placing a call to you now."
        dispatch_bot_response = action_config.get("dispatch_bot_response", True)

        try:
            channel_config = ChatDataProcessor.get_channel_config(
                ChannelTypes.VOICE.value, self.bot, mask_characters=False
            )["config"]

            provider_name = action_config.get("telephony_provider") or \
                            channel_config.get("telephony_provider", "twilio")

            client_cls = VoiceOutboundFactory.get_client(provider_name)
            client = client_cls(
                account_sid=channel_config["account_sid"],
                auth_token=channel_config["auth_token"],
                from_number=channel_config["phone_number"],
            )

            ph_cfg = action_config["to_phone_number"]
            if ph_cfg.get("parameter_type") == ActionParameterType.slot.value:
                to_phone = tracker.get_slot(ph_cfg["value"])
            else:
                to_phone = ph_cfg["value"]

            if not to_phone:
                raise ActionFailure("to_phone_number is empty or slot not set")

            call_url = channel_config.get("call_url", "")
            status_url = channel_config.get("status_url", "")
            call_sid = client.initiate_call(to_phone, call_url, status_url)

            ChannelLogs(
                type=ChannelTypes.VOICE.value,
                status="initiated",
                data={"to": to_phone, "call_sid": call_sid},
                message_id=call_sid or "unknown",
                bot=self.bot,
                user=channel_config.get("user", "system"),
                initiator="bot",
            ).save()

        except Exception as e:
            logger.exception(e)
            exception = str(e)
            bot_response = "I have failed to place the call"
            status = STATUSES.FAIL.value
        finally:
            if dispatch_bot_response:
                dispatcher.utter_message(bot_response)
            trigger_info_obj = TriggerInfo(**(action_call.get('trigger_info') or {}))
            ActionServerLogs(
                type=ActionType.voice_call_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                bot_response=bot_response,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                trigger_info=trigger_info_obj,
            ).save()

        return {KaironSystemSlots.kairon_action_response.value: bot_response}
