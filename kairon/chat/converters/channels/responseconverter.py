import json
from kairon import Utility
from kairon.exceptions import AppException
from kairon.chat.converters.channels.constants import ELEMENT_TYPE

class ElementTransformerOps():
    def __init__(self, type, channel):
        self.type = type
        self.channel = channel

    @staticmethod
    def getChannelConfig(channel, type):
        config_obj = Utility.system_metadata.get(channel)
        if config_obj is not None:
            return config_obj.get(type)
        else:
            message_config = Utility.system_metadata.get("No_Config_error_message")
            message_config = str(message_config).format(channel, type)
            raise AppException(message_config)

    def image_transformer(self, message):
        try:
            message_template = ElementTransformerOps.getChannelConfig(self.channel, self.type)
            op_message = self.message_extractor(message, self.type)
            response = ElementTransformerOps.replace_strategy(message_template, op_message, self.channel, self.type)
            return response
        except Exception as ex:
            raise AppException(f"Exception in ElementTransformerOps::Image_transformer: {str(ex)}")

    def link_transformer(self, message):
        try:
            link_extract = self.message_extractor(message, self.type)
            message_template = ElementTransformerOps.getChannelConfig(self.channel, self.type)
            response = ElementTransformerOps.replace_strategy(message_template, link_extract, self.channel, self.type)
            return response
        except Exception as ex:
            raise AppException(f"Exception in ElementTransformerOps::Link_Transformer: {str(ex)}")

    @staticmethod
    def json_generator(json_input):
        if isinstance(json_input, dict):
                yield json_input
        elif isinstance(json_input, list):
            for item in json_input:
                yield from ElementTransformerOps.json_generator(item)

    def message_extractor(self, json_message, type):
        try:
            if type == ELEMENT_TYPE.IMAGE.value:
                image_json = ElementTransformerOps.json_generator(json_message)
                body = {}
                for item in image_json:
                    if item.get("type") == ELEMENT_TYPE.IMAGE.value:
                        body.update({"type": item.get("type"), "URL": item.get("src"),
                                     "caption": item.get("alt")})
                        return  body
            elif type == ELEMENT_TYPE.LINK.value:
                jsoniterator = ElementTransformerOps.json_generator(json_message)
                stringbuilder = ElementTransformerOps.convertjson_to_link_format(jsoniterator)
                body = {"data":stringbuilder}
                return body
        except Exception as ex:
            raise Exception(f"Exception in ElementTransformerOps::message_extractor for channel: {self.channel} "
                            f"and type: {self.type}: - {str(ex)}")

    @staticmethod
    def replace_strategy(message_template, message, channel, type):
        keymapping = Utility.system_metadata.get("channel_messagetype_and_key_mapping")
        if keymapping is not None:
            jsonkey_mapping = json.loads(keymapping)
            channel_meta = jsonkey_mapping.get(channel)
            if channel_meta is not None:
                keydata_mapping = channel_meta.get(type)
                if keydata_mapping is not None:
                    for key in keydata_mapping:
                        value_from_json = message.get(key)
                        replace_in_template = keydata_mapping.get(key)
                        message_template = message_template.replace(replace_in_template, value_from_json)
                    return json.loads(message_template)
                else:
                    message_config = Utility.system_metadata.get("channel_key_mapping_missing")
                    message_config = str(message_config).format(channel, type)
                    raise Exception(message_config)
            else:
                message_config = Utility.system_metadata.get("channel_key_mapping_missing")
                message_config = str(message_config).format(channel, type)
                raise Exception(message_config)

    @staticmethod
    def convertjson_to_link_format(jsoniterator, bind_display_str = True):
        stringbuilder = ""
        for jsonlist in jsoniterator:
            childerobj = jsonlist.get("children")
            for items in childerobj:
                if items.get("type") is None and items.get("text") is not None \
                        and str(items.get("text")).strip().__len__() > 0:
                    stringbuilder = " ".join([stringbuilder, str(items.get("text"))]).strip()
                elif items.get("type") is not None and items.get("type") == ELEMENT_TYPE.LINK.value:
                    link = items.get("href")
                    if bind_display_str:
                        displaydata = items.get("children")
                        for displayobj in displaydata:
                            displaystring = displayobj.get("text")
                            link_formation = "<" + str(link) + "|" + str(displaystring) + ">"
                            break
                        stringbuilder = " ".join([stringbuilder, link_formation]).strip()
                    else:
                        stringbuilder = " ".join([stringbuilder, link]).strip()
        return stringbuilder

from kairon.chat.converters.channels.slack import SlackMessageConverter
from kairon.chat.converters.channels.hangout import HangoutResponseConverter
from kairon.chat.converters.channels.messenger import MessengerResponseConverter
from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
from kairon.chat.converters.channels.telegram import TelegramResponseConverter

class ConverterFactory():

    @staticmethod
    def getConcreteInstance(message_type, channel_type):
        class_instance_mapping = {"slack": SlackMessageConverter(message_type, channel_type),
                      "hangout": HangoutResponseConverter(message_type, channel_type),
                      "messenger": MessengerResponseConverter(message_type, channel_type),
                      "telegram": TelegramResponseConverter(message_type, channel_type),
                      "whatsapp": WhatsappResponseConverter(message_type, channel_type)}
        return class_instance_mapping.get(channel_type)