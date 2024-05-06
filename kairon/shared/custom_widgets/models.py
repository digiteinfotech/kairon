from pydantic import BaseModel

from kairon.shared.custom_widgets.constants import CustomWidgetParameterType

from typing import List
import validators


class HttpRequestParametersRequest(BaseModel):
    key: str
    value: str
    parameter_type: CustomWidgetParameterType = CustomWidgetParameterType.value.value


class CustomWidgetsRequest(BaseModel):
    name: str
    http_url: str
    request_method: str = "GET"
    request_parameters: List[HttpRequestParametersRequest] = None
    dynamic_parameters: str = None
    headers: List[HttpRequestParametersRequest] = None
