import logging
import os
import threading
import time
from typing import Text, Optional

from apscheduler.events import JobEvent, EVENT_JOB_ADDED, EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_EXECUTED
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from loguru import logger
from pymongo import MongoClient

from kairon import Utility
from kairon.events.executors.factory import ExecutorFactory
from kairon.events.scheduler.base import EventSchedulerBase
from kairon.events.scheduler.resilient_scheduler import ResilientBackgroundScheduler
from kairon.exceptions import AppException
from kairon.shared.data.constant import TASK_TYPE

logging.getLogger('apscheduler').setLevel(logging.DEBUG)
logging.basicConfig()

_start_lock = threading.Lock()


def _on_job_event(event):
    if event.exception:
        logger.error("SCHEDULER_JOB_FAILED | job_id={} | error={}", event.job_id, event.exception)
    elif event.code == EVENT_JOB_MISSED:
        logger.warning("SCHEDULER_JOB_MISSED | job_id={} | scheduled={}", event.job_id,
                       getattr(event, 'scheduled_run_time', None))
    else:
        logger.info("SCHEDULER_JOB_EXECUTED | job_id={}", event.job_id)


def _revive_scheduler_thread(scheduler):
    """
    Starts a new polling thread for a scheduler whose state is still RUNNING but whose thread died.
    Executors and job stores are left untouched: scheduler.shutdown() would stop the executor pool
    (later jobs fail with "cannot schedule new futures after shutdown") and close the shared MongoClient.
    """
    thread = threading.Thread(target=scheduler._main_loop, name='APScheduler', daemon=scheduler._daemon)
    scheduler._thread = thread
    thread.start()


def _build_watchdog(scheduler):
    interval = int(os.getenv(
        "SCHEDULER_WATCHDOG_INTERVAL",
        Utility.environment.get('events', {}).get('scheduler', {})
        .get('watchdog_interval_seconds', 60)
    ))

    def _watch():
        while True:
            time.sleep(interval)
            # `running` only reflects scheduler state; it stays True when the scheduler thread itself dies.
            thread = getattr(scheduler, '_thread', None)
            thread_dead = scheduler.running and thread is not None and not thread.is_alive()
            if not scheduler.running or thread_dead:
                logger.critical("APScheduler thread found dead — restarting scheduler")
                try:
                    if thread_dead:
                        _revive_scheduler_thread(scheduler)
                    else:
                        scheduler.start()
                    logger.info("APScheduler restarted by watchdog")
                except Exception as exc:
                    logger.exception("Watchdog failed to restart APScheduler: {}", exc)

    t = threading.Thread(target=_watch, name="SchedulerWatchdog", daemon=True)
    t.start()
    return t


class KScheduler(EventSchedulerBase):
    __client = MongoClient(Utility.environment['database']['url'])
    __events_db = Utility.environment['events']['queue']['name']
    __job_store_name = Utility.environment['events']['scheduler']['collection']
    __scheduler = ResilientBackgroundScheduler(
        jobstores={__job_store_name: MongoDBJobStore(__events_db, __job_store_name, __client)},
        job_defaults={'coalesce': True, 'misfire_grace_time': 7200})
    __scheduler.add_listener(_on_job_event, EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_EXECUTED)
    __watchdog = None

    @staticmethod
    def start():
        """
        Starts the scheduler and its watchdog. Must be called only by the event server:
        importing this module must not start a scheduler, otherwise every process importing it
        competes with the event server for the same job store.
        """
        with _start_lock:
            if not KScheduler.__scheduler.running:
                KScheduler.__scheduler.start()
            if KScheduler.__watchdog is None:
                KScheduler.__watchdog = _build_watchdog(KScheduler.__scheduler)

    def update_job(self, event_id: Text, task_type: TASK_TYPE, event_class: Text, data: dict, timezone=None,
                   cron_exp: Optional[Text] = None, run_at: Optional[int] = None):
        try:
            func = ExecutorFactory.get_executor().execute_task
            args = (event_class, data,)
            kwargs = {'task_type': task_type}
            changes = {
                "func": func, "args": args, "kwargs": kwargs, "name": func.__name__
            }
            trigger=None
            if cron_exp:
                trigger = CronTrigger.from_crontab(cron_exp, timezone=timezone)
            elif run_at:
                trigger = DateTrigger(run_date=run_at, timezone=timezone)
            else:
                raise AppException("Either cron_exp or run_at must be provided to update job!")

            if trigger:
                changes["trigger"] = trigger

            KScheduler.__scheduler.modify_job(event_id, KScheduler.__job_store_name, **changes)
            KScheduler.__scheduler.reschedule_job(event_id, KScheduler.__job_store_name, trigger)
        except JobLookupError as e:
            logger.exception(e)
            raise AppException(e)

    def add_job(self, event_id: Text, task_type: TASK_TYPE, cron_exp: Text, event_class: Text, data: dict, timezone=None):
        func = ExecutorFactory.get_executor().execute_task
        args = (event_class, data)
        kwargs = {'task_type': task_type}
        trigger = CronTrigger.from_crontab(cron_exp, timezone=timezone)
        KScheduler.__scheduler.add_job(func, trigger, args, kwargs, id=event_id, name=func.__name__,
                                       jobstore=KScheduler.__job_store_name)

    def add_one_time_job(self, event_id: Text, task_type: TASK_TYPE, run_at: Text,
                         event_class: Text, data: dict, timezone=None):
        func = ExecutorFactory.get_executor().execute_task
        args = (event_class, data)
        kwargs = {'task_type': task_type}

        trigger = DateTrigger(run_date=run_at, timezone=timezone)
        KScheduler.__scheduler.add_job(
            func, trigger, args, kwargs,
            id=event_id, name=func.__name__,
            jobstore=KScheduler.__job_store_name
        )


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
