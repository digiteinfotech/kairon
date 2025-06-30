from enum import Enum

from pydantic import BaseModel

from kairon.shared.data.constant import ACCESS_ROLES


class StoryStepType(str, Enum):
    intent = "INTENT"
    slot = "SLOT"
    form_start = "FORM_START"
    form_end = "FORM_END"
    bot = "BOT"
    http_action = "HTTP_ACTION"
    action = "ACTION"
    slot_set_action = "SLOT_SET_ACTION"
    form_action = "FORM_ACTION"
    google_search_action = "GOOGLE_SEARCH_ACTION"
    email_action = "EMAIL_ACTION"
    jira_action = "JIRA_ACTION"
    zendesk_action = "ZENDESK_ACTION"
    pipedrive_leads_action = "PIPEDRIVE_LEADS_ACTION"
    hubspot_forms_action = "HUBSPOT_FORMS_ACTION"
    razorpay_action = "RAZORPAY_ACTION"
    two_stage_fallback_action = "TWO_STAGE_FALLBACK_ACTION"
    pyscript_action = "PYSCRIPT_ACTION"
    prompt_action = "PROMPT_ACTION"
    database_action = "DATABASE_ACTION"
    web_search_action = "WEB_SEARCH_ACTION"
    live_agent_action = "LIVE_AGENT_ACTION"
    stop_flow_action = "STOP_FLOW_ACTION"
    callback_action = "CALLBACK_ACTION"
    schedule_action = "SCHEDULE_ACTION"
    parallel_action = "PARALLEL_ACTION"


class StoryType(str, Enum):
    story = "STORY"
    rule = "RULE"
    multiflow_story = "MULTIFLOW"


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


class HttpContentType(str, Enum):
    application_json = "application/json"
    urlencoded_form_data = "application/x-www-form-urlencoded"


class User(BaseModel):
    email: str
    first_name: str
    last_name: str
    active_bot: str = None
    bot_account: int = None
    account: int
    is_onboarded: bool = False
    status: bool
    alias_user: str = None
    is_integration_user: bool = False
    role: ACCESS_ROLES = None

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


class LlmPromptSource(str, Enum):
    static = "static"
    slot = "slot"
    action = "action"
    history = "history"
    tag = "tag"
    crud = "crud"
    bot_content = "bot_content"


class LlmPromptType(str, Enum):
    user = "user"
    system = "system"
    query = "query"


class CognitionDataType(str, Enum):
    text = "text"
    json = "json"


class CognitionMetadataType(str, Enum):
    str = "str"
    int = "int"
    float = "float"

class VaultSyncType(str, Enum):
    push_menu = ["column_length_mismatch", "invalid_columns", "pydantic_validation"]
    item_toggle = ["invalid_columns", "document_non_existence", "pydantic_validation"]

class GlobalSlotsEntryType(str, Enum):
    agentic_flow = "agentic_flow"

class FlowTagType(str, Enum):
    agentic_flow = "agentic_flow"
    chatbot_flow = "chatbot_flow"


class UserMediaUploadType(str, Enum):
    user_uploaded = "user_uploaded"
    system_uploaded = "system_uploaded"


class UserMediaUploadStatus(str, Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"

