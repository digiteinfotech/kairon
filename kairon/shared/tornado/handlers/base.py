from abc import ABC

from tornado.web import RequestHandler
from tornado.httputil import HTTPServerRequest
from ..auth import TornadoAuthenticate
from typing import Text


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
