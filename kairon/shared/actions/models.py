from enum import Enum

KAIRON_ACTION_RESPONSE_SLOT = "KAIRON_ACTION_RESPONSE"


class ParameterType(str, Enum):
    user = "user"
    action = "action"
    form = "form"
    slot = "slot"
    http = "http"
    sender_id = "sender_id"
    http_action_config = "http_action_config"


class ActionType(str, Enum):
    http_action = "http_action"
    slot_set_action = "slot_set_action"
    form_validation_action = "form_validation_action"


class LogicalOperators(str, Enum):
    and_operator = "and"
    or_operator = "or"
    not_operator = "not"


class SlotValidationOperators(str, Enum):
    is_exactly = "is_exactly"
    is_greater_than = "is_greater_than"
    is_less_than = "is_less_than"
    case_insensitive_is_exactly = "case_insensitive_is_exactly"
    contains = "contains"
    is_in = "is_in"
    is_not_in = "is_not_in"
    starts_with = "starts_with"
    ends_with = "ends_with"
    has_length = "has_length"
    has_length_greater_than = "has_length_greater_than"
    has_length_less_than = "has_length_less_than"
    has_no_whitespace = "has_no_whitespace"
    is_an_email_address = "is_an_email_address"
    matches_regex = "matches_regex"
    element_at_index_equals = 'element_at_index_equals'
    element_at_index_not_equals = 'element_at_index_not_equals'
    is_true = "is_true"
    is_false = "is_false"
    is_null_or_empty = "is_null_or_empty"
    is_not_null_or_empty = "is_not_null_or_empty"
