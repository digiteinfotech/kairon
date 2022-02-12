import re

from jwt import PyJWTError
from tornado.httputil import HTTPServerRequest

from kairon.shared.account.processor import AccountProcessor
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
            token: Text, request: HTTPServerRequest
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
        return user_model

    @staticmethod
    def get_current_user(
            request: HTTPServerRequest
    ):
        """
        validates jwt token

        :param token: jwt token, default extracted by fastapi
        :param request: http request object
        :return: dict of user details
        """
        token = TornadoAuthenticate.get_token(request)
        user = TornadoAuthenticate.get_user_from_token(token, request)
        if user.is_integration_user:
            alias_user = request.headers.get("X-USER")
            if Utility.check_empty_string(alias_user):
                raise Exception("Alias user missing for integration")
            user.alias_user = alias_user
        return user

    @staticmethod
    def get_current_user_and_bot(
            request: HTTPServerRequest, **kwargs
    ):
        user = TornadoAuthenticate.get_current_user(request)
        bot_id = kwargs.get('bot')
        if Utility.check_empty_string(bot_id):
            raise Exception({"status_code": 422,
                             "detail": "Bot is required",
                             "headers": {"WWW-Authenticate": "Bearer"}})
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
