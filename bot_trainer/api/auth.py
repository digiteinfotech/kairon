from datetime import datetime, timedelta
from typing import Text

import jwt
from fastapi import Depends, HTTPException, status
from jwt import PyJWTError

from bot_trainer.utils import Utility
from .models import *
from .processor import AccountProcessor

Utility.load_evironment()


class Authentication:
    SECRET_KEY = Utility.environment["SECRET_KEY"]
    ALGORITHM = Utility.environment["ALGORITHM"]
    ACCESS_TOKEN_EXPIRE_MINUTES = Utility.environment["ACCESS_TOKEN_EXPIRE_MINUTES"]

    async def get_current_user(self, token: str = Depends(Utility.oauth2_scheme)):
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, self.SECRET_KEY, algorithms=[self.ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise credentials_exception
            token_data = TokenData(username=username)
        except PyJWTError:
            raise credentials_exception
        user = AccountProcessor.get_user_details(token_data.username)
        if user is None:
            raise credentials_exception
        return User(**user)

    def __create_access_token(self, *, data: dict, expires_delta: timedelta = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.SECRET_KEY, algorithm=self.ALGORITHM)
        return encoded_jwt

    def __authenticate_user(self, username: str, password: str):
        user = AccountProcessor.get_user_details(username)
        if not user:
            return False
        if not Utility.verify_password(password, user["password"]):
            return False
        return user

    def authenticate(self, username: Text, password: Text):
        user = self.__authenticate_user(username, password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token_expires = timedelta(minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = self.__create_access_token(
            data={"sub": user["email"]}, expires_delta=access_token_expires
        )
        return access_token
