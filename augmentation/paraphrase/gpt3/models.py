from pydantic import BaseModel
from typing import Any


class Response(BaseModel):
    """ This class defines the variables (and their types) that will be defined in the response
            message when a HTTP error is detected """

    success: bool = True
    message: str = None
    data: Any
    error_code: int = 0


class GPTRequest(BaseModel):
    """ This class defines the variables (and their types) that will be defined in the request
                    message"""
    api_key: str
    data: list
    engine: str = "davinci"
    temperature: float = 0.75
    max_tokens: int = 100
    num_responses: int = 10

