from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
from kairon.chat.converters.channels.constants import ELEMENT_TYPE

class SlackMessageConverter(ElementTransformerOps):

    def __init__(self, message_type, channel_type):
        super().__init__(message_type, channel_type)
        self.message_type = message_type
        self.channel_type = channel_type

    async def messageConverter(self, message):
        try:
            if self.message_type == ELEMENT_TYPE.IMAGE.value:
                return super().image_transformer(message)
            elif self.message_type == ELEMENT_TYPE.LINK.value:
                return super().link_transformer(message)
            elif self.message_type == ELEMENT_TYPE.VIDEO.value:
                return super().video_transformer(message)
        except Exception as ex:
            raise Exception(f"Error in SlackMessageConverter::messageConverter {str(ex)}")