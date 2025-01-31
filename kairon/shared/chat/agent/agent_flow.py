import time

from mongoengine import DoesNotExist
from pymongo import MongoClient
from rasa.core.nlg import TemplatedNaturalLanguageGenerator
from rasa.shared.core.events import UserUttered
from rasa.shared.core.slots import TextSlot, BooleanSlot, CategoricalSlot, FloatSlot, ListSlot, AnySlot
from rasa.shared.core.trackers import DialogueStateTracker
from uuid6 import uuid7

from kairon import Utility
from kairon.chat.actions import KRemoteAction
from kairon.exceptions import AppException
from kairon.shared.data.data_objects import Slots, Rules, MultiflowStories, Responses, BotSettings
from kairon.shared.data.processor import MongoProcessor
from loguru import logger
import random


class AgenticFlow:
    mongo_processor = MongoProcessor()
    chat_history_client = None

    SLOT_TYPE_MAP = {
        "text": {
            'constructor': TextSlot,
            'args': ['name', 'initial_value', 'value_reset_delay', 'influence_conversation', 'mappings']
        },
        "boolean": {
            'constructor': BooleanSlot,
            'args': ['name', 'initial_value', 'value_reset_delay', 'influence_conversation']
        },
        "categorical": {
            'constructor': CategoricalSlot,
            'args': ['name', 'initial_value', 'value_reset_delay', 'influence_conversation', 'mappings']
        },
        "float": {
            'constructor': FloatSlot,
            'args': ['name', 'initial_value', 'value_reset_delay', 'influence_conversation', 'max_value', 'min_value']
        },
        "list": {
            'constructor': ListSlot,
            'args': ['name', 'initial_value', 'value_reset_delay', 'influence_conversation']
        },
        "any": {
            'constructor': AnySlot,
            'args': ['name', 'initial_value', 'value_reset_delay', 'influence_conversation', 'mappings']
        },
    }

    def __init__(self, bot: str, slot_vals: dict[str,any] = None, sender_id: str = None):
        self.bot = bot
        self.max_history = 20
        self.sender_id =  sender_id if sender_id else str(uuid7().hex)
        self.bot_settings = BotSettings.objects(bot=self.bot).first()
        if not self.bot_settings:
            raise AppException(f"Bot [{self.bot}] not found")
        self.responses = []
        self.errors = []
        slots = self.load_slots(slot_vals)
        self.input_slot_vals = slot_vals
        self.fake_tracker = DialogueStateTracker(sender_id=self.sender_id,
                                                 slots=slots,
                                                 max_event_history=self.max_history)
        endpoint = AgenticFlow.mongo_processor.get_endpoints(
            bot, raise_exception=False
        )
        self.action_endpoint = Utility.get_action_url(endpoint)
        self.domain = AgenticFlow.mongo_processor.load_domain(bot)
        self.nlg = TemplatedNaturalLanguageGenerator(self.domain.responses)
        self.executed_actions = []



    def load_slots(self, slot_vals: dict[str,any] = None) -> list:
        """
        Load slots for the bot from the database
        :param slot_vals: dictionary of slot values
        :return: list of slots
        """
        try:
            if not slot_vals:
                slot_vals = {}
            slots = []
            for slot in Slots.objects(bot=self.bot):
                slot_defination = AgenticFlow.SLOT_TYPE_MAP.get(slot.type)
                if not slot_defination:
                    raise ValueError(f"Unknown slot type: {slot.type}")
                if val := slot_vals.get(slot.name):
                    slot.initial_value = val
                slot_args = {arg: getattr(slot, arg, None) for arg in slot_defination['args']}
                slot_constructor = slot_defination['constructor']
                slots.append(slot_constructor(**slot_args))

            slots.append(TextSlot(name="agentic_flow_bot_user", initial_value=self.bot_settings.user, value_reset_delay=None, influence_conversation=False, mappings=[]))

            return slots
        except Exception as e:
            logger.error(f"Error in loading slots: {e}")
            raise AppException(f"Error in loading slots: {e}")

    def load_rule_events(self, name: str) -> tuple:
        self.fake_tracker.update(UserUttered(name,intent={'name': name, 'confidence': 1.0}))
        try:

            if rule := Rules.objects(bot=self.bot, block_name=name).first():
                events = [{
                        'name': event.name,
                        'type': event.type,
                    } for event in rule.events]
                return events, None
            elif multiflow := MultiflowStories.objects(bot=self.bot, block_name=name).first():
                events = multiflow.events
                event_map, start = AgenticFlow.sanitize_multiflow_events(events)
                return event_map, start
            else:
                raise DoesNotExist(f"[{name}] not found for this bot")
        except DoesNotExist as e:
            raise AppException(e)

    @staticmethod
    def sanitize_multiflow_events(events):
        """
        convert database multiflow events into usable graph format
        :param events: list of events
        :return: graph representing dictionary of events, start node id
        """
        start = events[0]["connections"][0]["node_id"]
        def sanitize_event(ev:dict)-> dict:
            node_id = ev['step']['node_id']
            node_type = ev['step']['type']
            if 'action' in node_type.lower():
                node_type = 'action'
            node_name = ev['step']['name']
            connections = ev['connections']
            conn = None
            if len(connections) == 1:
                conn = {
                    'type': 'jump',
                    'node_id': connections[0]['node_id'],
                }
            elif len(connections) > 1:
                conn = {
                    'type': 'branch',
                    'criteria': connections[0]['type'],
                    'name': connections[0]['name'],
                }
                for c in connections:
                    conn[str(c['value'])] = c['node_id']

            return {
                'node_id': node_id,
                'type': node_type,
                'name': node_name,
                'connections': conn,
            }
        new_graph = {}
        for event in events:
            e = sanitize_event(event)
            new_graph[e['node_id']] = e
        return new_graph, start

    def evaluate_criteria(self, criteria: str, connections: dict):
        if criteria == 'SLOT':
            slot_name = connections['name']
            slot_value = self.fake_tracker.get_slot(slot_name)
            if slot_value and connections.get(slot_value):
                return connections.get(slot_value)
            else:
                self.errors.append(f"Slot [{slot_name}] not set!")
                return None

    async def execute_rule(self, rule_name: str):
        """
        Execute a rule for the bot

        :param rule_name: name of the rule to be executed
        :return: list of responses, list of errors
        """
        self.responses = []
        self.errors = []
        self.executed_actions = []
        events, node_id = self.load_rule_events(rule_name)
        if not node_id:
            for event in events:
                await self.execute_event(event)
        else:
            while node_id:
                event = events[node_id]
                await self.execute_event(event)
                if event.get('connections'):
                    jump_type = event['connections'].get('type')
                    if jump_type == 'jump':
                        node_id = event['connections']['node_id']
                    elif jump_type == 'branch':
                        criteria = event['connections']['criteria']
                        node_id = self.evaluate_criteria(criteria, event['connections'])
                else:
                    node_id = None
        self.log_chat_history(rule_name)
        return self.responses, self.errors

    async def execute_event(self, event: dict):
        if event['type'] == 'action':
            if event['name'] == "...":
                return
            elif event['name'].startswith("utter_"):
                self.responses.append(self.get_utterance_response(event['name']))
                self.executed_actions.append(event['name'])
                return
            try:
                action = KRemoteAction(
                    name=event['name'],
                    action_endpoint=self.action_endpoint
                )
                new_events_for_tracker = await action.run(output_channel=None,
                                 nlg=self.nlg,
                                 tracker=self.fake_tracker,
                                 domain=self.domain)
                self.process_tracker_events(new_events_for_tracker)
                self.fake_tracker.events.extend(new_events_for_tracker)
                self.executed_actions.append(event['name'])
            except Exception as e:
                logger.error(f"Error in executing action [{event['name']}]: {e}")
                raise AppException(f"Error in executing action [{event['name']}]")

    def process_tracker_events(self, events:list):
        for event in events:
            if event.type_name == 'slot':
                self.fake_tracker.slots[event.key].value = event.value
            elif event.type_name == 'action':
                self.fake_tracker.latest_action_name = event.key
            elif event.type_name == 'user':
                self.fake_tracker.latest_message = event.key
            elif event.type_name == 'bot':
                if event.text:
                    self.responses.append({'text': event.text})
                else:
                    self.responses.append({'custom': event.data})

    def get_non_empty_slots(self, all_slots:bool = False) -> dict:
        slots = {}
        for name in self.fake_tracker.slots.keys():
            slot = self.fake_tracker.slots[name]
            if slot.value or all_slots:
                slots[name] = slot.value
        return slots

    def get_utterance_response(self, utterance: str):
        responses = Responses.objects(bot=self.bot, name=utterance)
        if not responses:
            raise AppException(f"No response found for [{utterance}]")
        responses_list = []
        for response in responses:
            if response.text:
                responses_list.append({'text': response.text.text})
            elif response.custom:
                responses_list.append({'custom': response.custom.custom})

        random_response = random.choice(responses_list)
        if random_response.get('text'):
            slot_vals = self.get_non_empty_slots(True)
            random_response['text'] = random_response['text'].format(**slot_vals)

        return random_response

    def log_chat_history(self, rule_name: str):
        if not AgenticFlow.chat_history_client:
            AgenticFlow.chat_history_client = MongoClient(host=Utility.environment["tracker"]["url"])
        db = AgenticFlow.chat_history_client.get_database()
        conversations = db.get_collection(self.bot)
        data = {
          "type": "flattened",
          "sender_id": self.sender_id,
          "conversation_id": str(uuid7().hex),
          "data": {
                "user_input": rule_name,
                "bot_response": self.responses,
                "slots": self.get_non_empty_slots(),
                "errors": self.errors,
                "input_slot_vals": self.input_slot_vals,
                "action": self.executed_actions
          },
          "timestamp": time.time(),
          "tag": "agentic_flow"
        }
        conversations.insert_one(data)