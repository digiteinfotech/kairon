import os

from kairon.exceptions import AppException
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets, LLMSecret
from kairon.shared.admin.processor import Sysadmin

os.environ["system_file"] = "./tests/testing_data/system.yaml"
import pytest
from mongoengine import connect, ValidationError
from kairon.shared.utils import Utility
from mongomock import MongoClient


class TestSysAdminProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        db_url = Utility.environment['database']["url"]
        pytest.db_url = db_url
        Utility.load_email_configuration()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_get_secrets_not_found(self):
        bot = "testing"
        name = BotSecretType.gpt_key.value
        with pytest.raises(AppException, match=f"Bot secret '{name}' not configured!"):
            Sysadmin.get_bot_secret(bot, name, True)

        assert Sysadmin.get_bot_secret(bot, name, raise_err=False) is None

    def test_get_secrets(self):
        bot = "testsecrettest"
        user = "test_user"
        value = "uditpandey"
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()
        secret = Sysadmin.get_bot_secret(bot, BotSecretType.gpt_key.value)
        assert secret == value

    def test_get_secrets_empty_value(self):
        bot = "test_secret"
        user = "test_user"
        value = ""
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()
        secret = Sysadmin.get_bot_secret(bot, BotSecretType.gpt_key.value)
        assert secret == value

    def test_add_bot_secret(self):
        bot = "test_bot"
        user = "test_user"
        secret = "test_secret"
        bot_secret_id = Sysadmin.add_bot_secret(bot, user, BotSecretType.gpt_key.value, secret)
        assert bot_secret_id
        bot_secret = BotSecrets.objects(bot=bot, secret_type=BotSecretType.gpt_key.value).get().to_mongo().to_dict()
        assert bot_secret['secret_type'] == 'gpt_key'
        assert Utility.decrypt_message(bot_secret['value']) == 'test_secret'

    def test_add_bot_secret_already_exists(self):
        bot = "test_bot"
        user = "test_user"
        secret = "test_secret"
        with pytest.raises(AppException, match="Bot secret exists!"):
            Sysadmin.add_bot_secret(bot, user, BotSecretType.gpt_key.value, secret)

    def test_get_llm_secret_not_found(self):
        llm_type = 'non_existent_llm'
        with pytest.raises(AppException, match=f"LLM secret for '{llm_type}' is not configured!"):
            Sysadmin.get_llm_secret(llm_type)

    def test_get_llm_secret(self):
        llm_type = 'testllm'
        bot = 'test_bot'
        user = 'test_user'
        models = ['model1', 'model2']
        api_key = 'test_api_key'
        api_version = 'v1'
        api_base_url = 'http://example.com'

        LLMSecret(llm_type=llm_type, api_key=api_key, api_version=api_version,
                  api_base_url=api_base_url, bot=bot, user=user, models=models).save()

        secret = Sysadmin.get_llm_secret(llm_type, bot)
        assert secret['api_key'] == api_key
        assert secret['api_version'] == api_version
        assert secret['api_base_url'] == api_base_url

    def test_get_llm_secret_empty_api_version(self):
        llm_type = 'testllm'
        bot = 'test_bot2'
        user = 'test_user'
        models = ['model1', 'model2']
        api_key = 'test_api_key'
        api_version = ''
        api_base_url = 'http://example.com'

        LLMSecret(llm_type=llm_type, api_key=api_key, api_version=api_version,
                  api_base_url=api_base_url, bot=bot, user=user, models=models).save()

        secret = Sysadmin.get_llm_secret(llm_type, bot)
        assert secret['api_key'] == api_key
        assert secret['api_base_url'] == api_base_url
        assert secret.get('api_version') is None

    def test_llm_secret_missing_api_key_none(self):
        llm_type = 'testllm'
        models = ['model1', 'model2']
        api_base_url = 'http://example.com'
        api_version = 'v1'
        bot = 'test_bot2'
        user = 'test_user'

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=None,
            models=models,
            api_base_url=api_base_url,
            api_version=api_version,
            bot=bot,
            user=user
        )

        with pytest.raises(ValidationError, match="api_key is required."):
            llm_secret.validate()

    def test_llm_secret_missing_api_key_empty(self):
        llm_type = 'testllm'
        models = ['model1', 'model2']
        api_base_url = 'http://example.com'
        api_version = 'v1'
        bot = 'test_bot2'
        user = 'test_user'

        # Create instance of LLMSecret with api_key as an empty string
        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key='',
            models=models,
            api_base_url=api_base_url,
            api_version=api_version,
            bot=bot,
            user=user
        )

        # Test validation
        with pytest.raises(ValidationError, match="api_key is required."):
            llm_secret.validate()