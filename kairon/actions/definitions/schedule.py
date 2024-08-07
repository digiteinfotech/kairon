from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from uuid6 import uuid7

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, ScheduleAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, DispatchType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.callback.data_objects import CallbackConfig
from kairon.shared.constants import EventClass


class ActionSchedule(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize cakkback action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name
        self.__response = None
        self.__is_success = False

    def retrieve_config(self):
        """
        Fetch AsyncCallbackActionConfig configuration parameters from the database

        :return: AsyncCallbackActionConfig containing configuration for the action as a dict.
        """
        try:
            config = ScheduleAction.objects().get(bot=self.bot,
                                                  name=self.name, status=True).to_mongo().to_dict()
            return config
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Schedule action found for given action and bot")

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        """
        Retrieves action config and executes it.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        from kairon.events.scheduler.kscheduler import KScheduler

        bot_response = None
        exception = None
        dispatch_bot_response = True
        status = "SUCCESS"
        msg_logger = []
        schedule_data_log = []
        schedule_action = None
        schedule_time = None
        timezone = None
        pyscript_code = None
        try:
            action_config = self.retrieve_config()
            dispatch_bot_response = action_config.get('dispatch_bot_response', True)
            bot_response = action_config.get('bot_response')
            tracker_data = ActionUtility.build_context(tracker, True)
            tracker_data.update({'bot': self.bot})
            schedule_action = action_config['schedule_action']
            timezone = action_config['timezone']
            callback = CallbackConfig.get_entry(name=schedule_action, bot=self.bot)
            pyscript_code = callback['pyscript_code']
            schedule_time = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data,
                                                                                     action_config['schedule_time'],
                                                                                     self.bot)
            logger.info(f"schedule_action: {schedule_action}, schedule_time: {schedule_time}")

            schedule_data, schedule_data_log = ActionUtility.prepare_request(tracker_data,
                                                                             action_config['params_list'],
                                                                             self.bot)
            logger.info("schedule_data: " + str(schedule_data_log))
            event_data = {'data': {'script': callback['pyscript_code'],
                                   'predefined_objects': schedule_data
                                   },
                          'datetime': schedule_time,
                          'timezone': action_config['timezone']
                          }
            KScheduler().add_job_for_date(event_class=EventClass.scheduler_evaluator,
                                          event_id=uuid7().hex, **event_data)
        except Exception as e:
            exception = e
            self.__is_success = False
            logger.exception(e)
            status = "FAILURE"
            bot_response = bot_response if bot_response else "Sorry, I am unable to process your request at the moment."
        finally:
            if dispatch_bot_response:
                bot_response, message = ActionUtility.handle_utter_bot_response(dispatcher, DispatchType.text.value,
                                                                                bot_response)
                if message:
                    msg_logger.append(message)
            ActionServerLogs(
                type=ActionType.schedule_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot_response=str(bot_response) if bot_response else None,
                messages=msg_logger,
                exception=str(exception) if exception else None,
                bot=self.bot,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                schedule_action=schedule_action,
                schedule_time=schedule_time,
                timezone=timezone,
                pyscript_code=pyscript_code,
                data=schedule_data_log
            ).save()
        return {}

    @property
    def is_success(self):
        return self.__is_success

    @property
    def response(self):
        return self.__response
