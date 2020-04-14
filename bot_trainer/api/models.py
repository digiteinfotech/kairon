from pydantic import BaseModel
from typing import Dict, List, Any


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


class Response(BaseModel):
    success: bool = True
    message: str = ""
    data: Any
    error_code: int = 0


class RequestData(BaseModel):
    data: Any
