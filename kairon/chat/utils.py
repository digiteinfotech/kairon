from typing import Text
from .agent_processor import AgentProcessor


class ChatUtils:

    @staticmethod
    async def chat(data: Text, bot: Text, user: Text):
        model = AgentProcessor.get_agent(bot)
        chat_response = await model.handle_text(
            data, sender_id=user
        )
        return chat_response

    @staticmethod
    async def reload(bot: Text):
        AgentProcessor.reload(bot)


