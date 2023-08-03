import os

from kairon.exceptions import AppException
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets
from kairon.shared.admin.processor import Sysadmin

os.environ["system_file"] = "./tests/testing_data/system.yaml"
import pytest
from mongoengine import connect
from kairon.shared.utils import Utility


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
        assert BotSecrets.objects(bot=bot, secret_type=BotSecretType.gpt_key.value).get()

    def test_add_bot_secret_already_exists(self):
        bot = "test_bot"
        user = "test_user"
        secret = "test_secret"
        with pytest.raises(AppException, match="Bot secret exists!"):
            Sysadmin.add_bot_secret(bot, user, BotSecretType.gpt_key.value, secret)
