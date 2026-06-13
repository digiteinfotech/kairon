import asyncio
import io
import json
import os
from datetime import datetime, timedelta
from typing import Text, Dict

import requests

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.account.activity_log import UserActivityLogger

from loguru import logger
from mongoengine import DoesNotExist

from kairon.shared.channels.whatsapp.bsp.base import WhatsappBusinessServiceProviderBase
from kairon.shared.chat.data_objects import Channels
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.chat.user_media import UserMedia
from kairon.shared.constants import WhatsappBSPTypes, ChannelTypes, UserActivityType
from kairon.shared.data.data_objects import UserMediaData
from kairon.shared.models import UserMediaUploadStatus, UserMediaUploadType


class BSPGupshup(WhatsappBusinessServiceProviderBase):

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
            Utility.validate_create_template_request(data, bsp_type=WhatsappBSPTypes.bsp_gupshup.value)

            config = ChatDataProcessor.get_channel_config(
                ChannelTypes.WHATSAPP.value,
                self.bot,
                mask_characters=False
            )

            app_id = config.get("config", {}).get("app_id")
            partner_app_token = config.get("config", {}).get("partner_app_token")
            partner_base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"][
                "partner_base_url"]
            header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["auth_header"]


            # payload = data.copy()
            # payload.update({
            #     "userid": userid,
            #     "password": password,
            #     "method": "create_whatsapp_hsm"
            # })
            #
            # files = None
            #
            # # Handle media header template
            # if payload.get("type") in ["image", "video", "document"]:
            #     header_example_path = payload.pop("header_examples", None)
            #
            #     # Remove text header if media type
            #     payload.pop("header", None)
            #
            #     if not header_example_path:
            #         raise AppException("header_examples file path is required for media templates")
            #
            #     files = {
            #         "header_examples": open(header_example_path, "rb")
            #     }

            payload = data.copy()
            payload['buttons'] = json.dumps(payload.get('buttons'))
            headers = {
                header: partner_app_token,
                "Content-Type": "application/x-www-form-urlencoded",
                "accept": "application/json"
            }


            url = f"{partner_base_url}/partner/app/{app_id}/templates"
            resp = requests.post(url, headers=headers, data=payload)

            if resp.status_code not in [200, 201]:
                raise AppException(
                    f"Failed to add gupshup template: {resp.text}"
                )

            UserActivityLogger.add_log(
                a_type=UserActivityType.template_creation.value,
                email=user,
                bot=bot,
                message=["Template created!"]
            )

            return resp.json()

        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")

        except Exception as e:
            logger.exception(e)
            raise AppException(str(e))

    def edit_template(self, data: Dict, template_id: str):
        try:
            config = ChatDataProcessor.get_channel_config(
                ChannelTypes.WHATSAPP.value,
                self.bot,
                mask_characters=False
            )

            app_id = config.get("config", {}).get("app_id")
            partner_app_token = config.get("config", {}).get("partner_app_token")
            partner_base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"][
                "partner_base_url"]
            header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["auth_header"]

            payload = data.copy()
            if payload.get('buttons'):
                payload['buttons'] = json.dumps(payload.get('buttons'))
            headers = {
                header: partner_app_token,
                "Content-Type": "application/x-www-form-urlencoded",
                "accept": "application/json"
            }

            url = f"{partner_base_url}/partner/app/{app_id}/templates/{template_id}"
            resp = requests.put(url, headers=headers, data=payload)

            if resp.status_code not in [200, 201]:
                raise AppException(
                    f"Failed to edit gupshup template: {resp.text}"
                )

            return resp.json()

        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")
        except Exception as e:
            logger.exception(e)
            raise AppException(str(e))

    def delete_template(self, template_name: str):
        try:
            config = ChatDataProcessor.get_channel_config(
                ChannelTypes.WHATSAPP.value,
                self.bot,
                mask_characters=False
            )

            app_id = config.get("config", {}).get("app_id")
            partner_app_token = config.get("config", {}).get("partner_app_token")
            partner_base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"][
                "partner_base_url"]
            header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["auth_header"]

            headers = {
                header: partner_app_token
            }

            url = f"{partner_base_url}/partner/app/{app_id}/template/{template_name}"
            resp = requests.delete(url, headers=headers)

            if resp.status_code not in [200, 201]:
                raise AppException(
                    f"Failed to delete gupshup template: {resp.text}"
                )

            return resp.json()

        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")

    def get_template(self, template_id: Text):
        return self.list_templates(id=template_id)

    def list_templates(self, **kwargs):
        from urllib.parse import urlencode
        query_string = urlencode(kwargs)
        try:
            config = ChatDataProcessor.get_channel_config(ChannelTypes.WHATSAPP.value, self.bot, mask_characters=False)
            app_id = config.get("config", {}).get("app_id")
            partner_app_token = config.get("config", {}).get("partner_app_token")
            partner_base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
            header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["auth_header"]

            headers = {header: partner_app_token}

            url = f"{partner_base_url}/partner/app/{app_id}/templates?{query_string}"
            resp = Utility.execute_http_request(request_method="GET", http_url=url, headers=headers,
                                                validate_status=True, err_msg="Failed to get gupshup template: ")
            return resp.get("templates")
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")
        except Exception as e:
            logger.exception(e)
            raise AppException(str(e))

    # @staticmethod
    # async def upload_media(bot: str, bsp_type: str, media_id: str) -> str:
    #     """
    #     Uploads the PDF to 360dialog and returns the external media ID.
    #     """
    #     connector_type = "whatsapp"
    #     try:
    #         media_doc = UserMediaData.objects.get(media_id=media_id)
    #     except DoesNotExist:
    #         raise AppException(f"UserMediaData not found for media_id: {media_id}")
    #
    #     channel_config = Channels.objects(bot=bot, connector_type=connector_type).first()
    #     if not channel_config or "config" not in channel_config or channel_config.config.get("bsp_type") != bsp_type:
    #         raise AppException(
    #             f"Channel config not found for bot: {bot}, connector_type: {connector_type}, bsp_type: {bsp_type}")
    #
    #     app_id = channel_config.get("config", {}).get("app_id")
    #     partner_app_token = channel_config.get("config", {}).get("partner_app_token")
    #
    #     if not partner_app_token:
    #         raise AppException("partner_app_token not found in channel config")
    #
    #     base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
    #     auth_header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["auth_header"]
    #
    #     try:
    #         media_url = media_doc.media_url
    #
    #         headers = {auth_header: partner_app_token}
    #         extension = "application/pdf"
    #
    #         response = requests.post(
    #             f"{base_url}/partner/app/{app_id}/media",
    #             headers=headers,
    #             files={
    #                 "file": (None, media_url),
    #                 "file_type": (None, extension)
    #             },
    #             timeout=(5, 60)
    #         )
    #
    #         external_media_id = response.json().get("id")
    #
    #         media_doc.external_upload_info = {
    #             "bsp": bsp_type,
    #             "external_media_id": external_media_id,
    #             "error": ""
    #         }
    #         media_doc.save()
    #
    #         return external_media_id
    #
    #     except Exception as e:
    #         media_doc.external_upload_info = {
    #             "bsp": bsp_type,
    #             "error": str(e)
    #         }
    #         media_doc.save()
    #         raise e

    @staticmethod
    async def upload_media_file(bot: str, channel_config: dict, sender_id: str, filename: str, extension: str,
                           filesize: int = 0) -> str:
        from uuid6 import uuid7

        app_id = channel_config.get("config", {}).get("app_id")
        partner_app_token = channel_config.get("config", {}).get("partner_app_token")

        if not partner_app_token:
            raise AppException("partner app token not found in channel config")

        partner_base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"][
            "partner_base_url"]
        header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["auth_header"]

        headers = {
            header: partner_app_token,
        }
        payload = {"file_type": extension}
        content_dir = os.path.join("media_upload_records", bot)
        os.makedirs(content_dir, exist_ok=True)
        file_path = os.path.join(content_dir, filename)

        media_doc = UserMedia.create_media_doc(
            bot=bot,
            sender_id = sender_id,
            filename = filename,
            extension = extension,
            filesize = filesize,
            bsp_type = WhatsappBSPTypes.bsp_gupshup.value
        )


        async def _post():
            def _do():
                with open(file_path, "rb") as f:
                    files = {"file": (filename, f, f"{extension}")}

                    return requests.post(
                            f"{partner_base_url}/partner/app/{app_id}/upload/media",
                            headers=headers,
                            data = payload,
                            files = files,
                            timeout = (5, 60),
                            )
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _do)

        async def _get_external_media_id():
            def _do():
                headers['accept'] = 'application/json'
                return requests.post(
                    f"{partner_base_url}/partner/app/{app_id}/media",
                    headers=headers,
                    files={
                        "file": (None, media_url),
                        "file_type": (None, extension)
                    },
                    timeout=(5, 60)
                )

            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _do)


        try:
            response = await _post()
        except requests.RequestException as e:
                    media_doc.update(
                        set__upload_status = UserMediaUploadStatus.failed.value,
                        set__additional_info ={"message": "Upload failed: network error"},
                        set__external_upload_info__error = str(e),
                    )
                    raise AppException(f"Upload request failed: {e}") from e

        if response.status_code not in (200, 201):
            media_doc.update(
                set__upload_status = UserMediaUploadStatus.failed.value,
                set__additional_info ={"message": "Upload failed"},
                set__external_upload_info__error = response.text,
            )
            raise AppException(response.text)

        media_id = uuid7().hex
        handle_id = response.json().get("handleId", {}).get("message")
        expiration_date = datetime.utcnow() + timedelta(days = 30)

        output_filename = f"template_media/{bot}/{filename}"
        bucket = Utility.environment["storage"]["whatsapp_media"].get("bucket")
        with open(file_path, "rb") as f:
            binary_data = f.read()
            media_url = UserMedia.save_media_content(bot, sender_id, media_id, binary_data, filename,
                                                     file_path, output_filename, bucket, False)

        media_doc.update(
            set__media_url=media_url,
            set__upload_type=UserMediaUploadType.broadcast.value,
            set__additional_info={"message": "Upload successful"},
            set__external_upload_info__handle_id=handle_id,
            set__external_upload_info__expiry_date=expiration_date,
        )

        external_media_id = None

        try:
            media_resp = await _get_external_media_id()

        except requests.RequestException as e:
            logger.exception(f"Failed to fetch external media id: {e}")

            media_doc.update(
                set__upload_status = UserMediaUploadStatus.failed.value,
                set__additional_info ={"message": "Upload failed: network error"},
                set__external_upload_info__error = str(e),
            )
            raise AppException(f"Upload request failed: {e}") from e

        if media_resp.status_code not in (200, 201):
            logger.error(f"Media API failed: {media_resp.text}")
            media_doc.update(
                set__upload_status = UserMediaUploadStatus.failed.value,
                set__additional_info ={"message": "Upload failed"},
                set__external_upload_info__error = media_resp.text,
            )
            raise AppException(media_resp.text)

        external_media_id = media_resp.json().get("mediaId")

        media_doc.update(
            set__media_id = external_media_id,
            set__upload_status = UserMediaUploadStatus.completed.value,
            set__upload_type = UserMediaUploadType.broadcast.value,
            set__additional_info ={"message": "Upload successful and media_id generated."},
            set__external_upload_info__external_media_id = external_media_id,
        )

        return external_media_id

    @staticmethod
    def delete_media_file(media_id: str, channel_config):
        app_id = channel_config.get("config", {}).get("app_id")
        partner_app_token = channel_config.get("config", {}).get("partner_app_token")

        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        url = f"{base_url}/partner/app/{app_id}/media/{media_id}"
        header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["auth_header"]
        headers = {header: partner_app_token}
        Utility.execute_http_request(request_method="DELETE", http_url=url, headers=headers,
                                     validate_status=True,
                                     err_msg="media file does not exist for this media id.")
        return "Media file deleted successfully"
