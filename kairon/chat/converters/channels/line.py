from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
import ujson as json
from kairon.shared.constants import ElementTypes


class LineResponseConverter(ElementTransformerOps):
    def __init__(self, message_type, channel_type):
        super().__init__(message_type, channel_type)
        self.message_type = message_type
        self.channel_type = channel_type

    def message_extractor(self, json_message, message_type):
        try:
            if message_type in {ElementTypes.IMAGE.value, ElementTypes.VIDEO.value, ElementTypes.AUDIO.value}:
                return super().message_extractor(json_message, message_type)
            elif message_type == ElementTypes.LINK.value:
                jsoniterator = ElementTransformerOps.json_generator(json_message)
                stringbuilder = ElementTransformerOps.convertjson_to_link_format(jsoniterator, bind_display_str=False)
                body = {"data": stringbuilder}
                return body
        except Exception as ex:
            raise Exception(f" Error in LineResponseConverter::message_extractor {str(ex)}")

    def link_transformer(self, message):
        try:
            link_extract = self.message_extractor(message, self.message_type)
            message_template = ElementTransformerOps.getChannelConfig(self.channel_type, self.message_type)
            if message_template is not None:
                response = ElementTransformerOps.replace_strategy(message_template, link_extract, self.channel_type,
                                                                  self.message_type)
                return response
        except Exception as ex:
            raise Exception(f" Error in LineResponseConverter::link_transformer {str(ex)}")

    def image_transformer(self, message):
        try:
            image_extract = self.message_extractor(message, self.message_type)
            message_template = ElementTransformerOps.getChannelConfig(self.channel_type, self.message_type)
            if message_template is not None:
                response = ElementTransformerOps.replace_strategy(message_template, image_extract, self.channel_type,
                                                                  self.message_type)
                return response
        except Exception as ex:
            raise Exception(f" Error in LineResponseConverter::image_transformer {str(ex)}")