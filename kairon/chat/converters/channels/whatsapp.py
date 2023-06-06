from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
import json

from kairon.shared.constants import ElementTypes


class WhatsappResponseConverter(ElementTransformerOps):

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
            raise Exception(f" Error in WhatsappResponseConverter::message_extractor {str(ex)}")

    def link_transformer(self, message):
        try:
            link_extract = self.message_extractor(message, self.message_type)
            message_template = ElementTransformerOps.getChannelConfig(self.channel_type, self.message_type)
            if message_template is not None:
                response = ElementTransformerOps.replace_strategy(message_template, link_extract, self.channel_type,
                                                                  self.message_type)
                return response
        except Exception as ex:
            raise Exception(f"Error in WhatsappResponseConverter::link_transformer {str(ex)}")

    def button_transformer(self, message):
        try:
            message_template = ElementTransformerOps.getChannelConfig(self.channel, self.message_type)
            button_json_temp = json.loads(message_template)
            jsoniterator = ElementTransformerOps.json_generator(message)
            buttons = {"buttons": []}
            body_default = ElementTransformerOps.getChannelConfig(self.channel, "body_message")
            body_msg = {"text": body_default}
            for item in jsoniterator:
                if item.get("type") == ElementTypes.BUTTON.value:
                    title = ElementTransformerOps.json_generator(item.get("children"))
                    for titletext in title:
                        button_text = titletext.get("text")
                    btn_body = {}
                    btn_body.update({"type": "reply"})
                    btn_body.update({"reply": {"id": item.get("value"), "title": button_text}})
                    buttons["buttons"].append(btn_body)
            button_json_temp.update({"body": body_msg})
            button_json_temp.update({"action": buttons})
            return button_json_temp
        except Exception as ex:
            raise Exception(f"Exception in WhatsappResponseConverter::button_transfomer: {str(ex)}")

    def dropdown_transformer(self, message):
        try:
            message_template = ElementTransformerOps.getChannelConfig(self.channel, self.message_type)
            dropdown_json_temp = json.loads(message_template)
            jsoniterator = ElementTransformerOps.json_generator(message)
            submit_button_text = ElementTransformerOps.getChannelConfig(self.channel, "dropdown_button_text")
            sections = {"sections": [], "button": submit_button_text}
            rows_list = {"rows": []}
            for item in jsoniterator:
                body_default = item["dropdownLabel"]
                body_msg = {"text": body_default}
                data_type = item.get("type")
                temp_header_value = None
                header_row_data = None
                if data_type == ElementTypes.DROPDOWN.value:
                    option_list = ElementTransformerOps.json_generator(item.get("options"))
                    for option in option_list:
                        label = option.get("label")
                        value = option.get("value")
                        header_value = option.get("optionHeader")
                        row_data = {}
                        row_data.update({"id": value})
                        row_data.update({"title": label})
                        row_data.update({"description": label})
                        if header_value is None:
                            rows_list["rows"].append(row_data)
                        elif header_value is not None:
                            if temp_header_value!=header_value:
                                if header_row_data is not None:
                                    sections["sections"].append(header_row_data)
                                header_row_data = {"title":header_value, "rows":[]}
                                header_row_data["rows"].append(row_data)
                                temp_header_value = header_value
                            elif temp_header_value==header_value:
                                header_row_data["rows"].append(row_data)
                    if header_value is None:
                        sections["sections"].append(rows_list)
                    elif header_value is not None:
                        sections["sections"].append(header_row_data)
                    dropdown_json_temp.update({"body": body_msg})
                    dropdown_json_temp.update({"action": sections})
                    return dropdown_json_temp
        except Exception as ex:
            raise Exception(f"Exception in WhatsappResponseConverter::dropdown_transformer: {str(ex)}")

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
            elif self.message_type == ElementTypes.DROPDOWN.value:
                return self.dropdown_transformer(message)
        except Exception as ex:
            raise Exception(f"Error in WhatsappResponseConverter::messageConverter {str(ex)}")
