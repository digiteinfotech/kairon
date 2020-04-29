from bot_trainer.api.data_objects import *
from bot_trainer.utils import Utility
from mongoengine.errors import DoesNotExist
from bot_trainer.data_processor.processor import MongoProcessor
from typing import Dict, Text
import logging

class AccountProcessor:
    @staticmethod
    def add_account(name: str, user: str):
        Utility.is_exist(
            Account, query={"name": name}, exp_message="Account name already exists!"
        )
        return Account(name=name, user=user).save().to_mongo().to_dict()

    @staticmethod
    def get_account(account: int):
        try:
            return Account.objects().get(id=account).to_mongo().to_dict()
        except:
            raise DoesNotExist("Account does not exists")

    @staticmethod
    def add_bot(name: str, account: int, user: str):
        Utility.is_exist(
            Bot, query={"name": name}, exp_message="Account name already exists!"
        )
        return Bot(name=name, account=account, user=user).save().to_mongo().to_dict()

    @staticmethod
    def get_bot(id: str):
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
        role="trainer"
    ):
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
                role=role
            )
            .save()
            .to_mongo()
            .to_dict()
        )

    @staticmethod
    def get_user(email: str):
        try:
            return User.objects().get(email=email).to_mongo().to_dict()
        except:
            raise DoesNotExist("User does not exists!")

    @staticmethod
    def get_user_details(email: str):
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
    def get_integration_user(bot: str, account: int):
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
        account = None
        bot = None
        user_details = None
        try:
            account = AccountProcessor.add_account(account_setup.get('account'), user)
            bot = AccountProcessor.add_bot(account_setup.get('bot'), account['_id'], user)
            user_details = AccountProcessor.add_user(email=account_setup.get('email'),
                                             first_name=account_setup.get('first_name'),
                                             last_name=account_setup.get('last_name'),
                                             password=account_setup.get('password'),
                                             account=account["_id"],
                                             bot=bot["_id"].__str__(),
                                             user=user,
                                             role="admin")
        except Exception as e:
            if account and "_id" in account:
                Account.objects().get(id=account['_id']).delete()
            if bot and "_id" in bot:
                Bot.objects().get(id=bot['_id']).delete()
            raise e
        return user_details

    @staticmethod
    def default_account_setup():
        account = {"account": "DemoAccount",
                   "bot": "Demo",
                   "email": "test@demo.in",
                   "first_name": "Test_First",
                   "last_name": "Test_Last",
                   "password": "welcome@1"}
        try:
            user = AccountProcessor.account_setup(account, user="sysadmin")
            if user:
                MongoProcessor().save_from_path('template/',user['bot'],user="sysadmin")
            return user
        except Exception as e:
            logging.info(str(e))

