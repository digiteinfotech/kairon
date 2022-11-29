from typing import Text

from kairon import Utility
from kairon.events.definitions.base import EventsBase
from kairon.shared.auth import Authentication
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import ACCESS_ROLES, TOKEN_TYPE, EVENT_STATUS
from kairon.shared.data.model_processor import ModelProcessor
from kairon.shared.data.utils import DataUtility


class ModelTrainingEvent(EventsBase):
    """
    Event to train a model for a particular bot.
    """

    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise event.
        """
        self.bot = bot
        self.user = user

    def validate(self):
        """
        Validates if there is enough data to train,
        an event is already running for that particular bot and also
        whether the event trigger limit has exceeded.
        """
        DataUtility.validate_existing_data_train(self.bot)
        ModelProcessor.is_training_inprogress(self.bot)
        ModelProcessor.is_daily_training_limit_exceeded(self.bot)

    def enqueue(self):
        """
        Send event to event server.
        """
        try:
            token, _ = Authentication.generate_integration_token(
                self.bot, self.user, ACCESS_ROLES.TESTER.value, expiry=180, token_type=TOKEN_TYPE.DYNAMIC.value
            )
            payload = {'bot': self.bot, 'user': self.user, 'token': token}
            ModelProcessor.set_training_status(self.bot, self.user, EVENT_STATUS.ENQUEUED.value)
            Utility.request_event_server(EventClass.model_training, payload)
        except Exception as e:
            ModelProcessor.delete_enqueued_event_log(self.bot)
            raise e

    def execute(self, **kwargs):
        """
        Execute the event.
        """
        from kairon.train import start_training

        return start_training(self.bot, self.user, kwargs.get('token'))
