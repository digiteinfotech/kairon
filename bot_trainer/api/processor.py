import logging
from typing import Dict, Text

from mongoengine.errors import DoesNotExist
from mongoengine.errors import ValidationError
from pydantic import SecretStr
from bot_trainer.api.data_objects import Account, User, Bot
from bot_trainer.data_processor.processor import MongoProcessor
from bot_trainer.utils import Utility


class AccountProcessor:
    @staticmethod
    def add_account(name: str, user: str):
        """ Adds a new account for the trainer app """
        Utility.is_exist(
            Account, query={"name": name}, exp_message="Account name already exists!"
        )
        return Account(name=name, user=user).save().to_mongo().to_dict()

    @staticmethod
    def get_account(account: int):
        """ Returns an account object based on user ID """
        try:
            return Account.objects().get(id=account).to_mongo().to_dict()
        except:
            raise DoesNotExist("Account does not exists")

    @staticmethod
    def add_bot(name: str, account: int, user: str):
        """ Adds a bot to the specified user account """
        Utility.is_exist(
            Bot,
            query={"name": name, "account": account},
            exp_message="Bot already exists!",
        )
        return Bot(name=name, account=account, user=user).save().to_mongo().to_dict()

    @staticmethod
    def get_bot(id: str):
        """ Loads the bot based on user ID """
        try:
            return Bot.objects().get(id=id).to_mongo().to_dict()
        except:
            raise DoesNotExist("Bot does not exists!")

    @staticmethod
    def add_user(
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        account: int,
        bot: str,
        user: str,
        is_integration_user=False,
        role="trainer",
    ):
        """ Adds a new user to the app based on the details
            provided by the user """
        Utility.is_exist(
            User,
            query={"email": email},
            exp_message="User already exists! try with different email address.",
        )
        return (
            User(
                email=email,
                password=Utility.get_password_hash(password),
                first_name=first_name,
                last_name=last_name,
                account=account,
                bot=bot,
                user=user,
                is_integration_user=is_integration_user,
                role=role,
            )
            .save()
            .to_mongo()
            .to_dict()
        )

    @staticmethod
    def get_user(email: str):
        """ Returns the user object based on input email """
        try:
            return User.objects().get(email=email).to_mongo().to_dict()
        except:
            raise DoesNotExist("User does not exists!")

    @staticmethod
    def get_user_details(email: str):
        """ Get details of the user such as account name and the
            chatbot he/she is training based on email input """
        user = AccountProcessor.get_user(email)
        if not user["status"]:
            raise ValidationError("Inactive User please contact admin!")
        bot = AccountProcessor.get_bot(user["bot"])
        account = AccountProcessor.get_account(user["account"])
        if not bot["status"]:
            raise ValidationError("Inactive Bot Please contact system admin!")
        if not account["status"]:
            raise ValidationError("Inactive Account Please contact system admin!")
        return user

    @staticmethod
    def get_complete_user_details(email: str):
        """ Get details of the user such as the account name, user ID,
            and the chatbot he/she is training based on email input """
        user = AccountProcessor.get_user(email)
        bot = AccountProcessor.get_bot(user["bot"])
        account = AccountProcessor.get_account(user["account"])
        user["bot_name"] = bot["name"]
        user["account_name"] = account["name"]
        user["_id"] = user["_id"].__str__()
        return user

    @staticmethod
    def get_integration_user(bot: str, account: int):
        """ Getting the integration user. If it does'nt exist, a new integration user
            is created """
        if not Utility.is_exist(
            User, query={"bot": bot, "is_integration_user": True}, raise_error=False
        ):
            email = bot + "@integration.com"
            password = Utility.generate_password()
            return AccountProcessor.add_user(
                email=email,
                password=password,
                first_name=bot,
                last_name=bot,
                account=account,
                bot=bot,
                user="auto_gen",
                is_integration_user=True,
            )
        else:
            return (
                User.objects(bot=bot).get(is_integration_user=True).to_mongo().to_dict()
            )

    @staticmethod
    def account_setup(account_setup: Dict, user: Text):
        """ Creating a new account based on details provided by the user """
        account = None
        bot = None
        user_details = None
        try:
            account = AccountProcessor.add_account(account_setup.get("account"), user)
            bot = AccountProcessor.add_bot(
                account_setup.get("bot"), account["_id"], user
            )
            user_details = AccountProcessor.add_user(
                email=account_setup.get("email"),
                first_name=account_setup.get("first_name"),
                last_name=account_setup.get("last_name"),
                password=account_setup.get("password").get_secret_value(),
                account=account["_id"].__str__(),
                bot=bot["_id"].__str__(),
                user=user,
                role="admin",
            )
        except Exception as e:
            if account and "_id" in account:
                Account.objects().get(id=account["_id"]).delete()
            if bot and "_id" in bot:
                Bot.objects().get(id=bot["_id"]).delete()
            raise e
        return user_details

    @staticmethod
    async def default_account_setup():
        """ Setting up an account for testing/demo purposes """
        account = {
            "account": "DemoAccount",
            "bot": "Demo",
            "email": "test@demo.in",
            "first_name": "Test_First",
            "last_name": "Test_Last",
            "password": SecretStr("Welcome@1"),
        }
        try:
            user = AccountProcessor.account_setup(account, user="sysadmin")
            if user:
                await MongoProcessor().save_from_path(
                    "template/", user["bot"], user="sysadmin"
                )
            return user
        except Exception as e:
            logging.info(str(e))
