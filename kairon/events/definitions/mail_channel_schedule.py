from typing import Text
from loguru import logger
from kairon import Utility
from kairon.events.definitions.base import EventsBase
from kairon.shared.channels.mail.processor import MailProcessor
from kairon.shared.constants import EventClass, ChannelTypes


class MailChannelScheduleEvent(EventsBase):
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
        pass


    def enqueue(self, **kwargs):
        """
        Send event to event server.
        """
        try:
            mails: list = kwargs.get('mails', [])
            payload = {'bot': self.bot, 'user': self.user, 'mails': mails}
            Utility.request_event_server(EventClass.email_channel_scheduler, payload)
        except Exception as e:
            logger.error(str(e))
            raise e

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
            raise e