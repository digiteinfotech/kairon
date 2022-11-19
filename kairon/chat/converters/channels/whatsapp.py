from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
from kairon.chat.converters.channels.constants import ELEMENT_TYPE
import json

class WhatsappResponseConverter(ElementTransformerOps):

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
            raise Exception(f" Error in WhatsappResponseConverter::message_extractor {str(ex)}")

    def link_transformer(self, message):
        try:
            link_extract = self.message_extractor(message, self.message_type)
            message_template = ElementTransformerOps.getChannelConfig(self.channel_type, self.message_type)
            if message_template is not None:
                response = ElementTransformerOps.replace_strategy(message_template, link_extract, self.channel_type, self.message_type)
                return response
        except Exception as ex:
            raise Exception(f"Error in WhatsappResponseConverter::link_transformer {str(ex)}")

    def button_transformer(self, message):
        try:
            message_template = ElementTransformerOps.getChannelConfig(self.channel, self.message_type)
            button_json_temp = json.loads(message_template)
            jsoniterator = ElementTransformerOps.json_generator(message)
            buttons = {"buttons":[]}
            body_default = ElementTransformerOps.getChannelConfig(self.channel, "body_message")
            body_msg = {"text":body_default}
            for item in jsoniterator:
                if item.get("type") == ELEMENT_TYPE.BUTTON.value:
                    title = ElementTransformerOps.json_generator(item.get("children"))
                    for titletext in title:
                        button_text = titletext.get("text")
                    btn_body = {}
                    btn_body.update({"type": "reply"})
                    btn_body.update({"reply":{"id":item.get("value"),"title":button_text}})
                    buttons["buttons"].append(btn_body)
            button_json_temp.update({"body":body_msg})
            button_json_temp.update({"action":buttons})
            return button_json_temp
        except Exception as ex:
            raise Exception(f"Exception in WhatsappResponseConverter::button_transfomer: {str(ex)}")

    async def messageConverter(self, message):
        try:
            if self.message_type == ELEMENT_TYPE.IMAGE.value:
                return super().image_transformer(message)
            elif self.message_type == ELEMENT_TYPE.LINK.value:
                return self.link_transformer(message)
            elif self.message_type == ELEMENT_TYPE.VIDEO.value:
                return super().video_transformer(message)
            elif self.message_type == ELEMENT_TYPE.BUTTON.value:
                return self.button_transformer(message)
        except Exception as ex:
            raise Exception(f"Error in WhatsappResponseConverter::messageConverter {str(ex)}")