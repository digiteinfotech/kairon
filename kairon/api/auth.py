from datetime import datetime, timedelta
from typing import Text

from fastapi import Depends, HTTPException, status, Request
from jwt import PyJWTError, decode, encode

from kairon.utils import Utility
from .processor import IntegrationsProcessor
from .models import User
from .processor import AccountProcessor
from kairon.data_processor.constant import TOKEN_TYPE

Utility.load_evironment()


class Authentication:
    """
    Class contains logic for api Authentication
    """

    SECRET_KEY = Utility.environment['security']["secret_key"]
    ALGORITHM = Utility.environment['security']["algorithm"]
    ACCESS_TOKEN_EXPIRE_MINUTES = Utility.environment['security']["token_expire"]

    async def get_current_user(
        self, request: Request, token: str = Depends(Utility.oauth2_scheme)
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
            payload = decode(token, self.SECRET_KEY, algorithms=[self.ALGORITHM])
            username: str = payload.get("sub")
            token_type: str = payload.get("token_type")
            issued_at: int = payload.get("iat")
            if not username or not token_type:
                raise credentials_exception
        except PyJWTError:
            raise credentials_exception
        user = AccountProcessor.get_user_details(username)
        if user is None:
            raise credentials_exception

        user_model = User(**user)
        if token_type == TOKEN_TYPE.INTEGRATION.value:
            alias_user = request.headers.get("X-USER")
            bot_id = request.path_params.get('bot')
            Authentication.validate_integration_claims(username, issued_at, alias_user, bot_id)
            user_model.alias_user = alias_user
            user_model.is_integration_user = True
        return user_model

    async def get_current_user_and_bot(self, request: Request, token: str = Depends(Utility.oauth2_scheme)):
        user = await self.get_current_user(request, token)
        bot_id = request.path_params.get('bot')
        if Utility.check_empty_string(bot_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='Bot is required',
            )
        if bot_id not in user.bot:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='Access denied for bot',
            )
        bot = AccountProcessor.get_bot(bot_id)
        if not bot["status"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Inactive Bot Please contact system admin!",
            )
        user.bot = bot_id
        return user

    @staticmethod
    def create_access_token(*, data: dict, is_integration=False, token_expire: int = 0):
        to_encode = data.copy()
        issued_at = datetime.utcnow()
        if not is_integration:
            if token_expire > 0:
                expire = issued_at + timedelta(minutes=token_expire)
            else:
                if Authentication.ACCESS_TOKEN_EXPIRE_MINUTES:
                    expires_delta = timedelta(minutes=Authentication.ACCESS_TOKEN_EXPIRE_MINUTES)
                else:
                    expires_delta = timedelta(minutes=15)
                expire = issued_at + expires_delta
            to_encode.update({"exp": expire, "token_type": TOKEN_TYPE.LOGIN.value})
        else:
            to_encode.update({"iat": datetime.timestamp(issued_at),
                              "token_type": TOKEN_TYPE.INTEGRATION.value})
        encoded_jwt = encode(to_encode, Authentication.SECRET_KEY, algorithm=Authentication.ALGORITHM)
        return encoded_jwt, issued_at

    def __authenticate_user(self, username: str, password: str):
        user = AccountProcessor.get_user_details(username)
        if not user:
            return False
        if not Utility.verify_password(password, user["password"]):
            return False
        return user

    def authenticate(self, username: Text, password: Text):
        """
        authenticate user and generate jwt token

        :param username: login id ie. email address
        :param password: login password
        :return: jwt token
        """
        user = self.__authenticate_user(username, password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token, issued_at = Authentication.create_access_token(data={"sub": user["email"]})
        return access_token

    @staticmethod
    def generate_integration_token(name: Text, bot: Text, user: Text):
        """ Generates an access token for secure integration of the bot
            with an external service/architecture """
        access_token, issued_at = Authentication.create_access_token(
            data={"sub": user}, is_integration=True
        )
        IntegrationsProcessor.add_integration(name, issued_at, bot, user)
        return access_token

    @staticmethod
    def validate_integration_claims(username: Text, issued_at: int, alias_user: Text, bot: Text = None):
        if Utility.check_empty_string(alias_user):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Alias user missing for integration",
                headers={"WWW-Authenticate": "Bearer"},
            )
        is_valid_token = IntegrationsProcessor.is_valid_token(username, datetime.fromtimestamp(issued_at), bot=bot)
        if not is_valid_token:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

