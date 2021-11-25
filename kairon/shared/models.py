from enum import Enum

from pydantic import BaseModel


class StoryStepType(str, Enum):
    intent = "INTENT"
    bot = "BOT"
    http_action = "HTTP_ACTION"
    action = "ACTION"
    slot_set_action = "SLOT_SET_ACTION"


class StoryType(str, Enum):
    story = "STORY"
    rule = "RULE"


class TemplateType(str, Enum):
    QNA = "Q&A"
    CUSTOM = "CUSTOM"


class StoryEventType(str, Enum):
    user = "user"
    action = "action"
    form = "form"
    slot = "slot"


class History_Month_Enum(int, Enum):
    One = 1
    Two = 2
    Three = 3
    Four = 4
    Five = 5
    Six = 6


class ParameterChoice(str, Enum):
    value = "value"
    slot = "slot"
    sender_id = "sender_id"
    user_message = "user_message"


class User(BaseModel):
    email: str
    first_name: str
    last_name: str
    bot: list
    active_bot: str = None
    account: int
    status: bool
    alias_user: str = None
    is_integration_user: bool

    def get_bot(self):
        return self.active_bot

    def get_user(self):
        if self.is_integration_user:
            return self.alias_user
        return self.email

    def get_integration_status(self):
        if self.is_integration_user:
            return True
        return False
