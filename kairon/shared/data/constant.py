from enum import Enum
from rasa.shared.core.slots import (
    CategoricalSlot,
    FloatSlot,
    UnfeaturizedSlot,
    ListSlot,
    TextSlot,
    BooleanSlot, AnySlot,
)


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


class ENDPOINT_TYPE(str, Enum):
    BOT_ENDPOINT = "bot_endpoint"
    ACTION_ENDPOINT = "action_endpoint"
    HISTORY_ENDPOINT = "history_endpoint"


class SLOT_TYPE(str, Enum):
    FLOAT = FloatSlot.type_name,
    CATEGORICAL = CategoricalSlot.type_name,
    UNFEATURIZED = UnfeaturizedSlot.type_name,
    LIST = ListSlot.type_name,
    TEXT = TextSlot.type_name,
    BOOLEAN = BooleanSlot.type_name,
    ANY = AnySlot.type_name


class SLOT_MAPPING_TYPE(str, Enum):
    FROM_ENTITY = "from_entity"
    FROM_INTENT = "from_intent"
    FROM_TRIGGER_INTENT = "from_trigger_intent"
    FROM_TEXT = "from_text"


class ACCESS_ROLES(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    DESIGNER = "designer"
    TESTER = "tester"
    CHAT = "chat"


class ACTIVITY_STATUS(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    INVITE_NOT_ACCEPTED = "invite_not_accepted"
    DELETED = "deleted"


class INTEGRATION_STATUS(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"


class TOKEN_TYPE(str, Enum):
    INTEGRATION = "integration"
    LOGIN = "login"
    DYNAMIC = "dynamic"
    CHANNEL = "channel"


class ModelTestType(str, Enum):
    stories = "stories"
    nlu = "nlu"
    common = "common"


ALLOWED_NLU_FORMATS = {'nlu.yml', 'nlu.md', 'nlu.yaml'}
ALLOWED_STORIES_FORMATS = {'stories.yml', 'stories.md', 'stories.yaml'}
ALLOWED_DOMAIN_FORMATS = {'domain.yml', 'domain.yaml'}
ALLOWED_CONFIG_FORMATS = {'config.yaml', 'config.yml'}
ALLOWED_RULES_FORMATS = {'rules.yaml', 'rules.yml'}
ALLOWED_ACTIONS_FORMATS = {'actions.yaml', 'actions.yml'}
REQUIREMENTS = {'nlu', 'domain', 'config', 'stories', 'rules', 'actions'}
COMPONENT_COUNT = {'intents': 0, 'utterances': 0, 'stories': 0, 'training_examples': 0,
                   'http_actions': 0, 'jira_actions': 0, 'google_search_actions': 0, 'zendesk_actions': 0,
                   'email_actions': 0, 'slot_set_actions': 0, 'form_validation_actions': 0, 'rules': 0,
                   'domain': {'intents': 0, 'actions': 0, 'slots': 0, 'utterances': 0, 'forms': 0, 'entities': 0}}

DEFAULT_NLU_FALLBACK_RULE = 'Ask the user to rephrase whenever they send a message with low NLU confidence'
DEFAULT_NLU_FALLBACK_RESPONSE = "I'm sorry, I didn't quite understand that. Could you rephrase?"
DEFAULT_ACTION_FALLBACK_RESPONSE = "Sorry I didn't get that. Can you rephrase?"
