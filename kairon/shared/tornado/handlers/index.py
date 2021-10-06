from abc import ABC

from .base import BaseHandler


class IndexHandler(BaseHandler, ABC):
    async def get(self):
        self.write("Kairon Server Running")

    async def post(self):
        self.write("Kairon Server Running")


