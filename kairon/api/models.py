from enum import Enum
from typing import List, Any, Dict
import validators
from kairon.data_processor.constant import TRAINING_DATA_GENERATOR_STATUS
from kairon.exceptions import AppException

ValidationFailure = validators.ValidationFailure
from pydantic import BaseModel, validator, SecretStr, root_validator


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str


class User(BaseModel):
    email: str
    first_name: str
    last_name: str
    bot: str
    account: int
    status: bool
    alias_user: str = None
    is_integration_user: bool

    def get_bot(self):
        return self.bot

    def get_user(self):
        if self.is_integration_user:
            return self.alias_user
        return self.email

    def get_integration_status(self):
        if self.is_integration_user:
            return True
        return False


class Response(BaseModel):
    success: bool = True
    message: str = None
    data: Any
    error_code: int = 0


class RequestData(BaseModel):
    data: Any


class TextData(BaseModel):
    data: str


class ListData(BaseModel):
    data: List[str]


class StoryEventType(str, Enum):
    user = "user"
    action = "action"
    form = "form"
    slot = "slot"


class StoryEventRequest(BaseModel):
    name: str
    type: StoryEventType
    value: str = None


class StoryRequest(BaseModel):
    name: str
    events: List[StoryEventRequest]

    def get_events(self):
        return [event.dict() for event in self.events]


class RegisterAccount(BaseModel):
    email: str
    first_name: str
    last_name: str
    password: SecretStr
    confirm_password: SecretStr
    account: str
    bot: str

    # file deepcode ignore E0213: Method definition is predefined
    @validator("password")
    def validate_password(cls, v, values, **kwargs):
        from kairon.utils import Utility

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


class EndPointTracker(BaseModel):
    type: str = "mongo"
    url: str
    db: str
    username: str = None
    password: str = None
    auth_source: str = None


class Endpoint(BaseModel):
    bot_endpoint: EndPointBot = None
    action_endpoint: EndPointAction = None
    tracker_endpoint: EndPointTracker = None


class Config(BaseModel):
    language: str = "en"
    pipeline: List[Dict]
    policies: List[Dict]


class Password(BaseModel):
    data: str
    password: SecretStr
    confirm_password: SecretStr

    @validator("password")
    def validate_password(cls, v, values, **kwargs):
        from kairon.utils import Utility

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


class History_Month_Enum(int, Enum):
    One = 1
    Two = 2
    Three = 3
    Four = 4
    Five = 5
    Six = 6


class HistoryMonth(BaseModel):
    month: History_Month_Enum


class ParameterChoice(str, Enum):
    value = "value"
    slot = "slot"
    sender_id = "sender_id"


class HttpActionParameters(BaseModel):
    key: str
    value: str = None
    parameter_type: ParameterChoice

    @root_validator
    def check(cls, values):
        from kairon.utils import Utility

        if Utility.check_empty_string(values.get('key')):
            raise ValueError("key cannot be empty")

        if values.get('parameter_type') == ParameterChoice.slot and Utility.check_empty_string(values.get('value')):
            raise ValueError("Provide name of the slot as value")
        return values


class HttpActionConfigRequest(BaseModel):
    auth_token: str = None
    action_name: str
    response: str
    http_url: str
    request_method: str
    http_params_list: List[HttpActionParameters] = None

    def get_http_params(self):
        return [param.dict() for param in self.http_params_list]

    @validator("action_name")
    def validate_action_name(cls, v, values, **kwargs):
        from kairon.utils import Utility

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
    intent: str
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
    status: TRAINING_DATA_GENERATOR_STATUS
    response: List[TrainingData] = None
    exception: str = None


class StoryStepType(str, Enum):
    intent = "INTENT"
    bot = "BOT"
    http_action = "HTTP_ACTION"


class StoryStepRequest(BaseModel):
    name: str
    type: StoryStepType


class AddStoryRequest(BaseModel):
    name: str
    steps: List[StoryStepRequest]

    def get_steps(self):
        return [step.dict() for step in self.steps]

    @validator("steps")
    def validate_request_method(cls, v, values, **kwargs):
        if not v:
            raise ValueError("Steps are required to form story")

        if v[0].type != StoryStepType.intent:
            raise ValueError("First step should be an intent")

        if v[len(v)-1].type == StoryStepType.intent:
            raise ValueError("Intent should be followed by utterance or action")

        for i, j in enumerate(range(1, len(v))):
            if v[i].type == StoryStepType.intent and v[j].type == StoryStepType.intent:
                raise ValueError("Found 2 consecutive intents")

        action_cnt_for_intent = {}
        intent = ""
        for step in v:
            if step.type == StoryStepType.intent:
                intent = step.name
                continue
            if step.type == StoryStepType.http_action:
                num_http_actions = action_cnt_for_intent.get(intent)
                if not num_http_actions:
                    num_http_actions = 0
                elif num_http_actions >= 1:
                    raise ValueError("You can have only one Http action against an intent")
                action_cnt_for_intent[intent] = num_http_actions + 1
        return v


class SimpleStoryRequest(BaseModel):
    action: str
    intent: str


class FeedbackRequest(BaseModel):
    rating: float
    scale: float = 5
    feedback: str = None


class GPTRequest(BaseModel):
    api_key: str
    data: list
    engine: str = "davinci"
    temperature: float = 0.75
    max_tokens: int = 100
    num_responses: int = 10
