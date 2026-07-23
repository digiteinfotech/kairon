import asyncio
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
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.chat.user_media import UserMedia
from kairon.shared.constants import WhatsappBSPTypes, ChannelTypes, UserActivityType
from kairon.shared.data.data_objects import UserMediaData
from kairon.shared.models import UserMediaUploadStatus, UserMediaUploadType


class BSPGupshup(WhatsappBusinessServiceProviderBase):

    def __init__(self, bot: Text, user: Text):
        """Initialize BSPGupshup with bot and user identifiers."""
        self.bot = bot
        self.user = user

    def validate(self, **kwargs):
        from kairon.shared.data.processor import MongoProcessor

        bot_settings = MongoProcessor.get_bot_settings(self.bot, self.user)
        bot_settings = bot_settings.to_mongo().to_dict()
        if bot_settings["whatsapp"] != WhatsappBSPTypes.bsp_gupshup.value:
            raise AppException("Feature disabled for this account. Please contact support!")

    def get_account(self, app_id: Text):
        # Gupshup identifies apps by app_id — no WABA account lookup needed
        return app_id

    def post_process(self):
        try:
            config = ChatDataProcessor.get_channel_config(
                ChannelTypes.WHATSAPP.value, self.bot, mask_characters=False,
                config__bsp_type=WhatsappBSPTypes.bsp_gupshup.value
            )
            app_id = config.get("config", {}).get("app_id")
            partner_base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]

            webhook_url = self.__update_channel_config(config, {}, self.bot, self.user)

            token = self.__get_partner_token(partner_base_url)
            url = f"{partner_base_url}/partner/app/{app_id}"
            Utility.execute_http_request(
                request_method="PUT", http_url=url,
                request_body={"webhookUrl": webhook_url},
                headers={"Authorization": token},
                validate_status=True,
                err_msg="Failed to set Gupshup webhook: "
            )
            return webhook_url
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")
        except Exception as e:
            logger.exception(e)
            raise AppException(str(e))

    @staticmethod
    def __get_partner_token(partner_base_url: Text) -> Text:
        gupshup_cfg = Utility.system_metadata["channels"]["gupshup"]
        email = gupshup_cfg.get("partner_email")
        password = gupshup_cfg.get("partner_password")
        if not email or not password:
            raise AppException("Gupshup partner_email / partner_password not configured in system metadata!")
        resp = requests.post(
            f"{partner_base_url}/partner/account/login",
            json={"email": email, "password": password},
            timeout=30
        )
        if resp.status_code != 200:
            raise AppException(f"Gupshup partner login failed: [{resp.status_code}] {resp.text}")
        token = resp.json().get("token")
        if not token:
            raise AppException(f"Gupshup partner login returned no token: {resp.text}")
        return token

    @staticmethod
    def __update_channel_config(config, payload, bot, user):
        conf = config["config"]
        conf.update(payload)
        config["config"] = conf
        return ChatDataProcessor.save_channel_config(config, bot, user)

    def save_channel_config(self, **kwargs):
        app_id = kwargs.get("app_id")
        app_name = kwargs.get("app_name") or app_id
        partner_app_token = kwargs.get("partner_app_token")
        phone_number = kwargs.get("phone_number")

        if not app_id:
            raise AppException("app_id is required for Gupshup channel setup!")
        if not partner_app_token:
            raise AppException("partner_app_token is required for Gupshup channel setup!")

        conf = {
            "config": {
                "app_id": Utility.sanitise_data(app_id),
                "app_name": Utility.sanitise_data(app_name),
                "partner_app_token": Utility.sanitise_data(partner_app_token),
                "phone_number": Utility.sanitise_data(phone_number) if phone_number else None,
                "bsp_type": WhatsappBSPTypes.bsp_gupshup.value
            },
            "connector_type": ChannelTypes.WHATSAPP.value
        }
        return ChatDataProcessor.save_channel_config(conf, self.bot, self.user)

    def validate_template_request(self, data: Dict):
        required_keys = ["elementName", "content", "category", "vertical", "templateType", "example"]
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            raise AppException(f'Missing {", ".join(missing_keys)} in request body!')
        template_type = data.get("templateType")
        if template_type in ["IMAGE", "VIDEO", "DOCUMENT"]:
            if not data.get("exampleMedia"):
                raise AppException(f"exampleMedia (handleId) is required for {template_type} templates")
        elif template_type == "TEXT":
            header = data.get("header")
            if header and "{{" in header and not data.get("exampleHeader"):
                raise AppException("exampleHeader is required when header contains variables")
        else:
            raise AppException(f"Invalid templateType: {template_type}")

    def add_template(self, data: Dict, bot: Text, user: Text):
        try:
            template_type = data.get("templateType")
            if template_type in ["IMAGE", "VIDEO", "DOCUMENT"]:
                media_id = data.get("media_id")
                if media_id:
                    handle_id = UserMedia.get_media_handle_id(self.bot, media_id)
                    if handle_id:
                        data["exampleMedia"] = handle_id
            self.validate_template_request(data)

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
            return resp.get("waba_templates") or resp.get("templates") or []
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("Channel not found!")
        except Exception as e:
            logger.exception(e)
            raise AppException(str(e))


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
            "Authorization": partner_app_token,
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
        resp_data = response.json()
        handle_id_raw = resp_data.get("handleId")
        handle_id = handle_id_raw if isinstance(handle_id_raw, str) else (handle_id_raw or {}).get("message")
        expiration_date = datetime.utcnow() + timedelta(days = 30)

        output_filename = f"template_media/{bot}/{filename}"
        bucket = Utility.environment["storage"]["whatsapp_media"].get("bucket")
        with open(file_path, "rb") as f:
            binary_data = f.read()
            media_url = UserMedia.save_media_content(bot, sender_id, media_id, binary_data, filename,
                                                     file_path, output_filename, bucket, False)

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

    def get_template_for_broadcast(self, name: Text, language: Text):
        """Fetch template matching name+language for broadcast use."""
        template_exception = None
        template = {}
        try:
            for t in self.list_templates():
                if t.get("id") == name:
                    template = t
                    break
        except Exception as e:
            logger.exception(e)
            template_exception = str(e)
        return template, template_exception

    def to_log_template(self, raw_template):
        """Convert Gupshup raw template dict to components list for broadcast logs."""
        if not isinstance(raw_template, dict):
            return []
        components = []
        template_type = raw_template.get("templateType", "TEXT")
        try:
            container_meta = json.loads(raw_template.get("containerMeta", "{}"))
        except Exception:
            container_meta = {}
        if template_type in ("IMAGE", "VIDEO", "DOCUMENT"):
            components.append({"type": "HEADER", "format": template_type})
        elif container_meta.get("header"):
            components.append({"type": "HEADER", "format": "TEXT", "text": container_meta["header"]})
        body_text = container_meta.get("data") or raw_template.get("data", "")
        if body_text:
            components.append({"type": "BODY", "text": body_text})
        footer = container_meta.get("footer")
        if footer:
            components.append({"type": "FOOTER", "text": footer})
        buttons = container_meta.get("buttons") or []
        if buttons:
            components.append({"type": "BUTTONS", "buttons": buttons})
        return components

    def normalize_raw_template(self, raw_template):
        return raw_template if isinstance(raw_template, dict) else {}

    def get_template_params_for_broadcast(self, raw_template, template_config, recipients, default_params):
        template, message = self.get_broadcast_template_params(raw_template, template_config)
        return [(template, message) for _ in recipients]

    def get_broadcast_namespace_and_language(self, raw_template, namespace, lang):
        return raw_template.get("namespace", namespace), raw_template.get("languageCode", lang)

    def get_broadcast_template_params(self, raw_template, template_config):
        """Return (template, message) tuple for Gupshup broadcast send."""
        if not isinstance(raw_template, dict):
            raw_template = {}
        template_id = template_config.get("template_id") or raw_template.get("id")
        template_type = raw_template.get("templateType")
        logger.debug(f"Gupshup template raw: {raw_template}")
        try:
            container_meta = json.loads(raw_template.get("containerMeta", "{}"))
        except Exception:
            container_meta = {}
        body_params, media_id = BSPGupshup._resolve_runtime_params(template_config, container_meta)
        return BSPGupshup._build_template_payload(template_id, body_params, media_id, template_type, container_meta)

    @staticmethod
    def _resolve_runtime_params(template_config, container_meta):
        import json
        try:
            parsed_data = json.loads(template_config.get("data", "[]") or "[]")
        except Exception:
            parsed_data = []
        if isinstance(parsed_data, dict):
            body_params = [v for _, v in sorted(parsed_data.items(), key=lambda x: int(x[0]))]
            media_id = None
        else:
            components = parsed_data[0] if parsed_data and isinstance(parsed_data[0], list) else []
            body_params, media_id = BSPGupshup._extract_components_params(components)
        if not body_params:
            body_params = BSPGupshup._extract_sample_text_params(container_meta)
        if not media_id:
            media_id = container_meta.get("sampleMedia")
        return body_params, media_id

    @staticmethod
    def _extract_components_params(components):
        body_params = []
        media_id = None
        for comp in components:
            comp_type = comp.get("type")
            if comp_type == "body":
                for param in comp.get("parameters", []):
                    if param.get("type") == "text":
                        body_params.append(param.get("text"))
            elif comp_type == "header":
                for param in comp.get("parameters", []):
                    p_type = param.get("type")
                    if p_type in ("image", "video", "document"):
                        media_id = param.get(p_type, {}).get("id")
        return body_params, media_id

    @staticmethod
    def _extract_sample_text_params(container_meta):
        import re
        template_text = container_meta.get("data", "")
        sample_text = container_meta.get("sampleText", "")
        placeholders = re.findall(r"\{\{(\d+)\}\}", template_text)
        if not (placeholders and sample_text):
            return []
        static_parts = re.split(r"\{\{\d+\}\}", template_text)
        temp_text = sample_text
        for part in static_parts:
            if part:
                temp_text = temp_text.replace(part, "|")
        extracted = [p.strip() for p in temp_text.split("|") if p.strip()]
        return extracted[:len(placeholders)]

    @staticmethod
    def fetch_media_ids(bot: str):
        try:
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            media_data = UserMediaData.objects(
                bot=bot,
                upload_status=UserMediaUploadStatus.completed.value,
                upload_type=UserMediaUploadType.broadcast.value,
                timestamp__gte=thirty_days_ago,
            ).only("filename", "media_id", "upload_status", "sender_id", "timestamp", "external_upload_info")
            return [
                {
                    "filename": doc.filename,
                    "handle_id": (doc.external_upload_info or {}).get("handle_id"),
                    "upload_status": doc.upload_status,
                    "sender_id": doc.sender_id,
                    "timestamp": doc.timestamp,
                }
                for doc in media_data
            ]
        except Exception as e:
            raise AppException(f"Error while fetching media ids for bot '{bot}': {str(e)}")

    @staticmethod
    def fetch_broadcast_media_ids(bot: str):
        try:
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            media_data = UserMediaData.objects(
                bot=bot,
                upload_status=UserMediaUploadStatus.completed.value,
                media_id__ne="",
                upload_type=UserMediaUploadType.broadcast.value,
                timestamp__gte=thirty_days_ago,
            ).only("filename", "media_id", "upload_status", "sender_id", "timestamp")
            return [
                {
                    "filename": doc.filename,
                    "media_id": doc.media_id,
                    "upload_status": doc.upload_status,
                    "sender_id": doc.sender_id,
                    "timestamp": doc.timestamp,
                }
                for doc in media_data
            ]
        except Exception as e:
            raise AppException(f"Error while fetching media ids for bot '{bot}': {str(e)}")

    @staticmethod
    def _build_template_payload(template_id, body_params, media_id, template_type, container_meta):
        template = {"id": template_id, "params": body_params}
        media_type_map = {"IMAGE": "image", "VIDEO": "video", "DOCUMENT": "document"}
        if media_id:
            m_type = media_type_map.get(template_type, "image")
            message = {"type": m_type, m_type: {"id": media_id}}
        else:
            text_template = container_meta.get("data", "")
            for i, val in enumerate(body_params, start=1):
                text_template = text_template.replace(f"{{{{{i}}}}}", str(val))
            message = {"type": "text", "text": text_template or " "}
        return template, message

