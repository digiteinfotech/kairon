from abc import ABC


class ChannelHandlerBase(ABC):

    async def validate(self):
        raise NotImplementedError("Provider not implemented")

    async def handle_message(self):
        raise NotImplementedError("Provider not implemented")
