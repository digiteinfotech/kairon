from enum import Enum

KAIRON_ACTION_RESPONSE_SLOT = "kairon_action_response"
BOT_ID_SLOT = 'bot'


class ParameterType(str, Enum):
    user = "user"
    action = "action"
    form = "form"
    http = "http"
    http_action_config = "http_action_config"


class ActionParameterType(str, Enum):
    value = "value"
    slot = "slot"
    sender_id = "sender_id"
    user_message = "user_message"
    intent = "intent"
    chat_log = "chat_log"
    key_vault = "key_vault"


class EvaluationType(str, Enum):
    expression = "expression"
    script = "script"


class ActionType(str, Enum):
    http_action = "http_action"
    slot_set_action = "slot_set_action"
    form_validation_action = "form_validation_action"
    email_action = "email_action"
    google_search_action = "google_search_action"
    jira_action = "jira_action"
    zendesk_action = "zendesk_action"
    pipedrive_leads_action = "pipedrive_leads_action"
    hubspot_forms_action = "hubspot_forms_action"
    two_stage_fallback = "two_stage_fallback"
    kairon_bot_response = "kairon_bot_response"
    razorpay_action = "razorpay_action"
    kairon_faq_action = "kairon_faq_action"


class HttpRequestContentType(str, Enum):
    json = "json"
    data = "data"


class LogicalOperators(str, Enum):
    and_operator = "and"
    or_operator = "or"
    not_operator = "not"


class SlotValidationOperators(str, Enum):
    equal_to = "=="
    not_equal_to = "!="
    is_greater_than = ">"
    is_less_than = "<"
    case_insensitive_equals = "case_insensitive_equals"
    contains = "contains"
    is_in = "in"
    is_not_in = "not in"
    starts_with = "startswith"
    ends_with = "endswith"
    has_length = "has_length"
    has_length_greater_than = "has_length_greater_than"
    has_length_less_than = "has_length_less_than"
    has_no_whitespace = "has_no_whitespace"
    is_an_email_address = "is_an_email_address"
    matches_regex = "matches_regex"
    is_true = "is_true"
    is_false = "is_false"
    is_null_or_empty = "is_null_or_empty"
    is_not_null_or_empty = "is_not_null_or_empty"
