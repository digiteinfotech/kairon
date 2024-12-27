import json

from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
from kairon.shared.constants import ElementTypes


class TelegramResponseConverter(ElementTransformerOps):

    def __init__(self, message_type, channel_type):
        super().__init__(message_type, channel_type)
        self.message_type = message_type
        self.channel_type = channel_type

    def message_extractor(self, json_message, message_type):
        try:
            if message_type == ElementTypes.IMAGE.value:
                return super().message_extractor(json_message, message_type)
            if message_type == ElementTypes.LINK.value:
                jsoniterator = ElementTransformerOps.json_generator(json_message)
                stringbuilder = ElementTransformerOps.convertjson_to_link_format(jsoniterator, bind_display_str=False)
                body = {"data": stringbuilder}
                return body
            if message_type == ElementTypes.VIDEO.value:
                return super().message_extractor(json_message, message_type)
        except Exception as ex:
            raise Exception(f" Error in TelegramResponseConverter::message_extractor {str(ex)}")

    def link_transformer(self, message):
        try:
            link_extract = self.message_extractor(message, self.message_type)
            message_template = ElementTransformerOps.getChannelConfig(self.channel_type, self.message_type)
            if message_template is not None:
                response = ElementTransformerOps.replace_strategy(message_template, link_extract, self.channel_type,
                                                                  self.message_type)
                return response
        except Exception as ex:
            raise Exception(f" Error in TelegramResponseConverter::link_transformer {str(ex)}")

    def paragraph_transformer(self, message):
        try:
            message_template = ElementTransformerOps.getChannelConfig(self.channel, self.message_type)
            paragraph_template = json.loads(message_template)
            jsoniterator = ElementTransformerOps.json_generator(message)
            final_text = ""
            for item in jsoniterator:
                if item.get("type") == "paragraph":
                    children = ElementTransformerOps.json_generator(item.get("children", []))
                    for child in children:
                        text = child.get("text", "")
                        leading_spaces = len(text) - len(text.lstrip())
                        trailing_spaces = len(text) - len(text.rstrip())
                        text = text.strip()
                        if child.get("bold"):
                            text = f"<b>{text}</b>"
                        if child.get("italic"):
                            text = f"<i>{text}</i>"
                        if child.get("strikethrough"):
                            text = f"<s>{text}</s>"
                        final_text += f"{' ' * leading_spaces}{text}{' ' * trailing_spaces}"
                    final_text += "\n"

            paragraph_template["text"] = final_text
            return paragraph_template
        except Exception as ex:
            raise Exception(f"Error in TelegramResponseConverter::paragraph_transformer {str(ex)}")

    def button_transformer(self, message):
        try:
            jsoniterator = ElementTransformerOps.json_generator(message)
            reply_markup = {}
            inline_keyboard = []
            reply_markup.update({"inline_keyboard": inline_keyboard})
            inline_keyboard_array = []
            for item in jsoniterator:
                if item.get("type") == ElementTypes.BUTTON.value:
                    title = ElementTransformerOps.json_generator(item.get("children"))
                    for titletext in title:
                        button_text = titletext.get("text")
                    btn_body = {}
                    btn_body.update({"text": button_text})
                    btn_body.update({"callback_data": item.get("value")})
                    inline_keyboard_array.append(btn_body)
            inline_keyboard.append(inline_keyboard_array)
            return reply_markup
        except Exception as ex:
            raise Exception(f"Exception in TelegramResponseConverter::button_transfomer: {str(ex)}")

    async def messageConverter(self, message):
        try:
            if self.message_type == ElementTypes.IMAGE.value:
                return super().image_transformer(message)
            elif self.message_type == ElementTypes.LINK.value:
                return self.link_transformer(message)
            elif self.message_type == ElementTypes.VIDEO.value:
                return super().video_transformer(message)
            elif self.message_type == ElementTypes.BUTTON.value:
                return self.button_transformer(message)
            elif self.message_type == ElementTypes.FORMAT_TEXT.value:
                return self.paragraph_transformer(message)
        except Exception as ex:
            raise Exception(f"Error in TelegramResponseConverter::messageConverter {str(ex)}")
