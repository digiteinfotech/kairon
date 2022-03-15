from datetime import datetime, timezone
from typing import Text

from mongoengine.errors import DoesNotExist
from kairon.exceptions import AppException
from kairon.shared.authorization.data_objects import Integration
from kairon.shared.data.constant import INTEGRATION_STATUS, ACCESS_ROLES
from kairon.shared.utils import Utility


class IntegrationProcessor:

    @staticmethod
    def add_integration(
            name: Text, bot: Text, user: Text, role: ACCESS_ROLES, iat: datetime = datetime.utcnow(), expiry: datetime = None,
            access_list: list = None
    ):
        integration_limit = Utility.environment['security'].get('integrations_per_user') or 2
        current_integrations_count = Integration.objects(bot=bot, status__ne=INTEGRATION_STATUS.DELETED.value).count()

        if current_integrations_count >= integration_limit:
            raise AppException('Integrations limit reached!')
        Utility.is_exist(
            Integration, 'Integration token with this name has already been initiated',
            name=name, bot=bot, status__ne=INTEGRATION_STATUS.DELETED.value
        )
        Integration(
            name=name, bot=bot, user=user, role=role, iat=iat, expiry=expiry, access_list=access_list,
            status=INTEGRATION_STATUS.ACTIVE.value
        ).save()

    @staticmethod
    def verify_integration_token(name: Text, bot: Text, user: Text, iat: datetime, role: Text):
        if isinstance(iat, float) or isinstance(iat, int):
            iat = datetime.fromtimestamp(iat, tz=timezone.utc)
        if not Utility.is_exist(
                Integration, raise_error=False,
                name=name, bot=bot, user=user, iat=iat, role=role, status=INTEGRATION_STATUS.ACTIVE.value
        ):
            raise AppException("Could not validate credentials")

    @staticmethod
    def get_integrations(bot: Text):
        for integration in Integration.objects(bot=bot, status__ne=INTEGRATION_STATUS.DELETED.value):
            integration = integration.to_mongo().to_dict()
            integration.pop('bot')
            integration.pop('_id')
            yield integration

    @staticmethod
    def update_integration(
            name: Text, bot: Text, user: Text, status: INTEGRATION_STATUS
    ):
        try:
            integration = Integration.objects(name=name, bot=bot, status__ne=INTEGRATION_STATUS.DELETED.value).get()
            integration.user = user
            integration.status = status
            integration.save()
        except DoesNotExist:
            raise AppException("Integration does not exists")
