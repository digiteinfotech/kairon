import asyncio
from datetime import datetime, timedelta

from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from pymongo import MongoClient

from kairon import Utility
from kairon.shared.channels.mail.processor import MailProcessor
from kairon.shared.chat.data_objects import Channels
from kairon.shared.constants import ChannelTypes
from loguru import logger


class MailScheduler:
    scheduler = None
    scheduled_bots = set()

    @staticmethod
    def epoch():
        is_initialized = False
        if not MailScheduler.scheduler:
            is_initialized = True
            client = MongoClient(Utility.environment['database']['url'])
            events_db = Utility.environment['events']['queue']['mail_queue_name']
            job_store_name = Utility.environment['events']['scheduler']['mail_scheduler_collection']

            MailScheduler.scheduler = BackgroundScheduler(
                jobstores={job_store_name: MongoDBJobStore(events_db, job_store_name, client)},
                job_defaults={'coalesce': True, 'misfire_grace_time': 7200})

        bots = Channels.objects(connector_type= ChannelTypes.MAIL)
        bots = set(bot['bot'] for bot in bots.values_list('bot'))


        unscheduled_bots = bots - MailScheduler.scheduled_bots
        logger.info(f"MailScheduler: Epoch: {MailScheduler.scheduled_bots}")
        for bot in unscheduled_bots:
            first_schedule_time = datetime.now() + timedelta(seconds=5)
            MailScheduler.scheduler.add_job(MailScheduler.process_mails_task,
                                            'date', args=[bot, MailScheduler.scheduler], run_date=first_schedule_time)
            MailScheduler.scheduled_bots.add(bot)

        MailScheduler.scheduled_bots = MailScheduler.scheduled_bots.intersection(bots)
        if is_initialized:
            MailScheduler.scheduler.start()
            return True
        return False

    @staticmethod
    def process_mails_task(bot, scheduler: BackgroundScheduler = None):
        if scheduler:
            asyncio.run(MailScheduler.process_mails(bot, scheduler))

    @staticmethod
    async def process_mails(bot, scheduler: BackgroundScheduler = None):

        if bot not in MailScheduler.scheduled_bots:
            return
        logger.info(f"MailScheduler: Processing mails for bot {bot}")
        _, next_delay = await MailProcessor.process_mails(bot, scheduler)
        logger.info(f"next_delay: {next_delay}")
        next_timestamp = datetime.now() + timedelta(seconds=next_delay)
        MailScheduler.scheduler.add_job(MailScheduler.process_mails_task, 'date', args=[bot, scheduler], run_date=next_timestamp)
        MailScheduler.epoch()
