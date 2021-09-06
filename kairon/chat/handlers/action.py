import logging
from abc import ABC

from kairon.shared.tornado.handlers.base import BaseHandler
from tornado.escape import json_decode, json_encode
from ..utils import ChatUtils
from kairon.shared.models import User

logger = logging.getLogger(__name__)


class ChatHandler(BaseHandler, ABC):

    async def post(self, bot: str):
        success = True
        message = None
        response = None
        error_code = 0
        try:
            user: User = super().authenticate(self.request)
            body = json_decode(self.request.body.decode("utf8"))
            response = {"response": await ChatUtils.chat(body.get("data"), bot, user.get_user()) }
            logger.info(f"text={body.get('data')} response={response}")
        except Exception as e:
            message = str(e)
            error_code = 422
            success = False
        self.set_status(200)
        self.write(json_encode({"data": response, "success": success, "error_code": error_code, "message": message}))
