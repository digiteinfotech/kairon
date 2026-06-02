import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from kairon.shared.request_context import REQUEST_ID_HEADER, set_request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Headers.get() is case-insensitive in Starlette — satisfies R2
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = incoming if incoming else str(uuid.uuid4())
        set_request_id(request_id)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def register_request_id_middleware(app) -> None:
    app.add_middleware(RequestIdMiddleware)
