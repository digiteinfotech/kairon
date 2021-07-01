from datetime import datetime, timedelta
from typing import Text

from fastapi import Depends, HTTPException, status, Request
from jwt import PyJWTError, decode, encode

from kairon.utils import Utility
from .models import User, TokenData
from .processor import AccountProcessor

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
    def create_access_token( *, data: dict, is_integration=False, token_expire: int=0):
        to_encode = data.copy()
        if not is_integration:
            if token_expire > 0:
                expire = datetime.utcnow() + timedelta(minutes=token_expire)
            else:
                if Authentication.ACCESS_TOKEN_EXPIRE_MINUTES:
                    expires_delta = timedelta(minutes=Authentication.ACCESS_TOKEN_EXPIRE_MINUTES)
                else:
                    expires_delta = timedelta(minutes=15)
                expire = datetime.utcnow() + expires_delta
            to_encode.update({"exp": expire})
        encoded_jwt = encode(to_encode, Authentication.SECRET_KEY, algorithm=Authentication.ALGORITHM)
        return encoded_jwt

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
        access_token = Authentication.create_access_token(data={"sub": user["email"]})
        return access_token

    def generate_integration_token(self, bot: Text, account: int):
        """ Generates an access token for secure integration of the bot
            with an external service/architecture """
        integration_user = AccountProcessor.get_integration_user(bot, account)
        access_token = Authentication.create_access_token(
            data={"sub": integration_user["email"]}, is_integration=True
        )
        return access_token
