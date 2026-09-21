import logging
from typing import Text, Dict, Any

from mongoengine.errors import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, StorePageAction, TriggerInfo
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.data.constant import STATUSES
from kairon.shared.request_context import get_request_id

logger = logging.getLogger(__name__)


class ActionStorePage(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        try:
            return StorePageAction.objects(
                bot=self.bot, name=self.name, status=True
            ).get().to_mongo().to_dict()
        except DoesNotExist:
            raise ActionFailure("No StorePageAction found for given action and bot")

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any], **kwargs):
        action_call = kwargs.get('action_call', {})
        status = STATUSES.SUCCESS.value
        exception = None
        slots = {}

        action_config = self.retrieve_config()
        page_name = action_config.get("page_name", "")
        identifier_slot = action_config.get("identifier_slot", "")
        callback_identifier_slot = action_config.get("callback_identifier")

        try:
            from kairon import Utility
            from kairon.shared.auth import Authentication

            identifier_value = tracker.get_slot(identifier_slot)
            callback_identifier_value=tracker.get_slot(callback_identifier_slot)
            if not identifier_value or (isinstance(identifier_value, str) and not identifier_value.strip()):
                raise ActionFailure(f"Slot '{identifier_slot}' is absent or empty for sender {tracker.sender_id}")

            encrypted_id = Utility.encrypt_message(str(identifier_value))
            token = Authentication.create_store_page_token(
                data={"sub": tracker.sender_id, "bot": self.bot},
                access_limit=[
                    "/api/bot/.+/customer_data/.*",
                    "/api/bot/.+/store_page/metadata",
                    "/api/bot/.+/data/collection/.*",
                ],
            )

            slots["user_identifier"] = encrypted_id
            slots["temp_token"] = token
            slots["store_page_name"] = page_name
            slots["callback_identifier"] = callback_identifier_value

        except ActionFailure as e:
            exception = str(e)
            status = STATUSES.FAIL.value
            raise
        except Exception as e:
            logger.exception(e)
            exception = str(e)
            status = STATUSES.FAIL.value
        finally:
            trigger_info_obj = TriggerInfo(**(action_call.get('trigger_info') or {}))
            ActionServerLogs(
                type=ActionType.store_page_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                trigger_info=trigger_info_obj,
                request_id=get_request_id(),
            ).save()

        return slots
