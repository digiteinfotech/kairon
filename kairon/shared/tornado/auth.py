import re

from jwt import PyJWTError
from tornado.httputil import HTTPServerRequest

from kairon.shared.account.processor import AccountProcessor
from kairon.shared.authorization.processor import IntegrationProcessor
from kairon.shared.data.constant import TOKEN_TYPE
from kairon.shared.models import User
from kairon.shared.utils import Utility
from typing import Text

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
        credentials_exception = Exception({"status_code": 401,
                                           "detail": "Could not validate credentials",
                                           "headers": {"WWW-Authenticate": "Bearer"}})
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
            if payload.get("type") == TOKEN_TYPE.INTEGRATION.value:
                TornadoAuthenticate.validate_integration_token(payload, kwargs.get('bot'))
            alias_user = request.headers.get("X-USER")
            if Utility.check_empty_string(alias_user) and payload.get("type") == TOKEN_TYPE.INTEGRATION.value:
                raise Exception("Alias user missing for integration")
            alias_user = alias_user or username
            user_model.alias_user = alias_user
            user_model.is_integration_user = True
            user_model.role = payload.get('role')

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
            raise Exception({"status_code": 422,
                             "detail": "Bot is required",
                             "headers": {"WWW-Authenticate": "Bearer"}})
        if not user.is_integration_user:
            AccountProcessor.fetch_role_for_user(user.email, bot_id)
        bot = AccountProcessor.get_bot(bot_id)
        if not bot["status"]:
            raise Exception({"status_code": 422,
                             "detail": "Inactive Bot Please contact system admin!",
                             "headers": {"WWW-Authenticate": "Bearer"}})
        user.active_bot = bot_id
        return user

    @staticmethod
    def get_current_user_and_bot_for_channel(
            token: Text, bot: Text, request: HTTPServerRequest
    ):
        user = TornadoAuthenticate.get_user_from_token(token, request)
        if Utility.check_empty_string(bot):
            raise Exception({"status_code": 422,
                             "detail": "Bot is required",
                             "headers": {"WWW-Authenticate": "Bearer"}})
        AccountProcessor.fetch_role_for_user(user.email, bot)
        bot = AccountProcessor.get_bot(bot)
        if not bot["status"]:
            raise Exception({"status_code": 422,
                             "detail": "Inactive Bot Please contact system admin!",
                             "headers": {"WWW-Authenticate": "Bearer"}})
        user.active_bot = bot
        return user

    @staticmethod
    def validate_limited_access_token(request: HTTPServerRequest, access_limit: list):
        if not access_limit:
            return
        requested_endpoint = request.uri
        matches = any(re.match(allowed_endpoint, requested_endpoint) for allowed_endpoint in access_limit)
        if not matches:
            raise Exception(
                 'Access denied for this endpoint'
            )

    @staticmethod
    def validate_integration_token(payload: dict, accessing_bot: Text):
        """
        Validates:
        1. whether integration token with this payload is active.
        2. the bot which is being accessed is the same bot for which the integration was generated.

        :param payload: Auth token claims dict.
        :param accessing_bot: bot for which the request was made.
        """
        exception = Exception({'status_code': 401, 'detail': 'Access to bot is denied'})
        name = payload.get('name')
        bot = payload.get('bot')
        user = payload.get('sub')
        iat = payload.get('iat')
        role = payload.get('role')
        if not Utility.check_empty_string(accessing_bot) and accessing_bot != bot:
            raise exception
        try:
            IntegrationProcessor.verify_integration_token(name, bot, user, iat, role)
        except Exception:
            raise exception
