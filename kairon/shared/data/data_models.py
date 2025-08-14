import json
from typing import List, Any, Dict, Optional, Text, Union, Literal

from validators import url
from validators.utils import ValidationError as ValidationFailure
from fastapi.param_functions import Form
from fastapi.security import OAuth2PasswordRequestForm
from rasa.shared.constants import DEFAULT_NLU_FALLBACK_INTENT_NAME

from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import ScheduleActionType, Actions
from kairon.shared.data.constant import (
    EVENT_STATUS,
    SLOT_MAPPING_TYPE,
    SLOT_TYPE,
    ACCESS_ROLES,
    ACTIVITY_STATUS,
    INTEGRATION_STATUS,
    FALLBACK_MESSAGE,
    DEFAULT_NLU_FALLBACK_RESPONSE, RE_ALPHA_NUM
)
from kairon.shared.actions.models import (
    ActionParameterType,
    EvaluationType,
    DispatchType,
    DbQueryValueType,
    DbActionOperationType, UserMessageType, HttpRequestContentType, ActionType
)
from kairon.shared.callback.data_objects import CallbackExecutionMode, CallbackResponseType
from kairon.shared.constants import SLOT_SET_TYPE, FORM_SLOT_SET_TYPE

from pydantic import BaseModel, validator, SecretStr, root_validator, constr, Field
from kairon.shared.models import (
    StoryStepType,
    StoryType,
    TemplateType,
    HttpContentType,
    LlmPromptSource,
    LlmPromptType,
    CognitionDataType,
    CognitionMetadataType, FlowTagType,
)


class RecaptchaVerifiedRequest(BaseModel):
    recaptcha_response: str = None
    remote_ip: str = None

    @root_validator
    def validate_recaptcha(cls, values):
        from kairon.shared.utils import Utility

        secret = Utility.environment["security"].get("recaptcha_secret", None)
        if Utility.environment["security"][
            "validate_recaptcha"
        ] and not Utility.check_empty_string(secret):
            Utility.validate_recaptcha(
                values.get("recaptcha_response"), values.get("remote_ip")
            )
        return values


class RecaptchaVerifiedOAuth2PasswordRequestForm(OAuth2PasswordRequestForm):
    """
    Dependency class overridden from OAuth2PasswordRequestForm.
    """

    def __init__(
        self,
        grant_type: str = Form(None, pattern="password"),
        username: str = Form(...),
        password: str = Form(...),
        scope: str = Form(""),
        client_id: Optional[str] = Form(None),
        client_secret: Optional[str] = Form(None),
        recaptcha_response: str = Form(None),
        remote_ip: str = Form(None),
        fingerprint: str = Form(None),
    ):
        """
        @param grant_type: the OAuth2 spec says it is required and MUST be the fixed string "password".
        Nevertheless, this dependency class is permissive and allows not passing it. If you want to enforce it,
        use instead the OAuth2PasswordRequestFormStrict dependency.
        @param username: username string. The OAuth2 spec requires the exact field name "username".
        @param password: password string. The OAuth2 spec requires the exact field name "password".
        @param scope: Optional string. Several scopes (each one a string) separated by spaces.
        E.g. "items:read items:write users:read profile openid"
        @param client_id: optional string. OAuth2 recommends sending the client_id and client_secret (if any)
        using HTTP Basic auth, as: client_id:client_secret
        @param client_secret: optional string. OAuth2 recommends sending the client_id and client_secret (if any)
        using HTTP Basic auth, as: client_id:client_secret
        @param recaptcha_response: optional string. recaptcha response.
        @param remote_ip: optional string.  remote ip address.
        @param fingerprint: optional string. device fingerprint.
        """
        from kairon.shared.utils import Utility

        secret = Utility.environment["security"].get("recaptcha_secret", None)
        if Utility.environment["security"][
            "validate_recaptcha"
        ] and not Utility.check_empty_string(secret):
            Utility.validate_recaptcha(recaptcha_response, remote_ip)
        OAuth2PasswordRequestForm.__init__(
            self,
            grant_type=grant_type,
            username=username,
            password=password,
            scope=scope,
            client_id=client_id,
            client_secret=client_secret
        )
        self.recaptcha_response = recaptcha_response
        self.remote_ip = remote_ip
        if Utility.environment["user"]["validate_trusted_device"] and Utility.check_empty_string(fingerprint):
            raise AppException("fingerprint is required")
        self.fingerprint = fingerprint


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str


class Response(BaseModel):
    success: bool = True
    message: Any = None
    data: Any
    error_code: int = 0

class ActionResponse(BaseModel):
    success: bool = True
    error: str = None
    action_name: str = None
    events: List[Dict[Text, Any]] = None
    responses: List[Dict[Text, Any]] = None
    error_code: int = 200


class RequestData(BaseModel):
    data: Any


class TextData(BaseModel):
    data: str


class RecaptchaVerifiedTextData(RecaptchaVerifiedRequest):
    data: str


class TextDataLowerCase(BaseModel):
    data: constr(to_lower=True, strip_whitespace=True)


class ListData(BaseModel):
    data: List[str]


class ConsentRequest(BaseModel):
    accepted_privacy_policy: bool
    accepted_terms: bool


class RegisterAccount(RecaptchaVerifiedRequest):
    email: constr(to_lower=True, strip_whitespace=True)
    first_name: str
    last_name: str
    password: SecretStr
    confirm_password: SecretStr
    account: str
    fingerprint: str = None
    accepted_privacy_policy: bool
    accepted_terms: bool

    @validator("email")
    def validate_email(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        try:
            Utility.verify_email(v)
        except AppException as e:
            raise ValueError(str(e))
        return v

    @validator("password")
    def validate_password(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        try:
            Utility.valid_password(v.get_secret_value())
        except AppException as e:
            raise ValueError(str(e))
        return v

    @validator("confirm_password")
    def validate_confirm_password(cls, v, values, **kwargs):
        if (
            "password" in values
            and v.get_secret_value() != values["password"].get_secret_value()
        ):
            raise ValueError("Password and Confirm Password does not match")
        return v

    @root_validator
    def validate_names(cls, values):
        from kairon.shared.utils import Utility

        first_name = values.get("first_name", "").strip()
        last_name = values.get("last_name", "").strip()

        if Utility.check_empty_string(first_name) or Utility.check_empty_string(last_name):
            raise ValueError("First name and last name cannot be empty or blank spaces.")

        first_valid = Utility.special_match(first_name, search=RE_ALPHA_NUM)
        last_valid = Utility.special_match(last_name, search=RE_ALPHA_NUM)

        if not first_valid or not last_valid:
            raise ValueError("First name and last name can only contain letters, numbers, spaces and underscores.")

        return values

    @root_validator
    def validate_fingerprint(cls, values):
        from kairon.shared.utils import Utility

        if Utility.environment["user"]["validate_trusted_device"] and Utility.check_empty_string(values.get("fingerprint")):
            raise ValueError("fingerprint is required")
        return values


class BotAccessRequest(RecaptchaVerifiedRequest):
    email: constr(to_lower=True, strip_whitespace=True)
    role: ACCESS_ROLES = ACCESS_ROLES.TESTER.value
    activity_status: ACTIVITY_STATUS = ACTIVITY_STATUS.INACTIVE.value

    @validator("email")
    def validate_email(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        try:
            Utility.verify_email(v)
        except AppException as e:
            raise ValueError(str(e))
        return v

    @validator("role")
    def validate_role(cls, v, values, **kwargs):
        if v == ACCESS_ROLES.OWNER.value:
            raise ValueError("There can be only 1 owner per bot")
        return v


class EndPointBot(BaseModel):
    url: str
    token: str = None
    token_type: str = None


class EndPointAction(BaseModel):
    url: str


class EndPointHistory(BaseModel):
    url: str
    token: str = None


class Endpoint(BaseModel):
    bot_endpoint: EndPointBot = None
    action_endpoint: EndPointAction = None
    history_endpoint: EndPointHistory = None


class RasaConfig(BaseModel):
    language: str = "en"
    pipeline: List[Dict]
    policies: List[Dict]


class ComponentConfig(BaseModel):
    nlu_epochs: int = None
    response_epochs: int = None
    ted_epochs: int = None
    nlu_confidence_threshold: float = None
    action_fallback: str = None
    action_fallback_threshold: float = None

    @validator("nlu_epochs", "response_epochs", "ted_epochs")
    def validate_epochs(cls, v):
        from kairon.shared.utils import Utility

        if v is not None and v < 1:
            raise ValueError("Choose a positive number as epochs")
        elif v > Utility.environment["model"]["config_properties"]["epoch_max_limit"]:
            epoch_max_limit = Utility.environment["model"]["config_properties"][
                "epoch_max_limit"
            ]
            raise ValueError(f"Please choose a epoch between 1 and {epoch_max_limit}")
        return v

    @validator("nlu_confidence_threshold", "action_fallback_threshold")
    def validate_confidence_threshold(cls, v):
        if v is not None and (v < 0.3 or v > 0.9):
            raise ValueError("Please choose a threshold between 0.3 and 0.9")
        return v


class Password(RecaptchaVerifiedRequest):
    data: str
    password: SecretStr
    confirm_password: SecretStr

    @validator("password")
    def validate_password(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        try:
            Utility.valid_password(v.get_secret_value())
        except AppException as e:
            raise ValueError(str(e))
        return v

    @validator("confirm_password")
    def validate_confirm_password(cls, v, values, **kwargs):
        if (
            "password" in values
            and v.get_secret_value() != values["password"].get_secret_value()
        ):
            raise ValueError("Password and Confirm Password does not match")
        return v


class HttpActionParameters(BaseModel):
    key: str
    value: str = None
    parameter_type: ActionParameterType
    encrypt: bool = False

    @root_validator
    def check(cls, values):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(values.get("key")):
            raise ValueError("key cannot be empty")

        if values.get(
            "parameter_type"
        ) == ActionParameterType.slot and Utility.check_empty_string(
            values.get("value")
        ):
            raise ValueError("Provide name of the slot as value")

        if values.get(
            "parameter_type"
        ) == ActionParameterType.key_vault and Utility.check_empty_string(
            values.get("value")
        ):
            raise ValueError("Provide key from key vault as value")

        if values.get("parameter_type") == ActionParameterType.key_vault:
            values["encrypt"] = True

        return values


class SetSlotsUsingActionResponse(BaseModel, use_enum_values=True):
    name: str
    value: str
    evaluation_type: EvaluationType = EvaluationType.expression

    @validator("name")
    def validate_name(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("slot name is required")
        return v

    @validator("value")
    def validate_expression(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("expression is required to evaluate value of slot")
        return v


class ActionResponseEvaluation(BaseModel):
    value: str = None
    dispatch: bool = True
    evaluation_type: EvaluationType = EvaluationType.expression
    dispatch_type: DispatchType = DispatchType.text.value

    @root_validator
    def check(cls, values):
        from kairon.shared.utils import Utility

        if values.get("dispatch") is True and Utility.check_empty_string(
            values.get("value")
        ):
            raise ValueError("response is required for dispatch")

        return values


class HttpActionConfigRequest(BaseModel):
    action_name: constr(to_lower=True, strip_whitespace=True)
    content_type: Union[HttpContentType, HttpRequestContentType] = HttpContentType.application_json
    response: ActionResponseEvaluation = None
    http_url: str
    request_method: str
    params_list: List[HttpActionParameters] = []
    dynamic_params: str = None
    headers: List[HttpActionParameters] = []
    set_slots: List[SetSlotsUsingActionResponse] = []

    @validator("action_name")
    def validate_action_name(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("action_name is required")
        return v

    @validator("http_url")
    def validate_http_url(cls, v, values, **kwargs):
        if isinstance(url(v), ValidationFailure):
            raise ValueError("URL is malformed")
        return v

    @validator("request_method")
    def validate_request_method(cls, v, values, **kwargs):
        if v.upper() not in ("GET", "POST", "PUT", "DELETE"):
            raise ValueError("Invalid HTTP method")
        return v.upper()


class PayloadConfig(BaseModel):
    type: DbQueryValueType
    value: Any
    query_type: DbActionOperationType

    @root_validator
    def check(cls, values):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(values.get("type")):
            raise ValueError("type is required")

        return values


class PyscriptActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    source_code: str
    dispatch_response: bool = True

    @validator("name")
    def validate_action_name(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("name is required")
        return v

    @validator("source_code")
    def validate_source_code(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("source_code is required")
        return v


class DatabaseActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    collection: str
    payload: List[PayloadConfig]
    response: ActionResponseEvaluation = None
    set_slots: List[SetSlotsUsingActionResponse] = []

    @validator("name")
    def validate_action_name(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("name is required")
        return v

    @validator("collection")
    def validate_collection_name(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("collection is required")
        return v

    @validator("payload")
    def validate_payload(cls, v, values, **kwargs):
        count_payload_search = 0
        if v:
            for item in v:
                if item.query_type == DbActionOperationType.payload_search:
                    count_payload_search += 1
                if count_payload_search > 1:
                    raise ValueError(f"Only One {DbActionOperationType.payload_search} is allowed!")
        else:
            raise ValueError("payload is required")
        return v


class LiveAgentActionRequest(BaseModel):
    bot_response: str = 'Connecting to live agent'
    agent_connect_response: str = 'Connected to live agent'
    agent_disconnect_response: str = 'Agent has closed the conversation'
    agent_not_available_response: str = 'No agents available at this moment. An agent will reply to you shortly.'
    dispatch_bot_response: bool = True
    dispatch_agent_connect_response: bool = True
    dispatch_agent_disconnect_response: bool = True
    dispatch_agent_not_available_response: bool = True


class TrainingData(BaseModel):
    intent: constr(to_lower=True, strip_whitespace=True)
    training_examples: List[str]
    response: str


class BulkTrainingDataAddRequest(BaseModel):
    history_id: str
    training_data: List[TrainingData]


class TrainingDataGeneratorResponseModel(BaseModel):
    intent: str
    training_examples: List[str]
    response: str


class TrainingDataGeneratorStatusModel(BaseModel):
    status: EVENT_STATUS
    response: List[TrainingData] = None
    exception: str = None


class StoryStepRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True) = None
    type: StoryStepType
    value: Any = None


class MultiStoryStepRequest(StoryStepRequest):
    node_id: str
    component_id: str


class StoryStepData(BaseModel):
    step: MultiStoryStepRequest
    connections: List[MultiStoryStepRequest] = None


class StoryMetadata(BaseModel):
    node_id: str
    flow_type: StoryType = StoryType.story.value


class MultiFlowStoryRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    steps: List[StoryStepData]
    metadata: List[StoryMetadata] = None
    flow_tags: List[str] = [FlowTagType.chatbot_flow.value]


    @validator("steps")
    def validate_request_method(cls, v, values, **kwargs):
        if not v:
            raise ValueError("Steps are required to form Flow")
        return v


class StoryRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    type: StoryType
    steps: List[StoryStepRequest]
    template_type: TemplateType = None
    flow_tags: List[str] = [FlowTagType.chatbot_flow.value]

    class Config:
        use_enum_values = True

    def get_steps(self):
        return [step.dict() for step in self.steps]

    @validator("steps")
    def validate_request_method(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if not v:
            raise ValueError("Steps are required to form Flow")

        if v[0].type != StoryStepType.intent:
            raise ValueError("First step should be an intent")

        if v[len(v) - 1].type == StoryStepType.intent:
            raise ValueError("Intent should be followed by utterance or action")

        intents = 0
        for i, j in enumerate(range(1, len(v))):
            if v[i].type == StoryStepType.intent:
                intents = intents + 1
            if v[i].type == StoryStepType.intent and v[j].type == StoryStepType.intent:
                raise ValueError("Found 2 consecutive intents")
            if (
                Utility.check_empty_string(v[i].name)
                and v[i].type != StoryStepType.form_end
            ):
                raise ValueError(
                    f"Only {StoryStepType.form_end} step type can have empty name"
                )
            if v[i].type == StoryStepType.stop_flow_action and i != len(v) - 1:
                raise ValueError("Stop Flow Action should only be at the end of the flow")
            if v[i].type == StoryStepType.intent and v[j].type == StoryStepType.stop_flow_action:
                raise ValueError("Stop Flow Action should not be after intent")

        if "type" in values:
            if values["type"] == StoryType.rule and intents > 1:
                raise ValueError(
                    f"""Found rules '{values['name']}' that contain more than intent.\nPlease use stories for this case"""
                )
        return v


class AnalyticsModel(BaseModel):
    fallback_intent: str = DEFAULT_NLU_FALLBACK_INTENT_NAME

    @validator('fallback_intent')
    def validate_fallback_intent(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility
        if Utility.check_empty_string(v):
            raise ValueError("fallback_intent field cannot be empty")
        return v


class BotSettingsRequest(BaseModel):
    analytics: AnalyticsModel = AnalyticsModel()


class FeedbackRequest(BaseModel):
    rating: float
    scale: float = 5
    feedback: str = None


class GPTRequest(BaseModel):
    api_key: str
    data: List[str]
    engine: str = "davinci"
    temperature: float = 0.75
    max_tokens: int = 100
    num_responses: int = 10

    @validator("data")
    def validate_gpt_questions(cls, v, values, **kwargs):
        if len(v) <= 0:
            raise ValueError("Question Please!")
        elif len(v) > 5:
            raise ValueError("Max 5 Questions are allowed!")
        return v


class ParaphrasesRequest(BaseModel):
    data: List[str]

    @validator("data")
    def validate_paraphrases_questions(cls, v, values, **kwargs):
        if len(v) <= 0:
            raise ValueError("Question Please!")
        elif len(v) > 5:
            raise ValueError("Max 5 Questions are allowed!")
        return v


class SlotRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    type: SLOT_TYPE
    initial_value: Any = None
    values: List[str] = None
    max_value: float = None
    min_value: float = None
    influence_conversation: bool = False

    class Config:
        use_enum_values = True


class SynonymRequest(BaseModel):
    value: List[str]

    @validator("value")
    def validate_value(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if len(v) <= 0:
            raise ValueError("value field cannot be empty")
        for ele in v:
            if Utility.check_empty_string(ele):
                raise ValueError("value cannot be an empty string")
        return v


class AddBotRequest(BaseModel):
    name: str
    from_template: str = None


class DictData(BaseModel):
    data: dict


class RecaptchaVerifiedDictData(DictData):
    recaptcha_response: str = None


class RegexRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    pattern: str

    @validator("name")
    def validate_name(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("Regex name cannot be empty or a blank space")
        return v

    @validator("pattern")
    def validate_pattern(cls, f, values, **kwargs):
        from kairon.shared.utils import Utility
        import re

        if Utility.check_empty_string(f):
            raise ValueError("Regex pattern cannot be empty or a blank space")
        try:
            re.compile(f)
        except Exception:
            raise AppException("invalid regular expression")
        return f


class LookupTablesRequest(BaseModel):
    value: List[str]

    @validator("value")
    def validate_value(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if len(v) <= 0:
            raise ValueError("value field cannot be empty")
        for ele in v:
            if Utility.check_empty_string(ele):
                raise ValueError("lookup value cannot be empty or a blank space")
        return v


class MappingCondition(BaseModel):
    active_loop: str = None
    requested_slot: str = None

    @root_validator
    def validate(cls, values):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(values.get("active_loop")) and not Utility.check_empty_string(values.get("requested_slot")):
            raise ValueError("active_loop is required to add requested_slot as condition!")

        return values


class SlotMapping(BaseModel):
    entity: constr(to_lower=True, strip_whitespace=True) = None
    type: SLOT_MAPPING_TYPE
    value: Any = None
    intent: List[constr(to_lower=True, strip_whitespace=True)] = None
    not_intent: List[constr(to_lower=True, strip_whitespace=True)] = None
    conditions: List[MappingCondition] = None

    class Config:
        use_enum_values = True


class SlotMappingRequest(BaseModel):
    slot: constr(to_lower=True, strip_whitespace=True)
    mapping: SlotMapping

    class Config:
        use_enum_values = True

    @validator("mapping")
    def validate_mapping(cls, v, values, **kwargs):
        if not v or v == [{}]:
            raise ValueError("At least one mapping is required")
        return v


class FormSlotSetModel(BaseModel):
    type: FORM_SLOT_SET_TYPE = FORM_SLOT_SET_TYPE.current.value
    value: Any = None
    class Config:
        use_enum_values = True



class FormSettings(BaseModel):
    ask_questions: List[str]
    slot: str
    is_required: bool = True
    validation_semantic: str = None
    valid_response: str = None
    invalid_response: str = None
    slot_set: FormSlotSetModel = FormSlotSetModel()

    @validator("ask_questions")
    def validate_responses(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        err_msg = "Questions cannot be empty or contain spaces"
        if not v:
            raise ValueError(err_msg)

        for response in v:
            if Utility.check_empty_string(response):
                raise ValueError(err_msg)
        return v

    @validator("slot")
    def validate_slot(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("Slot is required")
        return v


class Forms(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    settings: List[FormSettings]


class SetSlots(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    type: SLOT_SET_TYPE
    value: Any = None

    class Config:
        use_enum_values = True


class SlotSetActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    set_slots: List[SetSlots]


class CustomActionParameter(BaseModel):
    value: str = None
    parameter_type: ActionParameterType = ActionParameterType.value
    class Config:
        use_enum_values = True

    @validator("parameter_type")
    def validate_parameter_type(cls, v, values, **kwargs):
        allowed_values = {
            ActionParameterType.value,
            ActionParameterType.slot,
            ActionParameterType.key_vault,
            ActionParameterType.sender_id,
        }
        if v not in allowed_values:
            raise ValueError(
                f"Invalid parameter type. Allowed values: {allowed_values}"
            )
        return v

    @root_validator
    def check(cls, values):
        from kairon.shared.utils import Utility

        if values.get(
            "parameter_type"
        ) == ActionParameterType.slot and Utility.check_empty_string(
            values.get("value")
        ):
            raise ValueError("Provide name of the slot as value")

        if values.get(
            "parameter_type"
        ) == ActionParameterType.key_vault and Utility.check_empty_string(
            values.get("value")
        ):
            raise ValueError("Provide key from key vault as value")

        return values


class GoogleSearchActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    api_key: CustomActionParameter = None
    search_engine_id: str = None
    search_term: CustomActionParameter = None
    website: str = None
    failure_response: str = "I have failed to process your request."
    num_results: int = 1
    dispatch_response: bool = True
    set_slot: str = None

    @validator("num_results")
    def validate_num_results(cls, v, values, **kwargs):
        if not v or v < 1:
            raise ValueError("num_results must be greater than or equal to 1!")
        return v


class WebSearchActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    website: str = None
    failure_response: str = 'I have failed to process your request.'
    topn: int = 1
    dispatch_response: bool = True
    set_slot: str = None

    @validator("name")
    def validate_action_name(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("name is required")
        return v

    @validator("topn")
    def validate_top_n(cls, v, values, **kwargs):
        if not v or v < 1:
            raise ValueError("topn must be greater than or equal to 1!")
        return v


class CustomActionParameterModel(BaseModel):
    value: Any = None
    parameter_type: ActionParameterType = ActionParameterType.value

    @validator("parameter_type")
    def validate_parameter_type(cls, v, values, **kwargs):
        allowed_values = {ActionParameterType.value, ActionParameterType.slot}
        if v not in allowed_values:
            raise ValueError(f"Invalid parameter type. Allowed values: {allowed_values}")
        return v

    @root_validator
    def check(cls, values):
        if values.get('parameter_type') == ActionParameterType.slot and not values.get('value'):
            raise ValueError("Provide name of the slot as value")

        if values.get('parameter_type') == ActionParameterType.value and not isinstance(values.get('value'), list):
            raise ValueError("Provide list of emails as value")

        return values


class CustomActionDynamicParameterModel(BaseModel):
    value: Any = None
    parameter_type: ActionParameterType = ActionParameterType.value

    @validator("parameter_type")
    def validate_parameter_type(cls, v, values, **kwargs):
        allowed_values = {ActionParameterType.value, ActionParameterType.slot}
        if v not in allowed_values:
            raise ValueError(f"Invalid parameter type. Allowed values: {allowed_values}")
        return v

    @root_validator
    def check(cls, values):
        from kairon.shared.utils import Utility
        if values.get('parameter_type') == ActionParameterType.slot and not values.get('value'):
            raise ValueError("Provide name of the slot as value")

        if values.get('parameter_type') == ActionParameterType.value and Utility.check_empty_string(values.get("value")):
            raise ValueError("Value can not be blank")

        return values


class EmailActionRequest(BaseModel):
    action_name: constr(to_lower=True, strip_whitespace=True)
    smtp_url: str
    smtp_port: int
    smtp_userid: CustomActionParameter = None
    smtp_password: CustomActionParameter
    from_email: CustomActionParameter
    subject: str
    custom_text: CustomActionParameter = None
    to_email: CustomActionParameterModel
    response: str
    dispatch_bot_response: bool = True
    tls: bool = False


class JiraActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    url: str
    user_name: str
    api_token: CustomActionParameter
    project_key: str
    issue_type: str
    parent_key: str = None
    summary: str
    response: str


class ZendeskActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    subdomain: str
    user_name: str
    api_token: CustomActionParameter
    subject: str
    response: str


class PipedriveActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    domain: str
    api_token: CustomActionParameter
    title: str
    response: str
    metadata: dict

    @validator("metadata")
    def validate_metadata(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if not v or Utility.check_empty_string(v.get("name")):
            raise ValueError("name is required")
        return v


class HubspotFormsActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    portal_id: str
    form_guid: str
    fields: List[HttpActionParameters]
    response: str


class QuickReplies(BaseModel):
    text: str
    payload: str
    message: str = None
    is_dynamic_msg: bool = False


class TwoStageFallbackTextualRecommendations(BaseModel):
    count: int = 0
    use_intent_ranking: bool = False


class TwoStageFallbackConfigRequest(BaseModel):
    fallback_message: str = FALLBACK_MESSAGE
    text_recommendations: TwoStageFallbackTextualRecommendations = None
    trigger_rules: List[QuickReplies] = None

    @root_validator
    def check(cls, values):
        if not values.get("text_recommendations") and not values["trigger_rules"]:
            raise ValueError(
                "One of text_recommendations or trigger_rules should be defined"
            )
        if (
            values.get("text_recommendations")
            and values["text_recommendations"].count < 0
        ):
            raise ValueError("count cannot be negative")
        return values


class PromptHyperparameters(BaseModel):
    top_results: int = 10
    similarity_threshold: float = 0.70

    @root_validator
    def check(cls, values):
        if not 0.3 <= values.get('similarity_threshold') <= 1:
            raise ValueError("similarity_threshold should be within 0.3 and 1")
        if values.get('top_results') > 30:
            raise ValueError("top_results should not be greater than 30")
        return values


class CrudConfigRequest(BaseModel):
    collections: Optional[List[str]] = None
    query: Optional[Any] = None
    result_limit: int = 10
    query_source: Optional[Literal["value", "slot"]] = None

class LlmPromptRequest(BaseModel, use_enum_values=True):
    name: str
    hyperparameters: PromptHyperparameters = None
    data: str = None
    instructions: str = None
    type: LlmPromptType
    source: LlmPromptSource
    is_enabled: bool = True
    crud_config: Optional[CrudConfigRequest] = None

    @root_validator
    def check(cls, values):
        from kairon.shared.utils import Utility
        if values.get('source') == LlmPromptSource.crud.value:
            crud_config = values.get('crud_config')
            if not crud_config:
                raise ValueError("crud_config is required when source is 'crud'")

            query_source = crud_config.query_source
            if query_source == 'value':
                if isinstance(crud_config.query, str):
                    try:
                        crud_config.query = json.loads(crud_config.query)
                    except json.JSONDecodeError:
                        raise ValueError(f"Invalid JSON format in query: {crud_config.query}")
                elif not isinstance(crud_config.query, dict):
                    raise ValueError("When query_source is 'value', query must be a valid JSON object or JSON string.")
            elif query_source == 'slot':
                if not isinstance(crud_config.query, str):
                    raise ValueError("When query_source is 'slot', query must be a valid slot name.")
        else:
            values.pop('crud_config', None)

        if values.get('source') == LlmPromptSource.bot_content.value and Utility.check_empty_string(values.get('data')):
            values['data'] = "default"

        return values


class UserQuestionModel(BaseModel):
    type: UserMessageType = UserMessageType.from_user_message.value
    value: str = None


class PromptActionConfigUploadValidation(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    num_bot_responses: int = 5
    failure_message: str = DEFAULT_NLU_FALLBACK_RESPONSE
    user_question: UserQuestionModel = UserQuestionModel()
    llm_type: str
    hyperparameters: dict
    llm_prompts: List[LlmPromptRequest]
    instructions: List[str] = []
    set_slots: List[SetSlotsUsingActionResponse] = []
    dispatch_response: bool = True


class PromptActionConfigRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    num_bot_responses: int = 5
    failure_message: str = DEFAULT_NLU_FALLBACK_RESPONSE
    user_question: UserQuestionModel = UserQuestionModel()
    llm_type: str
    hyperparameters: dict
    llm_prompts: List[LlmPromptRequest]
    instructions: List[str] = []
    set_slots: List[SetSlotsUsingActionResponse] = []
    dispatch_response: bool = True
    process_media: bool = False
    bot: str

    @validator("llm_type", pre=True, always=True)
    def validate_llm_type(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility
        if v not in Utility.get_llms():
            raise ValueError("Invalid llm type")
        return v

    @validator("llm_prompts")
    def validate_llm_prompts(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        Utility.validate_kairon_faq_llm_prompts(
            [vars(value) for value in v], ValueError
        )
        return v

    @validator("num_bot_responses")
    def validate_num_bot_responses(cls, v, values, **kwargs):
        if v > 5:
            raise ValueError("num_bot_responses should not be greater than 5")
        return v

    @validator("hyperparameters")
    def validate_hyperparameters(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility
        bot = values.get('bot')
        llm_type = values.get('llm_type')
        if llm_type and v:
            Utility.validate_llm_hyperparameters(v, llm_type, bot, ValueError)
        return v

    @root_validator(pre=True)
    def validate_required_fields(cls, values):
        bot = values.get('bot')
        if not bot:
            raise ValueError("bot field is missing")
        return values


class ColumnMetadata(BaseModel):
    column_name: str
    data_type: CognitionMetadataType
    enable_search: bool = True
    create_embeddings: bool = True

    @root_validator
    def check(cls, values):
        from kairon.shared.utils import Utility

        if values.get('data_type') not in [CognitionMetadataType.str.value, CognitionMetadataType.int.value, CognitionMetadataType.float.value]:
            raise ValueError("Only str, int and float data types are supported")
        if Utility.check_empty_string(values.get('column_name')):
            raise ValueError("Column name cannot be empty")
        return values


class CognitionSchemaRequest(BaseModel):
    metadata: List[ColumnMetadata] = None
    collection_name: constr(to_lower=True, strip_whitespace=True)


class CollectionDataRequest(BaseModel):
    data: dict
    is_secure: list = []
    is_non_editable: list = []
    collection_name: constr(to_lower=True, strip_whitespace=True)

    @root_validator
    def check(cls, values):
        from kairon.shared.utils import Utility

        data = values.get("data")
        is_secure = values.get("is_secure")
        collection_name = values.get("collection_name")
        if Utility.check_empty_string(collection_name):
            raise ValueError("collection_name should not be empty!")

        if not isinstance(is_secure, list):
            raise ValueError("is_secure should be list of keys!")

        if is_secure:
            if not data or not isinstance(data, dict):
                raise ValueError("data cannot be empty and should be of type dict!")
            data_keys = set(data.keys())
            is_secure_set = set(is_secure)

            if not is_secure_set.issubset(data_keys):
                raise ValueError("is_secure contains keys that are not present in data")

        non_editable = values.get("is_non_editable")
        if not isinstance(non_editable, list):
            raise ValueError("is_non_editable should be a list of keys!")

        if non_editable:
            non_editable_set = set(non_editable)
            data_keys = set(data.keys())
            if not non_editable_set.issubset(data_keys):
                raise ValueError("is_non_editable contains keys that are not present in data")

        return values

class BulkCollectionDataRequest(BaseModel):
    collections: List[CollectionDataRequest]

class CognitiveDataRequest(BaseModel):
    data: Any
    content_type: CognitionDataType = CognitionDataType.text.value
    collection: constr(to_lower=True, strip_whitespace=True) = None

    @root_validator
    def check(cls, values):
        from kairon.shared.utils import Utility

        data = values.get("data")
        content_type = values.get("content_type")
        if isinstance(data, dict) and content_type != CognitionDataType.json.value:
            raise ValueError("content type and type of data do not match!")
        if not data or (isinstance(data, str) and Utility.check_empty_string(data)):
            raise ValueError("data cannot be empty")
        return values

class BulkDeleteRequest(BaseModel):
    row_ids: List[str]

    @root_validator
    def check(cls, values):
        row_ids = values.get("row_ids")
        if not row_ids or not isinstance(row_ids, list) or any(not row_id.strip() for row_id in row_ids):
            raise ValueError("row_ids must be a non-empty list of valid strings")

        return values

class RazorpayActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    api_key: CustomActionParameter
    api_secret: CustomActionParameter
    amount: CustomActionParameter
    currency: CustomActionParameter
    username: CustomActionParameter = None
    email: CustomActionParameter = None
    contact: CustomActionParameter = None
    notes: Optional[List[HttpActionParameters]]


class IntegrationRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    expiry_minutes: int = 0
    access_list: list = None
    role: ACCESS_ROLES = ACCESS_ROLES.CHAT.value
    status: INTEGRATION_STATUS = INTEGRATION_STATUS.ACTIVE.value


class KeyVaultRequest(BaseModel):
    key: str
    value: str

    @validator("key")
    def validate_key(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if not v or Utility.check_empty_string(v):
            raise ValueError("key is required")
        return v

    @validator("value")
    def validate_value(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if not v or Utility.check_empty_string(v):
            raise ValueError("value is required")
        return v


class EventConfig(BaseModel):
    ws_url: str
    headers: dict
    method: str

    @validator("ws_url")
    def validate_ws_url(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if not v or Utility.check_empty_string(v):
            raise ValueError("url can not be empty")
        return v

    @validator("headers")
    def validate_headers(cls, v, values, **kwargs):
        if not v or len(v) < 1:
            v = {}
        return v


class IDPConfig(BaseModel):
    config: dict
    organization: str

    @validator("config")
    def validate_config(cls, v, values, **kwargs):
        if not v or len(v) == 0:
            v = {}
        return v

    @validator("organization")
    def validate_organization(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if not v or Utility.check_empty_string(v):
            raise ValueError("Organization can not be empty")
        return v


class CallbackConfigRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    pyscript_code: str
    execution_mode: str = CallbackExecutionMode.ASYNC.value
    standalone: bool = False
    shorten_token: bool = False
    standalone_id_path: Optional[str] = None
    expire_in: int = 0
    response_type: str = CallbackResponseType.KAIRON_JSON.value


class CallbackActionConfigRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    callback_name: str
    dynamic_url_slot_name: Optional[str]
    metadata_list: list[HttpActionParameters] = []
    bot_response: Optional[str]
    dispatch_bot_response: bool = True


class ScheduleActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    schedule_time: CustomActionDynamicParameterModel
    timezone: str = None
    schedule_action: str
    response_text: Optional[str]
    params_list: Optional[List[HttpActionParameters]]
    dispatch_bot_response: bool = True
    schedule_action_type : str = ScheduleActionType.PYSCRIPT.value

    @root_validator
    def validate_name(cls, values):
        from kairon.shared.utils import Utility

        if not values.get("name") or Utility.check_empty_string(values.get("name")):
            raise ValueError("Schedule action name can not be empty")

        if not values.get("schedule_action") or Utility.check_empty_string(values.get("schedule_action")):
            raise ValueError("Schedule action can not be empty, it is needed to execute on schedule time")

        return values



class FlowTagChangeRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    tag: str
    type: str

class PetpoojaMetaConfig(BaseModel):
    access_token: str
    catalog_id: str

class PetpoojaSyncOptions(BaseModel):
    process_push_menu: bool
    process_item_toggle: bool

class POSIntegrationRequest(BaseModel):
    provider: str = Field(..., alias="connector_type")
    config: dict
    meta_config: Optional[PetpoojaMetaConfig]
    smart_catalog_enabled: bool
    meta_enabled: bool
    sync_options: Union[PetpoojaSyncOptions]

    @root_validator(pre=True)
    def validate_sync_options_by_provider(cls, values):
        provider = values.get("connector_type")
        sync_options = values.get("sync_options")

        if provider == "petpooja":
            try:
                values["sync_options"] = PetpoojaSyncOptions(**sync_options)
            except Exception as e:
                raise ValueError(f"Invalid sync_options for petpooja: {e}")

        return values

class ParallelActionRequest(BaseModel):
    """
    Model to store the configuration for parallel actions.
    """
    name: constr(to_lower=True, strip_whitespace=True)
    dispatch_response_text: bool = False
    response_text: Optional[str]
    actions: List[str]

    #Add validation for actions should not be empty
    @root_validator
    def validate_no_nested_parallel_actions(cls, values):
        action_names = values.get("actions", [])

        if not action_names:
            raise ValueError("The 'actions' field must contain at least one action.")

        existing = Actions.objects(name__in=action_names, type=ActionType.parallel_action.value).only("name") # Check if any of the actions are of type 'parallel_action'
        if existing:
            names = [a.name for a in existing]
            raise ValueError(f"ParallelAction cannot include other parallel actions: {names}")
        return values
