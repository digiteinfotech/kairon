import traceback
from abc import ABC
from http import HTTPStatus

from tornado.escape import json_encode
from tornado.web import RequestHandler
from tornado.httputil import HTTPServerRequest
from ..auth import TornadoAuthenticate
from typing import Text, Any, Union
from loguru import logger

from ..exception import ServiceHandlerException


class BaseHandler(RequestHandler, ABC):

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "*")
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.set_header("Content-Type", 'application/json')
        self.set_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
        self.set_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'self'; form-action 'self';")
        self.set_header("X-Content-Type-Options", 'no-sniff')
        self.set_header("Referrer-Policy", 'no-referrer')
        self.set_header("Permissions-Policy",
                        'accelerometer=(self), ambient-light-sensor=(self), autoplay=(self), battery=(self), camera=(self), cross-origin-isolated=(self), display-capture=(self), document-domain=(self), encrypted-media=(self), execution-while-not-rendered=(self), execution-while-out-of-viewport=(self), fullscreen=(self), geolocation=(self), gyroscope=(self), keyboard-map=(self), magnetometer=(self), microphone=(self), midi=(self), navigation-override=(self), payment=(self), picture-in-picture=(self), publickey-credentials-get=(self), screen-wake-lock=(self), sync-xhr=(self), usb=(self), web-share=(self), xr-spatial-tracking=(self)')
        self.set_header("server", 'Secure')
        self.set_header("Cache-Control", 'no-store')

    def options(self, *args):
        self.set_status(200)
        self.finish()

    def authenticate(self, request: HTTPServerRequest, **kwargs):
        return TornadoAuthenticate.get_current_user_and_bot(request, **kwargs)

    def authenticate_channel(self, token: Text, bot: Text, request: HTTPServerRequest):
        return TornadoAuthenticate.get_current_user_and_bot_for_channel(token, bot, request)

    def write_error(self, status_code: int = 422, **kwargs: Any) -> None:
        headers = {}
        if "exc_info" in kwargs:
            logger.exception(traceback.format_exception(*kwargs["exc_info"]))
            if isinstance(kwargs['exc_info'][1], ServiceHandlerException):
                status_code = kwargs['exc_info'][1].status_code
                headers = kwargs['exc_info'][1].headers
                message = kwargs['exc_info'][1].message
            else:
                message = str(kwargs['exc_info'][1])
        else:
            message = kwargs.get('message') or self._reason
        self.set_status(HTTPStatus.UNPROCESSABLE_ENTITY)
        self.set_default_headers()
        self.set_extra_headers(**headers)
        self.write(json_encode({"data": None, "success": False, "error_code": status_code, "message": message}))

    def set_extra_headers(self, **kwargs):
        for header, value in kwargs.items():
            self.set_header(header, value)

    def write(self, chunk: Union[str, bytes, dict]) -> None:
        super().write(chunk)
        logger.debug(chunk)
        self.finish()
