from typing import Text
from loguru import logger
from kairon import Utility
from kairon.events.definitions.base import EventsBase
from kairon.exceptions import AppException
from kairon.shared.channels.mail.processor import MailProcessor
from kairon.shared.constants import EventClass


class MailProcessEvent(EventsBase):
    """
    Event to start mail channel scheduler if not already running.
    """

    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise event.
        """
        self.bot = bot
        self.user = user

    def validate(self):
        """
        validate mail channel exists
        """
        return MailProcessor.validate_smtp_connection(self.bot)


    def enqueue(self, **kwargs):
        """
        Send event to event server.
        """
        try:
            mails: list = kwargs.get('mails', [])
            payload = {'bot': self.bot, 'user': self.user, 'mails': mails}
            Utility.request_event_server(EventClass.mail_channel_process_mails, payload)
        except Exception as e:
            logger.error(str(e))
            raise AppException(e)

    def execute(self, **kwargs):
        """
        Execute the event.
        """
        try:
            mails = kwargs.get('mails')
            if mails:
                MailProcessor.process_message_task(self.bot, mails)
        except Exception as e:
            logger.error(str(e))
            raise AppException(e)



class MailReadEvent(EventsBase):
    """
    Event to read mails from mail channel and create events for each mail tp process them via bot
    """

    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise event.
        """
        self.bot = bot
        self.user = user

    def validate(self):
        """
        validate mail channel exists
        """
        return MailProcessor.validate_imap_connection(self.bot)

    def enqueue(self, **kwargs):
        """
        Send event to event server.
        """
        try:
            payload = {'bot': self.bot, 'user': self.user}
            Utility.request_event_server(EventClass.mail_channel_read_mails, payload)
        except Exception as e:
            logger.error(str(e))
            raise AppException(e)

    def execute(self, **kwargs):
        """
        Execute the event.
        """
        try:
            vals = MailProcessor.read_mails(self.bot)
            print(vals)
            emails, user, next_delay = vals
            for email in emails:
                ev = MailProcessEvent(self.bot, self.user)
                ev.validate()
                ev.enqueue(mails=[email])

        except Exception as e:
            raise AppException(f"Failed to schedule mail reading for bot {self.bot}. Error: {str(e)}")
