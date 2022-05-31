from typing import Dict, Text

from mongoengine import DoesNotExist
from loguru import logger
from .data_objects import Channels
from datetime import datetime
from kairon.shared.utils import Utility
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
        try:
            channel = Channels.objects(bot=bot, connector_type=configuration['connector_type']).get()
            channel.config = configuration['config']
        except:
            channel = Channels(**configuration)
            channel.bot = bot
        channel.user = user
        channel.timestamp = datetime.utcnow()
        channel.save()
        channel_endpoint = DataUtility.get_channel_endpoint(channel)
        return channel_endpoint

    @staticmethod
    def delete_channel_config(connector_type: Text, bot: Text):
        """
        Delete a particular channel configuration for bot
        :param connector_type: channel name
        :param bot: bot id
        :return: None
        """
        Utility.hard_delete_document([Channels], bot=bot, connector_type=connector_type)

    @staticmethod
    def list_channel_config(bot: Text, mask_characters: bool = True):
        """
        list channel configuration against the bot
        :param bot: bot id
        :param mask_characters: whether to mask the security keys default is True
        :return: List
        """
        for channel in Channels.objects(bot=bot).exclude("user", "timestamp", "id"):
            data = channel.to_mongo().to_dict()
            data.pop("timestamp")
            channel_params = Utility.system_metadata['channels'][data['connector_type']]
            for require_field in channel_params['required_fields']:
                data['config'][require_field] = Utility.decrypt_message(data['config'][require_field])
                if mask_characters:
                    data['config'][require_field] = data['config'][require_field][:-5] + '*****'
            yield data

    @staticmethod
    def get_channel_config(connector_type: Text, bot: Text, mask_characters=True):
        """
        fetch particular channel config for bot
        :param connector_type: channel name
        :param bot: bot id
        :param mask_characters: whether to mask the security keys default is True
        :return: Dict
        """
        config = Channels.objects(bot=bot, connector_type=connector_type).exclude("user").get().to_mongo().to_dict()
        logger.debug(config)
        config.pop("timestamp")
        channel_params = Utility.system_metadata['channels'][config['connector_type']]
        for require_field in channel_params['required_fields']:
            config['config'][require_field] = Utility.decrypt_message(config['config'][require_field])
            if mask_characters:
                config['config'][require_field] = config['config'][require_field][:-5] + '*****'

        return config

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

