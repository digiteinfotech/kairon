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

class SYNC_STATUS(str, Enum):
    INITIATED = "Initiated"
    VALIDATING_REQUEST = "Validating request"
    VALIDATING_REQUEST_SUCCESS = "Validating request successful"
    VALIDATING_FAILED = "Validation Failed"
    VALIDATING_KNOWLEDGE_VAULT_DATA = "Validating Knowledge vault processed data"
    PREPROCESSING = "Preprocessing in progress"
    PREPROCESSING_FAILED = "Preprocessing Failed"
    PREPROCESSING_COMPLETED = "Preprocessing Completed"
    SAVE = "Importing data to kairon"
    SAVE_META = "Importing data to Meta"
    SYNC_FAILED = "Sync Failed"
    ENQUEUED = "Enqueued"
    COMPLETED = "Completed"
    FAILED = "Failed"
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
    DATA_INTEGRATION = "data_integration"


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

class LogTypes(str, Enum):
    content = "content"
    importer = "importer"
    history_deletion = "history_deletion"
    multilingual = "multilingual"
    catalog = "catalog"
    custom_widget = "custom_widget"
    mail_channel = "mail_channel"
    callback = "callback"
    llm = "llm"
    actions = "actions"
    executor = "executor"
    agent_handoff = "agent_handoff"
    audit = "audit"
    model_test = "model_test"
    agentic_flow = "agentic_flow"

LOG_TYPE_METADATA = {
    LogTypes.actions: [
        {"id": "action", "header": "logsPage.actionName", "cellComponent": "ActionCell"},
        {"id": "type", "header": "logsPage.actionType", "cellComponent": "TypeCell"},
        {"id": "intent", "header": "common.intent", "cellComponent": "SimpleCell"},
        {"id": "user_msg", "header": "formLabels.userMessage", "cellComponent": "UserMessageCell"},
        {"id": "timestamp", "header": "logsPage.timestamp", "accessorFunction": "formatLocalTime", "cellComponent": "SimpleCell"},
        {"id": "status", "header": "logsPage.status", "cellComponent": "StatusCell"}
    ],

    LogTypes.importer: [
        {"id": "files_received", "header": "logsPage.filesUploaded", "cellComponent": "FilesUploadedCell"},
        {"id": "start_timestamp", "header": "common.startTimeHeader", "accessorFunction": "formatStartTime", "cellComponent": "StartTimestampCell"},
        {"id": "end_timestamp", "header": "common.endTimeHeader", "accessorFunction": "formatEndTimeOrInProgress", "cellComponent": "EndTimestampInProgressCell"},
        {"id": "event_status", "header": "logsPage.uploadStatus", "cellComponent": "SimpleCell"},
        {"id": "status", "header": "logsPage.fileProcessingStatus", "cellComponent": "StatusCell"}
    ],

    LogTypes.agent_handoff: [
        {"id": "agent_type", "header": "logsPage.agentType", "cellComponent": "ClickableNameCell"},
        {"id": "sender_id", "header": "logsPage.senderId", "cellComponent": "SimpleCell"},
        {"id": "timestamp", "header": "logsPage.timeStamp", "accessorFunction": "formatTimeOrInProgress", "cellComponent": "AuditLogsTimestampInProgressCell"}
    ],

    LogTypes.history_deletion: [
        {"header": "common.user", "id": "user", "cellComponent": "ClickableNameCell"},
        {"header": "logsPage.sender", "id": "sender_id", "cellComponent": "SimpleCell"},
        {"id": "till_date", "header": "logsPage.tillDate", "accessorFunction": "formatTillDate", "cellComponent": "FormattedTillDateCell"},
        {"id": "start_timestamp", "header": "logsPage.startTimeStamp", "accessorFunction": "formatStartTime", "cellComponent": "StartTimestampCell"},
        {"id": "end_timestamp", "header": "logsPage.endTimeStamp", "accessorFunction": "formatEndTimeOrInProgress", "cellComponent": "EndTimestampInProgressCell"},
        {"header": "logsPage.status", "id": "status", "cellComponent": "StatusCell"}
    ],

    LogTypes.model_test: [
        {"header": "common.startTimeHeader", "id": "start_timestamp", "accessorFunction": "formatStartTime", "cellComponent": "StartTimestampCell"},
        {"header": "common.endTimeHeader", "id": "end_timestamp", "accessorFunction": "formatEndTimeOrInProgress", "cellComponent": "EndTimestampInProgressCell"},
        {"header": "logsPage.dataAugmented", "id": "is_augmented", "accessorFunction": "getAugmentedStatus", "cellComponent": "SimpleCell"},
        {"header": "logsPage.totalTests", "id": "total_tests", "accessorFunction": "calculateTotalTests", "cellComponent": "SimpleCell"},
        {"header": "logsPage.failedTests", "id": "failed_tests", "accessorFunction": "calculateFailedTests", "cellComponent": "ModelTestingFailedTestCell"},
        {"header": "logsPage.eventStatus", "id": "event_status", "cellComponent": "SimpleCell"},
        {"header": "common.details", "id": "exception", "accessorFunction": "getDetailsFromEventStatus", "cellComponent": "ModelTestingDetailsCell"}
    ],

    LogTypes.multilingual: [
        {"header": "logsPage.copyType", "id": "copy_type", "cellComponent": "ClickableNameCell"},
        {"header": "common.startTimeHeader", "id": "start_timestamp", "accessorFunction": "formatStartTime", "cellComponent": "StartTimestampCell"},
        {"header": "common.endTimeHeader", "id": "end_timestamp", "accessorFunction": "formatEndTimeOrInProgress", "cellComponent": "EndTimestampInProgressCell"},
        {"header": "logsPage.translationStatus", "id": "event_status", "cellComponent": "SimpleCell"},
        {"header": "logsPage.status", "id": "status", "cellComponent": "MultilingualLogsStatusCell"}
    ],

    LogTypes.audit: [
        {"header": "common.user", "id": "user", "cellComponent": "SimpleCell"},
        {"header": "logsPage.entityType", "id": "entity", "cellComponent": "SimpleCell"},
        {"header": "logsPage.actionType", "id": "action", "cellComponent": "SimpleCell"},
        {"id": "timestamp", "header": "logsPage.timeStamp", "accessorFunction": "formatTimeOrInProgress", "cellComponent": "AuditLogsTimestampInProgressCell"},
        {"header": "common.details", "id": "data", "cellComponent": "DetailsCell"}
    ],

    LogTypes.custom_widget: [
        {"id": "name", "header": "formLabels.name", "cellComponent": "SimpleCell"},
        {"id": "request_method", "header": "logsPage.requestMethod", "cellComponent": "SimpleCell"},
        {"id": "http_url", "header": "common.url", "cellComponent": "SimpleCell"},
        {"id": "timestamp", "header": "logsPage.timeStamp", "accessorFunction": "formatTimeOrInProgress", "cellComponent": "TimestampCell"},
        {"id": "exception", "header": "logsPage.exception", "accessorFunction": "formatExceptionText", "cellComponent": "ExceptionCell"},
        {"id": "details", "header": "common.details", "cellComponent": "DetailsCell"}
    ],

    LogTypes.callback: [
        {"header": "logsPage.callbackName", "id": "callback_name", "cellComponent": "ClickableNameCell"},
        {"header": "logsPage.senderId", "id": "sender_id", "cellComponent": "SenderIdCell"},
        {"header": "logsPage.channel", "id": "channel", "cellComponent": "SimpleCell"},
        {"id": "timestamp", "header": "logsPage.timestamp", "accessorFunction": "formatLocalTimestamp", "cellComponent": "SimpleCell"},
        {"header": "logsPage.status", "id": "status", "cellComponent": "StatusCell"}
    ],

    LogTypes.llm: [
        {"id": "llm_call_id", "header": "logsPage.llmCallId", "cellComponent": "ClickableNameCell"},
        {"id": "user", "accessorFunction": "getUserFromMetadata", "header": "common.user", "cellComponent": "SimpleDashCell"},
        {"id": "model_params", "accessorFunction": "getModelFromModelParams", "header": "logsPage.llmModel", "cellComponent": "SimpleDashCell"},
        {"id": "cost", "header": "logsPage.cost", "cellComponent": "SimpleCell"},
        {"id": "invocation", "accessorFunction": "getInvocationFromMetadata", "header": "logsPage.invocation", "cellComponent": "SimpleCell"}
    ],

    LogTypes.content: [
        {"id": "file_received", "header": "logsPage.filesUploaded", "cellComponent": "ClickableNameCell"},
        {"id": "table", "header": "promptManagementPage.tableName", "cellComponent": "SimpleCell"},
        {"id": "start_timestamp", "accessorFunction": "formatStartTime", "header": "common.startTimeHeader", "cellComponent": "StartTimestampCell"},
        {"id": "end_timestamp", "accessorFunction": "formatEndTimeOrInProgress", "header": "common.endTimeHeader", "cellComponent": "EndTimestampInProgressCell"},
        {"id": "event_status", "header": "logsPage.uploadStatus", "cellComponent": "SimpleCell"},
        {"id": "status", "header": "logsPage.fileProcessingStatus", "cellComponent": "ContentUploadLogsStatusCell"}
    ],

    LogTypes.executor: [
        {"id": "executor_log_id", "header": "logsPage.executorId", "cellComponent": "ClickableNameCell"},
        {"id": "event_class", "header": "logsPage.eventClass", "cellComponent": "SimpleCell"},
        {"id": "task_type", "header": "logsPage.taskType", "cellComponent": "SimpleCell"},
        {"id": "timestamp", "accessorFunction": "formatLocalTimestamp", "header": "logsPage.timestamp", "cellComponent": "TimestampCell"},
        {"id": "status", "header": "logsPage.status", "cellComponent": "StatusCell"}
    ],

    LogTypes.mail_channel: [
        {"id": "uid", "header": "logsPage.uniqueId", "cellComponent": "ClickableNameCell"},
        {"id": "sender_id", "header": "common.senderId", "cellComponent": "SimpleCell"},
        {"id": "timestamp", "accessorFunction": "formatUnixTimestamp", "header": "logsPage.timestamp", "cellComponent": "SimpleCell"},
        {"id": "status", "header": "logsPage.status", "cellComponent": "StatusCell"}
    ],

    LogTypes.catalog: [
        {"id": "execution_id", "header": "logsPage.executionId", "cellComponent": "ClickableNameCell"},
        {"id": "provider", "header": "logsPage.posName", "cellComponent": "SimpleCell"},
        {"id": "sync_type", "header": "logsPage.syncType", "cellComponent": "SimpleCell"},
        {"id": "start_timestamp", "accessorFunction": "formatStartTime", "header": "common.startTimeHeader", "cellComponent": "StartTimestampCell"},
        {"id": "end_timestamp", "accessorFunction": "formatEndTimeOrInProgress", "header": "common.endTimeHeader", "cellComponent": "EndTimestampInProgressCell"},
        {"id": "exception", "accessorFunction": "formatExceptionText", "header": "logsPage.exception", "cellComponent": "ExceptionCell"},
        {"id": "sync_status", "header": "logsPage.syncStatus", "cellComponent": "StatusCell"}
    ],
}



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

class SyncType(str, Enum):
    push_menu = "push_menu"
    item_toggle = "item_toggle"

ORG_SETTINGS_MESSAGES = {
    "create_user": "User creation is blocked by your OrgAdmin from SSO",
    "only_sso_login": "Login with your org SSO url, Login with username/password not allowed",
}

RE_ALPHA_NUM = re.compile(r"^[a-zA-Z0-9 _]+$").search
RE_VALID_NAME= re.compile(r"^[a-zA-Z0-9 _-]+$").search