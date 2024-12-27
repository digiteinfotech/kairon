import json

from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
from kairon.shared.constants import ElementTypes


class MessengerResponseConverter(ElementTransformerOps):

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
            raise Exception(f" Error in MessengerResponseConverter::message_extractor {str(ex)}")

    def link_transformer(self, message):
        try:
            link_extract = self.message_extractor(message, self.message_type)
            message_template = ElementTransformerOps.getChannelConfig(self.channel_type, self.message_type)
            if message_template is not None:
                response = ElementTransformerOps.replace_strategy(message_template, link_extract, self.channel_type,
                                                                  self.message_type)
                return response
        except Exception as ex:
            raise Exception(f" Error in MessengerResponseConverter::link_transformer {str(ex)}")

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
                        final_text += text
                    final_text += "\n"

            paragraph_template["text"] = final_text
            return paragraph_template
        except Exception as ex:
            raise Exception(f"Error in MessengerResponseConverter::paragraph_transformer {str(ex)}")

    def button_transformer(self, message):
        try:
            button_json_temp = {}
            jsoniterator = ElementTransformerOps.json_generator(message)
            buttons = []
            body_default = ElementTransformerOps.getChannelConfig(self.channel, "body_message")
            for item in jsoniterator:
                if item.get("type") == ElementTypes.BUTTON.value:
                    title = ElementTransformerOps.json_generator(item.get("children"))
                    for titletext in title:
                        button_text = titletext.get("text")
                    btn_body = {}
                    btn_body.update({"type": "postback", "title": button_text, "payload": item.get("value")})
                    buttons.append(btn_body)
            payload_data = {"template_type": "button", "text": body_default, "buttons": buttons}
            button_json_temp.update({"attachment": {"type": "template", "payload": payload_data}})
            return button_json_temp
        except Exception as ex:
            raise Exception(f"Exception in MessengerResponseConverter::button_transformer: {str(ex)}")

    def quick_reply_transformer(self, message):
        try:
            quick_replies_json_temp = {}
            jsoniterator = ElementTransformerOps.json_generator(message)
            quick_replies = []
            body_default = ElementTransformerOps.getChannelConfig(self.channel, "body_message")
            for item in jsoniterator:
                if item.get("type") == ElementTypes.QUICK_REPLY.value:
                    title = ElementTransformerOps.json_generator(item.get("children"))
                    for titletext in title:
                        text = titletext.get("text")
                    quick_reply_body = {}
                    if item.get('content_type') == "text":
                        quick_reply_body.update({"content_type": "text", "title": text,
                                                 "payload": item.get("value"), "image_url": item.get("image_url")})
                    else:
                        quick_reply_body.update({"content_type": text})
                    quick_replies.append(quick_reply_body)
            quick_replies_json_temp.update({"text": body_default, "quick_replies": quick_replies})
            return quick_replies_json_temp
        except Exception as ex:
            raise Exception(f"Exception in MessengerResponseConverter::quick_reply_transformer: {str(ex)}")

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
            elif self.message_type == ElementTypes.QUICK_REPLY.value:
                return self.quick_reply_transformer(message)
            elif self.message_type == ElementTypes.FORMAT_TEXT.value:
                return self.paragraph_transformer(message)
        except Exception as ex:
            raise Exception(f"Error in MessengerResponseConverter::messageConverter {str(ex)}")
