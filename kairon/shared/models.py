from enum import Enum


class StoryStepType(str, Enum):
    intent = "INTENT"
    bot = "BOT"
    http_action = "HTTP_ACTION"
    action = "ACTION"


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