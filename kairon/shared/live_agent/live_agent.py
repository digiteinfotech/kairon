import logging

from kairon.shared.actions.utils import ActionUtility
from rasa.core.channels import UserMessage

from kairon import Utility
from kairon.shared.data.data_objects import BotSettings

logger = logging.getLogger(__name__)


class LiveAgentHandler:
    @staticmethod
    def is_live_agent_service_enabled():
        v = Utility.environment.get('live_agent', {}).get('enable', False)
        return v

    @staticmethod
    def is_live_agent_service_available(bot_id: str) -> bool:
        if not LiveAgentHandler.is_live_agent_service_enabled():
            return False
        try:
            bot_setting = BotSettings.objects(bot=bot_id).get().to_mongo().to_dict()
            return bot_setting.get('live_agent_enabled', False)
        except Exception as e:
            logger.error(f"Error accessing bot settings: {repr(e)}")
            return False

    @staticmethod
    def get_channel(userdata: UserMessage):
        channel = userdata.output_channel.name()
        # output channel not set -> web
        if channel == 'collector':
            channel = 'web'
        return channel

    @staticmethod
    async def request_live_agent(bot_id: str, sender_id: str, channel: str):
        if not LiveAgentHandler.is_live_agent_service_available(bot_id):
            return {'msg': 'Live agent service is not available'}
        url = f"{Utility.environment['live_agent']['url']}/conversation/request"
        auth_token = Utility.environment['live_agent']['auth_token']
        data = {
            "bot_id": bot_id,
            "sender_id": sender_id,
            "channel": channel,
        }
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {auth_token}"
        }
        res, status, _, _ = await ActionUtility.execute_request_async(url, 'POST', data, headers)
        if status != 200:
            raise Exception(res.get('message', "Failed to process request"))
        return res.get('data')

    @staticmethod
    async def process_live_agent(bot_id, userdata: UserMessage):
        if not LiveAgentHandler.is_live_agent_service_available(bot_id):
            raise Exception("Live agent service is not enabled")
        text = userdata.text
        if text is None or text.strip() == "":
            return False
        url = f"{Utility.environment['live_agent']['url']}/conversation/chat"
        auth_token = Utility.environment['live_agent']['auth_token']
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {auth_token}"
        }
        data = {
            "bot_id": bot_id,
            "sender_id": userdata.sender_id,
            "channel": LiveAgentHandler.get_channel(userdata),
            "message": userdata.text
        }
        res, status, _, _ = await ActionUtility.execute_request_async(url, 'POST', data, headers)
        if status != 200:
            raise Exception("Failed to process request")

    @staticmethod
    async def check_live_agent_active(bot_id, userdata: UserMessage):
        if not LiveAgentHandler.is_live_agent_service_available(bot_id):
            return False
        channel = LiveAgentHandler.get_channel(userdata)
        sender_id = userdata.sender_id
        url = f"{Utility.environment['live_agent']['url']}/conversation/status/{bot_id}/{channel}/{sender_id}"
        auth_token = Utility.environment['live_agent']['auth_token']
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {auth_token}"
        }
        res, status, _, _ = await ActionUtility.execute_request_async(url, 'GET', None, headers)
        if status != 200:
            logger.error(res.get('message', "Failed to process request"))
            return False
        return res['data']['status']

    @staticmethod
    async def authenticate_agent(user, bot_id):
        if not LiveAgentHandler.is_live_agent_service_available(bot_id):
            return None
        url = f"{Utility.environment['live_agent']['url']}/auth"
        data = {
            "bot_id": bot_id,
            "user": user
        }
        auth_token = Utility.environment['live_agent']['auth_token']
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {auth_token}"
        }
        res, status, _, _ = await ActionUtility.execute_request_async(url, 'POST', data, headers)
        logger.info(res)
        if status != 200:
            if not res:
                res = {}
            logger.warning(res.get('data', {}).get('message', "Failed to authenticate live agent"))
            return None
        return res.get('data')

