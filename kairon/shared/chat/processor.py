import os
from datetime import datetime
from typing import Dict, Text

import aiofiles
from fastapi import File
from loguru import logger
from mongoengine import DoesNotExist

from kairon.shared.utils import Utility
from .broadcast.processor import MessageBroadcastProcessor
from .data_objects import Channels, ChannelLogs
from ..constants import ChannelTypes
from ..data.constant import MIME_TYPE_LIMITS
from ..data.utils import DataUtility
from ...exceptions import AppException


class ChatDataProcessor:

    @staticmethod
    def save_channel_config(configuration: Dict, bot: Text, user: Text):
        """
        save or updates channel configuration
        :param configuration: config dict
        :param bot: bot id
        :param user: user id
        :return: None
        """
        primary_slack_config_changed = False
        private_key = configuration['config'].get('private_key', None)
        if configuration['connector_type'] == ChannelTypes.BUSINESS_MESSAGES.value and private_key:
            configuration['config']['private_key'] = private_key.replace("\\n", "\n")
        if configuration['connector_type'] == ChannelTypes.MAIL.value:
            from kairon.shared.channels.mail.processor import MailProcessor
            if MailProcessor.check_email_config_exists(bot, configuration['config']):
                raise AppException("Email configuration already exists for same email address and subject")
        try:
            filter_args = ChatDataProcessor.__attach_metadata_and_get_filter(configuration, bot)
            channel = Channels.objects(**filter_args).get()
            channel.config = ChatDataProcessor.__validate_config_for_update(channel,configuration["config"])
            primary_slack_config_changed = True if channel.connector_type == 'slack' and channel.config.get(
                'is_primary') else False
        except DoesNotExist:
            channel = Channels(**configuration)
        channel.bot = bot
        channel.user = user
        channel.timestamp = datetime.utcnow()
        channel.save()
        if configuration['connector_type'] == ChannelTypes.MAIL.value:
            from kairon.shared.channels.mail.scheduler import MailScheduler
            MailScheduler.request_epoch(bot)
        if primary_slack_config_changed:
            ChatDataProcessor.delete_channel_config(bot, connector_type="slack", config__is_primary=False)
        channel_endpoint = DataUtility.get_channel_endpoint(channel)
        return channel_endpoint

    @staticmethod
    def __validate_config_for_update(channel: Channels, config: dict):
        channel_config = channel.config or {}
        for key, val in config.items():
            if isinstance(val, str) and val.endswith("*****") and key in ["app_secret", "page_access_token",
                                                                          "verify_token"]:
                decrypted = Utility.decrypt_message(channel.config.get(key))
                print("Decrypted:", key, decrypted)
                channel_config[key] = decrypted
                print(channel_config)
            else:
                channel_config[key] = val
        return channel_config

    @staticmethod
    def __attach_metadata_and_get_filter(configuration: Dict, bot: Text):
        filter_args = {"bot": bot, "connector_type": configuration['connector_type']}
        if configuration['connector_type'] == 'slack':
            auth_token = configuration['config'].get('bot_user_oAuth_token')
            if Utility.check_empty_string(auth_token):
                raise AppException("Missing 'bot_user_oAuth_token' in config")
            if not configuration['config'].get('team'):
                configuration['config']['team'] = Utility.get_slack_team_info(auth_token)
            filter_args["config__team__id"] = configuration['config']['team']['id']
        return filter_args

    def __getattribute__(self, __name):
        return super().__getattribute__(__name)

    @staticmethod
    def delete_channel_config(bot: Text, **kwargs):
        """
        Delete a particular channel configuration for bot
        :param bot: bot id
        :return: None
        """
        kwargs.update({"bot": bot})
        try:
            from kairon.shared.channels.mail.scheduler import MailScheduler
            MailScheduler.request_stop(bot)
        except Exception as e:
            logger.error(f"Error while stopping mail scheduler for bot {bot}. Error: {str(e)}")
        Utility.hard_delete_document([Channels], **kwargs)

    @staticmethod
    def list_channel_config(bot: Text, mask_characters: bool = True):
        """
        list channel configuration against the bot
        :param bot: bot id
        :param mask_characters: whether to mask the security keys default is True
        :return: List
        """
        for channel in Channels.objects(bot=bot).exclude("user", "timestamp"):
            data = channel.to_mongo().to_dict()
            data['_id'] = data['_id'].__str__()
            data.pop("timestamp")
            ChatDataProcessor.__prepare_config(data, mask_characters)
            yield data

    @staticmethod
    def get_channel_config(connector_type: Text, bot: Text, mask_characters=True, **kwargs):
        """
        fetch particular channel config for bot
        :param connector_type: channel name
        :param bot: bot id
        :param mask_characters: whether to mask the security keys default is True
        :return: Dict
        """
        kwargs.update({"bot": bot, "connector_type": connector_type})
        config = Channels.objects(**kwargs).exclude("user").get().to_mongo().to_dict()
        logger.debug(config)
        config.pop("timestamp")
        ChatDataProcessor.__prepare_config(config, mask_characters)
        return config

    @staticmethod
    def get_all_channel_configs(connector_type: str, mask_characters: bool = True, **kwargs):
        """
        fetch all channel configs for connector type
        :param connector_type: channel name
        :param mask_characters: whether to mask the security keys default is True
        :return: List
        """
        for channel in Channels.objects(connector_type=connector_type).exclude("user", "timestamp"):
            data = channel.to_mongo().to_dict()
            data['_id'] = data['_id'].__str__()
            data.pop("timestamp")
            ChatDataProcessor.__prepare_config(data, mask_characters)
            yield data

    @staticmethod
    def __prepare_config(config: dict, mask_characters: bool):
        connector_type = config['connector_type']
        if connector_type == ChannelTypes.WHATSAPP.value and config['config'].get('bsp_type'):
            bsp_type = config['config']['bsp_type']
            channel_params = Utility.system_metadata['channels'][connector_type]["business_providers"][bsp_type]
            ChatDataProcessor.__prepare_required_fields(config, channel_params, mask_characters)
        else:
            channel_params = Utility.system_metadata['channels'][connector_type]
            ChatDataProcessor.__prepare_required_fields(config, channel_params, mask_characters)
        return config

    @staticmethod
    def __prepare_required_fields(data: dict, channel_params, mask_characters: bool):
        for require_field in channel_params['required_fields']:
            data['config'][require_field] = Utility.decrypt_message(data['config'][require_field])
            if mask_characters:
                data['config'][require_field] = data['config'][require_field][:-5] + '*****'

    @staticmethod
    def get_channel_endpoint(connector_type: Text, bot: Text):
        """
        fetch particular channel config for bot
        :param connector_type: channel name
        :param bot: bot id
        :return: channel endpoint as string
        """
        try:
            channel = Channels.objects(bot=bot, connector_type=connector_type).get()
            channel_endpoint = DataUtility.get_channel_endpoint(channel)
            return channel_endpoint
        except DoesNotExist:
            raise AppException('Channel not configured')

    @staticmethod
    def save_whatsapp_audit_log(status_data: Dict, bot: Text, user: Text, recipient: Text, channel_type: Text):
        """
        save or updates channel configuration
        :param status_data: status_data dict
        :param bot: bot id
        :param user: user id
        :param recipient: recipient id
        :param channel_type: channel type
        :return: None
        """
        campaign_id = None
        status = status_data.get('status')
        msg_id = status_data.get('id')

        if msg_id and status in {"delivered", "read"}:
            campaign_id = MessageBroadcastProcessor.get_campaign_id(msg_id)

        data = status_data.get('payment') if status == "captured" else status_data.get('conversation')

        ChannelLogs(
            type=channel_type,
            status=status,
            data=data,
            initiator=status_data.get('conversation', {}).get('origin', {}).get('type'),
            message_id=msg_id,
            errors=status_data.get('errors', []),
            bot=bot,
            user=user,
            recipient=recipient,
            campaign_id=campaign_id
        ).save()

    @staticmethod
    def save_whatsapp_failed_messages(resp: Dict, bot: Text, recipient: Text, channel_type: Text, **kwargs):
        """
        Logs failed WhatsApp message responses for debugging and tracking purposes.

        Args:
            resp (Dict): The response dictionary containing error details.
            bot (Text): The bot identifier.
            recipient (Text): The recipient identifier.
            channel_type (Text): The type of channel (e.g., WhatsApp).

        Returns:
            None
        """
        error = resp.get("error", {})
        message_id = kwargs.get("message_id")
        user = kwargs.get("user")
        json_message = kwargs.get('json_message')
        metadata = kwargs.get("metadata")
        failure_reason = error.get("error_data", {}).get("details")
        logger.debug(f"WhatsApp message failed to send: {error}")

        ChannelLogs(
            type=channel_type,
            status="failed",
            data=resp,
            failure_reason=failure_reason,
            message_id=message_id,
            user=user,
            bot=bot,
            recipient=recipient,
            json_message=json_message,
            metadata=metadata
        ).save()

    @staticmethod
    def get_instagram_static_comment(bot: str) -> str:
        channel = ChatDataProcessor.get_channel_config(bot=bot, connector_type="instagram", mask_characters=False)
        comment_response = channel.get("config", {}).get("static_comment_reply")
        return comment_response

    @staticmethod
    async def save_media_file_path(bot: Text, user: Text, file_content: File):
        """
        Saves the media file and validates its type.

        :param bot: The bot ID
        :param user: The user ID
        :param file_content: The uploaded file
        :return: A dictionary of error messages if validation fails
        """
        content_dir = os.path.join("media_upload_records", bot)
        Utility.make_dirs(content_dir)
        file_path = os.path.join(content_dir, file_content.filename)

        async with aiofiles.open(file_path, "wb") as buffer:
            while chunk := await file_content.read(1024 * 1024):
                await buffer.write(chunk)

        await file_content.seek(0)
        return file_path

    @staticmethod
    async def upload_media_to_bsp(bot: str, user: str, channel: str, file_path: str, file_info: File):
        """
        Uploads the file to BSP and deletes the temporary local file.
        """
        from ..channels.whatsapp.bsp.factory import BusinessServiceProviderFactory
        media_id = None
        try:
            channel_config = ChatDataProcessor.get_channel_config(channel, bot)
            bsp_type = channel_config.get("config").get("bsp_type", "meta")
            media_id = await (BusinessServiceProviderFactory.get_instance(bsp_type).upload_media_file(bot,
                                                                        channel_config, user, file_info.filename,
                                                                        file_info.content_type, file_info.size))
            logger.info(f"Media uploaded successfully: {media_id}")
        except Exception as e:
            logger.error(f"Error uploading file to BSP: {str(e)}")
            raise AppException(f"Media upload failed: {str(e)}")

        finally:
            if file_path:
                try:
                    Utility.remove_file_path(file_path)
                except Exception as cleanup_err:
                    logger.warning(f"Failed to cleanup temp file {file_path}: {cleanup_err}")

        return media_id

    @staticmethod
    def validate_media_file_type(file_content: File):
        content_type = file_content.content_type

        if content_type not in MIME_TYPE_LIMITS:
            raise AppException(
                f"Invalid file type: {content_type}. "
                f"Allowed types are: {', '.join(MIME_TYPE_LIMITS.keys())}."
            )

        size_limit = MIME_TYPE_LIMITS[content_type]

        file_content.file.seek(0, 2)
        size = file_content.file.tell()
        file_content.file.seek(0)

        if size > size_limit:
            raise AppException(
                f"File size {size / (1024 * 1024):.2f} MB exceeds the "
                f"limit of {size_limit / (1024 * 1024):.2f} MB for {content_type}."
            )

