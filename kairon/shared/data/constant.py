import re
from enum import Enum

from rasa.shared.core.slots import (
    CategoricalSlot,
    FloatSlot,
    ListSlot,
    TextSlot,
    BooleanSlot,
    AnySlot,
)

TRAINING_DATA_GENERATOR_DIR = "data_generator"


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
    MIN_VALUE = "min_value"
    MAX_VALUE = "max_value"
    VALUES = "values"
    TYPE = "type"


class STORY_EVENT(str, Enum):
    NAME = "name"
    CONFIDENCE = "confidence"


class UTTERANCE_TYPE(str, Enum):
    BOT = "bot"
    HTTP = "http"


class CUSTOM_ACTIONS(str, Enum):
    HTTP_ACTION_NAME = "kairon_http_action"
    HTTP_ACTION_CONFIG = "http_action_config"


class DEMO_REQUEST_STATUS(str, Enum):
    REQUEST_RECEIVED = "request_received"
    MAIL_SENT = "mail_sent"
    DEMO_PLANNED = "demo_planned"
    DEMO_GIVEN = "demo_given"


class EVENT_STATUS(str, Enum):
    ENQUEUED = "Enqueued"
    INITIATED = "Initiated"
    TASKSPAWNED = "Task Spawned"
    INPROGRESS = "In progress"
    PARSE = "Parsing data"
    VALIDATING = "Validation in progress"
    SAVE = "Importing data to kairon"
    SKIP_IMPORT = "Skipping importing data to kairon"
    TRIGGER_TRAINING = "Triggering model training"
    EVALUATE_RECIPIENTS = "Recipients evaluated"
    TRIGGERED_API = "Triggered API, waiting for response"
    EVALUATE_TEMPLATE = "Templates evaluated"
    BROADCAST_STARTED = "Initiated broadcast to recipients"
    DATA_EXTRACTED = "Broadcast data extracted"
    COMPLETED = "Completed"
    DONE = "Done"
    FAIL = "Fail"
    ABORTED = "Aborted"


class ONBOARDING_STATUS(str, Enum):
    NOT_COMPLETED = "Not Completed"
    SKIPPED = "Skipped"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"


class TASK_TYPE(str, Enum):
    ACTION = "Action"
    EVENT = "Event"
    CALLBACK = "Callback"


class ModelTestingLogType(str, Enum):
    stories = "stories"
    nlu = "nlu"
    entity_evaluation_with_diet_classifier = "entity_evaluation_with_diet_classifier"
    entity_evaluation_with_regex_entity_extractor = (
        "entity_evaluation_with_regex_entity_extractor"
    )
    response_selection_evaluation = "response_selection_evaluation"


class ENDPOINT_TYPE(str, Enum):
    BOT_ENDPOINT = "bot_endpoint"
    ACTION_ENDPOINT = "action_endpoint"
    HISTORY_ENDPOINT = "history_endpoint"


class SLOT_TYPE(str, Enum):
    FLOAT = FloatSlot.type_name
    CATEGORICAL = CategoricalSlot.type_name
    LIST = ListSlot.type_name
    TEXT = TextSlot.type_name
    BOOLEAN = BooleanSlot.type_name
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
    VIEW = "view"
    AGENT = "agent"


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
    REFRESH = "refresh"


class ModelTestType(str, Enum):
    stories = "stories"
    nlu = "nlu"
    common = "common"


ALLOWED_NLU_FORMATS = {'nlu.yml', 'nlu.yaml'}
ALLOWED_STORIES_FORMATS = {'stories.yml', 'stories.yaml'}
ALLOWED_DOMAIN_FORMATS = {'domain.yml', 'domain.yaml'}
ALLOWED_CONFIG_FORMATS = {'config.yaml', 'config.yml'}
ALLOWED_RULES_FORMATS = {'rules.yaml', 'rules.yml'}
ALLOWED_ACTIONS_FORMATS = {'actions.yaml', 'actions.yml'}
ALLOWED_CHAT_CLIENT_CONFIG_FORMATS = {'chat_client_config.yml', 'chat_client_config.yaml'}
ALLOWED_MULTIFLOW_STORIES_FORMATS = {'multiflow_stories.yaml', 'multiflow_stories.yml'}
ALLOWED_BOT_CONTENT_FORMATS = {'bot_content.yaml', 'bot_content.yml'}
REQUIREMENTS = {'nlu', 'domain', 'config', 'stories', 'rules', 'actions', 'chat_client_config', 'multiflow_stories',
                'bot_content'}
COMPONENT_COUNT = {'intents': 0, 'utterances': 0, 'stories': 0, 'training_examples': 0,
                   'http_actions': 0, 'jira_actions': 0, 'google_search_actions': 0, 'zendesk_actions': 0,
                   'email_actions': 0, 'slot_set_actions': 0, 'form_validation_actions': 0, 'rules': 0,
                   'domain': {'intents': 0, 'actions': 0, 'slots': 0, 'utterances': 0, 'forms': 0, 'entities': 0}}

DEFAULT_NLU_FALLBACK_RULE = (
    "Ask the user to rephrase whenever they send a message with low NLU confidence"
)
DEFAULT_NLU_FALLBACK_RESPONSE = (
    "I'm sorry, I didn't quite understand that. Could you rephrase?"
)
DEFAULT_NLU_FALLBACK_UTTERANCE_NAME = "utter_default"
DEFAULT_ACTION_FALLBACK_RESPONSE = "Sorry I didn't get that. Can you rephrase?"
REQUEST_TIMESTAMP_HEADER = "X-TimeStamp"
KAIRON_TWO_STAGE_FALLBACK = "kairon_two_stage_fallback"
GPT_LLM_FAQ = "gpt_llm_faq"
DEFAULT_LLM_FALLBACK_RULE = "search answer in faq"
FALLBACK_MESSAGE = (
    "I could not understand you! Did you mean any of the suggestions below?"
    " Or else please rephrase your question."
)
DEFAULT_CONTEXT_PROMPT = "Answer question based on the context below, if answer is not in the context go check previous logs."
DEFAULT_SYSTEM_PROMPT = (
    "You are a personal assistant. Answer question based on the context below"
)
DEFAULT_LLM = "openai"

QDRANT_SUFFIX = "_faq_embd"


class AuditlogActions(str, Enum):
    SAVE = "save"
    UPDATE = "update"
    DELETE = "delete"
    SOFT_DELETE = "soft_delete"
    BULK_DELETE = "bulk_delete"
    BULK_INSERT = "bulk_insert"
    BULK_UPDATE = "bulk_update"
    ACTIVITY = "activity"
    DOWNLOAD = "download"


class LogType(str, Enum):
    multilingual = "multilingual"
    model_training = "model_training"
    model_testing = "model_testing"
    audit_logs = "audit_logs"
    history_deletion = "history_deletion"
    action_logs = "action_logs"
    training_data_generator = "training_data_generator"
    data_importer = "data_importer"


class FeatureMappings(str, Enum):
    ONLY_SSO_LOGIN = "only_sso_login"
    CREATE_USER = "create_user"


ORG_SETTINGS_MESSAGES = {
    "create_user": "User creation is blocked by your OrgAdmin from SSO",
    "only_sso_login": "Login with your org SSO url, Login with username/password not allowed",
}

RE_ALPHA_NUM = re.compile(r"^[a-zA-Z0-9]+$").search
RE_VALID_NAME= re.compile(r"^[a-zA-Z0-9 -_]+$").search