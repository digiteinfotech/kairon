from datetime import datetime, timedelta
from typing import Text

from fastapi import HTTPException
from starlette import status

from kairon.exceptions import AppException
from kairon.shared.constants import UserActivityType
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.audit.processor import AuditDataProcessor
from kairon.shared.data.constant import AuditlogActions
from kairon.shared.utils import Utility


class UserActivityLogger:

    @staticmethod
    def add_log(account: int, a_type: UserActivityType, email: Text = None, bot: Text = None, message: list = None, data: dict = None):
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
    def add_user_log(a_type: UserActivityType, email: Text = None, message: list = None, data: dict = None):
        """
        Adds user level log for various UserActivity

        :param a_type: UserActivityType
        :param email: email
        :param message: list of messages
        :param data: dictionary containing data
        """

        audit_data = {'message': message}
        audit_data.update(data) if data else None
        kwargs = {'action': AuditlogActions.ACTIVITY.value}
        AuditDataProcessor.log(a_type, email=email, data=audit_data, **kwargs)

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
            raise AppException(
                f'Password reset limit exhausted. Please come back in '
                f'{str(timedelta(seconds=(datetime.utcnow() - log.timestamp).seconds))}'
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
            user=email, action=AuditlogActions.ACTIVITY.value, entity=UserActivityType.login.value, timestamp__gte=cutoff_time
        ).count()
        first_login_with_cutoff = list(AuditLogData.objects(
            user=email, action=AuditlogActions.ACTIVITY.value, entity=UserActivityType.login.value, timestamp__gte=cutoff_time
        ))[0]
        next_allowed_login = ((datetime.utcnow() - first_login_with_cutoff.timestamp).total_seconds()) / 60
        if logins_within_cutoff >= login_request_limit:
            raise AppException(f'Only {login_request_limit} logins are allowed within {login_cooldown_period} minutes. '
                               f'Please come back in {next_allowed_login} minutes!')

    @staticmethod
    def is_relogin_done(uuid_value, email):
        """
        Checks if password is already reset or not

        :param uuid_value: uuid_value
        :param email: email
        :raises: AppException: Password already reset!
        """

        if uuid_value is not None and Utility.is_exist(
                AuditLogData, raise_error=False, user=email, action=AuditlogActions.ACTIVITY.value,
                entity=UserActivityType.link_usage.value,
                data__status="done", data__uuid=uuid_value, check_base_fields=False
        ):
            raise AppException("Password already reset!")

    @staticmethod
    def is_password_used_before(email, password):
        """
        Checks if same password is used or not

        :param email: email
        :param password: password
        :raises: AppException: You have already used that password, try another!
        """

        user_act_log = AuditLogData.objects(user=email, action=AuditlogActions.ACTIVITY.value,
                                            entity=UserActivityType.reset_password.value).order_by('-timestamp')
        if any(act_log.data is not None and act_log.data.get("password") is not None and
               Utility.verify_password(password.strip(), act_log.data.get("password"))
               for act_log in user_act_log):
            raise AppException("You have already used that password, try another!")

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
