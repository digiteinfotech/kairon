import re
from datetime import datetime, timedelta
from typing import Text

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import SecurityScopes
from jwt import PyJWTError, encode
from mongoengine import DoesNotExist
from pydantic import SecretStr
from starlette.status import HTTP_401_UNAUTHORIZED

from kairon.api.models import TokenData
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.data.utils import DataUtility
from kairon.shared.models import User
from kairon.shared.sso.factory import LoginSSOFactory
from kairon.shared.utils import Utility

Utility.load_environment()


class Authentication:
    """
    Class contains logic for api Authentication
    """

    @staticmethod
    async def get_current_user(
        request: Request, token: str = Depends(DataUtility.oauth2_scheme)
    ):
        """
        validates jwt token

        :param token: jwt token, default extracted by fastapi
        :param request: http request object
        :return: dict of user details
        """
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = Utility.decode_limited_access_token(token)
            username: str = payload.get("sub")
            Authentication.validate_limited_access_token(request, payload.get("access-limit"))
            if username is None:
                raise credentials_exception
            token_data = TokenData(username=username)
        except PyJWTError:
            raise credentials_exception
        user = AccountProcessor.get_user_details(token_data.username)
        if user is None:
            raise credentials_exception

        user_model = User(**user)
        if user["is_integration_user"]:
            alias_user = request.headers.get("X-USER")
            if Utility.check_empty_string(alias_user):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Alias user missing for integration",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user_model.alias_user = alias_user
        return user_model

    @staticmethod
    async def get_current_user_and_bot(security_scopes: SecurityScopes, request: Request, token: str = Depends(DataUtility.oauth2_scheme)):
        if security_scopes.scopes:
            authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
        else:
            authenticate_value = "Bearer"
        user = await Authentication.get_current_user(request, token)
        bot_id = request.path_params.get('bot')
        if Utility.check_empty_string(bot_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='Bot is required',
            )
        user_role = AccountProcessor.fetch_role_for_user(user.email, bot_id)
        if security_scopes.scopes and user_role['role'] not in security_scopes.scopes:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"{security_scopes.scopes} access is required to perform this operation on the bot",
                headers={"WWW-Authenticate": authenticate_value},
            )
        bot = AccountProcessor.get_bot(bot_id)
        if not bot["status"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Inactive Bot Please contact system admin!",
                headers={"WWW-Authenticate": authenticate_value},
            )
        user.active_bot = bot_id
        return user

    @staticmethod
    def create_access_token(*, data: dict, is_integration=False, token_expire: int = 0):
        access_token_expire_minutes = Utility.environment['security']["token_expire"]
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]
        to_encode = data.copy()
        if not is_integration:
            if token_expire > 0:
                expire = datetime.utcnow() + timedelta(minutes=token_expire)
            else:
                if access_token_expire_minutes:
                    expires_delta = timedelta(minutes=access_token_expire_minutes)
                else:
                    expires_delta = timedelta(minutes=15)
                expire = datetime.utcnow() + expires_delta
            to_encode.update({"exp": expire})
        encoded_jwt = encode(to_encode, secret_key, algorithm=algorithm)
        return encoded_jwt

    @staticmethod
    def __authenticate_user(username: str, password: str):
        user = AccountProcessor.get_user_details(username)
        if not user:
            return False
        if not Utility.verify_password(password, user["password"]):
            return False
        return user

    @staticmethod
    def authenticate(username: Text, password: Text):
        """
        authenticate user and generate jwt token

        :param username: login id ie. email address
        :param password: login password
        :return: jwt token
        """
        user = Authentication.__authenticate_user(username, password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = Authentication.create_access_token(data={"sub": user["email"]})
        return access_token

    @staticmethod
    def validate_limited_access_token(request: Request, access_limit: list):
        if not access_limit:
            return
        requested_endpoint = request.scope['path']
        matches = any(re.match(allowed_endpoint, requested_endpoint) for allowed_endpoint in access_limit)
        if not matches:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='Access denied for this endpoint',
            )

    @staticmethod
    async def authenticate_and_get_collection(request: Request, token: str = Depends(DataUtility.oauth2_scheme_non_strict)):
        token_configured = Utility.environment['authentication']['token']
        if token_configured != token:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if 'bot' == Utility.environment['tracker']['type']:
            bot_id = request.path_params.get('bot')
            if Utility.check_empty_string(bot_id):
                raise HTTPException(
                    status_code=422,
                    detail="Bot id is required",
                )
            return bot_id
        else:
            collection = Utility.environment['tracker']['collection']
            if Utility.check_empty_string(collection):
                raise HTTPException(
                    status_code=422,
                    detail="Collection not configured",
                )
            return collection

    @staticmethod
    def generate_integration_token(bot: Text, account: int, expiry: int = 0, access_limit: list = None):
        """ Generates an access token for secure integration of the bot
            with an external service/architecture """
        integration_user = AccountProcessor.get_integration_user(bot, account)
        data = {"sub": integration_user["email"]}
        if expiry > 0:
            expire = datetime.utcnow() + timedelta(minutes=expiry)
            data.update({"exp": expire})
        if access_limit:
            data['access-limit'] = access_limit
        access_token = Authentication.create_access_token(
            data=data, is_integration=True
        )
        return access_token

    @staticmethod
    async def get_redirect_url(sso_type: str):
        return await LoginSSOFactory.get_client(sso_type).get_redirect_url()

    @staticmethod
    async def verify_and_process(request, sso_type: str):
        """
        Fetches user details and returns a login token.
        If user does not have an account, it will be created.

        :param request: starlette request object
        :param sso_type: one of supported types - google/facebook/linkedin.
        """
        sso_client = LoginSSOFactory.get_client(sso_type)
        user_details = await sso_client.verify(request)
        try:
            AccountProcessor.get_user(user_details['email'])
            existing_user = True
        except DoesNotExist:
            existing_user = False
            user_details['password'] = SecretStr(Utility.generate_password())
            user_details['account'] = user_details['email']
        if existing_user:
            AccountProcessor.get_user_details(user_details['email'])
        else:
            await AccountProcessor.account_setup(user_details, "sysadmin")
            tmp_token = Utility.generate_token(user_details['email'])
            await AccountProcessor.confirm_email(tmp_token)
        access_token = Authentication.create_access_token(data={"sub": user_details["email"]})
        return existing_user, user_details, access_token
