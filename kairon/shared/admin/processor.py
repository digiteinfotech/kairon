from typing import Text

from loguru import logger
from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.admin.data_objects import BotSecrets


class Sysadmin:

    @staticmethod
    def get_bot_secret(bot: Text, name: Text, raise_err: bool = True):
        """
        Retrieves bot secrets.

        @param bot: bot id
        @param name: secret name
        @param raise_err: raises exception if no bot secret is configured and true is passed
        """
        try:
            secrets = BotSecrets.objects(bot=bot, secret_type=name).get().to_mongo().to_dict()
            value = secrets.get("value")
            if not Utility.check_empty_string(value):
                value = Utility.decrypt_message(value)
            return value
        except DoesNotExist as e:
            logger.exception(e)
            if raise_err:
                raise AppException(f"Bot secret '{name}' not configured!")
