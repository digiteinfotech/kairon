from abc import ABC

from tornado.escape import json_encode
from tornado.web import RequestHandler, Finish
from tornado.httputil import HTTPServerRequest
from ..auth import TornadoAuthenticate
from typing import Text, Any, Union
from loguru import logger


class BaseHandler(RequestHandler, ABC):

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.set_header("Content-Type", 'application/json')
        self.set_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
        self.set_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'self'; form-action 'self';")
        self.set_header("X-Content-Type-Options", 'no-sniff')
        self.set_header("Referrer-Policy", 'origin')
        self.set_header("Permissions-Policy",
                        'accelerometer=(self), ambient-light-sensor=(self), autoplay=(self), battery=(self), camera=(self), cross-origin-isolated=(self), display-capture=(self), document-domain=(self), encrypted-media=(self), execution-while-not-rendered=(self), execution-while-out-of-viewport=(self), fullscreen=(self), geolocation=(self), gyroscope=(self), keyboard-map=(self), magnetometer=(self), microphone=(self), midi=(self), navigation-override=(self), payment=(self), picture-in-picture=(self), publickey-credentials-get=(self), screen-wake-lock=(self), sync-xhr=(self), usb=(self), web-share=(self), xr-spatial-tracking=(self)')
        self.set_header("server", 'Secure')
        self.set_header("Cache-Control", 'no-store')

    def options(self):
        self.set_status(204)
        self.finish()

    def authenticate(self, request: HTTPServerRequest, **kwargs):
        return TornadoAuthenticate.get_current_user_and_bot(request, **kwargs)

    def authenticate_channel(self, token: Text, bot: Text, request: HTTPServerRequest):
        return TornadoAuthenticate.get_current_user_and_bot_for_channel(token, bot, request)

    def prepare(self):
        logger.debug(self.request)

    def _handle_request_exception(self, e) -> None:
        if isinstance(e, Finish):
            # Not an error; just finish the request without logging.
            if not self._finished:
                self.finish(*e.args)
            return
        logger.exception(e)

    def write_error(self, status_code: int, **kwargs: Any) -> None:
        msg = kwargs.get('msg') or self._reason
        self.write(json_encode({"data": None, "success": False, "error_code": 422, "message": msg}))

    def write(self, chunk: Union[str, bytes, dict]) -> None:
        super().write(chunk)
        logger.debug(chunk)
