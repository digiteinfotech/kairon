from typing import List

from pydantic import BaseModel, validator

from kairon.live_agent.factory import LiveAgentFactory
from kairon.shared.utils import Utility


class LiveAgentRequest(BaseModel):
    agent_type: str
    config: dict
    trigger_on_intents: List[str] = None
    trigger_on_actions: List[str] = None
    override_bot: bool = False

    @validator("agent_type")
    def validate_agent_type(cls, v, values, **kwargs):
        if v not in Utility.get_live_agents():
            raise ValueError("Agent system not supported")
        return v

    @validator("config")
    def validate_live_agent_config(cls, v, values, **kwargs):
        if 'agent_type' in values:
            Utility.validate_live_agent_config(values['agent_type'], v, ValueError)
            LiveAgentFactory.get_agent(values['agent_type'], v).validate_credentials()
        return v

    @validator("override_bot")
    def validate_channel_config_model(cls, v, values, **kwargs):
        if not (v or values.get('trigger_on_intents') or values.get('trigger_on_actions')):
            raise ValueError("At least 1 intent or action is required to perform agent handoff")
        return v
