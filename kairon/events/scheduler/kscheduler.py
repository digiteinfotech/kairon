import logging
from typing import Text

from apscheduler.events import JobEvent, EVENT_JOB_ADDED
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from pymongo import MongoClient

from kairon import Utility
from kairon.events.executors.factory import ExecutorFactory
from kairon.events.scheduler.base import EventSchedulerBase
from kairon.exceptions import AppException
from datetime import datetime
from apscheduler.events import JobEvent, EVENT_JOB_ADDED
from kairon.shared.data.constant import TASK_TYPE

logging.getLogger('apscheduler').setLevel(logging.DEBUG)
logging.basicConfig()


class KScheduler(EventSchedulerBase):
    __client = MongoClient(Utility.environment['database']['url'])
    __events_db = Utility.environment['events']['queue']['name']
    __job_store_name = Utility.environment['events']['scheduler']['collection']
    __scheduler = BackgroundScheduler(
        jobstores={__job_store_name: MongoDBJobStore(__events_db, __job_store_name, __client)},
        job_defaults={'coalesce': True, 'misfire_grace_time': 7200})
    __scheduler.start()

    def update_job(self, event_id: Text, task_type: TASK_TYPE, cron_exp: Text, event_class: Text, data: dict, timezone=None):
        try:
            func = ExecutorFactory.get_executor().execute_task
            args = (event_class, data,)
            kwargs = {'task_type': task_type}
            trigger = CronTrigger.from_crontab(cron_exp, timezone=timezone)
            changes = {
                "func": func, "trigger": trigger, "args": args, "kwargs": kwargs, "name": func.__name__
            }
            KScheduler.__scheduler.modify_job(event_id, KScheduler.__job_store_name, **changes)
            KScheduler.__scheduler.reschedule_job(event_id, KScheduler.__job_store_name, trigger)
        except JobLookupError as e:
            logger.exception(e)
            raise AppException(e)

    def add_job(self, event_id: Text, task_type: TASK_TYPE, cron_exp: Text, event_class: Text, data: dict, timezone=None):
        func = ExecutorFactory.get_executor().execute_task
        args = (event_class, task_type, data)
        kwargs = {'task_type': task_type}
        trigger = CronTrigger.from_crontab(cron_exp, timezone=timezone)
        KScheduler.__scheduler.add_job(func, trigger, args, kwargs, id=event_id, name=func.__name__,
                                       jobstore=KScheduler.__job_store_name)

    def list_jobs(self):
        return [job.id for job in KScheduler.__scheduler.get_jobs(jobstore=KScheduler.__job_store_name)]

    def get_job(self, event_id):
        job_info = KScheduler.__scheduler.get_job(event_id, jobstore=KScheduler.__job_store_name)
        if not job_info:
            raise AppException("Job not found!")
        return job_info

    def delete_job(self, event_id):
        try:
            KScheduler.__scheduler.remove_job(event_id, jobstore=KScheduler.__job_store_name)
        except JobLookupError as e:
            logger.exception(e)
            raise AppException(e)

    def dispatch_event(self, event_id):
        event = JobEvent(EVENT_JOB_ADDED, event_id, KScheduler.__job_store_name)
        KScheduler.__scheduler._dispatch_event(event)
        KScheduler.__scheduler.wakeup()
