import json
import re
from calendar import timegm
from datetime import datetime, timedelta, timezone
from typing import Text

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import SecurityScopes
from jwt import PyJWTError, encode
from loguru import logger
from mongoengine import DoesNotExist
from pydantic import SecretStr
from starlette.status import HTTP_401_UNAUTHORIZED

from kairon.api.models import TokenData
from kairon.shared.account.activity_log import UserActivityLogger
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.authorization.processor import IntegrationProcessor
from kairon.shared.constants import PluginTypes, ChannelTypes, UserActivityType
from kairon.shared.data.constant import INTEGRATION_STATUS, TOKEN_TYPE, ACCESS_ROLES
from kairon.shared.data.utils import DataUtility
from kairon.shared.models import User
from kairon.shared.plugins.factory import PluginFactory
from kairon.shared.sso.factory import LoginSSOFactory
from kairon.shared.utils import Utility, MailUtility

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
            user = AccountProcessor.get_user_details(username)
            if user is None:
                raise credentials_exception
            user_model = User(**user)
            if payload.get("type") != TOKEN_TYPE.LOGIN.value:
                Authentication.validate_bot_request(request.path_params.get('bot'), payload.get('bot'))
                if payload.get("type") == TOKEN_TYPE.INTEGRATION.value:
                    Authentication.validate_integration_token(payload)
                alias_user = request.headers.get("X-USER")
                if Utility.check_empty_string(alias_user) and payload.get("type") == TOKEN_TYPE.INTEGRATION.value:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Alias user missing for integration",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                user_model.active_bot = payload.get('bot')
                user_model.is_integration_user = True
                user_model.alias_user = alias_user or username
                user_model.role = payload.get('role')
            else:
                UserActivityLogger.is_password_reset(payload, username)
            return user_model
        except PyJWTError:
            raise credentials_exception

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
        if user.is_integration_user:
            user_role = user.role
        else:
            user_role = AccountProcessor.fetch_role_for_user(user.email, bot_id)
            user_role = user_role['role']
        if security_scopes.scopes and user_role not in security_scopes.scopes:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"{security_scopes.scopes} access is required to perform this operation on the bot",
                headers={"WWW-Authenticate": authenticate_value},
            )
        bot_info = AccountProcessor.get_bot_and_validate_status(bot_id)
        user.active_bot = bot_id
        user.bot_account = bot_info['account']
        return user

    @staticmethod
    async def authenticate_token_in_path_param(security_scopes: SecurityScopes, request: Request):
        from kairon.chat.handlers.channels.msteams import MSTeamsHandler
        from kairon.chat.handlers.channels.line import LineHandler

        token = request.path_params.get("token")
        if request.path_params.get("channel") == ChannelTypes.MSTEAMS.value:
            is_valid_hash, token = MSTeamsHandler.is_validate_hash(request)
            if not is_valid_hash:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Webhook url is not updated, please check. Url on msteams still refer old hashtoken",
                )
        if request.path_params.get("channel") == ChannelTypes.LINE.value:
            is_valid_hash, token = LineHandler.is_validate_hash(request)
            if not is_valid_hash:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Webhook url is not updated, please check. Url on line still refer old hashtoken",
                )
        user = await Authentication.get_current_user_and_bot(security_scopes, request, token)
        return user

    @staticmethod
    def validate_bot_specific_token(request: Request):
        bot = request.path_params.get("bot")
        token = request.path_params.get("token")
        claims = Utility.decode_limited_access_token(token)
        bot_config = AccountProcessor.get_bot(bot)
        multilingual_bots = list(AccountProcessor.get_multilingual_bots(bot))
        multilingual_bots = set(map(lambda bot_info: bot_info["id"], multilingual_bots))

        if bot_config['account'] != claims['account'] or bot not in multilingual_bots:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid token',
            )
        return claims

    @staticmethod
    def create_access_token(*, data: dict, token_type: TOKEN_TYPE = TOKEN_TYPE.LOGIN.value, token_expire: int = 0):
        access_token_expire_minutes = Utility.environment['security']["token_expire"]
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]
        to_encode = data.copy()

        if token_type == TOKEN_TYPE.LOGIN.value or token_type not in [t_type.value for t_type in TOKEN_TYPE]:
            token_type = TOKEN_TYPE.LOGIN.value
            if token_expire > 0:
                expire = datetime.utcnow() + timedelta(minutes=token_expire)
            else:
                if access_token_expire_minutes:
                    expires_delta = timedelta(minutes=access_token_expire_minutes)
                else:
                    expires_delta = timedelta(minutes=15)
                expire = datetime.utcnow() + expires_delta
            to_encode.update({"exp": expire})
            if to_encode.get("iat") is None:
                to_encode.update({"iat": datetime.utcnow()})
        to_encode.update({"type": token_type})
        to_encode = Authentication.encrypt_token_claims(to_encode)
        encoded_jwt = encode(to_encode, secret_key, algorithm=algorithm)
        return encoded_jwt

    @staticmethod
    def encrypt_token_claims(to_encode: dict):
        token_claims = to_encode.copy()
        for time_claim in ["exp", "iat", "nbf"]:
            # Convert datetime to a intDate value in known time-format claims
            if isinstance(token_claims.get(time_claim), datetime):
                token_claims[time_claim] = timegm(token_claims[time_claim].utctimetuple())

        claims_str = json.dumps(token_claims)
        encrypted_claims = Utility.encrypt_message(claims_str)
        encoded_jwt = {"sub": encrypted_claims, "version": "2.0"}
        [encoded_jwt.update({claim: to_encode[claim]}) for claim in ["exp", "iat"] if to_encode.get(claim)]
        return encoded_jwt

    @staticmethod
    def decrypt_token_claims(encypted_claims: str):
        claims_str = Utility.decrypt_message(encypted_claims)
        claims = json.loads(claims_str)
        return claims

    @staticmethod
    def __authenticate_user(username: str, password: str):
        UserActivityLogger.is_login_within_cooldown_period(username)
        user = AccountProcessor.get_user_details(username, is_login_request=True)
        if not user or not Utility.verify_password(password, user["password"]):
            data = {"username": username}
            message = ["Incorrect username or password"]
            UserActivityLogger.add_log(a_type=UserActivityType.invalid_login.value, account=user["account"], email=username.lower(), message=message, data=data)
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
        return Authentication.generate_login_tokens(user, True)

    @staticmethod
    def generate_login_tokens(user: dict, is_login: bool):
        username = user["email"]
        account = user["account"]
        access_token = Authentication.create_access_token(data={"sub": username, "account": account})
        claims = Utility.decode_limited_access_token(access_token)
        access_token_iat = datetime.fromtimestamp(claims['iat'])
        access_token_expiry = datetime.fromtimestamp(claims['exp'])
        refresh_token_expire_minutes = Utility.environment['security']["refresh_token_expire"]
        ttl = Utility.environment['security']["token_expire"]
        refresh_token = Authentication.__create_refresh_token(claims, access_token_iat, ttl, refresh_token_expire_minutes)
        refresh_token_expiry = access_token_iat + timedelta(minutes=refresh_token_expire_minutes)
        if is_login:
            metric_type = UserActivityType.login.value
        else:
            metric_type = UserActivityType.login_refresh_token.value
        UserActivityLogger.add_log(a_type=metric_type, account=user["account"], email=username, data={"username": username})
        return access_token, access_token_expiry.timestamp(), refresh_token, refresh_token_expiry.timestamp()

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
        token_configured = Utility.environment['tracker']['authentication']['token']
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
    def generate_integration_token(
            bot: Text, user: Text, role: ACCESS_ROLES = ACCESS_ROLES.CHAT.value, expiry: int = 0,
            access_limit: list = None, name: Text = None, token_type: TOKEN_TYPE = TOKEN_TYPE.INTEGRATION.value
    ):
        """ Generates an access token for secure integration of the bot
            with an external service/architecture """
        from kairon.shared.data.processor import MongoProcessor

        bot_settings = MongoProcessor.get_bot_settings(bot, user)
        if token_type == TOKEN_TYPE.LOGIN.value:
            raise NotImplementedError
        iat: datetime = datetime.now(tz=timezone.utc)
        iat = iat.replace(microsecond=0)
        account = AccountProcessor.get_bot(bot)['account']
        data = {'bot': bot, "sub": user, 'iat': iat, 'type': token_type, 'role': role, 'account': account}
        if not Utility.check_empty_string(name):
            data.update({"name": name})
        if access_limit:
            data['access-limit'] = access_limit
        if expiry > 0:
            ttl = expiry
            expiry = iat + timedelta(minutes=expiry)
            expiry = expiry.replace(microsecond=0)
            data.update({"exp": expiry})
            exp = bot_settings.refresh_token_expiry
            refresh_token = Authentication.__create_refresh_token(data, iat, ttl, exp)
        else:
            expiry = None
            refresh_token = None

        access_token = Authentication.create_access_token(data=data, token_type=token_type)
        if token_type == TOKEN_TYPE.INTEGRATION.value:
            IntegrationProcessor.add_integration(name, bot, user, role, iat, expiry, access_limit)
        return access_token, refresh_token

    @staticmethod
    def __create_refresh_token(claims: dict, parent_token_iat: datetime, ttl: int, expiry: int):
        token_claims = claims.copy()
        token_claims["primary-token-type"] = claims['type']
        if claims["type"] != TOKEN_TYPE.LOGIN.value:
            token_claims["primary-token-role"] = claims['role']
            token_claims["primary-token-access-limit"] = claims.get('access-limit')
            token_claims["access-limit"] = ['/api/auth/.+/token/refresh']
        else:
            token_claims["access-limit"] = ['/api/auth/token/refresh']
        token_claims["role"] = ACCESS_ROLES.TESTER.value
        token_claims["type"] = TOKEN_TYPE.REFRESH.value
        token_claims["ttl"] = ttl
        token_claims["exp"] = parent_token_iat + timedelta(minutes=expiry)
        refresh_token = Authentication.create_access_token(data=token_claims, token_type=TOKEN_TYPE.REFRESH.value)
        return refresh_token

    @staticmethod
    def generate_token_from_refresh_token(refresh_token: Text):
        claims = Utility.decode_limited_access_token(refresh_token)
        if claims["type"] != TOKEN_TYPE.REFRESH.value:
            raise HTTPException(
                status_code=422,
                detail=f"Only refresh tokens can be used to generate new token!",
            )
        if claims["primary-token-type"] in {TOKEN_TYPE.LOGIN.value, TOKEN_TYPE.INTEGRATION.value, TOKEN_TYPE.CHANNEL.value, TOKEN_TYPE.REFRESH.value}:
            raise HTTPException(
                status_code=422,
                detail=f"Refresh only allowed for {TOKEN_TYPE.DYNAMIC.value} tokens!",
            )

        access_token, new_refresh_token = Authentication.generate_integration_token(
            claims["bot"], claims["sub"], role=claims["primary-token-role"], expiry=claims["ttl"],
            access_limit=claims["primary-token-access-limit"],
            token_type=claims["primary-token-type"],
            name='from refresh token'
        )
        return access_token, new_refresh_token

    @staticmethod
    def generate_login_token_from_refresh_token(refresh_token: Text, user: dict):
        claims = Utility.decode_limited_access_token(refresh_token)
        if claims["type"] != TOKEN_TYPE.REFRESH.value:
            raise HTTPException(
                status_code=422,
                detail=f"Only refresh tokens can be used to generate new token!",
            )
        if claims["primary-token-type"] != TOKEN_TYPE.LOGIN.value:
            raise HTTPException(
                status_code=422,
                detail=f"Refresh only allowed for {TOKEN_TYPE.LOGIN.value} tokens!",
            )
        tokens_and_expiry = Authentication.generate_login_tokens(user, False)
        return tokens_and_expiry

    @staticmethod
    def update_integration_token(
            name: Text, bot: Text, user: Text, int_status: INTEGRATION_STATUS = INTEGRATION_STATUS.ACTIVE.value
    ):
        """
        Generates a new access token for an existing integration.
        """
        IntegrationProcessor.update_integration(name, bot, user, int_status)

    @staticmethod
    def validate_integration_token(payload: dict):
        """
        Validates whether integration token with this payload is active.

        :param payload: Auth token claims dict.
        """
        exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Access to bot is denied',
        )
        name = payload.get('name')
        bot = payload.get('bot')
        user = payload.get('sub')
        iat = payload.get('iat')
        role = payload.get('role')
        try:
            IntegrationProcessor.verify_integration_token(name, bot, user, iat, role)
        except Exception as e:
            logger.exception(str(e))
            raise exception

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
            await AccountProcessor.account_setup(user_details)
            tmp_token = Utility.generate_token(user_details['email'])
            await AccountProcessor.confirm_email(tmp_token)
        access_token = Authentication.create_access_token(data={"sub": user_details["email"]})
        return existing_user, user_details, access_token

    @staticmethod
    def validate_bot_request(bot_in_request_path: str, bot_in_token: str):
        """
        Validates the bot which is being accessed is the same bot for which the integration was generated.

        :param bot_in_request_path: bot for which the request was made.
        :param bot_in_token: bot which is present in auth token claims.
        """
        if not Utility.check_empty_string(bot_in_request_path) and bot_in_request_path != bot_in_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Access to bot is denied',
            )

    @staticmethod
    async def validate_trusted_device(user: Text, fingerprint: Text, request: Request):
        ip = Utility.get_client_ip(request)
        geo_location = PluginFactory.get_instance(PluginTypes.ip_info.value).execute(ip=ip)
        geo_location = geo_location or {}
        await Authentication.__validate_trusted_device(user, fingerprint, **geo_location)

    @staticmethod
    async def __validate_trusted_device(
            user: Text, fingerprint: Text, **geo_location
    ):
        if Utility.environment['user']['validate_trusted_device']:
            trusted_fingerprints = AccountProcessor.list_trusted_device_fingerprints(user)
            if fingerprint not in trusted_fingerprints and Utility.email_conf["email"]["enable"]:
                trust_device_url = AccountProcessor.add_trusted_device(user, fingerprint, True, **geo_location)
                await MailUtility.format_and_send_mail(
                    mail_type='untrusted_login', email=user, first_name=user, url=trust_device_url, **geo_location
                )
