import os

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from smart_config import ConfigLoader
from starlette.requests import Request
from starlette.status import HTTP_401_UNAUTHORIZED


class HistoryUtils:
    environment = {}

    @staticmethod
    def load_evironment():
        """
        Loads the environment variables and their values from the
        tracker.yaml file for defining the working environment of the app

        :return: None
        """
        HistoryUtils.environment = ConfigLoader(os.getenv("system_file", "./kairon/history/tracker.yaml")).get_config()

    @staticmethod
    def is_empty_string(value: str):
        """
        checks for empty string

        :param value: string value
        :return: boolean
        """
        if not value:
            return True
        if not value.strip():
            return True
        else:
            return False


class Authentication:

    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

    @staticmethod
    async def authenticate_and_get_collection(request: Request, token: str = Depends(oauth2_scheme)):
        token_configured = HistoryUtils.environment['authentication']['token']
        if token_configured != token:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if 'bot' == HistoryUtils.environment['tracker']['type']:
            bot_id = request.path_params.get('bot')
            if HistoryUtils.is_empty_string(bot_id):
                raise HTTPException(
                    status_code=HTTP_401_UNAUTHORIZED,
                    detail="Bot id is required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return bot_id
        else:
            collection = HistoryUtils.environment['tracker']['collection']
            if HistoryUtils.is_empty_string(collection):
                raise HTTPException(
                    status_code=HTTP_401_UNAUTHORIZED,
                    detail="Collection not configured",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return collection
