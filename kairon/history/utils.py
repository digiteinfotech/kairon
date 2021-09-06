import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from smart_config import ConfigLoader
from starlette.requests import Request
from starlette.status import HTTP_401_UNAUTHORIZED


class HistoryUtils:
    environment = {}

    @staticmethod
    def load_environment():

        """
        Load environment variables.

        Loads the environment variables and their values from the
        tracker.yaml file for defining the working environment of the app

        :return: None
        """
        HistoryUtils.environment = ConfigLoader(os.getenv("system_file", "./kairon/history/tracker.yaml")).get_config()

    @staticmethod
    def is_empty_string(value: str):

        """
        Checks for empty string.

        :param value: string value
        :return: boolean
        """
        if not value:
            return True
        if not value.strip():
            return True
        else:
            return False

    @staticmethod
    def get_timestamp_previous_month(month: int):
        start_time = datetime.now() - timedelta(month * 30, seconds=0, minutes=0, hours=0)
        return start_time.timestamp()

    @staticmethod
    def load_default_actions():
        from kairon.importer.validator.file_validator import DEFAULT_ACTIONS

        return list(DEFAULT_ACTIONS - {"action_default_fallback", "action_two_stage_fallback"})


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
                    status_code=422,
                    detail="Bot id is required",
                )
            return bot_id
        else:
            collection = HistoryUtils.environment['tracker']['collection']
            if HistoryUtils.is_empty_string(collection):
                raise HTTPException(
                    status_code=422,
                    detail="Collection not configured",
                )
            return collection
