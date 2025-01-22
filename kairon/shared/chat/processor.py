from datetime import datetime
from typing import Dict, Text

from loguru import logger
from mongoengine import DoesNotExist

from kairon.shared.utils import Utility
from .broadcast.processor import MessageBroadcastProcessor
from .data_objects import Channels, ChannelLogs
from ..constants import ChannelTypes
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
            channel.config = configuration['config']
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

