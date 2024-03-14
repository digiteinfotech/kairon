from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
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

    def video_transformer(self, message):
        try:
            video_extract = self.message_extractor(message, self.message_type)
            message_template = ElementTransformerOps.getChannelConfig(self.channel_type, self.message_type)
            if message_template is not None:
                response = ElementTransformerOps.replace_strategy(message_template, video_extract, self.channel_type,
                                                                  self.message_type)
                return response
        except Exception as ex:
            raise Exception(f" Error in LineResponseConverter::video_transformer {str(ex)}")

    def button_transformer(self, message):
        try:
            jsoniterator = ElementTransformerOps.json_generator(message)
            buttons = []
            for item in jsoniterator:
                if item.get("type") == ElementTypes.BUTTON.value:
                    title = ElementTransformerOps.json_generator(item.get("children"))
                    for title_text in title:
                        button_text = title_text.get("text")
                    btn_body = {"type": "message"}
                    btn_body.update({"label": button_text})
                    btn_body.update({"data": item.get("value")})
                    buttons.append(btn_body)
            reply_markup = {"type": "template",
                            "altText": "", "template": {"type": "buttons",
                                                        "text": "",
                                                        "actions": buttons}}
            return reply_markup
        except Exception as ex:
            raise Exception(f"Exception in LineResponseConverter::button_transfomer: {str(ex)}")

    async def messageConverter(self, message):
        try:
            if self.message_type == ElementTypes.IMAGE.value:
                return self.image_transformer(message)
            elif self.message_type == ElementTypes.LINK.value:
                return self.link_transformer(message)
            elif self.message_type == ElementTypes.VIDEO.value:
                return self.video_transformer(message)
            elif self.message_type == ElementTypes.BUTTON.value:
                return self.button_transformer(message)
        except Exception as ex:
            raise Exception(f"Error in TelegramResponseConverter::messageConverter {str(ex)}")


