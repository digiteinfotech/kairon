from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.shared.constants import KaironSystemSlots
from kairon.shared.utils import MailUtility
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, EmailActionConfig
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, ActionParameterType
from kairon.shared.actions.utils import ActionUtility


class ActionEmail(ActionsBase):

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
        Fetch Email action configuration parameters from the database.

        :return: EmailActionConfig containing configuration for the action as dict.
        """
        try:
            action = EmailActionConfig.objects(bot=self.bot, action_name=self.name, status=True).get().to_mongo().to_dict()
            logger.debug("email_action_config: " + str(action))
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Email action found for given action and bot")
        return action

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        """
        Retrieves action config and executes it.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        status = "SUCCESS"
        exception = None
        action_config = self.retrieve_config()
        bot_response = action_config.get("response")
        smtp_password = action_config.get('smtp_password')
        smtp_userid = action_config.get('smtp_userid')
        custom_text = action_config.get('custom_text')
        try:
            from_email, to_email = self.__get_from_email_and_to_email(action_config, tracker)
            tracker_data = ActionUtility.build_context(tracker)
            password = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, smtp_password, self.bot)
            userid = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, smtp_userid, self.bot)
            for mail in to_email:
                if custom_text:
                    text = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, custom_text, self.bot)
                    body = ActionUtility.prepare_email_text(text, action_config['subject'], mail)
                else:
                    body = ActionUtility.prepare_email_body(tracker_data[ActionParameterType.chat_log.value],
                                                        action_config['subject'], mail)
                await MailUtility.trigger_email(email=[mail],
                                                subject=f"{tracker.sender_id} {action_config['subject']}",
                                                body=body,
                                                smtp_url=action_config['smtp_url'],
                                                smtp_port=action_config['smtp_port'],
                                                sender_email=from_email,
                                                smtp_password=password,
                                                smtp_userid=userid,
                                                tls=action_config['tls']
                                                )

        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            bot_response = "I have failed to process your request"
            status = "FAILURE"
        finally:
            ActionServerLogs(
                type=ActionType.email_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=action_config['action_name'],
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                bot_response=bot_response,
                status=status,
                user_msg=tracker.latest_message.get('text')
            ).save()
        dispatcher.utter_message(bot_response)
        return {KaironSystemSlots.kairon_action_response.value: bot_response}

    @staticmethod
    def __get_from_email_and_to_email(action_config: EmailActionConfig, tracker: Tracker):
        from_email_type = action_config['from_email']['parameter_type']
        to_email_type = action_config['to_email']['parameter_type']
        from_email = tracker.get_slot(action_config['from_email']['value']) if from_email_type == "slot" \
            else action_config['from_email']['value']
        to_email = tracker.get_slot(action_config['to_email']['value']) if to_email_type == "slot" \
            else action_config['to_email']['value']

        if not isinstance(to_email, (str, list)):
            raise ValueError("Invalid 'to_email' type. It must be of type str or list.")

        if not isinstance(from_email, str):
            raise ValueError("Invalid 'from_email' type. It must be of type str.")

        to_email = [to_email] if isinstance(to_email, str) else to_email
        return from_email, to_email
