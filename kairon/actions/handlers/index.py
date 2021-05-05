from abc import ABC

from tornado.web import RequestHandler


class MainHandler(RequestHandler, ABC):
    async def get(self):
        self.write("Kairon Action Server Running")


