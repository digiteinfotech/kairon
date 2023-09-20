from datetime import datetime, timedelta
from typing import Text

from kairon.exceptions import AppException
from kairon.shared.constants import UserActivityType
from kairon.shared.data.base_data import AuditLogData
from kairon.shared.data.constant import AuditlogActions
from kairon.shared.metering.metering_processor import MeteringProcessor
from kairon.shared.utils import Utility


class UserActivityLogger:

    @staticmethod
    def add_log(account: int, a_type: UserActivityType, email: Text = None, bot: Text = None, message: list = None, data: dict = None):
        from kairon.shared.account.processor import AccountProcessor

        audit_data = {'message': message}
        audit_data.update(data) if data else None
        audit = {'Bot_id': bot.__str__(), 'account': account}
        kwargs = {'action': AuditlogActions.ACTIVITY.value}
        user_detail = email if email else AccountProcessor.get_account(account)['user']
        Utility.save_auditlog_document(audit, user_detail, a_type, audit_data, **kwargs)

    @staticmethod
    def is_password_reset_request_limit_exceeded(email: Text):
        reset_password_request_limit = Utility.environment['user']['reset_password_request_limit']
        reset_password_request_count = AuditLogData.objects(
            user=email, action=AuditlogActions.ACTIVITY.value, entity=UserActivityType.reset_password_request.value,
            timestamp__gte=datetime.utcnow().date()
        ).count()
        if reset_password_request_count >= reset_password_request_limit:
            raise AppException('Password reset limit exhausted for today.')

    @staticmethod
    def is_password_reset_within_cooldown_period(email: Text):
        reset_password_request_limit = Utility.environment['user']['reset_password_cooldown_period']
        cooldown_period = datetime.utcnow().__sub__(timedelta(seconds=reset_password_request_limit * 60))
        if Utility.is_exist(
                AuditLogData, raise_error=False, user=email, action=AuditlogActions.ACTIVITY.value, entity=UserActivityType.reset_password.value,
                timestamp__gte=cooldown_period, check_base_fields=False
        ):
            log = AuditLogData.objects(
                user=email, action=AuditlogActions.ACTIVITY.value, entity=UserActivityType.reset_password.value, timestamp__gte=cooldown_period
            ).get()
            raise AppException(
                f'Password reset limit exhausted. Please come back in '
                f'{str(timedelta(seconds=(datetime.utcnow() - log.timestamp).seconds))}'
            )

    @staticmethod
    def login_limit_exceeded(account, metric_type):
        login_limit = Utility.environment['security']['login_limit']
        login_count = MeteringProcessor.get_metric_count(account, metric_type=metric_type)
        if login_count >= login_limit:
            raise AppException('Login limit exhausted for today.')
