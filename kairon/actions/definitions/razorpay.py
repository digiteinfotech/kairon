from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, RazorpayAction, TriggerInfo
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import KaironSystemSlots
from kairon.shared.data.constant import STATUSES


class ActionRazorpay(ActionsBase):
    __URL = "https://api.razorpay.com/v1/payment_links/"

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Razorpay action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch Razorpay action configuration parameters from the database.

        :return: RazorpayAction containing configuration for the action as a dict.
        """
        try:
            action = RazorpayAction.objects(bot=self.bot, name=self.name, status=True).get().to_mongo().to_dict()
            logger.debug("razorpay_action_config: " + str(action))
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Razorpay action found for given action and bot")
        return action

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any], **kwargs):
        """
        Retrieves action config and executes it.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        action_call = kwargs.get('action_call', {})

        status = STATUSES.SUCCESS.value
        exception, http_response, bot_response = None, None, None
        action_config = self.retrieve_config()
        api_key = action_config.get('api_key')
        api_secret = action_config.get('api_secret')
        amount = action_config.get('amount')
        currency = action_config.get('currency')
        username = action_config.get('username')
        email = action_config.get('email')
        contact = action_config.get('contact')
        notes = action_config.get('notes')
        body = {}
        try:
            tracker_data = ActionUtility.build_context(tracker)
            api_key = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, api_key, self.bot)
            api_secret = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, api_secret, self.bot)
            amount = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, amount, self.bot)
            if not amount:
                raise ActionFailure(f"amount must be a whole number! Got {amount}.")
            amount = int(amount)
            currency = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, currency, self.bot)
            username = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, username, self.bot)
            email = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, email, self.bot)
            contact = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, contact, self.bot)
            headers = {"Authorization": ActionUtility.get_basic_auth_str(api_key, api_secret)}
            notes, notes_log = ActionUtility.prepare_request(tracker_data, notes, self.bot)
            body = {
                "amount": amount, "currency": currency,
                "customer": {"username": username, "email": email, "contact": contact},
                "notes": {**notes, "bot": self.bot}
            }
            http_response = ActionUtility.execute_http_request(
                headers=headers, http_url=ActionRazorpay.__URL, request_method="POST", request_body=body
            )
            bot_response = http_response["short_url"]
            logger.info("schedule_data: " + str(notes_log))
            logger.info("bot_response: " + str(bot_response))
        except ValueError as e:
            logger.exception(e)
            logger.debug(e)
            exception = f"amount must be a whole number! Got {amount}."
            status = STATUSES.FAIL.value
            bot_response = "I have failed to process your request"
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = STATUSES.FAIL.value
            bot_response = "I have failed to process your request"
        finally:
            trigger_info_data = action_call.get('trigger_info') or {}
            trigger_info_obj = TriggerInfo(**trigger_info_data)
            ActionServerLogs(
                type=ActionType.razorpay_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot=self.bot,
                exception=exception,
                api_response=str(http_response),
                bot_response=bot_response,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                request=body,
                trigger_info=trigger_info_obj
            ).save()
        dispatcher.utter_message(bot_response)
        return {KaironSystemSlots.kairon_action_response.value: bot_response}
