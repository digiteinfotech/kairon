from enum import Enum


TRAINING_DATA_GENERATOR_DIR = 'data_generator'


class RESPONSE(str, Enum):
    Text = "text"
    CUSTOM = "custom"
    IMAGE = "image"
    CHANNEL = "channel"
    BUTTONS = "buttons"


class DOMAIN(str, Enum):
    INTENTS = "intents"
    USE_ENTITIES_KEY = "use_entities"
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


class EVENT_STATUS(str, Enum):
    INITIATED = "Initiated"
    TASKSPAWNED = "Task Spawned"
    INPROGRESS = "In progress"
    PARSE = "Parsing data"
    VALIDATING = "Validation in progress"
    SAVE = "Importing data to kairon"
    SKIP_IMPORT = "Skipping importing data to kairon"
    TRIGGER_TRAINING = "Triggering model training"
    COMPLETED = "Completed"
    FAIL = "Fail"


ALLOWED_NLU_FORMATS = {'nlu.yml', 'nlu.md', 'nlu.yaml'}
ALLOWED_STORIES_FORMATS = {'stories.yml', 'stories.md', 'stories.yaml'}
ALLOWED_DOMAIN_FORMATS = {'domain.yml', 'domain.yaml'}
ALLOWED_CONFIG_FORMATS = {'config.yaml', 'config.yml'}
ALLOWED_RULES_FORMATS = {'rules.yaml', 'rules.yml'}
ALLOWED_HTTP_ACTIONS_FORMATS = {'http_action.yaml', 'http_action.yml'}
REQUIREMENTS = {'nlu', 'domain', 'config', 'stories', 'rules', 'http_actions'}
COMPONENT_COUNT = {'intents': 0, 'utterances': 0, 'stories': 0, 'training_examples': 0,
                   'http_actions': 0, 'rules': 0,
                   'domain': {'intents': 0, 'actions': 0, 'slots': 0, 'utterances': 0, 'forms': 0, 'entities': 0}}

DEFAULT_NLU_FALLBACK_RULE = 'Ask the user to rephrase whenever they send a message with low NLU confidence'
DEFAULT_NLU_FALLBACK_RESPONSE = "I'm sorry, I didn't quite understand that. Could you rephrase?"
DEFAULT_ACTION_FALLBACK_RESPONSE = "Sorry I didn't get that. Can you rephrase?"
