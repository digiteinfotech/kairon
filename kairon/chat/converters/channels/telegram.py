from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
from kairon.chat.converters.channels.constants import ELEMENT_TYPE

class TelegramResponseConverter(ElementTransformerOps):

    def __init__(self, message_type, channel_type):
        super().__init__(message_type, channel_type)
        self.message_type = message_type
        self.channel_type = channel_type

    def message_extractor(self, json_message, message_type):
        try:
            if message_type == ELEMENT_TYPE.IMAGE.value:
                return super().message_extractor(json_message, message_type)
            if message_type == ELEMENT_TYPE.LINK.value:
                jsoniterator = ElementTransformerOps.json_generator(json_message)
                stringbuilder = ElementTransformerOps.convertjson_to_link_format(jsoniterator, bind_display_str=False)
                body = {"data": stringbuilder}
                return body
            if message_type == ELEMENT_TYPE.VIDEO.value:
                return super().message_extractor(json_message, message_type)
        except Exception as ex:
            raise Exception(f" Error in TelegramResponseConverter::message_extractor {str(ex)}")

    def link_transformer(self, message):
        try:
            link_extract = self.message_extractor(message, self.message_type)
            message_template = ElementTransformerOps.getChannelConfig(self.channel_type, self.message_type)
            if message_template is not None:
                response = ElementTransformerOps.replace_strategy(message_template, link_extract, self.channel_type, self.message_type)
                return response
        except Exception as ex:
            raise Exception(f" Error in TelegramResponseConverter::link_transformer {str(ex)}")

    async def messageConverter(self, message):
        try:
            if self.message_type == ELEMENT_TYPE.IMAGE.value:
                return super().image_transformer(message)
            elif self.message_type == ELEMENT_TYPE.LINK.value:
                return self.link_transformer(message)
            elif self.message_type == ELEMENT_TYPE.VIDEO.value:
                return super().video_transformer(message)
        except Exception as ex:
            raise Exception(f"Error in TelegramResponseConverter::messageConverter {str(ex)}")