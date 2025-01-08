from datetime import datetime, timedelta
from typing import Text

from fastapi import HTTPException
from starlette import status

from kairon.exceptions import AppException
from kairon.shared.account.data_objects import UserActivityLog
from kairon.shared.constants import UserActivityType
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.audit.processor import AuditDataProcessor
from kairon.shared.data.constant import AuditlogActions
from kairon.shared.utils import Utility


class UserActivityLogger:

    @staticmethod
    def add_log(a_type: UserActivityType, account: int = None,  email: Text = None, bot: Text = None, message: list = None, data: dict = None):
        """
        Adds log for various UserActivity

        :param account: account id
        :param a_type: UserActivityType
        :param email: email
        :param bot: bot id
        :param message: list of messages
        :param data: dictionary containing data
        """

        audit_data = {'message': message}
        audit_data.update(data) if data else None
        kwargs = {'action': AuditlogActions.ACTIVITY.value}
        AuditDataProcessor.log(a_type, account, bot,  email, audit_data, **kwargs)

    @staticmethod
    def add_user_activity_log(a_type: UserActivityType, account: int = None,  email: Text = None,
                              message: list = None, data: dict = None):
        """
        Adds log for various UserActivity

        :param account: account id
        :param a_type: UserActivityType
        :param email: email
        :param message: list of messages
        :param data: dictionary containing data
        """
        try:
            user_activity_log = UserActivityLog(
                type=a_type,
                user=email,
                message=message,
                data=data
            )
            user_activity_log.save()
        except Exception as e:
            raise AppException(str(e))

    @staticmethod
    def get_user_activity_log(email: str):
        try:
            user_activity_log = UserActivityLog.objects(
                user=email, type=UserActivityType.user_consent.value
            ).order_by("-timestamp").first()
            user_activity_log = user_activity_log.to_mongo().to_dict()

        except Exception as e:
            raise AppException(str(e))
        return user_activity_log

    @staticmethod
    def is_password_reset_request_limit_exceeded(email: Text):
        """
        Checks if the password reset limit is exceeded or not

        :param email: email
        :raises: AppException: Password reset limit exhausted for today.
        """

        reset_password_request_limit = Utility.environment['user']['reset_password_request_limit']
        reset_password_request_count = AuditLogData.objects(
            user=email, action=AuditlogActions.ACTIVITY.value,
            entity=UserActivityType.reset_password_request.value,
            timestamp__gte=datetime.utcnow().date()
        ).order_by('-timestamp').count()
        if reset_password_request_count >= reset_password_request_limit:
            raise AppException('Password reset limit exhausted for today.')

    @staticmethod
    def is_password_reset_within_cooldown_period(email: Text):
        """
        Checks if the password is reset within cooldown period

        :param email: email
        :raises: AppException
        """

        reset_password_request_limit = Utility.environment['user']['reset_password_cooldown_period']
        cooldown_period = datetime.utcnow().__sub__(timedelta(seconds=reset_password_request_limit * 60))
        if Utility.is_exist(
                AuditLogData, raise_error=False, user=email, action=AuditlogActions.ACTIVITY.value, entity=UserActivityType.reset_password.value,
                timestamp__gte=cooldown_period, check_base_fields=False
        ):
            log = AuditLogData.objects(
                user=email, action=AuditlogActions.ACTIVITY.value,
                entity=UserActivityType.reset_password.value,
                timestamp__gte=cooldown_period).order_by('-timestamp').get()
            next_reset_time = log.timestamp + timedelta(minutes=reset_password_request_limit)
            next_reset = (next_reset_time - datetime.utcnow()).seconds
            next_login_duration = (int)((next_reset / 60) if (next_reset / 60) != 0 else next_reset)
            unit = "minutes" if (next_reset / 60) != 0 else "seconds"
            raise AppException(
                f'Password reset limit exhausted. Please come back in '
                f'{next_login_duration} {unit}!'
            )

    @staticmethod
    def is_login_within_cooldown_period(email: Text):
        """
        Checks if the login limit is exceeded or not

        :param email: email
        :raises: AppException
        """

        login_cooldown_period = Utility.environment['user']['login_cooldown_period']
        login_request_limit = Utility.environment['user']['login_limit']
        cutoff_time = datetime.utcnow() - timedelta(minutes=login_cooldown_period)
        logins_within_cutoff = AuditLogData.objects(
            user=email, action=AuditlogActions.ACTIVITY.value, entity=UserActivityType.invalid_login.value, timestamp__gte=cutoff_time
        ).count()
        if logins_within_cutoff >= login_request_limit:
            first_login_within_cutoff = list(AuditLogData.objects(
                user=email, action=AuditlogActions.ACTIVITY.value, entity=UserActivityType.invalid_login.value,
                timestamp__gte=cutoff_time
            ).order_by("timestamp"))
            next_login_time = first_login_within_cutoff[0].timestamp + timedelta(minutes=login_cooldown_period)
            next_login = (next_login_time - datetime.utcnow()).seconds
            next_login_duration = (int)((next_login / 60) if (next_login / 60) != 0 else next_login)
            unit = "minutes" if (next_login / 60) != 0 else "seconds"
            raise AppException(f'Account frozen due to too many unsuccessful login attempts. '
                               f'Please come back in {next_login_duration} {unit}!')

    @staticmethod
    def is_token_already_used(uuid_value, email):
        """
        Checks if password is already reset or not

        :param uuid_value: uuid_value
        :param email: email
        :raises: AppException: Link has already been used once and has thus expired!
        """

        if uuid_value is not None and Utility.is_exist(
                AuditLogData, raise_error=False, user=email, action=AuditlogActions.ACTIVITY.value,
                entity=UserActivityType.link_usage.value,
                data__status="done", data__uuid=uuid_value, check_base_fields=False
        ):
            raise AppException("Link has already been used once and has thus expired!")

    @staticmethod
    def is_password_used_before(email, password):
        """
        Checks if same password is used or not

        :param email: email
        :param password: password
        :raises: AppException: You have already used this password, try another!
        """

        user_act_log = AuditLogData.objects(user=email, action=AuditlogActions.ACTIVITY.value,
                                            entity=UserActivityType.reset_password.value).order_by('-timestamp')
        if email.lower() == password.lower():
            raise AppException("Email cannot be used as password!")
        if any(act_log.data and act_log.data.get("password") and
               Utility.verify_password(password.strip(), act_log.data.get("password")) for act_log in user_act_log):
            raise AppException("You have already used this password, try another!")

    @staticmethod
    def update_reset_password_link_usage(uuid_value, email):
        """
       Updates the status in data

        :param uuid_value: uuid_value
        :param email: email
        """

        if uuid_value is not None:
            AuditLogData.objects(user=email, action=AuditlogActions.ACTIVITY.value,
                                 entity=UserActivityType.link_usage.value,
                                 data__status="pending", data__uuid=uuid_value).order_by('-timestamp') \
                .update_one(set__data__status="done")

    @staticmethod
    def is_password_reset(payload, username):
        """
        Checks if password if session is expired or not

        :param payload: payload
        :param username: username
        :raises: AppException: Session expired. Please login again!
        """

        iat_val = payload.get("iat")
        if iat_val is not None:
            issued_at = datetime.utcfromtimestamp(iat_val)
            if Utility.is_exist(
                    AuditLogData, raise_error=False, user=username, action=AuditlogActions.ACTIVITY.value,
                    entity=UserActivityType.reset_password.value,
                    timestamp__gte=issued_at, check_base_fields=False):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='Session expired. Please login again!',
                )
