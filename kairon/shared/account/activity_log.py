from datetime import datetime, timedelta
from typing import Text

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.account.data_objects import UserActivityLog
from kairon.shared.constants import UserActivityType


class UserActivityLogger:

    @staticmethod
    def add_log(email: Text, a_type: UserActivityType):
        UserActivityLog(user=email, type=a_type).save()

    @staticmethod
    def is_password_reset_request_limit_exceeded(email: Text):
        reset_password_request_limit = Utility.environment['user']['reset_password_request_limit']
        reset_password_request_count = UserActivityLog.objects(
            user=email, type=UserActivityType.reset_password_request.value, timestamp__gte=datetime.utcnow().date()
        ).count()
        if reset_password_request_count >= reset_password_request_limit:
            raise AppException(f'Password reset limit exhausted for today.')

    @staticmethod
    def is_password_reset_within_cooldown_period(email: Text):
        reset_password_request_limit = Utility.environment['user']['reset_password_cooldown_period']
        cooldown_period = datetime.utcnow().__sub__(timedelta(seconds=reset_password_request_limit * 60))
        if Utility.is_exist(
                UserActivityLog, raise_error=False, user=email, type=UserActivityType.reset_password.value,
                timestamp__gte=cooldown_period
        ):
            log = UserActivityLog.objects(
                user=email, type=UserActivityType.reset_password.value, timestamp__gte=cooldown_period
            ).get()
            raise AppException(
                f'Password reset limit exhausted. Please come back in '
                f'{str(timedelta(seconds=(datetime.utcnow() - log.timestamp).seconds))}'
            )
