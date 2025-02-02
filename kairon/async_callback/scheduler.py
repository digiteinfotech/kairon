from apscheduler.triggers.date import DateTrigger
from apscheduler.util import astimezone
from pymongo import MongoClient
import os
import boto3
from typing import Dict, Text
from datetime import datetime
from uuid6 import uuid7
from pickle import dumps, HIGHEST_PROTOCOL
from calendar import timegm
from bson import Binary
from tzlocal import get_localzone
import requests
from loguru import logger

from kairon import Utility

ssm = boto3.client('ssm')
# client = MongoClient(
#     ssm.get_parameter(Name=os.getenv('DATABASE_URL'), WithDecryption=True).get('Parameter', {}).get('Value'))
#
# platform_db = client.get_database()
# events_db = client.get_database(
#     ssm.get_parameter(Name=os.getenv('EVENTS_DB_NAME'), WithDecryption=True).get('Parameter', {}).get('Value'))

# os.environ['EVENTS_EXECUTOR_TYPE'] = 'aws_lambda'
# os.environ['DATABASE_URL'] = 'uat_DATABASE_URL'
# os.environ['EVENTS_DB_NAME'] = 'uat_EVENTS_DB_NAME'
# os.environ['VECTOR_DB_URL'] = 'uat_VECTOR_DB_URL'
print(os.getenv('EVENTS_EXECUTOR_TYPE'))
print(os.getenv('DATABASE_URL'))

database_url = Utility.environment["database"]["url"]
# database_url = "mongodb://localhost:27017/conversations"
client = MongoClient(database_url)
platform_db = client.get_database()
events_db_name = Utility.environment["events"]["queue"]["name"]
events_db = client.get_database(events_db_name)
scheduler_collection = Utility.environment["events"]["scheduler"]["collection"]
job_store_name = events_db.get_collection(scheduler_collection)

callback = platform_db.get_collection("callback_config")
event_server = Utility.environment["events"]["server_url"]




# client = MongoClient("mongodb://localhost:27017/")
# platform_db = client.get_database("conversations")
# print(platform_db)
# events_db = client.get_database("kairon_events")
# print(events_db)
#
# job_store_name = events_db.get_collection(os.getenv('EVENT_SCHEDULER_COLLECTION', 'kscheduler'))
# callback = platform_db.get_collection(os.getenv("CALLBACK_CONFIG", "callback_config"))
# event_server = os.getenv('EVENT_SERVER_ENDPOINT')

__executors = {
    "aws_lambda": "kairon.events.executors.lamda:LambdaExecutor.execute_task",
    "dramatiq": "kairon.events.executors.dramatiq:DramatiqExecutor.execute_task",
    "standalone": "kairon.events.executors.standalone:StandaloneExecutor.execute_task",
}


def generate_id():
    return uuid7().hex


def datetime_to_utc_timestamp(timeval):
    """
    Converts a datetime instance to a timestamp.

    :type timeval: datetime
    :rtype: float

    """
    if timeval is not None:
        return timegm(timeval.utctimetuple()) + timeval.microsecond / 1000000


def add_schedule_job(schedule_action: Text, date_time: datetime, data: Dict, timezone: Text, _id: Text = None,
                     bot: Text = None, kwargs=None):
    if not bot:
        raise Exception("Missing bot id")

    if not _id:
        _id = uuid7().hex

    print(f"bot: {bot}, name: {schedule_action}")

    if not data:
        data = {}

    data['bot'] = bot
    data['event'] = _id

    callback_config = callback.find_one({"bot": bot, 'name': schedule_action})

    script = callback_config['pyscript_code']

    executor_type = os.getenv('EVENTS_EXECUTOR_TYPE', 'aws_lambda')
    if executor_type not in __executors.keys():
        raise Exception(f"Executor type not configured in system.yaml. Valid types: {__executors.values()}")
    func = __executors[executor_type]

    schedule_data = {'source_code': script,
                     'predefined_objects': data
                     }

    args = (func, "scheduler_evaluator", schedule_data,)
    kwargs = {'task_type': "Callback"} if kwargs is None else {**kwargs, 'task_type': "Callback"}
    trigger = DateTrigger(run_date=date_time, timezone=timezone)

    next_run_time = trigger.get_next_fire_time(None, datetime.now(astimezone(timezone) or get_localzone()))

    job_kwargs = {
        'version': 1,
        'trigger': trigger,
        'executor': "default",
        'func': func,
        'args': tuple(args) if args is not None else (),
        'kwargs': kwargs,
        'id': _id,
        'name': "execute_task",
        'misfire_grace_time': 7200,
        'coalesce': True,
        'next_run_time': next_run_time,
        'max_instances': 1,
    }

    logger.info(job_kwargs)

    job_store_name.insert_one({
        '_id': _id,
        'next_run_time': datetime_to_utc_timestamp(next_run_time),
        'job_state': Binary(dumps(job_kwargs, HIGHEST_PROTOCOL))
    })

    response = requests.get(f"{event_server}/api/events/dispatch/{_id}")
    if response.status_code != 200:
        raise Exception(response.text)
    else:
        logger.info(response.json())


def delete_schedule_job(event_id: Text, bot: Text):
    if not bot:
        raise Exception("Missing bot id")

    if not event_id:
        raise Exception("Missing event id")

    logger.info(f"event: {event_id}, bot: {bot}")

    response = requests.delete(f"{event_server}/api/events/{event_id}")
    if response.status_code != 200:
        raise Exception(response.text)
    else:
        logger.info(response.json())
