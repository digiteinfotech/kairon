from datetime import datetime
from typing import Dict, Text

from loguru import logger as logging
from mongoengine.errors import DoesNotExist
from mongoengine.errors import ValidationError
from pydantic import SecretStr
from validators import ValidationFailure
from validators import email as mail_check

from kairon.api.data_objects import Account, User, Bot, UserEmailConfirmation, Integrations
from kairon.data_processor.data_objects import Intents, Responses, Stories, Actions, Configs, Endpoints, Entities, \
    EntitySynonyms, Forms, LookupTables, ModelDeployment, ModelTraining, RegexFeatures, Rules, SessionConfigs, Slots, \
    TrainingDataGenerator, TrainingExamples
from kairon.data_processor.processor import MongoProcessor
from kairon.exceptions import AppException
from kairon.importer.data_objects import ValidationLogs
from kairon.shared.actions.data_objects import HttpActionConfig, HttpActionLog
from kairon.utils import Utility

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
        license = {"bots": 2, "intents": 10, "examples": 50, "training": 3, "augmentation": 5}
        return Account(name=name.strip(), user=user, license=license).save().to_mongo().to_dict()

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
    def add_bot(name: str, account: int, user: str, is_new_account: bool = False):
        """
        add a bot to account

        :param name: bot name
        :param account: account id
        :param user: user id
        :param is_new_account: True if it is a new account
        :return: bot id
        """
        if Utility.check_empty_string(name):
            raise AppException("Bot Name cannot be empty or blank spaces")

        if Utility.check_empty_string(user):
            raise AppException("user cannot be empty or blank spaces")

        Utility.is_exist(
            Bot,
            exp_message="Bot already exists!",
            name__iexact=name,
            account=account,
            status=True,
        )
        bot = Bot(name=name, account=account, user=user).save().to_mongo().to_dict()
        bot_id = bot['_id'].__str__()
        if not is_new_account:
            AccountProcessor.add_bot_for_user(bot_id, user)
        processor = MongoProcessor()
        config = processor.load_config(bot_id)
        processor.add_or_overwrite_config(config, bot_id, user, False)
        processor.add_default_fallback_data(bot_id, user, True, True)
        return bot

    @staticmethod
    def list_bots(account_id: int):
        for bot in Bot.objects(account=account_id, status=True):
            bot = bot.to_mongo().to_dict()
            bot.pop('account')
            bot.pop('user')
            bot.pop('timestamp')
            bot.pop('status')
            bot['_id'] = bot['_id'].__str__()
            yield bot

    @staticmethod
    def update_bot(name: Text, bot: Text):
        if Utility.check_empty_string(name):
            raise AppException('Name cannot be empty')
        try:
            bot_info = Bot.objects(id=bot, status=True).get()
            bot_info.name = name
            bot_info.save()
        except DoesNotExist:
            raise AppException('Bot not found')

    @staticmethod
    def delete_bot(bot: Text, user: Text):
        try:
            bot_info = Bot.objects(id=bot, status=True).get()
            bot_info.status = False
            bot_info.save()
            Utility.hard_delete_document([Actions, Configs, Endpoints, Entities, EntitySynonyms, Forms,
                                          HttpActionConfig, HttpActionLog, Intents, LookupTables, ModelDeployment,
                                          ModelTraining, RegexFeatures, Responses, Rules, SessionConfigs, Slots,
                                          Stories, TrainingDataGenerator, TrainingExamples, ValidationLogs], bot,
                                         user=user)
        except DoesNotExist:
            raise AppException('Bot not found')

    @staticmethod
    def add_bot_for_user(bot: Text, email: Text):
        try:
            user = User.objects().get(email=email, status=True)
            user.bot.append(bot)
            user.save()
        except DoesNotExist:
            raise AppException('User not found')

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
                bot=[bot.strip()],
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
        fetches complete user details, checks for whether it is inactive

        :param email: login id
        :return: dict
        """
        user = AccountProcessor.get_user(email)
        if not user["is_integration_user"]:
            AccountProcessor.check_email_confirmation(user["email"])
        if not user["status"]:
            raise ValidationError("Inactive User please contact admin!")
        account = AccountProcessor.get_account(user["account"])
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
        user["bot_name"] = []
        for bot in user["bot"]:
            user["bot_name"].append({bot: AccountProcessor.get_bot(bot)['name']})
        account = AccountProcessor.get_account(user["account"])
        user["account_name"] = account["name"]
        user["_id"] = user["_id"].__str__()
        return user

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
        body = None
        subject = None
        mail_to = None
        try:
            account = AccountProcessor.add_account(account_setup.get("account"), user)
            bot = AccountProcessor.add_bot('Hi-Hello', account["_id"], user, True)
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
            issued_at = datetime.utcnow()
            try:
                user = User.objects(email=mail.strip()).get()
                if user.last_password_reset_requested and Utility.time_diff_in_minutes(issued_at, user.last_password_reset_requested) < 420:
                    raise AppException("Last sent reset password link still active")
                user.last_password_reset_requested = issued_at
            except DoesNotExist:
                raise AppException("Error! There is no user with the following mail id")
            if not Utility.is_exist(UserEmailConfirmation, email__iexact=mail.strip(), raise_error=False):
                raise AppException("Error! The following user's mail is not verified")
            token = Utility.generate_token(mail)
            link = Utility.email_conf["app"]["url"] + '/reset_password/' + token
            body = Utility.email_conf['email']['templates']['password_reset_body'] + link
            subject = Utility.email_conf['email']['templates']['password_reset_subject']
            user.save()
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


class IntegrationsProcessor:

    @staticmethod
    def is_valid_token(email: Text, issued_at: datetime, bot: Text = None, raise_exception: bool = False):
        """
        Validated token based on claims received (email and issued_at).
        @param email: email received in claim
        @param issued_at: issue date and time received in claim
        @param bot: bot id if the request is bot specific
        @param raise_exception: raises exception if true
        @return:
        """
        try:
            if Utility.check_empty_string(bot):
                integration_info = Integrations.objects(user=email, issued_at=issued_at, status="active").get()
            else:
                integration_info = Integrations.objects(bot=bot, user=email, issued_at=issued_at, status="active").get()
            if integration_info:
                return True
        except DoesNotExist as e:
            logging.error(e)
        if raise_exception:
            raise AppException("Invalid token")
        return False

    @staticmethod
    def get_integrations(bot: Text):
        """
        Retrieves integrations for bot.

        :param bot: bot id
        :param raise_exception: Throws exception if true. Set to false by default.
        :return: dict
        """
        for integration in Integrations.objects(bot=bot, status__ne="deleted"):
            integration = integration.to_mongo().to_dict()
            integration.pop("_id")
            integration.pop("bot")
            integration.pop("user")
            yield integration

    @staticmethod
    def update_integrations(name: Text, status: Text, bot: Text):
        """
        Updates status of integrations created for bot.

        :param name: name of integration
        :param status: one of active, inactive, deleted.
        :param bot: bot id
        :param raise_exception: Throws exception if true. Set to false by default.
        :return: dict
        """
        try:
            if status not in {"active", "inactive", "deleted"}:
                raise AppException("status can only be: active, inactive, deleted")
            integration = Integrations.objects(name=name, bot=bot, status__ne="deleted").get()
            integration.status = status
            integration.save()
        except DoesNotExist as e:
            logging.error(e)
            raise AppException("Integration token not found")

    @staticmethod
    def add_integration(name: Text, issued_at: datetime, bot: Text, user: Text):
        """
        Retrieves integrations for bot.

        :param name: name of the token
        :param issued_at: token issue date and time
        :param bot: bot id
        :param user: user for whom it is to be created
        :return: integration access token
        """
        creation_limit = Utility.environment['security'].get('token_limit') or 2
        if Integrations.objects(bot=bot, status__ne="deleted").count() >= creation_limit:
            raise AppException("Integration limit exceeded")
        Utility.is_exist(Integrations,
                         exp_message="Name exists",
                         name=name, bot=bot, user=user, status__ne="deleted")
        integration = Integrations(name=name, bot=bot, user=user, status="active")
        integration.issued_at = issued_at
        integration.save()

