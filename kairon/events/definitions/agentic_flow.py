import asyncio
import json
from typing import Text
from loguru import logger
from kairon import Utility
from kairon.events.definitions.base import EventsBase
from kairon.exceptions import AppException
from kairon.shared.chat.agent.agent_flow import AgenticFlow
from kairon.shared.constants import EventClass


class AgenticFlowEvent(EventsBase):
    """
    Event to execute an agentic flow
    """

    def __init__(self, bot: Text, user: Text, **kwargs):
        """
        Initialise event.
        """
        self.bot = bot
        self.user = user
        self.flow_name = kwargs.get('flow_name')

    def validate(self):
        """
        validate mail channel exists and works properly
        """
        if self.flow_name:
            return AgenticFlow.flow_exists(self.bot, self.flow_name)

    def enqueue(self, **kwargs):
        """
        Send event to event server.
        """
        try:
            payload = {'bot': self.bot, 'user': self.user}
            if flow_name := kwargs.get('flow_name'):
                payload['flow_name'] = flow_name
                self.flow_name = flow_name
            if slot_data := kwargs.get('slot_data'):
                payload['slot_data'] = slot_data
            self.validate()
            Utility.request_event_server(EventClass.agentic_flow, payload)
        except Exception as e:
            logger.error(str(e))
            raise AppException(e)

    def execute(self, **kwargs):
        """
        Execute the event.
        """
        try:
            if flow_name := kwargs.get('flow_name'):
                self.flow_name = flow_name

            slot_vals = {}
            if slot_data := kwargs.get('slot_data'):
                if isinstance(slot_data, str):
                    slot_data = json.loads(slot_data)
                slot_vals = slot_data
            flow = AgenticFlow(bot=self.bot, slot_vals=slot_vals)
            resp, errors = asyncio.run(flow.execute_rule(self.flow_name))
            logger.info(resp)
            if errors:
                logger.error(f"Failed to execute flow {self.flow_name}. Errors: {errors}")
                raise AppException(f"Failed to execute flow {self.flow_name}. Errors: {errors}")
        except Exception as e:
            logger.error(str(e))
            raise AppException(f"Failed to execute flow {self.flow_name} for bot {self.bot}. Error: {str(e)}")
