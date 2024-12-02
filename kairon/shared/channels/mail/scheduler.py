from datetime import datetime, timedelta
from urllib.parse import urljoin

from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from pymongo import MongoClient

from kairon import Utility
from kairon.events.definitions.mail_channel_schedule import MailChannelScheduleEvent
from kairon.exceptions import AppException
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
        bots_list = [bot['bot'] for bot in bots]
        bots = set(bots_list)

        unscheduled_bots = bots - MailScheduler.scheduled_bots
        for bot in unscheduled_bots:
            first_schedule_time = datetime.now() + timedelta(seconds=5)
            MailScheduler.scheduler.add_job(MailScheduler.process_mails,
                                            'date', args=[bot, MailScheduler.scheduler], run_date=first_schedule_time)
            MailScheduler.scheduled_bots.add(bot)

        MailScheduler.scheduled_bots = MailScheduler.scheduled_bots.intersection(bots)
        if is_initialized:
            MailScheduler.scheduler.start()
            return True
        return False

    @staticmethod
    def request_epoch():
        event_server_url = Utility.get_event_server_url()
        resp = Utility.execute_http_request(
            "GET",
            urljoin(
                event_server_url,
                "/api/mail/request_epoch",
            ),
            err_msg=f"Failed to request epoch",
        )
        if not resp['success']:
            raise AppException("Failed to request email channel epoch")

    @staticmethod
    def process_mails(bot, scheduler: BackgroundScheduler = None):

        if bot not in MailScheduler.scheduled_bots:
            return
        logger.info(f"MailScheduler: Processing mails for bot {bot}")
        next_timestamp = MailScheduler.read_mailbox_and_schedule_events(bot)
        MailScheduler.scheduler.add_job(MailScheduler.process_mails, 'date', args=[bot, scheduler], run_date=next_timestamp)
        MailScheduler.epoch()

    @staticmethod
    def read_mailbox_and_schedule_events(bot) -> datetime:
        vals = MailProcessor.read_mails(bot)
        print(vals)
        emails, user, next_delay = vals
        for email in emails:
            MailChannelScheduleEvent(bot, user).enqueue(mails=[email])
        next_timestamp = datetime.now() + timedelta(seconds=next_delay)
        return next_timestamp









