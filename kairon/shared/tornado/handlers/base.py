from abc import ABC

from tornado.web import RequestHandler
from tornado.httputil import HTTPServerRequest
from ..auth import TornadoAuthenticate


class BaseHandler(RequestHandler, ABC):

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.set_header("Content-Type", 'application/json')

    def options(self):
        self.set_status(204)
        self.finish()

    def authenticate(self, request: HTTPServerRequest):
        return TornadoAuthenticate.get_current_user(request)