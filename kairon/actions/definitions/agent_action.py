from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, AgentActionConfig, TriggerInfo
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.auth import Authentication
from kairon.shared.constants import KaironSystemSlots, KAIRON_USER_MSG_ENTITY
from kairon.shared.data.constant import STATUSES, TOKEN_TYPE
from kairon.shared.request_context import get_request_id
from kairon.shared.utils import Utility


class ActionAgent(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        self.bot = bot
        self.name = name
        self.__response = None
        self.__is_success = False

    def retrieve_config(self):
        try:
            return AgentActionConfig.objects(
                bot=self.bot, name=self.name, status=True
            ).get().to_mongo().to_dict()
        except DoesNotExist:
            raise ActionFailure("No AgentAction found for given action and bot")

    @staticmethod
    def _get_user_message(tracker: Tracker) -> str:
        """Get the latest user text from conversation history, skipping intent-formatted messages."""
        user_msg = tracker.latest_message.get("text", "")
        if not ActionUtility.is_empty(user_msg) and user_msg.startswith("/"):
            entity_msg = next(tracker.get_latest_entity_values(KAIRON_USER_MSG_ENTITY), None)
            if not ActionUtility.is_empty(entity_msg):
                return entity_msg
        return user_msg or ""

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any], **kwargs):
        action_call = kwargs.get('action_call', {})
        status = STATUSES.SUCCESS.value
        exception = None
        bot_response = None
        filled_slots = {}
        http_url = None

        action_config = self.retrieve_config()
        dispatch_bot_response = action_config.get("dispatch_bot_response", True)

        try:
            agent_id = action_config["agent_id"]
            sender_id = tracker.sender_id

            base_url = Utility.environment.get('simple_agent', {}).get('url', '').rstrip('/')
            http_url = f"{base_url}/agents/{self.bot}/{agent_id}/run/{sender_id}/simple"

            bearer_token = Authentication.create_access_token(
                data={"sub": sender_id, "bot": self.bot},
                token_type=TOKEN_TYPE.LOGIN.value,
            )
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {bearer_token}",
            }

            user_message = self._get_user_message(tracker)
            request_body = {
                "message": user_message,
                "session_id": None,
                "metadata": {},
                "max_iterations": 1,
            }

            api_response, status_code, _, _ = await ActionUtility.execute_request_async(
                http_url=http_url,
                request_method="POST",
                request_body=request_body,
                headers=headers,
            )
            logger.info(f"agent_action response: {api_response}")

            if isinstance(api_response, dict):
                bot_response = api_response.get("output") or ""
            else:
                bot_response = str(api_response) if api_response else ""

            self.__response = bot_response
            self.__is_success = True

        except Exception as e:
            exception = str(e)
            logger.exception(e)
            status = STATUSES.FAIL.value
            bot_response = "I have failed to process your request."
            ActionUtility.trigger_action_failure_mail(
                slot_values=tracker.current_slot_values(),
                bot_name=self.bot,
                action_name=self.name,
                user_query_history=tracker.latest_message.get('text'),
            )
        finally:
            if dispatch_bot_response and bot_response:
                dispatcher.utter_message(text=bot_response)
            trigger_info_obj = TriggerInfo(**(action_call.get('trigger_info') or {}))
            ActionServerLogs(
                type=ActionType.agent_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot=self.bot,
                url=http_url,
                bot_response=str(bot_response) if bot_response else None,
                exception=exception,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                trigger_info=trigger_info_obj,
                request_id=get_request_id(),
            ).save()
            filled_slots[KaironSystemSlots.kairon_action_response.value] = bot_response

        return filled_slots

    @property
    def is_success(self):
        return self.__is_success

    @property
    def response(self):
        return self.__response
