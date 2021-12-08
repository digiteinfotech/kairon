from typing import List, Any, Dict
import validators
from kairon.shared.data.constant import EVENT_STATUS, SLOT_MAPPING_TYPE, SLOT_TYPE
from ..shared.actions.models import SlotValidationOperators, LogicalOperators
from ..shared.constants import SLOT_SET_TYPE
from kairon.exceptions import AppException

ValidationFailure = validators.ValidationFailure
from pydantic import BaseModel, validator, SecretStr, root_validator, constr
from ..shared.models import StoryStepType, StoryType, TemplateType, ParameterChoice


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


class RequestData(BaseModel):
    data: Any


class TextData(BaseModel):
    data: str


class TextDataLowerCase(BaseModel):
    data: constr(to_lower=True, strip_whitespace=True)


class ListData(BaseModel):
    data: List[str]


class RegisterAccount(BaseModel):
    email: str
    first_name: str
    last_name: str
    password: SecretStr
    confirm_password: SecretStr
    account: str

    # file deepcode ignore E0213: Method definition is predefined
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

    @validator('nlu_epochs', 'response_epochs', 'ted_epochs')
    def validate_epochs(cls, v):
        if v is not None and v < 1:
            raise ValueError("Choose a positive number as epochs")
        return v

    @validator("nlu_confidence_threshold", "action_fallback_threshold")
    def validate_confidence_threshold(cls, v):
        if v is not None and (v < 0.3 or v > 0.9):
            raise ValueError("Please choose a threshold between 0.3 and 0.9")
        return v


class Password(BaseModel):
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
    parameter_type: ParameterChoice

    @root_validator
    def check(cls, values):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(values.get('key')):
            raise ValueError("key cannot be empty")

        if values.get('parameter_type') == ParameterChoice.slot and Utility.check_empty_string(values.get('value')):
            raise ValueError("Provide name of the slot as value")
        return values


class HttpActionConfigRequest(BaseModel):
    auth_token: str = None
    action_name: constr(to_lower=True, strip_whitespace=True)
    response: str
    http_url: str
    request_method: str
    http_params_list: List[HttpActionParameters] = None

    def get_http_params(self):
        return [param.dict() for param in self.http_params_list]

    @validator("action_name")
    def validate_action_name(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility

        if Utility.check_empty_string(v):
            raise ValueError("action_name is required")
        return v

    @validator("http_url")
    def validate_http_url(cls, v, values, **kwargs):
        if isinstance(validators.url(v), ValidationFailure):
            raise ValueError("URL is malformed")
        return v

    @validator("request_method")
    def validate_request_method(cls, v, values, **kwargs):
        if v.upper() not in ("GET", "POST", "PUT", "DELETE"):
            raise ValueError("Invalid HTTP method")
        return v.upper()


class HttpActionParametersResponse(BaseModel):
    key: str
    value: str
    parameter_type: str


class HttpActionConfigResponse(BaseModel):
    auth_token: str
    action_name: str
    response: str
    http_url: str
    request_method: str
    params_list: List[HttpActionParametersResponse]
    bot: str
    user: str


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
    name: constr(to_lower=True, strip_whitespace=True)
    type: StoryStepType


class StoryRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    type: StoryType
    steps: List[StoryStepRequest]
    template_type: TemplateType = None

    class Config:
        use_enum_values = True

    def get_steps(self):
        return [step.dict() for step in self.steps]

    @validator("steps")
    def validate_request_method(cls, v, values, **kwargs):
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
        if 'type' in values:
            if values['type'] == StoryType.rule and intents > 1:
                raise ValueError(f"""Found rules '{values['name']}' that contain more than intent.\nPlease use stories for this case""")
        return v


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
    auto_fill: bool = True
    values: List[str] = None
    max_value: float = None
    min_value: float = None
    influence_conversation: bool = False


class SynonymRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
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

    @validator("name")
    def validate_synonym(cls, f, values, **kwargs):
        from kairon.shared.utils import Utility
        if Utility.check_empty_string(f):
            raise ValueError("synonym cannot be empty")
        return f


class DictData(BaseModel):
    data: dict


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
    name: constr(to_lower=True, strip_whitespace=True)
    value: List[str]

    @validator("name")
    def validate_name(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility
        if Utility.check_empty_string(v):
            raise ValueError("name cannot be empty or a blank space")
        return v

    @validator("value")
    def validate_value(cls, v, values, **kwargs):
        from kairon.shared.utils import Utility
        if len(v) <= 0:
            raise ValueError("value field cannot be empty")
        for ele in v:
            if Utility.check_empty_string(ele):
                raise ValueError("lookup value cannot be empty or a blank space")
        return v


class SlotMapping(BaseModel):
    entity: str = None
    type: SLOT_MAPPING_TYPE
    value: Any = None
    intent: List[str] = None
    not_intent: List[str] = None


class Validation(BaseModel):
    operator: SlotValidationOperators
    value: Any


class Expression(BaseModel):
    logical_operator: LogicalOperators = None
    validations: List[Validation]


class SlotValidation(BaseModel):
    logical_operator: LogicalOperators = LogicalOperators.and_operator.value
    expressions: List[Expression]


class FormPath(BaseModel):
    responses: List[str]
    slot: str
    mapping: List[SlotMapping]
    validation: SlotValidation = None
    utter_msg_on_valid: str = None
    utter_msg_on_invalid: str = None


class Forms(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    path: List[FormPath]


class SlotSetActionRequest(BaseModel):
    name: constr(to_lower=True, strip_whitespace=True)
    slot: str
    type: SLOT_SET_TYPE
    value: Any = None
