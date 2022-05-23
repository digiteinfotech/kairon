from mongoengine import Document, StringField, DictField, DateTimeField, ValidationError, ListField, BooleanField
from datetime import datetime

from kairon.shared.account.processor import AccountProcessor
from kairon.shared.data.signals import push_notification
from kairon.shared.utils import Utility


@push_notification.apply
class LiveAgents(Document):
    agent_type = StringField(required=True, choices=Utility.get_live_agents)
    config = DictField(required=True)
    override_bot = BooleanField(default=False)
    trigger_on_intents = ListField(StringField(), default=[])
    trigger_on_actions = ListField(StringField(), default=[])
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    def validate(self, clean=True):
        Utility.validate_live_agent_config(self.agent_type, self.config, ValidationError)
        if not (self.override_bot or self.trigger_on_intents or self.trigger_on_actions):
            raise ValueError("At least 1 intent or action is required to perform agent handoff")

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        from kairon.live_agent.factory import LiveAgentFactory

        bot_info = AccountProcessor.get_bot(document.bot)
        agent = LiveAgentFactory.get_agent(document.agent_type, document.config)
        agent.validate_credentials()
        metadata = agent.complete_prerequisites(**bot_info)
        if metadata:
            document.config.update(metadata)
        for required_field in Utility.system_metadata['live_agents'][document.agent_type]['required_fields']:
            document.config[required_field] = Utility.encrypt_message(document.config[required_field])


class LiveAgentMetadata(Document):
    agent_type = StringField(required=True, choices=Utility.get_live_agents())
    sender_id = StringField(required=True)
    metadata = DictField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)


from mongoengine import signals
signals.pre_save_post_validation.connect(LiveAgents.pre_save_post_validation, sender=LiveAgents)
