import ast
from typing import Text, Dict

from loguru import logger
from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.account.activity_log import UserActivityLogger
from kairon.shared.channels.whatsapp.bsp.base import WhatsappBusinessServiceProviderBase
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import WhatsappBSPTypes, ChannelTypes, UserActivityType


class BSP360Dialog(WhatsappBusinessServiceProviderBase):

    def __init__(self, bot: Text, user: Text):
        self.bot = bot
        self.user = user
        
    def validate(self, **kwargs):
        from kairon.shared.data.processor import MongoProcessor
        
        bot_settings = MongoProcessor.get_bot_settings(self.bot, self.user)
        bot_settings = bot_settings.to_mongo().to_dict()
        if bot_settings["whatsapp"] != WhatsappBSPTypes.bsp_360dialog.value:
            raise AppException("Feature disabled for this account. Please contact support!")

    def get_account(self, channel_id: Text):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        partner_id = Utility.environment["channels"]["360dialog"]["partner_id"]
        url = f'{base_url}/api/v2/partners/{partner_id}/channels?filters={{"id":"{channel_id}"}}'
        headers = {"Authorization": BSP360Dialog.get_partner_auth_token()}
        resp = Utility.execute_http_request(request_method="GET", http_url=url, headers=headers, validate_status=True, err_msg="Failed to retrieve account info: ")
        return resp.get("partner_channels", {})[0].get("waba_account", {}).get("id")

    def post_process(self):
        try:
            config = ChatDataProcessor.get_channel_config(
                ChannelTypes.WHATSAPP.value, self.bot, mask_characters=False, config__bsp_type=WhatsappBSPTypes.bsp_360dialog.value
            )
            channel_id = config.get("config", {}).get("channel_id")
            api_key = BSP360Dialog.generate_waba_key(channel_id)
            account_id = self.get_account(channel_id)
            payload = {"api_key": api_key, "waba_account_id": account_id}
            webhook_url = BSP360Dialog.__update_channel_config(config, payload, self.bot, self.user)
            BSP360Dialog.set_webhook_url(api_key, webhook_url)
            return webhook_url
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")
        except Exception as e:
            logger.exception(e)
            raise AppException(e)

    @staticmethod
    def __update_channel_config(config, payload, bot, user):
        conf = config["config"]
        conf.update(payload)
        config["config"] = conf
        return ChatDataProcessor.save_channel_config(config, bot, user)

    def save_channel_config(self, clientId: Text, client: Text, channels: list, partner_id: Text = None):
        if partner_id is None:
            partner_id = Utility.environment["channels"]["360dialog"]["partner_id"]

        if isinstance(channels, str):
            try:
                channels = ast.literal_eval(channels)
            except ValueError:
                channels = channels.strip('[]').split(',')
        if len(channels) == 0:
            raise AppException("Failed to save channel config, onboarding unsuccessful!")

        conf = {
            "config": {
                "client_name": Utility.sanitise_data(clientId),
                "client_id": Utility.sanitise_data(client),
                "channel_id": Utility.sanitise_data(channels[0]),
                "partner_id": Utility.sanitise_data(partner_id),
                "waba_account_id": self.get_account(channels[0]),
                "api_key": BSP360Dialog.generate_waba_key(channels[0]),
                "bsp_type": WhatsappBSPTypes.bsp_360dialog.value
            }, "connector_type": ChannelTypes.WHATSAPP.value
        }
        return ChatDataProcessor.save_channel_config(conf, self.bot, self.user)

    def add_template(self, data: Dict, bot: Text, user: Text):
        try:
            Utility.validate_create_template_request(data)
            config = ChatDataProcessor.get_channel_config(ChannelTypes.WHATSAPP.value, self.bot, mask_characters=False)
            api_key = config.get("config", {}).get("api_key")
            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
            header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["auth_header"]

            headers = {header: api_key}
            url = f"{base_url}/v1/configs/templates"
            resp = Utility.execute_http_request(request_method="POST", http_url=url, request_body=data, headers=headers,
                                                validate_status=True, err_msg="Failed to add template: ",
                                                expected_status_code=201)
            UserActivityLogger.add_log(a_type=UserActivityType.template_creation.value, email=user, bot=bot, message=['Template created!'])
            return resp
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")

    def edit_template(self, data: Dict, template_id: str):
        try:
            Utility.validate_edit_template_request(data)
            config = ChatDataProcessor.get_channel_config(ChannelTypes.WHATSAPP.value, self.bot, mask_characters=False)
            partner_id = Utility.environment["channels"]["360dialog"]["partner_id"]
            waba_account_id = config.get("config", {}).get("waba_account_id")
            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
            template_endpoint = f'/v1/partners/{partner_id}/waba_accounts/{waba_account_id}/waba_templates/{template_id}'
            headers = {"Authorization": BSP360Dialog.get_partner_auth_token()}
            url = f"{base_url}{template_endpoint}"
            resp = Utility.execute_http_request(request_method="PATCH", http_url=url, request_body=data, headers=headers,
                                                validate_status=True, err_msg="Failed to edit template: ")
            return resp
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")
        except Exception as e:
            logger.exception(e)
            raise AppException(str(e))

    def delete_template(self, template_name: str):
        try:
            config = ChatDataProcessor.get_channel_config(ChannelTypes.WHATSAPP.value, self.bot, mask_characters=False)
            api_key = config.get("config", {}).get("api_key")
            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
            header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["auth_header"]

            headers = {header: api_key}
            template_endpoint = f'/v1/configs/templates/{template_name}'
            url = f"{base_url}{template_endpoint}"
            resp = Utility.execute_http_request(request_method="DELETE", http_url=url, headers=headers,
                                                validate_status=True, err_msg="Failed to delete template: ")
            return resp
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")

    def get_template(self, template_id: Text):
        return self.list_templates(id=template_id)

    def list_templates(self, **kwargs):
        filters = "{}"
        try:
            if kwargs:
                filters = str(kwargs).replace('\'', "\"")
            config = ChatDataProcessor.get_channel_config(ChannelTypes.WHATSAPP.value, self.bot, mask_characters=False)
            api_key = config.get("config", {}).get("api_key")
            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
            header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["auth_header"]

            headers = {header: api_key}
            url = f"{base_url}/v1/configs/templates?filters={filters}&sort=business_templates.name"
            resp = Utility.execute_http_request(request_method="GET", http_url=url, headers=headers,
                                                validate_status=True, err_msg="Failed to get template: ")
            return resp.get("waba_templates")
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")
        except Exception as e:
            logger.exception(e)
            raise AppException(str(e))

    @staticmethod
    def get_partner_auth_token():
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        partner_username = Utility.environment["channels"]["360dialog"]["partner_username"]
        partner_password = Utility.environment["channels"]["360dialog"]["partner_password"]
        request_body = {
            "username": partner_username,
            "password": partner_password
        }
        token_url = f"{base_url}/api/v2/token"
        resp = Utility.execute_http_request(request_method="POST", http_url=token_url, request_body=request_body,
                                            validate_status=True, err_msg="Failed to get partner auth token: ")
        return resp.get("token_type") + " " + resp.get("access_token")

    @staticmethod
    def generate_waba_key(channel_id: Text):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        partner_id = Utility.environment["channels"]["360dialog"]["partner_id"]
        url = f"{base_url}/api/v2/partners/{partner_id}/channels/{channel_id}/api_keys"
        headers = {"Authorization": BSP360Dialog.get_partner_auth_token()}
        resp = Utility.execute_http_request(request_method="POST", http_url=url, headers=headers,
                                            validate_status=False,
                                            err_msg="Failed to generate api_keys for business account: ")
        api_key = resp.get("api_key")
        return api_key

    @staticmethod
    def set_webhook_url(api_key: Text, webhook_url: Text):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
        header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["auth_header"]
        waba_webhook_url = f"{base_url}/v1/configs/webhook"
        headers = {header: api_key}
        request_body = {"url": webhook_url}
        resp = Utility.execute_http_request(request_method="POST", http_url=waba_webhook_url,
                                            request_body=request_body, headers=headers, validate_status=True,
                                            err_msg="Failed to set webhook url: ")
        return resp.get("url")
