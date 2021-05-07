from abc import ABC

from .base import BaseHandler


class MainHandler(BaseHandler, ABC):
    async def get(self):
        self.write("Kairon Action Server Running")

    async def post(self):
        self.write("Kairon Action Server Running")


