import asyncio
import os

from mongoengine import connect
from mongoengine.errors import ValidationError
import pytest
from pydantic import SecretStr

from bot_trainer.api.processor import AccountProcessor
from bot_trainer.utils import Utility
from bot_trainer.exceptions import AppException

os.environ["system_file"] = "./tests/testing_data/system.yaml"



def pytest_configure():
    return {'bot': None}

class TestAccountProcessor:
    @pytest.fixture(autouse=True)
    def init_connection(self):
        Utility.load_evironment()
        connect(Utility.environment["mongo_db"], host=Utility.environment["mongo_url"])

    def test_add_account(self):
        account_response = AccountProcessor.add_account("paypal", "testAdmin")
        account = AccountProcessor.get_account(account_response["_id"])
        assert account_response
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

    def test_add_bot(self):
        bot_response = AccountProcessor.add_bot("test", 1, "testAdmin")
        assert bot_response
        pytest.bot = bot_response["_id"].__str__()

    def test_get_bot(self):
        bot_response = AccountProcessor.get_bot(pytest.bot)
        assert bot_response
        assert bot_response["account"] == 1

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

    def test_add_user(self):
        user = AccountProcessor.add_user(
            email="fshaikh@digite.com",
            first_name="Fahad Ali",
            last_name="Shaikh",
            password="Welcome@1",
            account=1,
            bot=pytest.bot,
            user="testAdmin",
        )
        assert user
        assert user["password"] != "12345"
        assert user["status"]

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

    def test_get_user_details_bot_inactive(self, mock_bot_inactive):
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

    def test_account_setup_missing_bot_name(self):
        account = {
            "account": "TestAccount",
            "email": "demo@ac.in",
            "first_name": "Test_First",
            "last_name": "Test_Last",
            "password": "Welcome@1",
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
        actual = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account, user="testAdmin"))
        assert actual["role"] == "admin"
        assert actual["_id"]
        assert actual["account"]
        assert actual["bot"]

    def test_default_account_setup(self):
        loop = asyncio.new_event_loop()
        actual = loop.run_until_complete(AccountProcessor.default_account_setup())
        assert actual

    def test_send_mail(self,monkeypatch):
        monkeypatch.setitem(Utility.verification['email']['sender'], "email", "chirontestmail@gmail.com")
        monkeypatch.setitem(Utility.verification['email']['sender'], "password", "Welcome@1")
        monkeypatch.setitem(Utility.verification['email']['sender'], "service", "gmail")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(Utility.send_mail('demo@ac.in',subject='test',body='test'))
        assert True

    def test_send_false_email_id(self,monkeypatch):
        monkeypatch.setitem(Utility.verification['email']['sender'], "email", "chirontestmail@gmail.com")
        monkeypatch.setitem(Utility.verification['email']['sender'], "password", "Welcome@1")
        monkeypatch.setitem(Utility.verification['email']['sender'], "service", "gmail")
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(Utility.send_mail('..',subject='test',body="test"))

    def test_send_empty_mail_subject(self,monkeypatch):
        monkeypatch.setitem(Utility.verification['email']['sender'], "email", "chirontestmail@gmail.com")
        monkeypatch.setitem(Utility.verification['email']['sender'], "password", "Welcome@1")
        monkeypatch.setitem(Utility.verification['email']['sender'], "service", "gmail")
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(Utility.send_mail('demo@ac.in',subject=' ',body='test'))

    def test_send_empty_mail_body(self,monkeypatch):
        monkeypatch.setitem(Utility.verification['email']['sender'], "email", "chirontestmail@gmail.com")
        monkeypatch.setitem(Utility.verification['email']['sender'], "password", "Welcome@1")
        monkeypatch.setitem(Utility.verification['email']['sender'], "service", "gmail")
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(Utility.send_mail('demo@ac.in',subject='test',body=' '))

    def test_valid_token(self):
        mail = Utility.verify_token('eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoic2hhc2hhbmsubUBkaWdpdGUuY29tIn0.GtM8cYPf35-dJWkjYFNlcripFWh7yds8-80oeSvKEiE')
        assert mail

    def test_invalid_token(self):
        with pytest.raises(Exception):
            Utility.verify_token('..')

    def test_user_not_confirmed(self):
        with pytest.raises(Exception):
            AccountProcessor.is_user_confirmed('sd')

    def test_user_confirmed(self):
        AccountProcessor.is_user_confirmed('integ1@gmail.com')
        assert True

    def test_send_empty_token(self):
        with pytest.raises(Exception):
            Utility.verify_token(' ')

    def test_new_user_confirm(self,monkeypatch):
        monkeypatch.setitem(Utility.verification['email']['sender'], "email", "chirontestmail@gmail.com")
        monkeypatch.setitem(Utility.verification['email']['sender'], "password", "Welcome@1")
        monkeypatch.setitem(Utility.verification['email']['sender'], "service", "gmail")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.confirm_email("eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoic2hhc2hhbmsubUBkaWdpdGUuY29tIn0.GtM8cYPf35-dJWkjYFNlcripFWh7yds8-80oeSvKEiE"))
        assert True

    def test_user_already_confirmed(self,monkeypatch):
        monkeypatch.setitem(Utility.verification['email']['sender'], "email", "chirontestmail@gmail.com")
        monkeypatch.setitem(Utility.verification['email']['sender'], "password", "Welcome@1")
        monkeypatch.setitem(Utility.verification['email']['sender'], "service", "gmail")
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.confirm_email("eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoic2hhc2hhbmsubUBkaWdpdGUuY29tIn0.GtM8cYPf35-dJWkjYFNlcripFWh7yds8-80oeSvKEiE"))



