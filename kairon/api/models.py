from enum import Enum
from typing import List, Any, Dict
import validators
from kairon.data_processor.constant import EVENT_STATUS
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
    bot: list
    account: int
    status: bool
    alias_user: str = None
    is_integration_user: bool

    def get_bot(self):
        return self.bot[0]

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
    message: Any = None
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


class RasaConfig(BaseModel):
    language: str = "en"
    pipeline: List[Dict]
    policies: List[Dict]


class ComponentConfig(BaseModel):
    nlu_epochs: int = None
    response_epochs: int = None
    ted_epochs: int = None
    nlu_confidence_threshold: int = None
    action_fallback: str = None

    @validator('nlu_epochs', 'response_epochs', 'ted_epochs')
    def validate_epochs(cls, v):
        if v is not None and v < 1:
            raise ValueError("Choose a positive number as epochs")
        return v

    @validator("nlu_confidence_threshold")
    def validate_confidence_threshold(cls, v):
        if v and (v > 90 or v < 30):
            raise ValueError("Please choose a threshold between 30 and 90")
        return v


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
    status: EVENT_STATUS
    response: List[TrainingData] = None
    exception: str = None


class StoryStepType(str, Enum):
    intent = "INTENT"
    bot = "BOT"
    http_action = "HTTP_ACTION"
    action = "ACTION"


class StoryType(str, Enum):
    story = "STORY"
    rule = "RULE"


class StoryStepRequest(BaseModel):
    name: str
    type: StoryStepType


class StoryRequest(BaseModel):
    name: str
    type: StoryType
    steps: List[StoryStepRequest]

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
