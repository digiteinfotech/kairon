import os

import pytest
from mongoengine import connect

from bot_trainer.api.data_objects import *
from bot_trainer.api.processor import AccountProcessor

os.environ["system_file"] = "./tests/testing_data/system.yaml"


class TestAccountProcessor:
    @pytest.fixture(autouse=True)
    def init_connection(self):
        Utility.load_evironment()
        connect(Utility.environment["mongo_db"], host=Utility.environment["mongo_url"])

    def test_add_account(self):
        account_response = AccountProcessor.add_account("paypal", "testAdmin")
        assert account_response
        assert account_response["_id"] == 3
        assert account_response["name"] == "paypal"
        account_response = AccountProcessor.add_account("ebay", "testAdmin")
        assert account_response
        assert account_response["_id"] == 4
        assert account_response["name"] == "ebay"

    def test_get_account(self):
        account = AccountProcessor.get_account(3)
        assert account
        assert account["name"] == "paypal"

    def test_add_duplicate_account(self):
        with pytest.raises(Exception):
            AccountProcessor.add_account("paypal", "testAdmin")

    def test_add_blank_account(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_account("", "testAdmin")

    def test_add_empty_account(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_account(" ", "testAdmin")

    def test_add_none_account(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_account(None, "testAdmin")

    def test_add_bot(self):
        bot = AccountProcessor.add_bot("test", 1, "testAdmin")
        assert bot

    def test_get_bot(self):
        bot = AccountProcessor.get_bot("test")
        assert bot
        assert bot["account"] == 1

    def test_add_duplicate_bot(self):
        with pytest.raises(Exception):
            AccountProcessor.add_bot("test", 1, "testAdmin")

    def test_add_blank_bot(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_bot(" ", 1, "testAdmin")

    def test_add_empty_bot(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_bot("", 1, "testAdmin")

    def test_add_none_bot(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_bot(None, 1, "testAdmin")

    def test_add_user(self):
        user = AccountProcessor.add_user(
            email="fshaikh@digite.com",
            first_name="Fahad Ali",
            last_name="Shaikh",
            password="12345",
            account=1,
            bot="test",
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
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_empty_email(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_blank_email(self):
        with pytest.raises(Exception):
            AccountProcessor.add_user(
                email=" ",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_invalid_email(self):
        with pytest.raises(Exception):
            AccountProcessor.add_user(
                email="demo",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_none_email(self):
        with pytest.raises(Exception):
            AccountProcessor.add_user(
                email=None,
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_empty_firstname(self):
        with pytest.raises(Exception):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="",
                last_name="Shaikh",
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_blank_firstname(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name=" ",
                last_name="Shaikh",
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_none_firstname(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="",
                last_name="Shaikh",
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_empty_lastname(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="",
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_none_lastname(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name=None,
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_blank_lastname(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name=" ",
                password="12345",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_empty_password(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_blank_password(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password=" ",
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_add_user_None_password(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password=None,
                account=1,
                bot="test",
                user="testAdmin",
            )

    def test_get_user(self):
        user = AccountProcessor.get_user("fshaikh@digite.com")
        assert all(user[key] is False if key == "is_integration_user" else user[key] for key in user.keys())

    def test_get_user_details(self):
        user = AccountProcessor.get_user_details("fshaikh@digite.com")
        assert all(user[key] is False if key == "is_integration_user" else user[key] for key in user.keys())

    def test_get_user_details_user_inactive(self):
        account = AccountProcessor.add_account("paytm", "testAdmin")
        bot = AccountProcessor.add_bot("support", account["_id"], "testAdmin")
        user = AccountProcessor.add_user(
            email="demo@demo.ai",
            first_name="Demo",
            last_name="User",
            password="welcome@1",
            account=account["_id"],
            bot=bot["name"],
            user="testAdmin",
        )
        user_details = AccountProcessor.get_user_details(user["email"])
        assert all(user_details[key] is False if key == "is_integration_user" else user_details[key] for key in user_details.keys())
        user_details = User.objects().get(id=user["_id"])
        user_details.status = False
        user_details.save()
        with pytest.raises(ValidationError):
            user_details = AccountProcessor.get_user_details(user_details["email"])
            assert all(user_details[key] is False if key == "is_integration_user" else user_details[key] for key in user_details.keys())
        user_details.status = True
        user_details.save()

    def test_get_user_details_bot_inactive(self):
        user_details = AccountProcessor.get_user_details("demo@demo.ai")
        assert all(user_details[key] is False if key == "is_integration_user" else user_details[key] for key in user_details.keys())
        bot = Bot.objects().get(name="support")
        bot.status = False
        bot.save()
        with pytest.raises(ValidationError):
            user_details = AccountProcessor.get_user_details(user_details["email"])
            assert all(
                user_details[key] is False if key == "is_integration_user" else user_details[key]
                for key in AccountProcessor.get_user_details(
                    user_details["email"]
                ).keys()
            )
        bot.status = True
        bot.save()

    def test_get_user_details_account_inactive(self):
        user_details = AccountProcessor.get_user_details("demo@demo.ai")
        assert all(user_details[key] is False if key == "is_integration_user" else user_details[key] for key in user_details.keys())
        account = Account.objects().get(name="paytm")
        account.status = False
        account.save()
        with pytest.raises(ValidationError):
            user_details = AccountProcessor.get_user_details(user_details["email"])
            assert all(
                user_details[key] is False if key == "is_integration_user" else user_details[key]
                for key in AccountProcessor.get_user_details(
                    user_details["email"]
                ).keys()
            )
        account.status = True
        account.save()

    def test_get_integration_user(self):
        user_details = AccountProcessor.get_user_details("demo@demo.ai")
        integration_user = AccountProcessor.get_integration_user(bot=user_details['bot'], account=user_details['account'])
        assert integration_user['is_integration_user']
        assert all(integration_user[key] for key in integration_user.keys())
