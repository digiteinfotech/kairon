from calendar import timegm
from datetime import datetime
from pickle import dumps, HIGHEST_PROTOCOL
from typing import Text, Dict, Any

from apscheduler.triggers.date import DateTrigger
from apscheduler.util import astimezone
from apscheduler.util import obj_to_ref
from bson import Binary
from dateutil import parser as date_parser
from loguru import logger
from mongoengine import DoesNotExist
from pymongo import MongoClient
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from tzlocal import get_localzone
from uuid6 import uuid7

from kairon import Utility
from kairon.actions.definitions.base import ActionsBase
from kairon.events.executors.factory import ExecutorFactory
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import ActionServerLogs, ScheduleAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.callback.data_objects import CallbackConfig


class ActionSchedule(ActionsBase):
    __client = MongoClient(Utility.environment['database']['url'])
    __events_db = Utility.environment['events']['queue']['name']
    __job_store_name = Utility.environment['events']['scheduler']['collection']

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
        bot_response = None
        exception = None
        dispatch_bot_response = True
        status = "SUCCESS"
        msg_logger = []
        schedule_data_log = {}
        schedule_action = None
        schedule_time = None
        timezone = None
        pyscript_code = None
        try:
            action_config = self.retrieve_config()
            dispatch_bot_response = action_config.get('dispatch_bot_response', True)
            bot_response = action_config.get('response_text')
            tracker_data = ActionUtility.build_context(tracker, True)
            tracker_data.update({'bot': self.bot})
            schedule_action = action_config['schedule_action']
            timezone = action_config['timezone']
            callback = CallbackConfig.get_entry(name=schedule_action, bot=self.bot)
            pyscript_code = callback['pyscript_code']
            schedule_time, _ = ActionUtility.get_parameter_value(tracker_data,
                                                                 action_config['schedule_time'],
                                                                 self.bot)
            logger.info(f"schedule_action: {schedule_action}, schedule_time: {schedule_time}")

            schedule_data, schedule_data_log = ActionUtility.prepare_request_with_bot(tracker_data,
                                                                                      action_config['params_list'],
                                                                                      self.bot)
            logger.info("schedule_data: " + str(schedule_data_log))
            event_data = {'data': {'source_code': callback['pyscript_code'],
                                   'predefined_objects': schedule_data
                                   },
                          'date_time': date_parser.parse(schedule_time),
                          'timezone': action_config['timezone']
                          }
            await self.add_schedule_job(**event_data)
        except Exception as e:
            exception = e
            self.__is_success = False
            logger.exception(e)
            status = "FAILURE"
            bot_response = "Sorry, I am unable to process your request at the moment."
        finally:
            if dispatch_bot_response:
                dispatcher.utter_message(bot_response)
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

    async def add_schedule_job(self,
                               date_time: datetime,
                               data: Dict,
                               timezone: Text,
                               kwargs=None):
        func = obj_to_ref(ExecutorFactory.get_executor().execute_task)

        _id = uuid7().hex
        data['predefined_objects']['event'] = _id
        args = (func, "scheduler_evaluator", data,)
        trigger = DateTrigger(run_date=date_time, timezone=timezone)

        next_run_time = trigger.get_next_fire_time(None, datetime.now(astimezone(timezone) or get_localzone()))

        job_kwargs = {
            'version': 1,
            'trigger': trigger,
            'executor': "default",
            'func': func,
            'args': tuple(args) if args is not None else (),
            'kwargs': dict(kwargs) if kwargs is not None else {},
            '_id': _id,
            'name': "execute_task",
            'misfire_grace_time': 7200,
            'coalesce': True,
            'next_run_time': next_run_time,
            'max_instances': 1,
        }

        logger.info(job_kwargs)

        self.__save_job(_id, job_kwargs, next_run_time)

        event_server = Utility.environment['events']['server_url']

        http_response, status_code, _, _ = await ActionUtility.execute_request_async(
            f"{event_server}/api/events/dispatch/{_id}",
            "GET")

        if status_code != 200:
            raise AppException(http_response)
        else:
            logger.info(http_response)

    @property
    def is_success(self):
        return self.__is_success

    @property
    def response(self):
        return self.__response

    def __save_job(self, _id, job_kwargs, next_run_time):
        self.__client.get_database(self.__events_db).get_collection(self.__job_store_name).insert_one({
            '_id': _id,
            'next_run_time': self.datetime_to_utc_timestamp(next_run_time),
            'job_state': Binary(dumps(job_kwargs, HIGHEST_PROTOCOL))
        })

    def datetime_to_utc_timestamp(self, timeval):
        """
        Converts a datetime instance to a timestamp.

        :type timeval: datetime
        :rtype: float

        """
        if timeval is not None:
            return timegm(timeval.utctimetuple()) + timeval.microsecond / 1000000
