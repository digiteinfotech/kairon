from typing import Text
from loguru import logger
from kairon import Utility
from kairon.events.definitions.base import EventsBase
from kairon.exceptions import AppException
from kairon.shared.channels.mail.constants import MailConstants
from kairon.shared.channels.mail.processor import MailProcessor
from kairon.shared.constants import EventClass


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
        validate mail channel exists and works properly
        """
        return MailProcessor.validate_imap_connection(self.bot) and MailProcessor.validate_smtp_connection(self.bot)

    def enqueue(self, **kwargs):
        """
        Send event to event server.
        """
        try:
            payload = {'bot': self.bot, 'user': self.user}
            self.validate()
            Utility.request_event_server(EventClass.mail_channel_read_mails, payload)
        except Exception as e:
            logger.error(str(e))
            raise AppException(e)

    def execute(self, **kwargs):
        """
        Execute the event.
        """
        try:
            emails, _ = MailProcessor.read_mails(self.bot)
            batch_size = MailConstants.PROCESS_MESSAGE_BATCH_SIZE
            for i in range(0, len(emails), batch_size):
                batch = emails[i:i + batch_size]
                MailProcessor.process_message_task(self.bot, batch)
        except Exception as e:
            raise AppException(f"Failed to schedule mail reading for bot {self.bot}. Error: {str(e)}")
