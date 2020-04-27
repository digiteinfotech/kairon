from pydantic import BaseModel, validator, ValidationError
from typing import List, Any
from enum import Enum
from bot_trainer.utils import Utility


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str


class User(BaseModel):
    email: str
    first_name: str
    last_name: str
    bot: str
    account: int
    status: bool
    alias_user: str = None
    is_integration_user: bool

    def get_bot(self):
        return str(self.account) + "_" + self.bot

    def get_user(self):
        if self.is_integration_user:
            return self.alias_user
        return self.email


class Response(BaseModel):
    success: bool = True
    message: str = None
    data: Any
    error_code: int = 0


class RequestData(BaseModel):
    data: Any


class TextData(BaseModel):
    data: str


class ListData(BaseModel):
    data: List[str]


class StoryEventType(str, Enum):
    user = "user"
    action = "action"
    form = "form"
    slot = "slot"


class StoryEventRequest(BaseModel):
    name: str
    type: StoryEventType
    value: str = None


class StoryRequest(BaseModel):
    name: str
    events: List[StoryEventRequest]

    def get_events(self):
        return [event.dict() for event in self.events]
