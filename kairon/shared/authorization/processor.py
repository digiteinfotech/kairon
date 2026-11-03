from datetime import datetime, timedelta, timezone
from typing import Text

from mongoengine.errors import DoesNotExist
from kairon.shared.clock import utc_now
from kairon.exceptions import AppException
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.authorization.data_objects import Integration
from kairon.shared.data.constant import INTEGRATION_STATUS, ACCESS_ROLES, TOKEN_TYPE
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility


class IntegrationProcessor:

    @staticmethod
    def add_integration(
            name: Text, bot: Text, user: Text, role: ACCESS_ROLES, iat: datetime = utc_now(), expiry: datetime = None,
            access_list: list = None
    ):

        bot_settings = MongoProcessor.get_bot_settings(bot, user)
        integration_limit = bot_settings.integrations_per_user_limit if bot_settings else 3

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
                name=name, bot=bot, iat=iat, role=role, status=INTEGRATION_STATUS.ACTIVE.value
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

    @staticmethod
    def create_agent_action_token(bot: Text, user: Text, token_expire: int = 15):
        from kairon.shared.auth import Authentication
        integration = Integration.objects(
            name="agent-action", bot=bot,
            status=INTEGRATION_STATUS.ACTIVE.value
        ).first()
        if not integration:
            iat = datetime.now(tz=timezone.utc).replace(microsecond=0)
            IntegrationProcessor.add_integration(
                "agent-action", bot, user, ACCESS_ROLES.ADMIN.value, iat
            )
            integration = Integration.objects(
                name="agent-action", bot=bot,
                status=INTEGRATION_STATUS.ACTIVE.value
            ).first()
        data = {
            "sub": user, "bot": bot, "name": "agent-action",
            "role": integration.role, "iat": integration.iat.replace(tzinfo=timezone.utc),
            "account": AccountProcessor.get_bot(bot)["account"],
            "exp": datetime.utcnow() + timedelta(minutes=token_expire),
            "access-limit": [f"/api/agents/{bot}/.+/run/.+"],
        }
        return Authentication.create_access_token(
            data=data, token_type=TOKEN_TYPE.INTEGRATION.value, token_expire=token_expire
        )
