from loguru import logger as logging
from typing import Dict, Text
from mongoengine.errors import DoesNotExist
from mongoengine.errors import ValidationError
from pydantic import SecretStr
from bot_trainer.api.data_objects import Account, User, Bot, UserEmailConfirmation
from bot_trainer.data_processor.processor import MongoProcessor
from bot_trainer.utils import Utility
from bot_trainer.exceptions import AppException
from validators import ValidationFailure
from validators import email as mail_check
from datetime import datetime

Utility.load_email_configuration()


class AccountProcessor:
    EMAIL_ENABLED = Utility.email_conf["email"]["enable"]

    @staticmethod
    def add_account(name: str, user: str):
        """
        adds a new account

        :param name: account name
        :param user: user id
        :return: account id
        """
        if Utility.check_empty_string(name):
            raise AppException("Account Name cannot be empty or blank spaces")
        Utility.is_exist(
            Account,
            exp_message="Account name already exists!",
            name__iexact=name,
            status=True,
        )
        return Account(name=name.strip(), user=user).save().to_mongo().to_dict()

    @staticmethod
    def get_account(account: int):
        """
        fetch account object

        :param account: account id
        :return: account details
        """
        try:
            account = Account.objects().get(id=account).to_mongo().to_dict()
            return account
        except:
            raise DoesNotExist("Account does not exists")

    @staticmethod
    def add_bot(name: str, account: int, user: str):
        """
        add a bot to account

        :param name: bot name
        :param account: account id
        :param user: user id
        :return: bot id
        """
        if Utility.check_empty_string(name):
            raise AppException("Bot Name cannot be empty or blank spaces")

        Utility.is_exist(
            Bot,
            exp_message="Bot already exists!",
            name__iexact=name,
            account=account,
            status=True,
        )
        return Bot(name=name, account=account, user=user).save().to_mongo().to_dict()

    @staticmethod
    def get_bot(id: str):
        """
        fetches bot details

        :param id: bot id
        :return: bot details
        """
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
        """
        adds new user to the account

        :param email: user login id
        :param password: user password
        :param first_name: user firstname
        :param last_name:  user lastname
        :param account: account id
        :param bot: bot id
        :param user: user id
        :param is_integration_user: is this
        :param role: user role
        :return: user details
        """
        if (
            Utility.check_empty_string(email)
            or Utility.check_empty_string(last_name)
            or Utility.check_empty_string(first_name)
            or Utility.check_empty_string(password)
        ):
            raise AppException(
                "Email, FirstName, LastName and password cannot be empty or blank spaces"
            )

        Utility.is_exist(
            User,
            exp_message="User already exists! try with different email address.",
            email__iexact=email.strip(),
            status=True,
        )
        return (
            User(
                email=email.strip(),
                password=Utility.get_password_hash(password.strip()),
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                account=account,
                bot=bot.strip(),
                user=user.strip(),
                is_integration_user=is_integration_user,
                role=role.strip(),
            )
            .save()
            .to_mongo()
            .to_dict()
        )

    @staticmethod
    def get_user(email: str):
        """
        fetch user details

        :param email: user login id
        :return: user details
        """
        try:
            return User.objects().get(email=email).to_mongo().to_dict()
        except:
            raise DoesNotExist("User does not exist!")

    @staticmethod
    def get_user_details(email: str):
        """
        fetches complete user details, checks for wether it is inactive

        :param email: login id
        :return: dict
        """
        user = AccountProcessor.get_user(email)
        if not user["is_integration_user"]:
            AccountProcessor.check_email_confirmation(user["email"])
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
        """
        fetches complete user details including account and bot

        :param email: login id
        :return: dict
        """
        user = AccountProcessor.get_user(email)
        bot = AccountProcessor.get_bot(user["bot"])
        account = AccountProcessor.get_account(user["account"])
        user["bot_name"] = bot["name"]
        user["account_name"] = account["name"]
        user["_id"] = user["_id"].__str__()
        return user

    @staticmethod
    def get_integration_user(bot: str, account: int):
        """
        creates integration user if it does not exist

        :param bot: bot id
        :param account: account id
        :return: dict
        """
        if not Utility.is_exist(
            User, raise_error=False, bot=bot, is_integration_user=True, status=True
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
    async def account_setup(account_setup: Dict, user: Text):
        """
        create new account

        :param account_setup: dict of account details
        :param user: user id
        :return: dict user details, user email id, confirmation mail subject, mail body
        """
        account = None
        bot = None
        user_details = None
        body = None
        subject = None
        mail_to = None
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
            await MongoProcessor().save_from_path(
                "template/use-cases/Hi-Hello", bot["_id"].__str__(), user="sysadmin"
            )
            if AccountProcessor.EMAIL_ENABLED:
                token = Utility.generate_token(account_setup.get("email"))
                link = Utility.email_conf["app"]["url"] + '/verify/' + token
                body = Utility.email_conf['email']['templates']['confirmation_body'] + link
                subject = Utility.email_conf['email']['templates']['confirmation_subject']
                mail_to = account_setup.get("email")

        except Exception as e:
            if account and "_id" in account:
                Account.objects().get(id=account["_id"]).delete()
            if bot and "_id" in bot:
                Bot.objects().get(id=bot["_id"]).delete()
            raise e

        return user_details, mail_to, subject, body

    @staticmethod
    async def default_account_setup():
        """
        default account for testing/demo purposes

        :return: user details
        :raises: if account already exist
        """
        account = {
            "account": "DemoAccount",
            "bot": "Demo",
            "email": "test@demo.in",
            "first_name": "Test_First",
            "last_name": "Test_Last",
            "password": SecretStr("Changeit@123"),
        }
        try:
            user, mail, subject, body = await AccountProcessor.account_setup(account, user="sysadmin")
            return user, mail, subject, body
        except Exception as e:
            logging.info(str(e))

    @staticmethod
    async def confirm_email(token: str):
        """
        Confirms the user through link and updates the database

        :param token: the token from link
        :return: mail id, subject of mail, body of mail
        """
        email_confirm = Utility.verify_token(token)
        Utility.is_exist(
            UserEmailConfirmation,
            exp_message="Email already confirmed!",
            email__iexact=email_confirm.strip(),
        )
        confirm = UserEmailConfirmation()
        confirm.email = email_confirm
        confirm.save()
        subject = Utility.email_conf['email']['templates']['confirmed_subject']
        body = Utility.email_conf['email']['templates']['confirmed_body']
        return email_confirm, subject, body


    @staticmethod
    def is_user_confirmed(email: str):
        """
        Checks if user is verified and raises an Exception if not

        :param email: mail id of user
        :return: None
        """
        if not Utility.is_exist(UserEmailConfirmation, email__iexact=email.strip(), raise_error=False):
            raise AppException("Please verify your mail")

    @staticmethod
    def check_email_confirmation(email: str):
        """
        Checks if the account is verified through mail

        :param email: email of the user
        :return: None
        """
        if AccountProcessor.EMAIL_ENABLED:
            AccountProcessor.is_user_confirmed(email)

    @staticmethod
    async def send_reset_link(mail: str):
        """
        Sends a password reset link to the mail id

        :param mail: email id of the user
        :return: mail id, mail subject, mail body
        """
        if AccountProcessor.EMAIL_ENABLED:
            if isinstance(mail_check(mail), ValidationFailure):
                raise AppException("Please enter valid email id")
            if not Utility.is_exist(User, email__iexact=mail.strip(), raise_error=False):
                raise AppException("Error! There is no user with the following mail id")
            if not Utility.is_exist(UserEmailConfirmation, email__iexact=mail.strip(), raise_error=False):
                raise AppException("Error! The following user's mail is not verified")
            token = Utility.generate_token(mail)
            link = Utility.email_conf["app"]["url"] + '/reset_password/' + token
            body = Utility.email_conf['email']['templates']['password_reset_body'] + link
            subject = Utility.email_conf['email']['templates']['password_reset_subject']
            return mail, subject, body
        else:
            raise AppException("Error! Email verification is not enabled")

    @staticmethod
    async def overwrite_password(token: str, password: str):
        """
        Changes the user's password

        :param token: unique token from the password reset page
        :param password: new password entered by the user
        :return: mail id, mail subject and mail body
        """
        if Utility.check_empty_string(password):
            raise AppException("password cannot be empty or blank")
        email = Utility.verify_token(token)
        user = User.objects().get(email=email)
        user.password = Utility.get_password_hash(password.strip())
        user.user = email
        user.timestamp = datetime.utcnow
        user.save()
        subject = Utility.email_conf['email']['templates']['password_changed_subject']
        body = Utility.email_conf['email']['templates']['password_changed_body']
        return email, subject, body

    @staticmethod
    async def send_confirmation_link(mail: str):
        """
        Sends a link to the user's mail id for account verification

        :param mail: the mail id of the user
        :return: mail id, mail subject and mail body
        """
        if AccountProcessor.EMAIL_ENABLED:
            if isinstance(mail_check(mail), ValidationFailure):
                raise AppException("Please enter valid email id")
            Utility.is_exist(UserEmailConfirmation, exp_message="Email already confirmed!", email__iexact=mail.strip())
            if not Utility.is_exist(User, email__iexact=mail.strip(), raise_error=False):
                raise AppException("Error! There is no user with the following mail id")
            token = Utility.generate_token(mail)
            link = Utility.email_conf["app"]["url"] + '/verify/' + token
            body = Utility.email_conf['email']['templates']['confirmation_body'] + link
            subject = Utility.email_conf['email']['templates']['confirmation_subject']
            return mail, subject, body
        else:
            raise AppException("Error! Email verification is not enabled")
