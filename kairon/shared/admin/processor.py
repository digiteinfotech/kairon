from typing import Text
from loguru import logger
from mongoengine import DoesNotExist
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.admin.data_objects import BotSecrets, LLMSecret


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

    @staticmethod
    def add_bot_secret(bot: Text, user: Text, name: Text, secret: Text):
        Utility.is_exist(BotSecrets, bot=bot, secret_type=name, exp_message="Bot secret exists!")
        secret_object = BotSecrets(bot=bot, user=user, secret_type=name, value=secret).save()
        return secret_object.to_mongo().to_dict()['_id']

    @staticmethod
    def get_llm_secret(llm_type: Text, bot: Text = None):
        """
        Retrieves LLM secrets.

        @param bot: bot id
        @param llm_type: llm type
        """
        try:
            try:
                secret = LLMSecret.objects(bot=bot, llm_type=llm_type).get()
            except DoesNotExist:
                secret = LLMSecret.objects(llm_type=llm_type, bot__exists=False).get()

            result = {}
            if not Utility.check_empty_string(secret.api_key):
                result['api_key'] = Utility.decrypt_message(secret.api_key)
            if not Utility.check_empty_string(secret.api_version):
                result['api_version'] = secret.api_version
            if not Utility.check_empty_string(secret.api_base_url):
                result['api_base_url'] = secret.api_base_url

            return result
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException(f"LLM secret for '{llm_type}' is not configured!")

    def check_llm_model_exists(model_to_check: Text, llm_type: Text, bot: Text = None):
        """
        Check if a specific model is available for the given LLM type and bot
        @param model_to_check: Model name to check
        @param llm_type: LLM type
        @param bot: bot id
        @raises ActionFailure: If model is not available for the given LLM type
        """
        try:
            LLMSecret.objects(bot=bot, llm_type=llm_type, models__in=[model_to_check]).get()
        except DoesNotExist:
            try:
                LLMSecret.objects(llm_type=llm_type, bot__exists=False, models__in=[model_to_check]).get()
            except DoesNotExist:
                raise ActionFailure(f"The model '{model_to_check}' is not available for '{llm_type}'.")