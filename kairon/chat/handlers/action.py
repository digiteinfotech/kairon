import logging
from abc import ABC

from kairon.shared.tornado.handlers.base import BaseHandler
from tornado.escape import json_decode, json_encode
from ..utils import ChatUtils
from kairon.shared.models import User
from tornado import concurrent

from ...live_agent.live_agent import LiveAgent
from tornado.web import HTTPError

executor = concurrent.futures.ThreadPoolExecutor(2)

logger = logging.getLogger(__name__)


class ChatHandler(BaseHandler, ABC):

    async def post(self, bot: str):
        success = True
        message = None
        response = None
        error_code = 0
        try:
            user: User = super().authenticate(self.request, bot=bot)
            body = json_decode(self.request.body.decode("utf8"))
            response = await ChatUtils.chat(body.get("data"), user.account, bot, user.get_user(),
                                            user.is_integration_user)
            logger.info(f"text={body.get('data')} response={response}")
        except HTTPError as ex:
            logger.exception(ex)
            message = str(ex.reason)
            error_code = ex.status_code
            success = False
        except Exception as e:
            logger.exception(e)
            message = str(e)
            error_code = 422
            success = False
        self.set_status(200)
        self.write(json_encode({"data": response, "success": success, "error_code": error_code, "message": message}))


class ReloadHandler(BaseHandler, ABC):

    async def get(self, bot: str):
        success = True
        message = "Reloading Model!"
        response = None
        error_code = 0
        try:
            user: User = super().authenticate(self.request, bot=bot)
            executor.submit(ChatUtils.reload, bot)
        except HTTPError as ex:
            logger.exception(ex)
            message = str(ex.reason)
            error_code = ex.status_code
            success = False
        except Exception as e:
            logger.exception(e)
            message = str(e)
            error_code = 422
            success = False
        self.set_status(200)
        self.write(json_encode({"data": response, "success": success, "error_code": error_code, "message": message}))


class LiveAgentHandler(BaseHandler, ABC):

    async def post(self, bot: str, destination: str):
        success = True
        message = None
        response = None
        error_code = 0
        try:
            user: User = super().authenticate(self.request, bot=bot)
            body = json_decode(self.request.body.decode("utf8"))
            response = {"response": LiveAgent.from_bot(bot).send_message(body.get("data"), destination)}
            logger.info(f"text={body.get('data')} response={response}")
        except HTTPError as ex:
            logger.exception(ex)
            message = str(ex.reason)
            error_code = ex.status_code
            success = False
        except Exception as e:
            logger.exception(e)
            message = str(e)
            error_code = 422
            success = False
        self.set_status(200)
        self.write(json_encode({"data": response, "success": success, "error_code": error_code, "message": message}))


class SessionConversationHandler(BaseHandler, ABC):

    async def get(self, bot: str):
        success = True
        response = None
        error_code = 0
        try:
            user: User = super().authenticate(self.request, bot=bot)
            response, message = ChatUtils.get_last_session_conversation(bot, user.get_user())
        except HTTPError as ex:
            logger.exception(ex)
            message = str(ex.reason)
            error_code = ex.status_code
            success = False
        except Exception as e:
            logger.exception(e)
            message = str(e)
            error_code = 422
            success = False
        self.set_status(200)
        self.write(json_encode({"data": response, "success": success, "error_code": error_code, "message": message}))
