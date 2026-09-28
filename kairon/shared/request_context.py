from contextvars import ContextVar
from typing import Optional

REQUEST_ID_HEADER = "X-Kairon-Request-ID"
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)
