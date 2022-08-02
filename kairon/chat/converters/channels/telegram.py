from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
from kairon import Utility
from kairon.chat.converters.channels.constants import ELEMENT_TYPE

class TelegramResponseConverter(ElementTransformerOps):

    def __init__(self, message_type, channel_type):
        super().__init__(message_type, channel_type)
        self.message_type = message_type
        self.channel_type = channel_type

    def message_extractor(self, json_message, type):
        try:
            if type == ELEMENT_TYPE.IMAGE.value:
                return super().message_extractor(json_message, type)
            if type == ELEMENT_TYPE.LINK.value:
                jsoniterator = ElementTransformerOps.json_generator(json_message)
                stringbuilder = ElementTransformerOps.convertjson_to_link_format(jsoniterator, bind_display_str=False)
                body = {"data": stringbuilder}
                return body
        except Exception as ex:
            raise Exception(f" Error in TelegramResponseConverter::message_extractor {str(ex)}")

    def link_transformer(self, message):
        try:
            link_extract = self.message_extractor(message, self.type)
            message_template = ElementTransformerOps.getChannelConfig(self.channel_type, self.message_type)
            if message_template is not None:
                response = ElementTransformerOps.replace_strategy(message_template, link_extract, self.channel_type, self.message_type)
                return response
            else:
                message_config = Utility.system_metadata.get("No_Config_error_message")
                message_config = str(message_config).format(self.channel, self.type)
                raise Exception(message_config)
        except Exception as ex:
            raise Exception(f" Error in TelegramResponseConverter::link_transformer {str(ex)}")

    async def messageConverter(self, message):
        try:
            if self.message_type == ELEMENT_TYPE.IMAGE.value:
                return super().image_transformer(message)
            elif self.message_type == ELEMENT_TYPE.LINK.value:
                return self.link_transformer(message)
        except Exception as ex:
            raise Exception(f"Error in TelegramResponseConverter::messageConverter {str(ex)}")