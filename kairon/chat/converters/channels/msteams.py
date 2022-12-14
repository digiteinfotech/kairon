from kairon.chat.converters.channels.constants import ELEMENT_TYPE
from kairon.chat.converters.channels.responseconverter import ElementTransformerOps


class MSTeamsResponseConverter(ElementTransformerOps):

    def __init__(self,message_type, channel_type):
        super().__init__(message_type, channel_type)
        self.message_type = message_type
        self.channel_type = channel_type

    def link_transformer(self, message):
        try:
            jsoniterator = ElementTransformerOps.json_generator(message)
            stringbuilder = ElementTransformerOps.convertjson_to_link_format(jsoniterator, bind_display_str=False)
            body = {"text": stringbuilder}
            return body
        except Exception as ex:
            raise Exception(f" Error in MSTeamsResponseConverter::link_transformer {str(ex)}")

    def video_transformer(self, message):
        jsoniterator = ElementTransformerOps.json_generator(message)
        body = {}
        for item in jsoniterator:
            if item.get("type") == ELEMENT_TYPE.VIDEO.value:
                body.update({"text": item.get("url")})
                return body

    def image_transformer(self, message):
        jsoniterator = ElementTransformerOps.json_generator(message)
        attachment = {"attachments":[]}
        for item in jsoniterator:
            if item.get("type") == ELEMENT_TYPE.IMAGE.value:
                imagejson = {}
                imagejson.update({"contentType": "image/png",
                             "contentUrl": item.get("src")})
                attachment.update({"text":item.get("alt")})
                attachment["attachments"].append(imagejson)
                return attachment

    def button_transformer(self, message):
        jsoniterator = ElementTransformerOps.json_generator(message)
        attachment = {"attachments":[]}
        content = {}
        buttons = []
        body_default = ElementTransformerOps.getChannelConfig(self.channel, "body_message")
        for item in jsoniterator:
            if item.get("type") == ELEMENT_TYPE.BUTTON.value:
                title = ElementTransformerOps.json_generator(item.get("children"))
                for titletext in title:
                    button_text = titletext.get("text")
                content.update({"text":body_default})
                btn_body = {}
                btn_body.update({"type": "imBack"})
                btn_body.update({"value":item.get("value"), "title": button_text})
                buttons.append(btn_body)
                content.update({"buttons":buttons})
        attachment_element = {"contentType": "application/vnd.microsoft.card.hero",
                                          "content":content}
        attachment["attachments"].append(attachment_element)
        return attachment

    async def messageConverter(self, message):
        try:
            if self.message_type ==  ELEMENT_TYPE.IMAGE.value:
                return self.image_transformer(message)
            elif self.message_type == ELEMENT_TYPE.LINK.value:
                return self.link_transformer(message)
            elif self.message_type == ELEMENT_TYPE.BUTTON.value:
                return self.button_transformer(message)
            elif self.message_type == ELEMENT_TYPE.VIDEO.value:
                return self.video_transformer(message)
        except Exception as ex:
            raise Exception(f"Error in MSTeamsResponseConverter::messageConverter {str(ex)}")