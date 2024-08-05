from datetime import datetime
from typing import Dict, Text

from loguru import logger
from mongoengine import DoesNotExist

from kairon.shared.utils import Utility
from kairon.exceptions import AppException
from kairon.shared.live_agent.data_objects import LiveAgents, LiveAgentMetadata


class LiveAgentsProcessor:

    @staticmethod
    def save_config(configuration: Dict, bot: Text, user: Text):
        """
        Save or updates live agent configuration.

        :param configuration: config dict
        :param bot: bot id
        :param user: user id
        :return: None
        """
        try:
            agent = LiveAgents.objects(bot=bot).get()
            agent.agent_type = configuration['agent_type']
            agent.config = configuration['config']
            agent.override_bot = configuration['override_bot']
            agent.trigger_on_intents = configuration.get('trigger_on_intents')
            agent.trigger_on_actions = configuration.get('trigger_on_actions')
        except DoesNotExist:
            agent = LiveAgents(**configuration)
            agent.bot = bot
        agent.user = user
        agent.timestamp = datetime.utcnow()
        agent.save()

    @staticmethod
    def delete_config(bot: Text, user: str = None):
        """
        Delete a particular live agent configuration for bot

        :param bot: bot id
        :return: None
        """
        Utility.hard_delete_document([LiveAgents], bot=bot, user=user)

    @staticmethod
    def get_config(bot: Text, mask_characters=True, raise_error: bool = True):
        """
        Fetch particular live agent config for bot.

        :param bot: bot id
        :param mask_characters: whether to mask the security keys default is True
        :param raise_error: raise exception if config not found
        :return: Dict
        """
        try:
            config = LiveAgents.objects(bot=bot).exclude("bot", "user").get().to_mongo().to_dict()
            config.pop("_id")
            logger.debug(config)
            agent_params = Utility.system_metadata['live_agents'][config['agent_type']]
            for require_field in agent_params['required_fields']:
                config['config'][require_field] = Utility.decrypt_message(config['config'][require_field])
                if mask_characters:
                    config['config'][require_field] = config['config'][require_field][:-3] + '***'
            return config
        except DoesNotExist:
            if raise_error:
                raise AppException("Live agent config not found!")

    @staticmethod
    def get_contact(bot: Text, sender_id: Text, agent_type: Text):
        """
        Retrieve chatwoot contact metadata for a particular bot, sender and agent type.

        :param bot: bot id
        :param sender_id: end user identifier
        :param agent_type: agent type(eg: chatwoot)
        """
        try:
            contact = LiveAgentMetadata.objects(bot=bot, sender_id=sender_id, agent_type=agent_type).get()
            return contact.to_mongo().to_dict()
        except DoesNotExist:
            return None

    @staticmethod
    def save_contact(bot: Text, sender_id: Text, agent_type: Text, metadata: Dict):
        """
        Add contact metadata for a particular bot, sender and agent type.

        :param bot: bot id
        :param sender_id: end user identifier
        :param agent_type: agent type(eg: chatwoot)
        :param metadata: metadata about sender as dict
        """
        try:
            contact = LiveAgentMetadata.objects(bot=bot, sender_id=sender_id, agent_type=agent_type).get()
        except DoesNotExist:
            contact = LiveAgentMetadata(bot=bot, sender_id=sender_id, agent_type=agent_type)
        contact.metadata = metadata
        contact.save()
