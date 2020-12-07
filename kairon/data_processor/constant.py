from enum import Enum


class RESPONSE(str, Enum):
    Text = "text"
    CUSTOM = "custom"
    IMAGE = "image"
    CHANNEL = "channel"
    BUTTONS = "buttons"


class DOMAIN(str, Enum):
    INTENTS = "intents"
    ACTIONS = "actions"
    SLOTS = "slots"
    SESSION_CONFIG = "session_config"
    RESPONSES = "responses"
    FORMS = "forms"
    ENTITIES = "entities"


class ENTITY(str, Enum):
    START = "start"
    END = "end"
    VALUE = "value"
    ENTITY = "entity"


class TRAINING_EXAMPLE(str, Enum):
    INTENT = "intent"
    ENTITIES = "entities"


class LOOKUP_TABLE(str, Enum):
    NAME = "name"
    ELEMENTS = "elements"


class REGEX_FEATURES(str, Enum):
    NAME = "name"
    PATTERN = "pattern"


class SESSION_CONFIG(str, Enum):
    SESSION_EXPIRATION_TIME = "session_expiration_time"
    CARRY_OVER_SLOTS = "carry_over_slots"


class SLOTS(str, Enum):
    INITIAL_VALUE = "initial_value"
    VALUE_RESET_DELAY = "value_reset_delay"
    AUTO_FILL = "auto_fill"
    MIN_VALUE = "min_value"
    MAX_VALUE = "max_value"
    VALUES = "values"
    TYPE = "type"


class STORY_EVENT(str, Enum):
    NAME = "name"
    CONFIDENCE = "confidence"


class MODEL_TRAINING_STATUS(str, Enum):
    INPROGRESS = "Inprogress"
    DONE = "Done"
    FAIL = "Fail"


class UTTERANCE_TYPE(str, Enum):
    BOT = "bot"
    HTTP = "http"


class CUSTOM_ACTIONS(str, Enum):
    HTTP_ACTION_NAME = "kairon_http_action"
    HTTP_ACTION_CONFIG = "http_action_config"


class TRAINING_DATA_GENERATOR_STATUS(str, Enum):
    INITIATED = "Initiated"
    TASKSPAWNED = "Task Spawned"
    INPROGRESS = "In progress"
    PARSE = "Task Spawned"
    COMPLETED = "Completed"
    FAIL = "Fail"