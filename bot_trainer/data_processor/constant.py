from enum import Enum


class RESPONSE(Enum):
    Text = "text"
    CUSTOM = "custom"
    IMAGE = "image"
    CHANNEL = "channel"
    BUTTONS = "buttons"


class DOMAIN(Enum):
    INTENTS = 'intents'
    ACTIONS = 'actions'
    SLOTS = 'slots'
    SESSION_CONFIG = 'session_config'
    RESPONSES = 'responses'
    FORMS = 'forms'
    ENTITIES = 'entities'


class ENTITY(Enum):
    START = "start"
    END = "end"
    VALUE = "value"
    ENTITY = "entity"


class TRAINING_EXAMPLE(Enum):
    INTENT = "intent"
    ENTITIES = "entities"


class LOOKUP_TABLE(Enum):
    NAME = "name"
    ELEMENTS = "elements"


class REGEX_FEATURES(Enum):
    NAME = "name"
    PATTERN = "pattern"


class SESSION_CONFIG(Enum):
    SESSION_EXPIRATION_TIME = "session_expiration_time"
    CARRY_OVER_SLOTS = "carry_over_slots"


class SLOTS(Enum):
    INITIAL_VALUE = "initial_value"
    VALUE_RESET_DELAY = "value_reset_delay"
    AUTO_FILL = "auto_fill"
    MIN_VALUE = "min_value"
    MAX_VALUE = "max_value"
    VALUES = "values"
    TYPE = "type"


class STORY_EVENT(Enum):
    NAME = "name"
    CONFIDENCE = "confidence"
