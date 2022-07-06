import re

from jwt import PyJWTError
from tornado.httputil import HTTPServerRequest

from kairon.shared.account.processor import AccountProcessor
from kairon.shared.authorization.processor import IntegrationProcessor
from kairon.shared.data.constant import TOKEN_TYPE
from kairon.shared.models import User
from kairon.shared.tornado.exception import ServiceHandlerException
from kairon.shared.utils import Utility
from typing import Text
from datetime import datetime
from kairon.shared.account.data_objects import UserActivityLog, UserActivityType
from tornado.web import HTTPError

Utility.load_environment()


class TornadoAuthenticate:

    @staticmethod
    def get_token(request: HTTPServerRequest):
        authorization = request.headers.get('Authorization')
        token = ""
        if authorization:
            scheme, token = authorization.split(" ")
        return token.strip()

    @staticmethod
    def get_user_from_token(
            token: Text, request: HTTPServerRequest, **kwargs
    ):
        """
        validates jwt token

        :param token: jwt token
        :param request: http request object
        :return: dict of user details
        """
        credentials_exception = ServiceHandlerException("Could not validate credentials", 401, {"WWW-Authenticate": "Bearer"})
        try:
            payload = Utility.decode_limited_access_token(token)
            username: str = payload.get("sub")
            TornadoAuthenticate.validate_limited_access_token(request, payload.get("access-limit"))
            if username is None:
                raise credentials_exception
        except PyJWTError:
            raise credentials_exception
        user = AccountProcessor.get_user_details(username)
        if user is None:
            raise credentials_exception
        user_model = User(**user)
        if payload.get("type") != TOKEN_TYPE.LOGIN.value:
            TornadoAuthenticate.validate_bot_request(kwargs.get('bot'), payload.get('bot'))
            if payload.get("type") == TOKEN_TYPE.INTEGRATION.value:
                TornadoAuthenticate.validate_integration_token(payload)
            alias_user = request.headers.get("X-USER")
            if Utility.check_empty_string(alias_user) and payload.get("type") == TOKEN_TYPE.INTEGRATION.value:
                raise ServiceHandlerException("Alias user missing for integration", 401)
            alias_user = alias_user or username
            user_model.alias_user = alias_user
            user_model.is_integration_user = True
            user_model.role = payload.get('role')
        else:
            iat_val = payload.get("iat")
            if iat_val is not None:
                issued_at = datetime.utcfromtimestamp(iat_val)
                if Utility.is_exist(
                        UserActivityLog, raise_error=False, user=username, type=UserActivityType.reset_password.value,
                        timestamp__gte=issued_at):
                    raise HTTPError(
                        status_code=401,
                        reason='Session expired. Please login again.',
                    )
        return user_model

    @staticmethod
    def get_current_user(
            request: HTTPServerRequest, **kwargs
    ):
        """
        validates jwt token

        :param token: jwt token, default extracted by fastapi
        :param request: http request object
        :return: dict of user details
        """
        token = TornadoAuthenticate.get_token(request)
        user = TornadoAuthenticate.get_user_from_token(token, request, **kwargs)
        return user

    @staticmethod
    def get_current_user_and_bot(
            request: HTTPServerRequest, **kwargs
    ):
        user = TornadoAuthenticate.get_current_user(request, **kwargs)
        bot_id = kwargs.get('bot')
        if Utility.check_empty_string(bot_id):
            raise ServiceHandlerException("Bot is required", 422, {"WWW-Authenticate": "Bearer"})
        if not user.is_integration_user:
            AccountProcessor.fetch_role_for_user(user.email, bot_id)
        bot = AccountProcessor.get_bot(bot_id)
        if not bot["status"]:
            raise ServiceHandlerException("Inactive Bot Please contact system admin!", 422, {"WWW-Authenticate": "Bearer"})
        user.active_bot = bot_id
        return user

    @staticmethod
    def get_current_user_and_bot_for_channel(
            token: Text, bot: Text, request: HTTPServerRequest
    ):
        user = TornadoAuthenticate.get_user_from_token(token, request)
        if Utility.check_empty_string(bot):
            raise ServiceHandlerException("Bot is required", 422, {"WWW-Authenticate": "Bearer"})
        AccountProcessor.fetch_role_for_user(user.email, bot)
        bot = AccountProcessor.get_bot(bot)
        if not bot["status"]:
            raise ServiceHandlerException("Inactive Bot Please contact system admin!", 422, {"WWW-Authenticate": "Bearer"})
        user.active_bot = bot
        return user

    @staticmethod
    def validate_limited_access_token(request: HTTPServerRequest, access_limit: list):
        if not access_limit:
            return
        requested_endpoint = request.uri
        matches = any(re.match(allowed_endpoint, requested_endpoint) for allowed_endpoint in access_limit)
        if not matches:
            raise ServiceHandlerException('Access denied for this endpoint', 401)

    @staticmethod
    def validate_integration_token(payload: dict):
        """
        Validates whether integration token with this payload is active.

        :param payload: Auth token claims dict.
        """
        exception = ServiceHandlerException('Access to bot is denied', 401)
        name = payload.get('name')
        bot = payload.get('bot')
        user = payload.get('sub')
        iat = payload.get('iat')
        role = payload.get('role')
        try:
            IntegrationProcessor.verify_integration_token(name, bot, user, iat, role)
        except Exception:
            raise exception

    @staticmethod
    def validate_bot_request(bot_in_request_path: str, bot_in_token: str):
        """
        Validates the bot which is being accessed is the same bot for which the integration was generated.

        :param bot_in_request_path: bot for which the request was made.
        :param bot_in_token: bot which is present in auth token claims.
        """
        if not Utility.check_empty_string(bot_in_request_path) and bot_in_request_path != bot_in_token:
            raise ServiceHandlerException('Access to bot is denied', 401)
