from pydantic import ConfigDict
from kairon.shared.pydantic_compat import KaironModel

from kairon.shared.custom_widgets.constants import CustomWidgetParameterType

from typing import Optional, List, Dict, Any
import validators


class HttpRequestParametersRequest(KaironModel):
    key: str
    value: str
    parameter_type: CustomWidgetParameterType = CustomWidgetParameterType.value.value


class CustomWidgetsRequest(KaironModel):
    name: str
    http_url: str
    request_method: str = "GET"
    request_parameters: Optional[List[HttpRequestParametersRequest]] = None
    dynamic_parameters: Optional[str] = None
    headers: Optional[List[HttpRequestParametersRequest]] = None

class GlobalFilterConfigRequest(KaironModel):
    global_config: List[Dict[str, Any]]

    model_config = ConfigDict(extra='allow')
