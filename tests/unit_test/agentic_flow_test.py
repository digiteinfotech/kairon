import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import mongomock
from mock.mock import AsyncMock
from rasa.shared.core.events import (
    Event,
    BotUttered,
)

import pytest
from joblib.testing import fixture
from mongoengine import connect, disconnect
from rasa.shared.core.slots import TextSlot
from rasa.shared.core.trackers import DialogueStateTracker

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.chat.agent.agent_flow import AgenticFlow



from kairon.shared.account.data_objects import Bot, Account

from kairon.shared.data.data_objects import BotSettings, Slots, Rules, Responses, MultiflowStories, GlobalSlots
from kairon.shared.models import GlobalSlotsEntryType


class TestAgenticFlow:
    @classmethod
    def setup_class(cls):

        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        connect(**Utility.mongoengine_connection())
        BotSettings.objects(user="af_channel_test_user_acc").delete()

        a = Account.objects.create(name="af_channel_test_user_acc", user="af_channel_test_user_acc")
        bot = Bot.objects.create(name="af_channel_test_bot", user="af_channel_test_user_acc", status=True,
                                 account=a.id)
        pytest.af_test_bot = str(bot.id)
        pytest.af_test_user = 'af_channel_test_user_acc'
        BotSettings(bot=pytest.af_test_bot, user="af_channel_test_user_acc").save()
        print("setup")
        utterance_rule = {
            "block_name": "simple_utter",
            "condition_events_indices": [],
            "start_checkpoints": ["STORY_START"],
            "end_checkpoints": [],
            "events": [
                {"name": "...", "type": "action"},
                {"name": "simple_utter_int", "type": "user"},
                {"name": "utter_greet", "type": "action"}
            ],
            "bot": pytest.af_test_bot,
            "user": pytest.af_test_user,
            "timestamp": datetime.strptime("2025-01-28T09:43:29.549Z", "%Y-%m-%dT%H:%M:%S.%fZ"),
            "status": True,
            "template_type": "CUSTOM"
        }
        action_rule = {
            "block_name": "action_rule",
            "condition_events_indices": [],
            "start_checkpoints": ["STORY_START"],
            "end_checkpoints": [],
            "events": [
                {"name": "...", "type": "action"},
                {"name": "simple_act_int", "type": "user"},
                {"name": "simple_action", "type": "action"}
            ],
            "bot": pytest.af_test_bot,
            "user": pytest.af_test_user,
            "timestamp": datetime.strptime("2025-01-28T09:43:29.549Z", "%Y-%m-%dT%H:%M:%S.%fZ"),
            "status": True,
            "template_type": "CUSTOM"
        }
        Rules(**utterance_rule).save()
        Rules(**action_rule).save()

        utter_greet = {
            "name": "utter_greet",
            "text": {
                "text": "Let me be your AI Assistant and provide you with service"
            },
            "bot": pytest.af_test_bot,
            "user": pytest.af_test_user,
            "timestamp": {
                "$date": "2024-12-13T09:26:19.675Z"
            },
            "status": True
        }

        Responses(**utter_greet).save()

        slot_data_1 = {

            "name": "trigger_conditional",
            "type": "categorical",
            "initial_value": "1",
            "values": [
                "1",
                "2"
            ],
            "bot": pytest.af_test_bot,
            "user": pytest.af_test_user,
            "status": True,
            "influence_conversation": True,
            "_has_been_set": False,
            "is_default": False
        }

        slot_data_2 = {
            "name": "subject",
            "type": "text",
            "bot": pytest.af_test_bot,
            "user": pytest.af_test_user,
            "status": True,
            "influence_conversation": True,
            "_has_been_set": False,
            "is_default": True
        }

        slot_data_3 = {
            "name": "order",
            "type": "any",
            "bot": pytest.af_test_bot,
            "user": pytest.af_test_user,
            "status": True,
            "influence_conversation": False,
            "_has_been_set": False,
            "is_default": True
        }

        Slots(**slot_data_1).save()
        Slots(**slot_data_2).save()
        Slots(**slot_data_3).save()

        multiflow_data = {
            "block_name": "py_multiflow",
            "start_checkpoints": [
                "STORY_START"
            ],
            "end_checkpoints": [],
            "events": [
                {
                    "step": {
                        "name": "i_multiflow",
                        "type": "INTENT",
                        "node_id": "5691320b-6007-4609-8386-bee3afdd9490",
                        "component_id": "676a9c57097f6a9872bc49d5"
                    },
                    "connections": [
                        {
                            "name": "py_multi",
                            "type": "PYSCRIPT_ACTION",
                            "node_id": "715f57e6-90df-42b1-b0de-daa14b22d72f",
                            "component_id": "676a9cbc097f6a9872bc49d7"
                        }
                    ]
                },
                {
                    "step": {
                        "name": "py_multi",
                        "type": "PYSCRIPT_ACTION",
                        "node_id": "715f57e6-90df-42b1-b0de-daa14b22d72f",
                        "component_id": "676a9cbc097f6a9872bc49d7"
                    },
                    "connections": [
                        {
                            "name": "trigger_conditional",
                            "type": "SLOT",
                            "value": "1",
                            "node_id": "fe210aa4-4885-4454-9acf-607621228ffd",
                            "component_id": "fe210aa4-4885-4454-9acf-607621228ffd"
                        },
                        {
                            "name": "trigger_conditional",
                            "type": "SLOT",
                            "value": "2",
                            "node_id": "589cebb9-7a93-4e76-98f8-342b123f32b8",
                            "component_id": "589cebb9-7a93-4e76-98f8-342b123f32b8"
                        }
                    ]
                },
                {
                    "step": {
                        "name": "trigger_conditional",
                        "type": "SLOT",
                        "value": "1",
                        "node_id": "fe210aa4-4885-4454-9acf-607621228ffd",
                        "component_id": ""
                    },
                    "connections": [
                        {
                            "name": "py_ans_a",
                            "type": "PYSCRIPT_ACTION",
                            "node_id": "61d7459c-5a34-464a-b9e5-25e7808f1f24",
                            "component_id": "676a9ceb097f6a9872bc49db"
                        }
                    ]
                },
                {
                    "step": {
                        "name": "py_ans_a",
                        "type": "PYSCRIPT_ACTION",
                        "node_id": "61d7459c-5a34-464a-b9e5-25e7808f1f24",
                        "component_id": "676a9ceb097f6a9872bc49db"
                    },
                    "connections": [{
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "7c58bd84-48ab-45e3-aa50-bef52c50c4b6",
                            "component_id": "67a5a302956678b8f9106ee6"
                        }]
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "7c58bd84-48ab-45e3-aa50-bef52c50c4b6",
                        "component_id": "67a5a302956678b8f9106ee6"
                    },
                    "connections": []
                },
                {
                    "step": {
                        "name": "trigger_conditional",
                        "type": "SLOT",
                        "value": "2",
                        "node_id": "589cebb9-7a93-4e76-98f8-342b123f32b8",
                        "component_id": ""
                    },
                    "connections": [
                        {
                            "name": "fetch_poke_details",
                            "type": "HTTP_ACTION",
                            "node_id": "4f331af0-870e-40f3-883e-51c2a86f98eb",
                            "component_id": "676bfe0390a2c983e628f108"
                        }
                    ]
                },
                {
                    "step": {
                        "name": "fetch_poke_details",
                        "type": "HTTP_ACTION",
                        "node_id": "4f331af0-870e-40f3-883e-51c2a86f98eb",
                        "component_id": "676bfe0390a2c983e628f108"
                    },
                    "connections": [
                        {
                            "name": "py_ans_b",
                            "type": "PYSCRIPT_ACTION",
                            "node_id": "1019cbaa-68fe-40c6-bcb9-c3e08e58e7ef",
                            "component_id": "676a9d3c097f6a9872bc49df"
                        }
                    ]
                },
                {
                    "step": {
                        "name": "py_ans_b",
                        "type": "PYSCRIPT_ACTION",
                        "node_id": "1019cbaa-68fe-40c6-bcb9-c3e08e58e7ef",
                        "component_id": "676a9d3c097f6a9872bc49df"
                    },
                    "connections": []
                }
            ],
            "metadata": [
                {
                    "node_id": "61d7459c-5a34-464a-b9e5-25e7808f1f24",
                    "flow_type": "RULE"
                },
                {
                    "node_id": "1019cbaa-68fe-40c6-bcb9-c3e08e58e7ef",
                    "flow_type": "RULE"
                }
            ],
            "bot": pytest.af_test_bot,
            "user": pytest.af_test_user,
            "status": True,
            "template_type": "CUSTOM"
        }

        MultiflowStories(**multiflow_data).save()

    @classmethod
    def teardown_class(cls):
        BotSettings.objects().delete()
        Bot.objects().delete()
        Account.objects().delete()
        Slots.objects().delete()
        Rules.objects().delete()
        Responses.objects().delete()
        MultiflowStories.objects().delete()

        disconnect()


    @pytest.mark.asyncio
    @patch('kairon.shared.chat.agent.agent_flow.AgenticFlow.log_chat_history')
    async def test_simple_utter(self, patch_log_chat_history):
        print(pytest.af_test_bot)
        flow = AgenticFlow(pytest.af_test_bot)
        res, err = await flow.execute_rule("simple_utter")
        assert res == [{'text': 'Let me be your AI Assistant and provide you with service'}]
        assert not err
        patch_log_chat_history.assert_called_once()

    @pytest.mark.asyncio
    @patch('kairon.shared.chat.agent.agent_flow.AgenticFlow.log_chat_history')
    async def test_non_existing_rule(self, patch_log_chat_history):
        flow = AgenticFlow(pytest.af_test_bot)
        with pytest.raises(AppException, match='\[non_existing_rule\] not found for this bot'):
            res, err = await flow.execute_rule("non_existing_rule")
        patch_log_chat_history.assert_not_called()

    @pytest.mark.asyncio
    @patch('kairon.shared.chat.agent.agent_flow.AgenticFlow.log_chat_history')
    async def test_bot_doesnot_exist(self, patch_log_chat_history):
        with pytest.raises(AppException, match='Bot \[non_existing_bot\] not found'):
            flow = AgenticFlow("non_existing_bot")
            res, err = await flow.execute_rule("simple_utter")
        patch_log_chat_history.assert_not_called()

    @fixture
    def mock_action(self):
        with patch('kairon.chat.actions.KRemoteAction.run', ) as mock_action:
            yield mock_action

    @pytest.mark.asyncio
    @patch('kairon.shared.chat.agent.agent_flow.AgenticFlow.log_chat_history')
    async def test_execute__rule_with_action(self, patch_log_chat_history):
        flow = AgenticFlow(pytest.af_test_bot)
        with patch('kairon.chat.actions.KRemoteAction.run' ) as mock_action:
            mock_action.return_value = [BotUttered("Action Executed")]
            res, err = await flow.execute_rule("action_rule")
            assert res == [{'text': 'Action Executed'}]
            assert not err
            mock_action.assert_called_once()
            patch_log_chat_history.assert_called_once()

    @pytest.mark.asyncio
    @patch('kairon.shared.chat.agent.agent_flow.AgenticFlow.log_chat_history')
    async def test_execute__rule_with_action2(self, patch_log_chat_history):
        flow = AgenticFlow(pytest.af_test_bot, sender_id='sender')
        with patch('kairon.chat.actions.KRemoteAction.run') as mock_action:
            mock_action.return_value = [BotUttered("Action Executed")]
            res, err = await flow.execute_rule("action_rule")
            assert res == [{'text': 'Action Executed'}]
            print(flow.sender_id)
            assert not err
            slots = flow.get_non_empty_slots(False)
            assert slots == {'trigger_conditional': '1', 'agentic_flow_bot_user': 'af_channel_test_user_acc'}

            mock_action.assert_called_once()
            patch_log_chat_history.assert_called_once()

    @pytest.mark.asyncio
    @patch('kairon.shared.chat.agent.agent_flow.AgenticFlow.log_chat_history')
    async def test_execute__rule_with_multiflow(self, patch_log_chat_history):
        flow = AgenticFlow(pytest.af_test_bot)
        with patch('kairon.chat.actions.KRemoteAction.run') as mock_action:
            mock_action.return_value = [BotUttered("Action Executed")]
            res, err = await flow.execute_rule("py_multiflow")
            assert len(res) == 3
            assert res[0] == {'text': 'Action Executed'}
            assert not err
            assert flow.executed_actions == ['py_multi', 'py_ans_a', 'utter_greet']
            mock_action.assert_called()
            patch_log_chat_history.assert_called_once()

    @pytest.mark.asyncio
    @patch('kairon.shared.chat.agent.agent_flow.AgenticFlow.log_chat_history')
    async def test_execute__rule_with_multiflow_slot_influence(self, patch_log_chat_history):
        flow = AgenticFlow(pytest.af_test_bot)
        flow.fake_tracker.slots["trigger_conditional"].value = "2"
        with patch('kairon.chat.actions.KRemoteAction.run') as mock_action:
            mock_action.return_value = [BotUttered("Action Executed")]
            res, err = await flow.execute_rule("py_multiflow")
            assert len(res) == 3
            assert res[0] == {'text': 'Action Executed'}
            assert not err
            mock_action.assert_called()
            assert flow.executed_actions == ['py_multi', 'fetch_poke_details', 'py_ans_b']
            patch_log_chat_history.assert_called_once()

    @pytest.mark.asyncio
    @patch('kairon.shared.chat.agent.agent_flow.AgenticFlow.log_chat_history')
    async def test_execute__rule_with_multiflow_slot_influence2(self, patch_log_chat_history):
        flow = AgenticFlow(pytest.af_test_bot, {
            "trigger_conditional": "2"
        })
        with patch('kairon.chat.actions.KRemoteAction.run') as mock_action:
            mock_action.return_value = [BotUttered("Action Executed")]
            res, err = await flow.execute_rule("py_multiflow")
            assert len(res) == 3
            mock_action.assert_called()
            assert flow.executed_actions == ['py_multi', 'fetch_poke_details', 'py_ans_b']

        flow = AgenticFlow(pytest.af_test_bot, {
            "trigger_conditional": "1"
        })
        with patch('kairon.chat.actions.KRemoteAction.run') as mock_action:
            mock_action.return_value = [BotUttered("Action Executed")]
            res, err = await flow.execute_rule("py_multiflow")
            assert len(res) == 3
            mock_action.assert_called()
            print(flow.executed_actions)
            assert flow.executed_actions == ['py_multi', 'py_ans_a', 'utter_greet']

        patch_log_chat_history.assert_called()


    def test_loading_slots(self):
        flow = AgenticFlow(pytest.af_test_bot)
        slots = flow.load_slots()
        print(slots)
        assert len(slots) == 4
        slot_names = [slot.name for slot in slots]
        assert "trigger_conditional" in slot_names
        assert "subject" in slot_names
        assert "order" in slot_names
        assert "agentic_flow_bot_user" in slot_names

    def test_evaluate_criteria_slot_set(self):
        criteria = "SLOT"
        agentic_flow = AgenticFlow(pytest.af_test_bot)
        agentic_flow.fake_tracker.slots["order"].value = "apple"
        connections = {"name": "order", "order": "apple", "apple": "next_node"}
        result = agentic_flow.evaluate_criteria(criteria, connections)
        assert result == "next_node"
        assert not agentic_flow.errors

    def test_evaluate_criteria_slot_set_value_not_set(self):
        criteria = "SLOT"
        agentic_flow = AgenticFlow(pytest.af_test_bot)
        connections = {"name": "order", "order": "apple", "apple": "next_node"}
        result = agentic_flow.evaluate_criteria(criteria, connections)
        assert not result
        assert agentic_flow.errors
        assert agentic_flow.errors ==  ['Slot [order] not set!']

    def test_sanitize_multiflow_events(self):
        multiflow = MultiflowStories.objects(bot=pytest.af_test_bot, block_name='py_multiflow').first()
        events = multiflow.events
        event_map, start = AgenticFlow.sanitize_multiflow_events(events)
        expected = {
            '5691320b-6007-4609-8386-bee3afdd9490': {'node_id': '5691320b-6007-4609-8386-bee3afdd9490', 'type': 'INTENT', 'name': 'i_multiflow', 'connections': {'type': 'jump', 'node_id': '715f57e6-90df-42b1-b0de-daa14b22d72f'}},
            '715f57e6-90df-42b1-b0de-daa14b22d72f': {'node_id': '715f57e6-90df-42b1-b0de-daa14b22d72f', 'type': 'action', 'name': 'py_multi', 'connections': {'type': 'branch', 'criteria': 'SLOT', 'name': 'trigger_conditional', '1': 'fe210aa4-4885-4454-9acf-607621228ffd', '2': '589cebb9-7a93-4e76-98f8-342b123f32b8'}},
            'fe210aa4-4885-4454-9acf-607621228ffd': {'node_id': 'fe210aa4-4885-4454-9acf-607621228ffd', 'type': 'SLOT', 'name': 'trigger_conditional', 'connections': {'type': 'jump', 'node_id': '61d7459c-5a34-464a-b9e5-25e7808f1f24'}},
            '61d7459c-5a34-464a-b9e5-25e7808f1f24': {'node_id': '61d7459c-5a34-464a-b9e5-25e7808f1f24', 'type': 'action', 'name': 'py_ans_a', 'connections': {'type': 'jump', 'node_id': '7c58bd84-48ab-45e3-aa50-bef52c50c4b6'}},
            '7c58bd84-48ab-45e3-aa50-bef52c50c4b6': {'node_id': '7c58bd84-48ab-45e3-aa50-bef52c50c4b6', 'type': 'BOT', 'name': 'utter_greet', 'connections': None},
            '589cebb9-7a93-4e76-98f8-342b123f32b8': {'node_id': '589cebb9-7a93-4e76-98f8-342b123f32b8', 'type': 'SLOT', 'name': 'trigger_conditional', 'connections': {'type': 'jump', 'node_id': '4f331af0-870e-40f3-883e-51c2a86f98eb'}},
            '4f331af0-870e-40f3-883e-51c2a86f98eb': {'node_id': '4f331af0-870e-40f3-883e-51c2a86f98eb', 'type': 'action', 'name': 'fetch_poke_details', 'connections': {'type': 'jump', 'node_id': '1019cbaa-68fe-40c6-bcb9-c3e08e58e7ef'}},
            '1019cbaa-68fe-40c6-bcb9-c3e08e58e7ef': {'node_id': '1019cbaa-68fe-40c6-bcb9-c3e08e58e7ef', 'type': 'action', 'name': 'py_ans_b', 'connections': None}}

        print(event_map)
        assert event_map == expected
        assert  start == '715f57e6-90df-42b1-b0de-daa14b22d72f'


    @pytest.mark.asyncio
    async def test_log_chathistory(self):
        flow = AgenticFlow(pytest.af_test_bot)
        pymongo_mock_client = mongomock.MongoClient('mongodb://localhost:27017/db')
        AgenticFlow.chat_history_client = pymongo_mock_client
        with patch('kairon.chat.actions.KRemoteAction.run') as mock_action:
            mock_action.return_value = [BotUttered("Action Executed")]
            res, err = await flow.execute_rule("action_rule")
            assert res == [{'text': 'Action Executed'}]
            assert not err
            mock_action.assert_called_once()

        collection = pymongo_mock_client.get_database().get_collection(f"{pytest.af_test_bot}_agent")
        data =  collection.find()
        data_entries = list(data)

        pymongo_mock_client.close()

        assert len(data_entries) == 1
        assert data_entries[0]['data']
        assert data_entries[0]['data']['action'] == ['simple_action']
        assert data_entries[0]['data']['bot_response'] == [{'text': 'Action Executed'}]
        assert data_entries[0]['data']['user_input'] == 'action_rule'

    @patch.object(AgenticFlow, 'load_slots')
    @patch.object(AgenticFlow, '__init__', lambda self, bot: None)
    def test_create_fake_tracker(self, mock_load_slots):
        mock_load_slots.return_value = [
            TextSlot(name='slot1', initial_value='value1', influence_conversation=True, mappings=[]),
            TextSlot(name='slot2', initial_value='value2', influence_conversation=True, mappings=[])
        ]
        agentic_flow = AgenticFlow(bot='test_bot')
        agentic_flow.bot = 'test_bot'
        agentic_flow.should_use_global_slots = False
        tracker = agentic_flow.create_fake_tracker(slot_vals={'slot1': 'value1'}, sender_id='test_sender')

        assert isinstance(tracker, DialogueStateTracker)
        assert tracker.sender_id == 'test_sender'
        assert tracker.slots['slot1'].value == 'value1'
        assert tracker.slots['slot2'].value == 'value2'
        assert tracker._max_event_history == 20
        mock_load_slots.assert_called_once_with({'slot1': 'value1'})



    @patch.object(AgenticFlow, 'load_rule_events')
    @patch.object(AgenticFlow, 'create_fake_tracker')
    @patch.object(AgenticFlow, 'execute_event', new_callable=AsyncMock)
    @patch.object(AgenticFlow, 'log_chat_history', new_callable=AsyncMock)
    @patch.object(AgenticFlow, '__init__', lambda self, bot: None)
    @pytest.mark.asyncio
    async def test_execute_rule_2(self, mock_log_chat_history, mock_execute_event, mock_create_fake_tracker, mock_load_rule_events):
        mock_create_fake_tracker.return_value = DialogueStateTracker(sender_id='test_sender', slots=[], max_event_history=20)
        mock_load_rule_events.return_value = ([{'type': 'action', 'name': 'test_action'}], None)

        agentic_flow = AgenticFlow(bot='test_bot')
        agentic_flow.sender_id = 'test_sender'
        agentic_flow.should_use_global_slots = True
        agentic_flow.bot = 'test_bot'
        agentic_flow.fake_tracker = mock_create_fake_tracker.return_value
        agentic_flow.should_use_global_slots = False
        responses, errors = await agentic_flow.execute_rule(rule_name='test_rule', sender_id='test_sender', slot_vals={'slot1': 'value1'})

        assert responses == []
        assert errors == []
        mock_create_fake_tracker.assert_called_once_with({'slot1': 'value1'}, 'test_sender')
        mock_load_rule_events.assert_called_once_with('test_rule')
        mock_execute_event.assert_called_once_with({'type': 'action', 'name': 'test_action'})
        mock_log_chat_history.assert_called_once_with('test_rule')



    @patch.object(Rules, 'objects')
    @patch.object(MultiflowStories, 'objects')
    def test_flow_exists(self, mock_multiflow_objects, mock_rules_objects):
        mock_rules_objects.return_value = True
        mock_multiflow_objects.return_value = False

        assert AgenticFlow.flow_exists('test_bot', 'test_flow') is True
        mock_rules_objects.assert_called_once_with(bot='test_bot', block_name='test_flow')
        mock_multiflow_objects.assert_not_called()

        mock_rules_objects.return_value = False
        mock_multiflow_objects.return_value = True

        assert AgenticFlow.flow_exists('test_bot', 'test_flow') is True
        mock_rules_objects.assert_called_with(bot='test_bot', block_name='test_flow')
        mock_multiflow_objects.assert_called_with(bot='test_bot', block_name='test_flow')

        mock_rules_objects.return_value = False
        mock_multiflow_objects.return_value = False

        assert AgenticFlow.flow_exists('test_bot', 'test_flow') is False
        mock_rules_objects.assert_called_with(bot='test_bot', block_name='test_flow')
        mock_multiflow_objects.assert_called_with(bot='test_bot', block_name='test_flow')

    @patch('kairon.shared.chat.agent.agent_flow.GlobalSlots.objects')
    def test_save_global_slots_no_entry(self, mock_global_slots_objects):
        mock_global_slots_objects.return_value.first.return_value = None
        mock_entry = MagicMock()
        mock_global_slots_objects.return_value.create.return_value = mock_entry

        agentic_flow = AgenticFlow(bot=pytest.af_test_bot, sender_id='test_sender')
        agentic_flow.save_global_slots()

        mock_global_slots_objects.assert_any_call(
            bot=pytest.af_test_bot,
            sender_id='test_sender',
            entry_type=GlobalSlotsEntryType.agentic_flow.value
        )

    @patch('kairon.shared.chat.agent.agent_flow.GlobalSlots.objects')
    def test_save_global_slots_with_entry(self, mock_global_slots_objects):
        mock_entry = MagicMock()
        mock_global_slots_objects.return_value.first.return_value = mock_entry

        agentic_flow = AgenticFlow(bot=pytest.af_test_bot, sender_id='test_sender')
        agentic_flow.save_global_slots()

        assert agentic_flow.should_use_global_slots
        mock_global_slots_objects.assert_any_call(
            bot=pytest.af_test_bot,
            sender_id='test_sender',
            entry_type=GlobalSlotsEntryType.agentic_flow.value
        )
        mock_entry.save.assert_called_once()

    @patch('kairon.shared.chat.agent.agent_flow.GlobalSlots.objects')
    def test_update_existing_global_slots(self, mock_global_slots_objects):
        mock_entry = MagicMock()
        mock_global_slots_objects.return_value.first.return_value = mock_entry

        agentic_flow = AgenticFlow(bot=pytest.af_test_bot, sender_id='test_sender')
        agentic_flow.save_global_slots()

        mock_global_slots_objects.assert_any_call(
            bot=pytest.af_test_bot,
            sender_id='test_sender',
            entry_type=GlobalSlotsEntryType.agentic_flow.value
        )
        mock_entry.save.assert_called_once()

    @patch('kairon.shared.chat.agent.agent_flow.GlobalSlots.objects')
    def test_save_global_slots_exception(self, mock_global_slots_objects):
        mock_global_slots_objects.return_value.first.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            agentic_flow = AgenticFlow(bot=pytest.af_test_bot, sender_id='test_sender')
            agentic_flow.save_global_slots()

        mock_global_slots_objects.assert_called_once()

    def test_save_global_slots_not_used(self):
        agentic_flow = AgenticFlow(bot=pytest.af_test_bot)
        assert not agentic_flow.should_use_global_slots



    @patch.object(AgenticFlow, 'load_global_slots')
    def test_create_fake_tracker_new(self, mock_load_global_slots):
        mock_load_global_slots.return_value = {
            'order': 'global_value1',
            'subject': 'global_value2'
        }

        agentic_flow = AgenticFlow(bot=pytest.af_test_bot, sender_id='test_sender')
        agentic_flow.should_use_global_slots = True
        slot_vals = {'subject': 'local_value2'}
        tracker = agentic_flow.create_fake_tracker(slot_vals, 'test_sender')
        assert isinstance(tracker, DialogueStateTracker)
        assert tracker.sender_id == 'test_sender'
        assert tracker.slots['order'].value == 'global_value1'
        assert tracker.slots['subject'].value == 'local_value2'
        mock_load_global_slots.assert_called()

