import asyncio
import datetime
import os

import jwt
from mongoengine import connect
from mongoengine.errors import ValidationError, DoesNotExist
import pytest
from pydantic import SecretStr

from kairon.api.auth import Authentication
from kairon.api.data_objects import User
from kairon.api.processor import AccountProcessor
from kairon.data_processor.data_objects import Configs, Rules, Responses
from kairon.utils import Utility
from kairon.exceptions import AppException
from stress_test.data_objects import Bot

os.environ["system_file"] = "./tests/testing_data/system.yaml"


def pytest_configure():
    return {'bot': None, 'account': None}


class TestAccountProcessor:
    @pytest.fixture(autouse=True)
    def init_connection(self):
        Utility.load_evironment()
        connect(host=Utility.environment['database']["url"])

    def test_add_account(self):
        account_response = AccountProcessor.add_account("paypal", "testAdmin")
        account = AccountProcessor.get_account(account_response["_id"])
        assert account_response
        pytest.account = account_response["_id"]
        assert account_response["_id"] == account["_id"]
        assert account_response["name"] == account["name"]
        account_response = AccountProcessor.add_account("ebay", "testAdmin")
        account = AccountProcessor.get_account(account_response["_id"])
        assert account_response
        assert account_response["_id"] == account["_id"]
        assert account_response["name"] == account["name"]

    def test_add_duplicate_account(self):
        with pytest.raises(Exception):
            AccountProcessor.add_account("paypal", "testAdmin")

    def test_add_duplicate_account_case_insentive(self):
        with pytest.raises(Exception):
            AccountProcessor.add_account("PayPal", "testAdmin")

    def test_add_blank_account(self):
        with pytest.raises(AppException):
            AccountProcessor.add_account("", "testAdmin")

    def test_add_empty_account(self):
        with pytest.raises(AppException):
            AccountProcessor.add_account(" ", "testAdmin")

    def test_add_none_account(self):
        with pytest.raises(AppException):
            AccountProcessor.add_account(None, "testAdmin")

    def test_list_bots_none(self):
        assert not list(AccountProcessor.list_bots(5))

    def test_add_bot(self):
        bot_response = AccountProcessor.add_bot("test", pytest.account, "fshaikh@digite.com", True)
        bot = Bot.objects(name="test").get().to_mongo().to_dict()
        assert bot['_id'].__str__() == bot_response['_id'].__str__()
        config = Configs.objects(bot=bot['_id'].__str__()).get().to_mongo().to_dict()
        assert config['language']
        assert config['pipeline'][6]['name'] == 'FallbackClassifier'
        assert config['pipeline'][6]['threshold'] == 0.7
        assert config['policies'][2]['name'] == 'RulePolicy'
        assert config['policies'][2]['core_fallback_action_name'] == "action_default_fallback"
        assert config['policies'][2]['core_fallback_threshold'] == 0.3
        assert Rules.objects(bot=bot['_id'].__str__()).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot['_id'].__str__(), status=True).get()
        assert Responses.objects(name='utter_default', bot=bot['_id'].__str__(), status=True).get()
        pytest.bot = bot_response['_id'].__str__()

    def test_list_bots(self):
        bot = list(AccountProcessor.list_bots(pytest.account))
        assert bot[0]['name'] == 'test'
        assert bot[0]['_id']

    def test_get_bot(self):
        bot_response = AccountProcessor.get_bot(pytest.bot)
        assert bot_response
        assert bot_response["account"] == pytest.account

    def test_add_duplicate_bot(self):
        with pytest.raises(Exception):
            AccountProcessor.add_bot("test", 1, "testAdmin")

    def test_add_duplicate_bot_case_insensitive(self):
        with pytest.raises(Exception):
            AccountProcessor.add_bot("TEST", 1, "testAdmin")

    def test_add_blank_bot(self):
        with pytest.raises(AppException):
            AccountProcessor.add_bot(" ", 1, "testAdmin")

    def test_add_empty_bot(self):
        with pytest.raises(AppException):
            AccountProcessor.add_bot("", 1, "testAdmin")

    def test_add_none_bot(self):
        with pytest.raises(AppException):
            AccountProcessor.add_bot(None, 1, "testAdmin")

    def test_add_none_user(self):
        with pytest.raises(AppException):
            AccountProcessor.add_bot('test', 1, None)

    def test_add_user(self):
        user = AccountProcessor.add_user(
            email="fshaikh@digite.com",
            first_name="Fahad Ali",
            last_name="Shaikh",
            password="Welcome@1",
            account=pytest.account,
            bot=pytest.bot,
            user="testAdmin",
        )
        assert user
        assert user["password"] != "12345"
        assert user["status"]

    def test_add_bot_for_existing_user(self):
        bot_response = AccountProcessor.add_bot("test_version_2", pytest.account, "fshaikh@digite.com", False)
        bot = Bot.objects(name="test_version_2").get().to_mongo().to_dict()
        assert bot['_id'].__str__() == bot_response['_id'].__str__()
        user = User.objects(email="fshaikh@digite.com").get()
        assert len(user.bot) == 2
        config = Configs.objects(bot=bot['_id'].__str__()).get().to_mongo().to_dict()
        assert config['language']
        assert config['pipeline'][6]['name'] == 'FallbackClassifier'
        assert config['pipeline'][6]['threshold'] == 0.7
        assert config['policies'][2]['name'] == 'RulePolicy'
        assert config['policies'][2]['core_fallback_action_name'] == "action_default_fallback"
        assert config['policies'][2]['core_fallback_threshold'] == 0.3
        assert Rules.objects(bot=bot['_id'].__str__()).get()
        assert Responses.objects(name='utter_default', bot=bot['_id'].__str__(), status=True).get()

    def test_list_bots_2(self):
        bot = list(AccountProcessor.list_bots(pytest.account))
        assert bot[0]['name'] == 'test'
        assert bot[0]['_id']
        assert bot[1]['name'] == 'test_version_2'
        assert bot[1]['_id']

    def test_update_bot_name(self):
        AccountProcessor.update_bot('test_bot', pytest.bot)
        bot = list(AccountProcessor.list_bots(pytest.account))
        assert bot[0]['name'] == 'test_bot'
        assert bot[0]['_id']

    def test_update_bot_not_exists(self):
        with pytest.raises(AppException):
            AccountProcessor.update_bot('test_bot', '5f256412f98b97335c168ef0')

    def test_update_bot_empty_name(self):
        with pytest.raises(AppException):
            AccountProcessor.update_bot(' ', '5f256412f98b97335c168ef0')

    def test_delete_bot(self):
        bot = list(AccountProcessor.list_bots(pytest.account))
        pytest.deleted_bot = bot[1]['_id']
        AccountProcessor.add_bot_for_user(pytest.deleted_bot, "fshaikh@digite.com")
        print(bot)
        print(pytest.account)
        for user in User.objects(account=pytest.account, status=True):
            print(user.to_mongo().to_dict())
        AccountProcessor.delete_bot(pytest.deleted_bot, 'testAdmin')
        with pytest.raises(DoesNotExist):
            Bot.objects(id=pytest.deleted_bot, status=True).get()
        user = User.objects(account=pytest.account, status=True).get()
        assert len(user.bot) == 1
        assert pytest.deleted_bot not in user.bot

    def test_delete_bot_not_exists(self):
        with pytest.raises(AppException):
            AccountProcessor.delete_bot(pytest.deleted_bot, 'testAdmin')

    def test_add_bot_to_user_not_present(self):
        with pytest.raises(AppException):
            AccountProcessor.add_bot_for_user(pytest.deleted_bot, "fshaikh")

    def test_add_user_duplicate(self):
        with pytest.raises(Exception):
            AccountProcessor.add_user(
                email="fshaikh@digite.com",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_duplicate_case_insensitive(self):
        with pytest.raises(Exception):
            AccountProcessor.add_user(
                email="FShaikh@digite.com",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_empty_email(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_blank_email(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email=" ",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_invalid_email(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="demo",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_none_email(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email=None,
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_empty_firstname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_blank_firstname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name=" ",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_none_firstname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_empty_lastname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_none_lastname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name=None,
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_blank_lastname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name=" ",
                password="Welcome@1",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_empty_password(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_blank_password(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password=" ",
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_add_user_None_password(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password=None,
                account=1,
                bot=pytest.bot,
                user="testAdmin",
            )

    def test_get_user(self):
        user = AccountProcessor.get_user("fshaikh@digite.com")
        assert all(
            user[key] is False if key == "is_integration_user" else user[key]
            for key in user.keys()
        )

    def test_get_user_details(self):
        user = AccountProcessor.get_user_details("fshaikh@digite.com")
        assert all(
            user[key] is False if key == "is_integration_user" else user[key]
            for key in user.keys()
        )

    @pytest.fixture
    def mock_user_inactive(self, monkeypatch):
        def user_response(*args, **kwargs):
            return {
                "email": "demo@demo.ai",
                "status": False,
                "bot": "support",
                "account": 2,
                "is_integration_user": False
            }

        def bot_response(*args, **kwargs):
            return {"name": "support", "status": True}

        def account_response(*args, **kwargs):
            return {"name": "paytm", "status": True}

        monkeypatch.setattr(AccountProcessor, "get_user", user_response)
        monkeypatch.setattr(AccountProcessor, "get_bot", bot_response)
        monkeypatch.setattr(AccountProcessor, "get_account", account_response)

    def test_get_user_details_user_inactive(self, mock_user_inactive):
        with pytest.raises(ValidationError):
            user_details = AccountProcessor.get_user_details("demo@demo.ai")
            assert all(
                user_details[key] is False
                if key == "is_integration_user"
                else user_details[key]
                for key in user_details.keys()
            )

    @pytest.fixture
    def mock_bot_inactive(self, monkeypatch):
        def user_response(*args, **kwargs):
            return {
                "email": "demo@demo.ai",
                "status": True,
                "bot": "support",
                "account": 2,
                "is_integration_user": False
            }

        def bot_response(*args, **kwargs):
            return {"name": "support", "status": False}

        def account_response(*args, **kwargs):
            return {"name": "paytm", "status": True}

        monkeypatch.setattr(AccountProcessor, "get_user", user_response)
        monkeypatch.setattr(AccountProcessor, "get_bot", bot_response)
        monkeypatch.setattr(AccountProcessor, "get_account", account_response)

    def test_get_user_details_bot_inactive(self, mock_bot_inactive, monkeypatch):
        monkeypatch.setattr(AccountProcessor, 'EMAIL_ENABLED', True)
        with pytest.raises(AppException) as e:
            AccountProcessor.get_user_details("demo@demo.ai")
        assert str(e).__contains__('Please verify your mail')

    @pytest.fixture
    def mock_account_inactive(self, monkeypatch):
        def user_response(*args, **kwargs):
            return {
                "email": "demo@demo.ai",
                "status": True,
                "bot": "support",
                "account": 2,
                "is_integration_user": False
            }

        def bot_response(*args, **kwargs):
            return {"name": "support", "status": True}

        def account_response(*args, **kwargs):
            return {"name": "paytm", "status": False}

        monkeypatch.setattr(AccountProcessor, "get_user", user_response)
        monkeypatch.setattr(AccountProcessor, "get_bot", bot_response)
        monkeypatch.setattr(AccountProcessor, "get_account", account_response)

    def test_get_user_details_account_inactive(self, mock_account_inactive):
        with pytest.raises(ValidationError):
            user_details = AccountProcessor.get_user_details("demo@demo.ai")
            assert all(
                user_details[key] is False
                if key == "is_integration_user"
                else user_details[key]
                for key in AccountProcessor.get_user_details(
                    user_details["email"]
                ).keys()
            )

    def test_get_integration_user(self):
        integration_user = AccountProcessor.get_integration_user(
            bot="support", account=2
        )
        assert integration_user["is_integration_user"]
        assert all(integration_user[key] for key in integration_user.keys())

    def test_account_setup_empty_values(self):
        account = {}
        with pytest.raises(AppException):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(AccountProcessor.account_setup(account_setup=account, user="testAdmin"))

    def test_account_setup_missing_account(self):
        account = {
            "bot": "Test",
            "email": "demo@ac.in",
            "first_name": "Test_First",
            "last_name": "Test_Last",
            "password": "welcome@1",
        }
        with pytest.raises(AppException):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(AccountProcessor.account_setup(account_setup=account, user="testAdmin"))

    def test_account_setup_user_info(self):
        account = {
            "account": "Test_Account",
            "bot": "Test",
            "first_name": "Test_First",
            "last_name": "Test_Last",
            "password": SecretStr("Welcome@1"),
        }
        with pytest.raises(AppException):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(AccountProcessor.account_setup(account_setup=account, user="testAdmin"))

    def test_account_setup(self):
        account = {
            "account": "Test_Account",
            "bot": "Test",
            "email": "demo@ac.in",
            "first_name": "Test_First",
            "last_name": "Test_Last",
            "password": SecretStr("Welcome@1"),
        }
        loop = asyncio.new_event_loop()
        actual, mail, subject, body = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account, user="testAdmin"))
        assert actual["role"] == "admin"
        assert actual["_id"]
        assert actual["account"]
        assert actual["bot"]

    def test_default_account_setup(self):
        loop = asyncio.new_event_loop()
        actual, mail, subject, body = loop.run_until_complete(AccountProcessor.default_account_setup())
        assert actual

    async def mock_smtp(self, *args, **kwargs):
        return None

    def test_validate_and_send_mail(self,monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(Utility.validate_and_send_mail('demo@ac.in',subject='test',body='test'))
        assert True

    def test_send_false_email_id(self,monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(Utility.validate_and_send_mail('..',subject='test',body="test"))

    def test_send_empty_mail_subject(self,monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(Utility.validate_and_send_mail('demo@ac.in',subject=' ',body='test'))

    def test_send_empty_mail_body(self,monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(Utility.validate_and_send_mail('demo@ac.in',subject='test',body=' '))

    def test_valid_token(self):
        token = Utility.generate_token('integ1@gmail.com')
        mail = Utility.verify_token(token)
        assert mail

    def test_invalid_token(self):
        with pytest.raises(Exception):
            Utility.verify_token('..')

    def test_new_user_confirm(self,monkeypatch):
        AccountProcessor.add_user(
            email="integ2@gmail.com",
            first_name="inteq",
            last_name="2",
            password='Welcome@1',
            account=1,
            bot=pytest.bot,
            user="testAdmin",
        )
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('integ2@gmail.com')
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.confirm_email(token))
        assert True

    def test_user_already_confirmed(self,monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        token = Utility.generate_token('integ2@gmail.com')
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.confirm_email(token))

    def test_user_not_confirmed(self):
        with pytest.raises(Exception):
            AccountProcessor.is_user_confirmed('sd')

    def test_user_confirmed(self):
        AccountProcessor.is_user_confirmed('integ2@gmail.com')
        assert True

    def test_send_empty_token(self):
        with pytest.raises(Exception):
            Utility.verify_token(' ')

    def test_reset_link_with_mail(self,monkeypatch):
        AccountProcessor.EMAIL_ENABLED = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.send_reset_link('integ2@gmail.com'))
        AccountProcessor.EMAIL_ENABLED = False
        assert True

    def test_reset_link_with_empty_mail(self,monkeypatch):
        AccountProcessor.EMAIL_ENABLED = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link(''))
        AccountProcessor.EMAIL_ENABLED = False

    def test_reset_link_with_unregistered_mail(self, monkeypatch):
        AccountProcessor.EMAIL_ENABLED = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link('sasha.41195@gmail.com'))
        AccountProcessor.EMAIL_ENABLED = False

    def test_reset_link_with_unconfirmed_mail(self, monkeypatch):
        AccountProcessor.EMAIL_ENABLED = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link('integration@demo.ai'))
        AccountProcessor.EMAIL_ENABLED = False

    def test_overwrite_password_with_invalid_token(self,monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.overwrite_password('fgh',"asdfghj@1"))

    def test_overwrite_password_with_empty_password_string(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.overwrite_password('eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20', " "))

    def test_overwrite_password_with_valid_entries(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('integ2@gmail.com')
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.overwrite_password(token,"Welcome@3"))
        assert True

    def test_send_confirmation_link_with_valid_id(self, monkeypatch):
        AccountProcessor.add_user(
            email="integ3@gmail.com",
            first_name="inteq",
            last_name="3",
            password='Welcome@1',
            account=1,
            bot=pytest.bot,
            user="testAdmin",
        )
        AccountProcessor.EMAIL_ENABLED = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.send_confirmation_link('integ3@gmail.com'))
        AccountProcessor.EMAIL_ENABLED = False
        assert True

    def test_send_confirmation_link_with_confirmed_id(self, monkeypatch):
        AccountProcessor.EMAIL_ENABLED = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link('integ1@gmail.com'))
        AccountProcessor.EMAIL_ENABLED = False

    def test_send_confirmation_link_with_invalid_id(self, monkeypatch):
        AccountProcessor.EMAIL_ENABLED = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link(''))
        AccountProcessor.EMAIL_ENABLED = False

    def test_send_confirmation_link_with_unregistered_id(self, monkeypatch):
        AccountProcessor.EMAIL_ENABLED = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link('sasha.41195@gmail.com'))
        AccountProcessor.EMAIL_ENABLED = False

    def test_reset_link_with_mail_not_enabled(self,monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link('integ1@gmail.com'))

    def test_send_confirmation_link_with_mail_not_enabled(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link('integration@demo.ai'))

    def test_create_authentication_token_with_expire_time(self, monkeypatch):
        start_date = datetime.datetime.now()
        token = Authentication.create_access_token(data={"sub": "test"},token_expire=180)
        payload = jwt.decode(token, Authentication.SECRET_KEY, algorithms=[Authentication.ALGORITHM])
        assert round((datetime.datetime.fromtimestamp(payload.get('exp')) - start_date).total_seconds()/60) == 180
        assert payload.get('sub') == 'test'

        start_date = datetime.datetime.now()
        token = Authentication.create_access_token(data={"sub": "test"})
        payload = jwt.decode(token, Authentication.SECRET_KEY, algorithms=[Authentication.ALGORITHM])
        assert round((datetime.datetime.fromtimestamp(payload.get('exp')) - start_date).total_seconds() / 60) == 10080

        monkeypatch.setattr(Authentication, 'ACCESS_TOKEN_EXPIRE_MINUTES', None)
        start_date = datetime.datetime.now()
        token = Authentication.create_access_token(data={"sub": "test"})
        payload = jwt.decode(token, Authentication.SECRET_KEY, algorithms=[Authentication.ALGORITHM])
        assert round((datetime.datetime.fromtimestamp(payload.get('exp')) - start_date).total_seconds() / 60) == 15
