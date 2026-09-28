from typing import Text

from loguru import logger

from kairon import Utility
from kairon.events.definitions.base import EventsBase
from kairon.exceptions import AppException
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS, STATUSES
from kairon.shared.multilingual.processor import MultilingualLogProcessor


class MultilingualEvent(EventsBase):
    """
    Event to create bot in a language different from source bot's language.
    Training examples, responses (utterances as well as the ones configured in custom actions) are
    translated.
    """

    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise the event.
        """
        self.bot = bot
        self.user = user
        self.dest_lang = kwargs.get('dest_lang')
        self.translate_responses = kwargs.get('translate_responses', True)
        self.translate_actions = kwargs.get('translate_actions', False)

    def validate(self):
        """
        Validates if an event is already running for that particular bot and also
        whether the event trigger limit has exceeded.
        """
        MultilingualLogProcessor.is_event_in_progress(self.bot)
        MultilingualLogProcessor.is_limit_exceeded(self.bot)
        bot_info = AccountProcessor.get_bot(self.bot)
        if bot_info['metadata']['language'] == self.dest_lang:
            raise AppException("Source and destination language cannot be the same.")

    def enqueue(self):
        """
        Send event to event server.
        """
        translate_responses = '--translate-responses' if self.translate_responses is True else ''
        translate_actions = '--translate-actions' if self.translate_actions is True else ''
        payload = {
            'bot': self.bot, 'user': self.user, "dest_lang": self.dest_lang,
            "translate_responses": translate_responses, "translate_actions": translate_actions
        }
        MultilingualLogProcessor.add_log(
            source_bot=self.bot, user=self.user, d_lang=self.dest_lang, translate_responses=self.translate_responses,
            translate_actions=self.translate_actions, event_status=EVENT_STATUS.ENQUEUED.value
        )
        try:
            Utility.request_event_server(EventClass.multilingual, payload)
        except Exception as e:
            MultilingualLogProcessor.delete_enqueued_event_log(self.bot)
            raise e

    def execute(self, **kwargs):
        """
        Execute the event.
        """
        from kairon.multilingual.processor import MultilingualTranslator

        translation_status = STATUSES.FAIL.value
        try:
            bot_info = AccountProcessor.get_bot(self.bot)
            account = bot_info['account']
            source_bot_name = bot_info['name']
            s_lang = bot_info['metadata']['language']

            MultilingualLogProcessor.add_log(
                source_bot=self.bot, user=self.user, source_bot_name=source_bot_name, s_lang=s_lang,
                d_lang=self.dest_lang, account=account, event_status=EVENT_STATUS.INPROGRESS.value
            )

            # translate bot and get new bot id
            multilingual_translator = MultilingualTranslator(account=account, user=self.user)
            destination_bot = multilingual_translator.create_multilingual_bot(
                base_bot_id=self.bot, base_bot_name=source_bot_name, s_lang=s_lang, d_lang=self.dest_lang,
                translate_responses=self.translate_responses, translate_actions=self.translate_actions
            )
            translation_status = STATUSES.SUCCESS.value if destination_bot else STATUSES.FAIL.value
            MultilingualLogProcessor.update_summary(
                self.bot, self.user, destination_bot=destination_bot, status=translation_status,
                event_status=EVENT_STATUS.COMPLETED.value
            )
        except Exception as e:
            logger.error(str(e))
            MultilingualLogProcessor.add_log(
                source_bot=self.bot, user=self.user, exception=str(e), status=translation_status,
                event_status=EVENT_STATUS.FAIL.value
            )
