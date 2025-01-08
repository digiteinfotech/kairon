import ujson as json
import uuid
from datetime import datetime
from typing import Dict, Text

from loguru import logger as logging
from mongoengine import Q
from mongoengine.errors import DoesNotExist
from mongoengine.errors import ValidationError
from pydantic import SecretStr
from starlette.requests import Request
from validators.utils import ValidationError as ValidationFailure
from validators import email as mail_check

from kairon.exceptions import AppException
from kairon.shared.account.activity_log import UserActivityLogger
from kairon.shared.account.data_objects import (
    Account,
    User,
    Bot,
    UserEmailConfirmation,
    Feedback,
    UiConfig,
    MailTemplates,
    SystemProperties,
    BotAccess,
    
    BotMetaData,
    TrustedDevice,
)
from kairon.shared.actions.data_objects import (
    FormValidationAction,
    SlotSetAction,
    EmailActionConfig,
)
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.processor import Sysadmin
from kairon.shared.constants import UserActivityType, PluginTypes
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.constant import ACCESS_ROLES, ACTIVITY_STATUS, INTEGRATION_STATUS, ONBOARDING_STATUS
from kairon.shared.data.data_objects import BotSettings, ChatClientConfig, SlotMapping
from kairon.shared.plugins.factory import PluginFactory
from kairon.shared.utils import Utility
from kairon.shared.models import User as UserModel

Utility.load_email_configuration()


class AccountProcessor:
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
        license = {
            "bots": 2,
            "intents": 3,
            "examples": 20,
            "training": 3,
            "augmentation": 5,
        }
        return (
            Account(name=name.strip(), user=user, license=license)
            .save()
            .to_mongo()
            .to_dict()
        )

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
    def check_bot_exists(name: str, account: int, raise_exception: bool = True):
        bot_exists = Utility.is_exist(
            Bot,
            raise_error=False,
            name__iexact=name,
            account=account,
            status=True,
        )
        if bot_exists and raise_exception:
            raise AppException("Bot already exists!")

        return bot_exists

    @staticmethod
    async def add_bot_with_template(
        name: str, account: int, user: str, template_name: str = None
    ):
        """
        add a bot to account and apply template

        :param name: bot name
        :param account: account id
        :param user: user id
        :param template_name: template name
        :param enable_llm: enable LLM
        :return: bot id
        """
        from kairon.shared.data.processor import MongoProcessor

        metadata = {"metadata": {"from_template": template_name}}
        add_default_data = True if Utility.check_empty_string(template_name) else False
        bot = AccountProcessor.add_bot(
            name, account, user, False, add_default_data, **metadata
        )
        bot_id = bot["_id"].__str__()
        if not Utility.check_empty_string(template_name):
            processor = MongoProcessor()
            await processor.apply_template(template_name, bot_id, user)
            Utility.copy_pretrained_model(bot_id, template_name)
            if template_name.__contains__("GPT"):
                processor.enable_llm_faq(bot_id, user)
                if not Utility.check_empty_string(Utility.environment["llm"].get("key")):
                    Sysadmin.add_bot_secret(
                        bot_id,
                        user,
                        name=BotSecretType.gpt_key.value,
                        secret=Utility.environment["llm"]["key"],
                    )
        return bot_id

    @staticmethod
    def add_bot(
        name: str,
        account: int,
        user: str,
        is_new_account: bool = False,
        add_default_data: bool = True,
        **metadata,
    ):
        """
        add a bot to account

        :param metadata: metadata of new bot
        :param name: bot name
        :param account: account id
        :param user: user id
        :param is_new_account: True if it is a new account
        :param add_default_data: True if default data is to be added
        :return: bot id
        """
        from kairon.shared.data.processor import MongoProcessor
        from kairon.shared.data.data_objects import BotSettings

        if Utility.check_empty_string(name):
            raise AppException("Bot Name cannot be empty or blank spaces")

        if not Utility.check_character_limit(name):
            raise AppException("Bot Name cannot be more than 60 characters.")

        if Utility.check_empty_string(user):
            raise AppException("user cannot be empty or blank spaces")

        AccountProcessor.check_bot_exists(name, account)

        if metadata:
            bot_metadata = BotMetaData(**metadata["metadata"])
        else:
            bot_metadata = BotMetaData()

        bot = (
            Bot(name=name, account=account, user=user, metadata=bot_metadata)
            .save()
            .to_mongo()
            .to_dict()
        )
        bot_id = bot["_id"].__str__()
        if not is_new_account:
            AccountProcessor.__allow_access_to_bot(
                bot_id,
                user,
                user,
                account,
                ACCESS_ROLES.OWNER.value,
                ACTIVITY_STATUS.ACTIVE.value,
            )
        BotSettings(bot=bot_id, user=user).save()
        processor = MongoProcessor()
        if add_default_data:
            config = processor.load_config(bot_id)
            processor.add_or_overwrite_config(config, bot_id, user)
            processor.add_default_fallback_data(bot_id, user, True, True)
            processor.add_system_required_slots(bot_id, user)
            processor.add_default_training_data(bot_id, user)
        return bot

    @staticmethod
    def list_bots(account_id: int):
        for bot in Bot.objects(account=account_id, status=True):
            bot = bot.to_mongo().to_dict()
            bot.pop("status")
            bot["role"] = ACCESS_ROLES.OWNER.value
            bot["_id"] = bot["_id"].__str__()
            yield bot

    @staticmethod
    def update_bot(name: Text, bot: Text):
        if Utility.check_empty_string(name):
            raise AppException('Name cannot be empty')
        if not Utility.check_character_limit(name):
            raise AppException("Bot Name cannot be more than 60 characters.")
        try:
            bot_info = Bot.objects(id=bot, status=True).get()
            bot_info.name = name
            bot_info.save()
        except DoesNotExist:
            raise AppException("Bot not found")

    @staticmethod
    def delete_bot(bot: Text, user: Text = None):
        from kairon.shared.data.data_objects import (
            Intents,
            Responses,
            Stories,
            Configs,
            Endpoints,
            Entities,
            EntitySynonyms,
            Forms,
            LookupTables,
            ModelDeployment,
            ModelTraining,
            RegexFeatures,
            Rules,
            SessionConfigs,
            Slots,
            TrainingExamples,
        )
        from kairon.shared.test.data_objects import ModelTestingLogs
        from kairon.shared.importer.data_objects import ValidationLogs
        from kairon.shared.actions.data_objects import (
            HttpActionConfig,
            ActionServerLogs,
            Actions,
        )

        try:
            bot_info = Bot.objects(id=bot, status=True).get()
            bot_info.status = False
            bot_info.save()
            Utility.hard_delete_document(
                [
                    Actions,
                    BotAccess,
                    BotSettings,
                    Configs,
                    ChatClientConfig,
                    Endpoints,
                    Entities,
                    EmailActionConfig,
                    EntitySynonyms,
                    Forms,
                    FormValidationAction,
                    HttpActionConfig,
                    Intents,
                    LookupTables,
                    RegexFeatures,
                    Responses,
                    Rules,
                    SlotMapping,
                    SlotSetAction,
                    SessionConfigs,
                    Slots,
                    Stories,
                    TrainingExamples,
                    ActionServerLogs,
                    ModelTraining,
                    ModelTestingLogs,
                    ModelDeployment,
                    ValidationLogs,
                ],
                bot,
                user=user
            )
            AccountProcessor.remove_bot_access(bot)
        except DoesNotExist:
            raise AppException("Bot not found")

    @staticmethod
    def fetch_role_for_user(email: Text, bot: Text):
        try:
            return (
                BotAccess.objects(
                    accessor_email__iexact=email,
                    bot=bot,
                    status=ACTIVITY_STATUS.ACTIVE.value,
                )
                .get()
                .to_mongo()
                .to_dict()
            )
        except DoesNotExist as e:
            logging.error(e)
            raise AppException("Access to bot is denied")

    @staticmethod
    def get_accessible_bot_details(account_id: int, email: Text):
        shared_bots = []
        account_bots = list(AccountProcessor.list_bots(account_id))
        for bot in BotAccess.objects(
            accessor_email__iexact=email,
            bot_account__ne=account_id,
            status=ACTIVITY_STATUS.ACTIVE.value,
        ):
            bot_details = AccountProcessor.get_bot(bot["bot"])
            bot_details["_id"] = bot_details["_id"].__str__()
            bot_details["role"] = bot["role"]
            shared_bots.append(bot_details)
        return {"account_owned": account_bots, "shared": shared_bots}

    @staticmethod
    def allow_bot_and_generate_invite_url(
        bot: Text,
        email: Text,
        user: Text,
        bot_account: int,
        role: ACCESS_ROLES = ACCESS_ROLES.TESTER.value,
    ):
        token = Utility.generate_token(email)
        link = f'{Utility.email_conf["app"]["url"]}/{bot}/invite/accept/{token}'
        if role == ACCESS_ROLES.OWNER.value:
            raise AppException("There can be only 1 owner per bot")
        if Utility.email_conf["email"]["enable"]:
            activity_status = ACTIVITY_STATUS.INVITE_NOT_ACCEPTED.value
        else:
            activity_status = ACTIVITY_STATUS.ACTIVE.value
        bot_details = AccountProcessor.__allow_access_to_bot(
            bot, email, user, bot_account, role, activity_status
        )
        return bot_details["name"], link

    @staticmethod
    def __allow_access_to_bot(
        bot: Text,
        accessor_email: Text,
        user: Text,
        bot_account: int,
        role: ACCESS_ROLES = ACCESS_ROLES.TESTER.value,
        activity_status: ACTIVITY_STATUS = ACTIVITY_STATUS.INVITE_NOT_ACCEPTED.value,
    ):
        """
        Adds bot to a user account.

        :param bot: bot id
        :param accessor_email: email id of the new member
        :param user: user adding the new member
        :param bot_account: account where bot exists
        :param activity_status: can be one of active, inactive or deleted.
        :param role: can be one of admin, designer or tester.
        """
        bot_details = AccountProcessor.get_bot_and_validate_status(bot)
        Utility.is_exist(
            BotAccess,
            "User is already a collaborator",
            accessor_email__iexact=accessor_email,
            bot=bot,
            status__ne=ACTIVITY_STATUS.DELETED.value,
        )
        BotAccess(
            accessor_email=accessor_email,
            bot=bot,
            role=role,
            user=user,
            bot_account=bot_account,
            status=activity_status,
        ).save()
        return bot_details

    @staticmethod
    def update_bot_access(
        bot: Text,
        accessor_email: Text,
        user: Text,
        role: ACCESS_ROLES = ACCESS_ROLES.TESTER.value,
        status: ACTIVITY_STATUS = ACTIVITY_STATUS.ACTIVE.value,
        validate_ownership_modification: bool = True,
    ):
        """
        Adds bot to a user account.

        :param bot: bot id
        :param accessor_email: email id of the new member
        :param user: user adding the new member
        :param role: can be one of admin, designer or tester.
        :param status: can be one of active, inactive or deleted.
        :param validate_ownership_modification: whether ownership is being modified
        """
        bot_info = AccountProcessor.get_bot_and_validate_status(bot)
        owner_info = AccountProcessor.get_bot_owner(bot)
        owner = AccountProcessor.get_user(owner_info["accessor_email"])
        member = AccountProcessor.get_user(accessor_email)
        AccountProcessor.__update_role(
            bot, accessor_email, user, role, status, validate_ownership_modification
        )
        return (
            bot_info["name"],
            owner_info["accessor_email"],
            owner["first_name"],
            member["first_name"],
        )

    @staticmethod
    def __update_role(
        bot: Text,
        accessor_email: Text,
        user: Text,
        role: ACCESS_ROLES = ACCESS_ROLES.TESTER.value,
        status: ACTIVITY_STATUS = ACTIVITY_STATUS.ACTIVE.value,
        validate_ownership_modification: bool = True,
    ):
        AccountProcessor.get_user(accessor_email)
        try:
            bot_access = BotAccess.objects(
                accessor_email__iexact=accessor_email,
                bot=bot,
                status__ne=ACTIVITY_STATUS.DELETED.value,
            ).get()
            if (
                Utility.email_conf["email"]["enable"]
                and bot_access.status == ACTIVITY_STATUS.INVITE_NOT_ACCEPTED.value
            ):
                raise AppException("User is yet to accept the invite")
            if validate_ownership_modification and ACCESS_ROLES.OWNER.value in {
                role,
                bot_access.role,
            }:
                raise AppException("Ownership modification denied")
            if bot_access.role == role:
                raise AppException(f"User is already {role} of the bot")
            bot_access.role = role
            bot_access.user = user
            bot_access.status = status
            bot_access.timestamp = datetime.utcnow()
            bot_access.save()
        except DoesNotExist:
            raise AppException("User not yet invited to collaborate")

    @staticmethod
    def get_bot_owner(bot: Text):
        return (
            BotAccess.objects(
                bot=bot,
                role=ACCESS_ROLES.OWNER.value,
                status__ne=ACTIVITY_STATUS.DELETED.value,
            )
            .get()
            .to_mongo()
            .to_dict()
        )

    @staticmethod
    def transfer_ownership(account: int, bot: Text, current_owner: Text, to_user: Text):
        bot_info = AccountProcessor.get_bot_and_validate_status(bot)
        AccountProcessor.__update_role(
            bot,
            to_user,
            current_owner,
            ACCESS_ROLES.OWNER.value,
            validate_ownership_modification=False,
        )
        AccountProcessor.__update_role(
            bot,
            current_owner,
            current_owner,
            ACCESS_ROLES.ADMIN.value,
            validate_ownership_modification=False,
        )
        AccountProcessor.__change_bot_account(bot, to_user)
        UserActivityLogger.add_log(
            UserActivityType.transfer_ownership.value,
            account,
            current_owner,
            bot,
            [f"Ownership transferred to {to_user}"],
        )
        return bot_info["name"]

    @staticmethod
    def __change_bot_account(bot_id: Text, to_owner: Text):
        user = AccountProcessor.get_user(to_owner)
        Bot.objects(id=bot_id, status=True).update(set__account=user["account"])
        BotAccess.objects(bot=bot_id, status__ne=ACTIVITY_STATUS.DELETED.value).update(
            set__bot_account=user["account"]
        )

    @staticmethod
    def validate_request_and_accept_bot_access_invite(token: Text, bot: Text):
        """
        Activate user's access to bot.

        :param token: token sent in the link
        :param bot: bot id
        """
        accessor_email = Utility.verify_token(token).get("mail_id")
        AccountProcessor.get_user_details(accessor_email)
        return AccountProcessor.accept_bot_access_invite(bot, accessor_email)

    @staticmethod
    def accept_bot_access_invite(bot: Text, accessor_email: Text):
        """
        Activate user's access to bot.

        :param accessor_email: user invited to bot
        :param bot: bot id
        """
        bot_details = AccountProcessor.get_bot_and_validate_status(bot)
        try:
            bot_access = BotAccess.objects(
                accessor_email__iexact=accessor_email,
                bot=bot,
                status=ACTIVITY_STATUS.INVITE_NOT_ACCEPTED.value,
            ).get()
            bot_access.status = ACTIVITY_STATUS.ACTIVE.value
            bot_access.accept_timestamp = datetime.utcnow()
            bot_access.save()
            return (
                bot_access.user,
                bot_details["name"],
                bot_access.accessor_email,
                bot_access.role,
            )
        except DoesNotExist:
            raise AppException("No pending invite found for this bot and user")

    @staticmethod
    def list_active_invites(user: Text):
        """
        List active bot invites.

        :param user: account username
        """
        for invite in BotAccess.objects(
            accessor_email__iexact=user,
            status=ACTIVITY_STATUS.INVITE_NOT_ACCEPTED.value,
        ):
            invite = invite.to_mongo().to_dict()
            bot_details = AccountProcessor.get_bot(invite["bot"])
            invite["bot_name"] = bot_details["name"]
            invite.pop("_id")
            invite.pop("bot_account")
            invite.pop("status")
            yield invite

    @staticmethod
    def search_user(txt: Text):
        """
        List active bot invites.

        :param txt: name to search
        """
        for user in User.objects().search_text(txt).order_by("$text_score").limit(5):
            yield user.email

    @staticmethod
    def remove_bot_access(bot: Text, **kwargs):
        """
        Removes bot from either for all users or only for user supplied.

        :param bot: bot id
        :param kwargs: can be either account or email.
        """
        if kwargs:
            if not Utility.is_exist(
                BotAccess,
                None,
                False,
                **kwargs,
                bot=bot,
                status__ne=ACTIVITY_STATUS.DELETED.value,
            ):
                raise AppException("User not a collaborator to this bot")
            active_bot_access = BotAccess.objects(
                **kwargs, bot=bot, status__ne=ACTIVITY_STATUS.DELETED.value
            ).get()
            active_bot_access.update(set__status=ACTIVITY_STATUS.DELETED.value, user=kwargs.get('accessor_email'))
        else:
            active_bot_access = BotAccess.objects(
                bot=bot, status__ne=ACTIVITY_STATUS.DELETED.value
            )
            active_bot_access.update(set__status=ACTIVITY_STATUS.DELETED.value)

    @staticmethod
    def remove_member(bot: Text, accessor_email: Text, current_user: Text):
        if accessor_email == current_user:
            raise AppException("User cannot remove himself")
        Utility.is_exist(
            BotAccess,
            "Bot owner cannot be removed",
            accessor_email__iexact=accessor_email,
            bot=bot,
            status__ne=ACTIVITY_STATUS.DELETED.value,
            role=ACCESS_ROLES.OWNER.value,
        )
        AccountProcessor.remove_bot_access(bot, accessor_email=accessor_email)

    @staticmethod
    def list_bot_accessors(bot: Text):
        """
        List users who have access to bot.

        :param bot: bot id
        """
        for accessor in BotAccess.objects(
            bot=bot, status__ne=ACTIVITY_STATUS.DELETED.value
        ):
            accessor = accessor.to_mongo().to_dict()
            accessor["_id"] = accessor["_id"].__str__()
            yield accessor

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
    def get_bot_and_validate_status(bot_id: str):
        """
        fetches bot details

        :param bot_id: bot id
        :return: bot details
        """
        bot = AccountProcessor.get_bot(bot_id)
        if not bot["status"]:
            raise AppException("Inactive Bot Please contact system admin!")
        return bot

    @staticmethod
    def add_user(
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        account: int,
        user: str,
    ):
        """
        adds new user to the account

        :param email: user login id
        :param password: user password
        :param first_name: user firstname
        :param last_name:  user lastname
        :param account: account id
        :param user: user id
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
            check_base_fields=False,
        )
        return (
            User(
                email=email.strip(),
                password=Utility.get_password_hash(password.strip()),
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                account=account,
                user=user.strip(),
            )
            .save()
            .to_mongo()
            .to_dict()
        )

    @staticmethod
    def get_user(email: str, is_login_request: bool = False, raise_error: bool = True):
        """
        fetch user details

        :param email: user login id
        :param is_login_request: logs invalid logins if true
        :param raise_error: logs raise error saying **User does not exist!** if true
        :return: user details
        """
        try:
            return (
                User.objects(email__iexact=email, status=True)
                .get()
                .to_mongo()
                .to_dict()
            )
        except Exception as e:
            logging.error(e)
            if is_login_request:
                UserActivityLogger.add_log(
                    a_type=UserActivityType.invalid_login.value, email=email, data={"username": email}
                )
            if raise_error:
                raise DoesNotExist("User does not exist!")

    @staticmethod
    def get_user_details(email: str, is_login_request: bool = False):
        """
        fetches complete user details, checks for whether it is inactive

        :param email: login id
        :param is_login_request: logs invalid logins if true
        :return: dict
        """
        user = AccountProcessor.get_user(email, is_login_request)
        AccountProcessor.check_email_confirmation(user, is_login_request)
        if not user["status"]:
            if is_login_request:
                message = ["Inactive User please contact admin!"]
                UserActivityLogger.add_log(
                    a_type=UserActivityType.invalid_login.value, account=user["account"],
                    email=email,
                    message=message, data={"username": email}
                )
            raise ValidationError("Inactive User please contact admin!")
        account = AccountProcessor.get_account(user["account"])
        if not account["status"]:
            if is_login_request:
                message = ["Inactive Account Please contact system admin!"]
                UserActivityLogger.add_log(
                    a_type=UserActivityType.invalid_login.value, account=user["account"], email=email,
                    message=message, data={"username": email}
                )
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
        account = AccountProcessor.get_account(user["account"])
        bots = AccountProcessor.get_accessible_bot_details(user["account"], email)
        user["account_name"] = account["name"]
        user["bots"] = bots
        user["_id"] = user["_id"].__str__()
        user.pop("password")
        return user

    @staticmethod
    def update_user_details(email: Text, status: Text):
        try:
            user = User.objects(email__iexact=email, status=True).get()
            if status in [ONBOARDING_STATUS.COMPLETED.value, ONBOARDING_STATUS.SKIPPED.value]:
                user.is_onboarded = True
            user.onboarding_status = status
            user.onboarding_timestamp = datetime.utcnow()
            user.save()
        except DoesNotExist as e:
            logging.error(e)
            raise AppException("User does not exists!")

    @staticmethod
    def add_user_consent_details(email: str, consent_details: dict):
        terms_and_policy_version = Utility.environment["app"]["terms_and_policy_version"]
        accepted_privacy_policy = consent_details.get("accepted_privacy_policy")
        accepted_terms = consent_details.get("accepted_terms")
        Utility.verify_privacy_policy_and_terms_consent(accepted_privacy_policy, accepted_terms)
        UserActivityLogger.add_user_activity_log(
            a_type=UserActivityType.user_consent.value,
            email=email,
            message=["Privacy Policy, Terms and Conditions consent"],
            data={
                "username": email,
                "accepted_privacy_policy": accepted_privacy_policy,
                "accepted_terms": accepted_terms,
                "terms_and_policy_version": terms_and_policy_version
            }
        )

    @staticmethod
    def get_user_details_and_filter_bot_info_for_integration_user(
        email: Text, is_integration_user: bool, bot: Text = None
    ):
        user_details = AccountProcessor.get_complete_user_details(email)
        if is_integration_user:
            user_details["bots"] = Utility.filter_bot_details_for_integration_user(
                bot, user_details["bots"]
            )
        user_activity_log = UserActivityLogger.get_user_activity_log(email=email)
        user_activity_log, show_updated_terms_and_policy = Utility.compare_terms_and_policy_version(user_activity_log)
        user_details["accepted_privacy_policy"] = user_activity_log["data"]["accepted_privacy_policy"]
        user_details["accepted_terms"] = user_activity_log["data"]["accepted_terms"]
        user_details["accepted_datetime"] = user_activity_log["timestamp"]
        user_details["show_updated_terms_and_policy"] = show_updated_terms_and_policy
        return user_details

    @staticmethod
    def verify_and_log_user_consent(account_setup: dict):
        terms_and_policy_version = Utility.environment["app"]["terms_and_policy_version"]
        user = account_setup.get("email")
        accepted_privacy_policy = account_setup.get("accepted_privacy_policy")
        accepted_terms = account_setup.get("accepted_terms")
        UserActivityLogger.add_user_activity_log(
            a_type=UserActivityType.user_consent.value,
            email=user,
            message=["Privacy Policy, Terms and Conditions consent"],
            data={
                "username": user,
                "accepted_privacy_policy": accepted_privacy_policy,
                "accepted_terms": accepted_terms,
                "terms_and_policy_version": terms_and_policy_version
            }
        )
        Utility.verify_privacy_policy_and_terms_consent(accepted_privacy_policy, accepted_terms)

    @staticmethod
    async def account_setup(account_setup: Dict):
        """
        create new account

        :param account_setup: dict of account details
        :return: dict user details, user email id, confirmation mail subject, mail body
        """

        account = None
        mail_to = None
        email_enabled = Utility.email_conf["email"]["enable"]
        link = None
        user = account_setup.get("email")
        try:
            account = AccountProcessor.add_account(account_setup.get("account"), user)
            user_details = AccountProcessor.add_user(
                email=account_setup.get("email"),
                first_name=account_setup.get("first_name"),
                last_name=account_setup.get("last_name"),
                password=account_setup.get("password").get_secret_value(),
                account=account["_id"].__str__(),
                user=user,
            )
            if email_enabled:
                token = Utility.generate_token(account_setup.get("email"))
                link = Utility.email_conf["app"]["url"] + "/verify/" + token
                mail_to = account_setup.get("email")

        except Exception as e:
            if account and "_id" in account:
                Account.objects().get(id=account["_id"]).delete()
            raise e

        return user_details, mail_to, link

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
            "password": SecretStr("Changeit@123")
        }
        try:
            user, mail, link = await AccountProcessor.account_setup(account)
            return user, mail, link
        except Exception as e:
            logging.info(str(e))

    @staticmethod
    def load_system_properties():
        try:
            system_properties = SystemProperties.objects().get().to_mongo().to_dict()
        except DoesNotExist:
            mail_templates = MailTemplates(
                password_reset=open("template/emails/passwordReset.html", "r").read(),
                password_reset_confirmation=open(
                    "template/emails/passwordResetConfirmation.html", "r"
                ).read(),
                verification=open("template/emails/verification.html", "r").read(),
                verification_confirmation=open(
                    "template/emails/verificationConfirmation.html", "r"
                ).read(),
                add_member_invitation=open(
                    "template/emails/memberAddAccept.html", "r"
                ).read(),
                add_member_confirmation=open(
                    "template/emails/memberAddConfirmation.html", "r"
                ).read(),
                password_generated=open(
                    "template/emails/passwordGenerated.html", "r"
                ).read(),
                conversation=open("template/emails/conversation.html", "r").read(),
                custom_text_mail=open(
                    "template/emails/custom_text_mail.html", "r"
                ).read(),
                bot_msg_conversation=open(
                    "template/emails/bot_msg_conversation.html", "r"
                ).read(),
                user_msg_conversation=open(
                    "template/emails/user_msg_conversation.html", "r"
                ).read(),
                update_role=open("template/emails/memberUpdateRole.html", "r").read(),
                untrusted_login=open("template/emails/untrustedLogin.html", "r").read(),
                add_trusted_device=open(
                    "template/emails/addTrustedDevice.html", "r"
                ).read(),
                button_template=open("template/emails/button.html", "r").read(),
                leave_bot_owner_notification=open("template/emails/leaveBotOwnerNotification.html", "r").read(),
            )
            system_properties = (
                SystemProperties(mail_templates=mail_templates)
                .save()
                .to_mongo()
                .to_dict()
            )
        Utility.email_conf["email"]["templates"]["verification"] = system_properties[
            "mail_templates"
        ]["verification"]
        Utility.email_conf["email"]["templates"][
            "verification_confirmation"
        ] = system_properties["mail_templates"]["verification_confirmation"]
        Utility.email_conf["email"]["templates"]["password_reset"] = system_properties[
            "mail_templates"
        ]["password_reset"]
        Utility.email_conf["email"]["templates"][
            "password_reset_confirmation"
        ] = system_properties["mail_templates"]["password_reset_confirmation"]
        Utility.email_conf["email"]["templates"][
            "add_member_invitation"
        ] = system_properties["mail_templates"]["add_member_invitation"]
        Utility.email_conf["email"]["templates"][
            "add_member_confirmation"
        ] = system_properties["mail_templates"]["add_member_confirmation"]
        Utility.email_conf["email"]["templates"][
            "password_generated"
        ] = system_properties["mail_templates"]["password_generated"]
        Utility.email_conf["email"]["templates"]["conversation"] = system_properties[
            "mail_templates"
        ]["conversation"]
        Utility.email_conf["email"]["templates"][
            "custom_text_mail"
        ] = system_properties["mail_templates"]["custom_text_mail"]
        Utility.email_conf["email"]["templates"][
            "bot_msg_conversation"
        ] = system_properties["mail_templates"]["bot_msg_conversation"]
        Utility.email_conf["email"]["templates"][
            "user_msg_conversation"
        ] = system_properties["mail_templates"]["user_msg_conversation"]
        Utility.email_conf["email"]["templates"]["update_role"] = system_properties[
            "mail_templates"
        ]["update_role"]
        Utility.email_conf["email"]["templates"]["untrusted_login"] = system_properties[
            "mail_templates"
        ]["untrusted_login"]
        Utility.email_conf["email"]["templates"][
            "add_trusted_device"
        ] = system_properties["mail_templates"]["add_trusted_device"]
        Utility.email_conf["email"]["templates"]["button_template"] = system_properties[
            "mail_templates"
        ]["button_template"]
        Utility.email_conf["email"]["templates"]["leave_bot_owner_notification"] = system_properties["mail_templates"][
            "leave_bot_owner_notification"]

    @staticmethod
    async def confirm_email(token: str):
        """
        Confirms the user through link and updates the database

        :param token: the token from link
        :return: mail id, subject of mail, body of mail
        """
        decoded_jwt = Utility.verify_token(token)
        email_confirm = decoded_jwt.get("mail_id")
        Utility.is_exist(
            UserEmailConfirmation,
            exp_message="Email already confirmed!",
            email__iexact=email_confirm.strip(),
        )
        confirm = UserEmailConfirmation()
        confirm.email = email_confirm
        confirm.save()
        user = AccountProcessor.get_user(email_confirm)
        return email_confirm, user["first_name"]

    @staticmethod
    def is_user_confirmed(email: str):
        """
        Checks if user is verified and raises an Exception if not

        :param email: mail id of user
        :return: None
        """
        if not Utility.is_exist(
            UserEmailConfirmation, email__iexact=email.strip(), raise_error=False
        ):
            raise AppException("Please verify your mail")

    @staticmethod
    def check_email_confirmation(user_info: dict, is_login_request: bool = False):
        """
        Checks if the account is verified through mail

        :param user_info: details of the user
        :param is_login_request: login request
        :return: None
        """
        email_enabled = Utility.email_conf["email"]["enable"]

        if email_enabled:
            try:
                AccountProcessor.is_user_confirmed(user_info["email"])
            except Exception as e:
                if is_login_request:
                    message = ["Please verify your mail"]
                    UserActivityLogger.add_log(
                        a_type=UserActivityType.invalid_login.value, account=user_info["account"],
                        message=message, data={"username": user_info["email"]}
                    )
                raise e

    @staticmethod
    async def send_reset_link(mail: str):
        """
        Sends a password reset link to the mail id

        :param mail: email id of the user
        :return: mail id, mail subject, mail body
        """
        email_enabled = Utility.email_conf["email"]["enable"]

        if email_enabled:
            mail = mail.strip()
            if isinstance(mail_check(mail), ValidationFailure):
                raise AppException("Please enter valid email id")
            if not Utility.is_exist(
                User,
                email__iexact=mail,
                status=True,
                raise_error=False,
                check_base_fields=False,
            ):
                raise AppException("Error! There is no user with the following mail id")
            if not Utility.is_exist(
                UserEmailConfirmation, email__iexact=mail, raise_error=False
            ):
                raise AppException("Error! The following user's mail is not verified")
            UserActivityLogger.is_password_reset_within_cooldown_period(mail)
            UserActivityLogger.is_password_reset_request_limit_exceeded(mail)
            token_expiry = (
                Utility.environment["user"]["reset_password_cooldown_period"] or 120
            )
            uuid_value = str(uuid.uuid1())
            token = Utility.generate_token_payload(
                {"mail_id": mail, "uuid": uuid_value}, token_expiry * 60
            )
            user = AccountProcessor.get_user(mail)
            link = Utility.email_conf["app"]["url"] + '/reset_password/' + token
            UserActivityLogger.add_log(
                a_type=UserActivityType.reset_password_request.value,
                account=user['account'],
                email=mail
            )
            data = {"status": "pending", "uuid": uuid_value}
            UserActivityLogger.add_log(
                a_type=UserActivityType.link_usage.value, account=user["account"],
                email=mail,
                
                message=["Send Reset Link"],
                data=data,
            )
            return mail, user["first_name"], link
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
        decoded_jwt = Utility.verify_token(token)
        email = decoded_jwt.get("mail_id")
        uuid_value = decoded_jwt.get("uuid")
        UserActivityLogger.is_token_already_used(uuid_value, email)
        user = User.objects(email__iexact=email, status=True).get()
        UserActivityLogger.is_password_reset_within_cooldown_period(email)
        previous_passwrd = user.password
        if Utility.verify_password(password.strip(), previous_passwrd):
            raise AppException("You have already used this password, try another!")
        UserActivityLogger.is_password_used_before(email, password)
        user.password = Utility.get_password_hash(password.strip())
        user.user = email
        user.save()
        data = {"password": previous_passwrd}
        UserActivityLogger.add_log(
            a_type=UserActivityType.reset_password.value,
            account=user['account'],
            email=email,
            data=data
        )
        UserActivityLogger.update_reset_password_link_usage(uuid_value, email)
        return email, user.first_name

    @staticmethod
    async def send_confirmation_link(mail: str):
        """
        Sends a link to the user's mail id for account verification

        :param mail: the mail id of the user
        :return: mail id, mail subject and mail body
        """
        email_enabled = Utility.email_conf["email"]["enable"]

        if email_enabled:
            if isinstance(mail_check(mail), ValidationFailure):
                raise AppException("Please enter valid email id")
            Utility.is_exist(
                UserEmailConfirmation,
                exp_message="Email already confirmed!",
                email__iexact=mail.strip(),
                check_base_fields=False,
            )
            if not Utility.is_exist(
                User,
                email__iexact=mail.strip(),
                status=True,
                raise_error=False,
                check_base_fields=False,
            ):
                raise AppException("Error! There is no user with the following mail id")
            user = AccountProcessor.get_user(mail)
            token = Utility.generate_token(mail)
            link = Utility.email_conf["app"]["url"] + "/verify/" + token
            return mail, user["first_name"], link
        else:
            raise AppException("Error! Email verification is not enabled")

    @staticmethod
    def add_feedback(
        rating: float, user: str, scale: float = 5.0, feedback: str = None
    ):
        """
        Add user feedback.
        @param rating: user given rating.
        @param user: Kairon username.
        @param scale: Scale on which rating is given. %.0 is the default value.
        @param feedback: feedback if any.
        @return:
        """
        Feedback(rating=rating, scale=scale, feedback=feedback, user=user).save()

    @staticmethod
    def update_ui_config(config: dict, user: str):
        """
        Adds UI configuration such as themes, layout type, flags for stepper
        to render UI components based on it.
        @param config: UI configuration to save.
        @param user: username
        """
        try:
            ui_config = UiConfig.objects(user=user).get()
        except DoesNotExist:
            ui_config = UiConfig(user=user)
        ui_config.config = config
        ui_config.save()

    @staticmethod
    def get_ui_config(user: str):
        """
        Retrieves UI configuration such as themes, layout type, flags for stepper
        to render UI components based on it.
        @param user: username
        """
        try:
            ui_config = UiConfig.objects(user=user).get()
            config = ui_config.config
        except DoesNotExist:
            config = {}
            AccountProcessor.update_ui_config(config, user)
        return config

    @staticmethod
    def delete_account(account_id: int, email: str = None):
        """
        Delete User Account

        :param account_id: user account id
        :param email: user email
        :return: None
        """
        try:
            account_obj = Account.objects(id=account_id, status=True).get()

        except DoesNotExist:
            raise AppException("Account does not exist!")

        # List all bots for the account
        account_bots = list(AccountProcessor.list_bots(account_id))
        # Delete all account_owned bots
        for bot in account_bots:
            AccountProcessor.delete_bot(bot["_id"], email)
            UserActivityLogger.add_log(
                
                a_type=UserActivityType.delete_bot.value,
               account=account_id, bot=bot["_id"],
            )

        # Delete all Users for Account
        for user in User.objects(account=account_id, status=True):
            BotAccess.objects(
                accessor_email=user.email, status__ne=ACTIVITY_STATUS.DELETED.value
            ).update(set__status=ACTIVITY_STATUS.DELETED.value)
            user.status = False
            user.save()
            UserActivityLogger.add_log(
                a_type=UserActivityType.delete_user.value,
                account=account_id,
                email=user.email
            )

        account_obj.status = False
        account_obj.save()
        UserActivityLogger.add_log(
             a_type=UserActivityType.delete_account.value
        , account=account_id)

    @staticmethod
    def get_location_and_add_trusted_device(
        user: Text,
        fingerprint: Text,
        request: Request,
        send_confirmation: bool = True,
        raise_err: bool = False,
    ):
        if Utility.environment["user"]["validate_trusted_device"]:
            ip = Utility.get_client_ip(request)
            geo_location = (
                PluginFactory.get_instance(PluginTypes.ip_info.value).execute(ip=ip)
                or {}
            )
            link = AccountProcessor.add_trusted_device(
                user, fingerprint, send_confirmation, **geo_location
            )
            return link, geo_location
        else:
            if raise_err:
                raise AppException("Trusted devices are disabled!")
            return None, None

    @staticmethod
    def add_trusted_device(
        user: Text, fingerprint: Text, send_confirmation: bool = True, **geo_location
    ):
        link = None
        if not Utility.is_exist(
            TrustedDevice,
            raise_error=False,
            user=user,
            fingerprint=fingerprint,
            status=True,
        ):
            device = TrustedDevice(
                user=user, fingerprint=fingerprint, geo_location=geo_location
            )
            if Utility.email_conf["email"]["enable"] and send_confirmation:
                payload = {"mail_id": user, "fingerprint": fingerprint}
                token = Utility.generate_token_payload(payload, minutes_to_expire=120)
                link = (
                    Utility.email_conf["app"]["url"]
                    + "/device/trusted/confirm/"
                    + token
                )
            else:
                device.is_confirmed = True
                device.confirmation_timestamp = datetime.utcnow()
            device.save()
            return link

    @staticmethod
    def confirm_add_trusted_device(user: Text, fingerprint: Text):
        if not Utility.is_exist(
            TrustedDevice,
            raise_error=False,
            user=user,
            fingerprint=fingerprint,
            is_confirmed=False,
            status=True,
        ):
            raise AppException("Device not found!")
        device = TrustedDevice.objects(
            user=user, fingerprint=fingerprint, is_confirmed=False, status=True
        ).get()
        device.is_confirmed = True
        device.confirmation_timestamp = datetime.utcnow()
        device.save()

    @staticmethod
    def remove_trusted_device(user: Text, fingerprint: Text):
        try:
            trusted_device = TrustedDevice.objects(
                user=user, fingerprint=fingerprint, status=True
            ).get()
            trusted_device.status = False
            trusted_device.save()
        except DoesNotExist as e:
            logging.exception(e)

    @staticmethod
    def list_trusted_device_fingerprints(user: Text):
        return list(
            TrustedDevice.objects(
                user=user, is_confirmed=True, status=True
            ).values_list("fingerprint")
        )

    @staticmethod
    def list_trusted_devices(user: Text):
        for device in TrustedDevice.objects(user=user, is_confirmed=True, status=True):
            device = device.to_mongo().to_dict()
            device["_id"] = device["_id"].__str__()
            device.pop("fingerprint")
            yield device

    @staticmethod
    def get_auditlog_for_user(user, start_idx: int = 0, page_size: int = 10):
        auditlog_data = (
            AuditLogData.objects(user=user)
            .skip(start_idx)
            .limit(page_size)
            .exclude("id")
            .order_by('-timestamp').to_json()
        )
        return json.loads(auditlog_data)

    @staticmethod
    def get_accessible_multilingual_bots(bot: Text, email: Text):
        accessible_bots = BotAccess.objects(
            accessor_email=email, status=ACTIVITY_STATUS.ACTIVE.value
        ).values_list("bot")
        multilingual_bots = list(AccountProcessor.get_multilingual_bots(bot))
        accessible_multilingual_bots = filter(
            lambda bot_info: bot_info["id"] in accessible_bots, multilingual_bots
        )
        return list(accessible_multilingual_bots)

    @staticmethod
    def get_multilingual_bots(bot: Text):
        source_bot = AccountProcessor.get_bot(bot)["metadata"].get("source_bot_id")
        if Utility.check_empty_string(source_bot):
            source_bot = bot
        for bot_info in Bot.objects(
            Q(metadata__source_bot_id=source_bot) | Q(id=bot), status=True
        ):
            bot_id = bot_info["id"].__str__()
            yield {
                "id": bot_id,
                "name": bot_info["name"],
                "language": bot_info["metadata"]["language"],
            }

    def get_model_testing_accuracy_of_all_accessible_bots(account_id: int, email: Text):
        from kairon.shared.test.data_objects import ModelTestingLogs

        bot_accuracies = {}
        bots = AccountProcessor.get_accessible_bot_details(account_id, email)
        for bot in bots["account_owned"] + bots["shared"]:
            accuracy_list = list(
                ModelTestingLogs.objects(bot=bot["_id"]).aggregate(
                    [
                        {"$match": {"type": "nlu"}},
                        {"$match": {"data.intent_evaluation.accuracy": {"$ne": None}}},
                        {"$project": {"accuracy": "$data.intent_evaluation.accuracy"}},
                    ]
                )
            )

            if accuracy_list:
                accuracy = accuracy_list[-1]["accuracy"]
            else:
                accuracy = None

            bot_accuracies[bot["_id"]] = accuracy

        return bot_accuracies

    @staticmethod
    async def process_leave_bot(bot: str, current_user: UserModel, account):

        bot_data = AccountProcessor.get_bot(bot)
        if not bot_data:
            raise AppException("Bot not found")

        owner_info = AccountProcessor.get_bot_owner(bot)
        if owner_info["accessor_email"] == current_user.email:
            raise AppException("Owner cannot leave the bot")

        from kairon.shared.authorization.data_objects import Integration

        tokens_data=(Integration.objects(bot=bot, user=current_user.email, status__ne=INTEGRATION_STATUS.DELETED.value))
        if tokens_data:
            raise AppException("You must delete all your integration tokens before leaving the bot")

        # Remove user from bot
        AccountProcessor.remove_bot_access(bot, accessor_email=current_user.email)

        return {
            "bot_data": bot_data,
            "owner_info": owner_info
        }