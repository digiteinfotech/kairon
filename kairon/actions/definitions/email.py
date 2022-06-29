from typing import Text

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon import Utility
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, EmailActionConfig
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, KAIRON_ACTION_RESPONSE_SLOT
from kairon.shared.actions.utils import ActionUtility


class ActionEmail(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        try:
            action = EmailActionConfig.objects(bot=self.bot, action_name=self.name, status=True).get().to_mongo().to_dict()
            logger.debug("email_action_config: " + str(action))
            action['smtp_url'] = Utility.decrypt_message(action['smtp_url'])
            action['smtp_password'] = Utility.decrypt_message(action['smtp_password'])
            action['from_email'] = Utility.decrypt_message(action['from_email'])
            if not ActionUtility.is_empty(action.get('smtp_userid')):
                action['smtp_userid'] = Utility.decrypt_message(action['smtp_userid'])
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("Email action not found")
        return action

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker):
        status = "SUCCESS"
        exception = None
        action_config = self.retrieve_config()
        bot_response = action_config.get("response")
        to_email = action_config['to_email']
        try:
            for mail in to_email:
                body = ActionUtility.prepare_email_body(tracker.events, action_config['subject'], mail)
                await Utility.trigger_email(email=[mail],
                                            subject=f"{tracker.sender_id} {action_config['subject']}",
                                            body=body,
                                            smtp_url=action_config['smtp_url'],
                                            smtp_port=action_config['smtp_port'],
                                            sender_email=action_config['from_email'],
                                            smtp_password=action_config['smtp_password'],
                                            smtp_userid=action_config.get("smtp_userid"),
                                            tls=action_config['tls'],
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
                intent=tracker.get_intent_of_latest_message(),
                action=action_config['action_name'],
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                bot_response=bot_response,
                status=status
            ).save()
        dispatcher.utter_message(bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}
