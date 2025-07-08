from datetime import datetime, date
from typing import Text
from loguru import logger
from kairon import Utility
from kairon.events.definitions.base import EventsBase
from kairon.shared.constants import EventClass
from kairon.shared.data.collection_processor import DataProcessor
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.data.utils import ChatHistoryUtils


class DeleteHistoryEvent(EventsBase):
    """
    Event to delete and archive conversation
    history of either for the bot or a sender in the bot.
    """

    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise event.
        """
        self.bot = bot
        self.user = user
        self.till_date = kwargs.get('till_date', datetime.utcnow().date())
        if not isinstance(self.till_date, date):
            self.till_date = datetime.strptime(self.till_date, "%Y-%m-%d").date()
        self.sender_id = kwargs.get('sender_id') if not Utility.check_empty_string(kwargs.get('sender_id')) else ''

    def validate(self):
        """
        Validate if an event is already in progress and the
        history is being maintained with kairon.
        """
        HistoryDeletionLogProcessor.is_event_in_progress(bot=self.bot)
        ChatHistoryUtils.validate_history_endpoint(bot=self.bot)

    def enqueue(self):
        """
        Send event to event server.
        """
        try:
            payload = {'bot': self.bot, 'user': self.user,
                       'till_date': Utility.convert_date_to_string(self.till_date), 'sender_id': self.sender_id}
            HistoryDeletionLogProcessor.add_log(
                self.bot, self.user, self.till_date,
                status=EVENT_STATUS.ENQUEUED.value, sender_id=self.sender_id
            )
            Utility.request_event_server(EventClass.delete_history, payload)
        except Exception as e:
            HistoryDeletionLogProcessor.delete_enqueued_event_log(self.bot)
            raise e

    def execute(self, **kwargs):
        """
        Execute the event.
        """
        from kairon.history.processor import HistoryProcessor
        from datetime import datetime
        today = datetime.today().date()
        try:
            HistoryDeletionLogProcessor.add_log(
                self.bot, self.user, self.till_date,
                status=EVENT_STATUS.INPROGRESS.value, sender_id=self.sender_id
            )
            if not Utility.check_empty_string(self.sender_id):
                HistoryProcessor.delete_user_history(self.bot, self.sender_id, self.till_date)
                if self.till_date == today:
                    DataProcessor.delete_collection_data_with_user(self.bot, self.sender_id)
            else:
                HistoryProcessor.delete_bot_history(self.bot, self.till_date)
            HistoryDeletionLogProcessor.add_log(
                self.bot, self.user, status=EVENT_STATUS.COMPLETED.value, sender_id=self.sender_id
            )
        except Exception as e:
            logger.error(str(e))
            HistoryDeletionLogProcessor.add_log(self.bot, self.user, exception=str(e), status=EVENT_STATUS.FAIL.value)
