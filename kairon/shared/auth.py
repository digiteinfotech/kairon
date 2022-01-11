import json
import re
from urllib.parse import urljoin
from datetime import datetime, timedelta
from typing import Dict, Optional
from typing import Text

import httpx
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import SecurityScopes
from fastapi_sso.sso.base import OpenID, SSOBase
from fastapi_sso.sso.facebook import FacebookSSO
from fastapi_sso.sso.google import GoogleSSO
from jwt import PyJWTError, encode
from mongoengine import DoesNotExist
from pydantic import SecretStr
from starlette.status import HTTP_401_UNAUTHORIZED

from kairon.api.models import TokenData
from kairon.exceptions import AppException
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.constants import SSO_TYPES
from kairon.shared.data.utils import DataUtility
from kairon.shared.models import User
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


class LinkedinSSO(SSOBase):

    """
    Class providing login via linkedin OAuth
    """

    provider = "linkedin"
    discovery_url = "https://www.linkedin.com/oauth/v2"
    profile_url = "https://api.linkedin.com/v2"
    grant_type = "authorization_code"
    scope = 'r_liteprofile r_emailaddress'

    @property
    async def useremail_endpoint(self) -> Optional[str]:
        """
        Return `useremail_endpoint` from discovery document.
        """
        discovery = await self.get_discovery_document()
        return discovery.get("useremail_endpoint")

    @classmethod
    async def openid_from_response(cls, response: dict) -> OpenID:
        """
        Returns user details.
        """
        if response.get("emailAddress"):
            return OpenID(
                    email=response.get("emailAddress"),
                    provider=cls.provider,
                    id=response.get("id"),
                    first_name=response.get("localizedFirstName"),
                    last_name=response.get("localizedLastName"),
                    display_name=response.get("localizedFirstName"),
                    picture=response.get("profilePicture", {}).get("displayImage"),
                )

        raise AppException("User was not verified with linkedin")

    @classmethod
    async def get_discovery_document(cls) -> Dict[str, str]:
        """
        Get document containing handy urls.
        """
        return {
            "authorization_endpoint": f"{cls.discovery_url}/authorization",
            "token_endpoint": f"{cls.discovery_url}/accessToken",
            "userinfo_endpoint": f"{cls.profile_url}/me",
            "useremail_endpoint": f"{cls.profile_url}/emailAddress?q=members&projection=(elements*(handle~))"
        }

    async def process_login(self, code: str, request: Request) -> Optional[OpenID]:
        """
        This method should be called from callback endpoint to verify the user and request user info endpoint.
        This is low level, you should use {verify_and_process} instead.
        """
        url = request.url
        scheme = url.scheme
        if not self.allow_insecure_http and scheme != "https":
            current_url = str(url).replace("http://", "https://")
            scheme = "https"
        else:
            current_url = str(url)
        current_path = f"{scheme}://{url.netloc}{url.path}"

        token_url, headers, body = self.oauth_client.prepare_token_request(
            await self.token_endpoint, authorization_response=current_url, redirect_url=current_path, code=code
        )  # type: ignore

        if token_url is None:
            return {}

        auth = httpx.BasicAuth(self.client_id, self.client_secret)
        async with httpx.AsyncClient() as session:
            response = await session.post(token_url, headers=headers, content=body, auth=auth)
            content = response.json()
            self.oauth_client.parse_request_body_response(json.dumps(content))

            uri, headers, _ = self.oauth_client.add_token(await self.userinfo_endpoint)
            response = await session.get(uri, headers=headers)
            profile_details = response.json()

            uri, headers, _ = self.oauth_client.add_token(await self.useremail_endpoint)
            response = await session.get(uri, headers=headers)
            content = response.json()
            profile_details['emailAddress'] = content.get('elements', [{}])[0].get('handle~', {}).get('emailAddress')

        return await self.openid_from_response(profile_details)


class LoginSSOFactory:

    """
    Factory to get redirect url as well as the login token.
    """
    facebook_sso: FacebookSSO = NotImplemented
    linkedin_sso: LinkedinSSO = NotImplemented
    google_sso: GoogleSSO = NotImplemented

    @staticmethod
    def get_client(sso_type: str, raise_error_if_not_enabled=True):
        """
        Returns SSO client based on type.
        Raises exception if client requested is not enabled.

        :param sso_type: sso login type
        :param raise_error_if_not_enabled: raise exception is sso type is not enabled.
        """
        is_enabled = Utility.check_is_enabled(sso_type, raise_error_if_not_enabled)
        if sso_type == SSO_TYPES.FACEBOOK.value:
            if is_enabled and LoginSSOFactory.facebook_sso == NotImplemented:
                LoginSSOFactory.facebook_sso = FacebookSSO(
                    Utility.environment["sso"][SSO_TYPES.FACEBOOK.value]["client_id"],
                    Utility.environment["sso"][SSO_TYPES.FACEBOOK.value]["client_secret"],
                    urljoin(Utility.environment["sso"]["redirect_url"], SSO_TYPES.FACEBOOK.value),
                    allow_insecure_http=False, use_state=True
                )
            return LoginSSOFactory.facebook_sso
        if sso_type == SSO_TYPES.LINKEDIN.value:
            if is_enabled and LoginSSOFactory.linkedin_sso == NotImplemented:
                LoginSSOFactory.linkedin_sso = LinkedinSSO(
                    Utility.environment["sso"][SSO_TYPES.LINKEDIN.value]["client_id"],
                    Utility.environment["sso"][SSO_TYPES.LINKEDIN.value]["client_secret"],
                    urljoin(Utility.environment["sso"]["redirect_url"], SSO_TYPES.LINKEDIN.value),
                    allow_insecure_http=False, use_state=True
                )
            return LoginSSOFactory.linkedin_sso
        if sso_type == SSO_TYPES.GOOGLE.value:
            if is_enabled and LoginSSOFactory.google_sso == NotImplemented:
                LoginSSOFactory.google_sso = GoogleSSO(
                    Utility.environment["sso"][SSO_TYPES.GOOGLE.value]["client_id"],
                    Utility.environment["sso"][SSO_TYPES.GOOGLE.value]["client_secret"],
                    urljoin(Utility.environment["sso"]["redirect_url"], SSO_TYPES.GOOGLE.value),
                    allow_insecure_http=False, use_state=True
                )
            return LoginSSOFactory.google_sso

    @staticmethod
    async def get_redirect_url(sso_type: str):
        """
        Returns redirect url based on sso_type.

        :param sso_type: one of supported types - google/facebook/linkedin.
        """
        sso_client = LoginSSOFactory.get_client(sso_type)
        return await sso_client.get_login_redirect()

    @staticmethod
    async def verify(request, sso_type: str):
        """
        Fetches user details using code received in the request.

        :param request: starlette request object
        :param sso_type: one of supported types - google/facebook/linkedin.
        """
        try:
            sso_client = LoginSSOFactory.get_client(sso_type)
            user = await sso_client.verify_and_process(request)
            return vars(user)
        except Exception as e:
            raise AppException(f'Failed to verify with {sso_type}: {e}')

    @staticmethod
    async def verify_and_process(request, sso_type: str):
        """
        Fetches user details and returns a login token.
        If user does not have an account, it will be created.

        :param request: starlette request object
        :param sso_type: one of supported types - google/facebook/linkedin.
        """
        user_details = await LoginSSOFactory.verify(request, sso_type)
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
