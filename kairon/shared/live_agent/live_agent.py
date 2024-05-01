import aiohttp
import logging
from kairon.shared.actions.utils import ActionUtility
from rasa.core.channels import UserMessage

from kairon import Utility
from kairon.shared.chat.processor import ChatDataProcessor

logger = logging.getLogger(__name__)


class LiveAgentHandler:

    @staticmethod
    async def request_live_agent(bot_id: str, sender_id: str, channel: str):
        url = f"{Utility.environment['live_agent']['url']}/conversation/request"

        data = {
            "bot_id": bot_id,
            "sender_id": sender_id,
            "channel": channel,
        }
        res, status, _ = await ActionUtility.execute_request_async(url, 'POST', data)
        if status != 200:
            raise Exception(res.get('message', "Failed to process request"))
        return res.get('data')


    @staticmethod
    async def close_conversation(identifier):
        url = f"{Utility.environment['live_agent']['url']}/conversation/close/{identifier}"
        headers = {
            'Content-Type': 'application/json'
        }
        res, status, _ = await ActionUtility.execute_request_async(url, 'GET', None, headers)
        if status != 200:
            raise Exception(res.get('message', "Failed to process request"))
        return res.get('data')

    @staticmethod
    async def process_live_agent(bot_id, userdata: UserMessage):
        text = userdata.text
        if text is None or text.strip() == "":
            return False
        url = f"{Utility.environment['live_agent']['url']}/conversation/chat"
        headers = {
            'Content-Type': 'application/json'
        }
        data = {
            "bot_id": bot_id,
            "sender_id": userdata.sender_id,
            "channel": userdata.output_channel.name(),
            "message": userdata.text
        }

        res, status, _ = await ActionUtility.execute_request_async(url, 'POST', data, headers)
        if status != 200:
            raise Exception(res.get('message', "Failed to process request"))

    @staticmethod
    async def check_live_agent_active(bot_id, userdata: UserMessage):
        channel = userdata.output_channel.name()
        sender_id = userdata.sender_id
        url = f"{Utility.environment['live_agent']['url']}/conversation/status/{bot_id}/{channel}/{sender_id}"

        res, status, _ = await ActionUtility.execute_request_async(url, 'GET')
        if status != 200:
            raise Exception(res.get('message', "Failed to process request"))
        return res['data']['status']

    @staticmethod
    async def authenticate_agent(user, bot_id):
        url = f"{Utility.environment['live_agent']['url']}/auth"
        data = {
            "bot_id": bot_id,
            "user": user
        }
        res, status, _ = await ActionUtility.execute_request_async(url, 'POST', data)
        logger.info(res)
        if status != 200:
            raise Exception(res.get('message', "Failed to process request"))
        return res.get('data')
