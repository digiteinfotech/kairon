import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import mongomock
from rasa.shared.core.events import (
    Event,
    BotUttered,
)

import pytest
from imap_tools import MailMessage
from joblib.testing import fixture
from mongoengine import connect, disconnect

import kairon.shared.chat.agent.agent_flow
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.chat.agent.agent_flow import AgenticFlow

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

from kairon.shared.account.data_objects import Bot, Account

from kairon.shared.data.data_objects import BotSettings, Slots, Rules, Responses, MultiflowStories


class TestAgenticFlow:


    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
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
        
        
        yield

        BotSettings.objects(user="af_channel_test_user_acc").delete()
        Bot.objects(user="af_channel_test_user_acc").delete()
        Account.objects(user="af_channel_test_user_acc").delete()
        Rules.objects(user="af_channel_test_user_acc").delete()
        Responses.objects(user="af_channel_test_user_acc").delete()
        Slots.objects(user="af_channel_test_user_acc").delete()
        MultiflowStories.objects(user="af_channel_test_user_acc").delete()


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
    async def test_execute__rule_with_multiflow(self, patch_log_chat_history):
        flow = AgenticFlow(pytest.af_test_bot)
        with patch('kairon.chat.actions.KRemoteAction.run') as mock_action:
            mock_action.return_value = [BotUttered("Action Executed")]
            res, err = await flow.execute_rule("py_multiflow")
            assert len(res) == 2
            assert res[0] == {'text': 'Action Executed'}
            assert not err
            assert flow.executed_actions == ['py_multi', 'py_ans_a']
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
            assert len(res) == 2
            mock_action.assert_called()
            print(flow.executed_actions)
            assert flow.executed_actions == ['py_multi', 'py_ans_a']

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
        expected = {'5691320b-6007-4609-8386-bee3afdd9490': {
            'node_id': '5691320b-6007-4609-8386-bee3afdd9490', 'type': 'INTENT', 'name': 'i_multiflow', 'connections': {
                'type': 'jump', 'node_id': '715f57e6-90df-42b1-b0de-daa14b22d72f'}},
            '715f57e6-90df-42b1-b0de-daa14b22d72f': { 'node_id': '715f57e6-90df-42b1-b0de-daa14b22d72f', 'type': 'action', 'name': 'py_multi', 'connections': {'type': 'branch', 'criteria': 'SLOT', 'name': 'trigger_conditional', '1': 'fe210aa4-4885-4454-9acf-607621228ffd', '2': '589cebb9-7a93-4e76-98f8-342b123f32b8'}}
            , 'fe210aa4-4885-4454-9acf-607621228ffd': {'node_id': 'fe210aa4-4885-4454-9acf-607621228ffd', 'type': 'SLOT', 'name': 'trigger_conditional', 'connections': {'type': 'jump', 'node_id': '61d7459c-5a34-464a-b9e5-25e7808f1f24'}},
            '61d7459c-5a34-464a-b9e5-25e7808f1f24': {'node_id': '61d7459c-5a34-464a-b9e5-25e7808f1f24', 'type': 'action', 'name': 'py_ans_a', 'connections': None},
            '589cebb9-7a93-4e76-98f8-342b123f32b8': {'node_id': '589cebb9-7a93-4e76-98f8-342b123f32b8', 'type': 'SLOT', 'name': 'trigger_conditional', 'connections': {'type': 'jump', 'node_id': '4f331af0-870e-40f3-883e-51c2a86f98eb'}},
            '4f331af0-870e-40f3-883e-51c2a86f98eb': {'node_id': '4f331af0-870e-40f3-883e-51c2a86f98eb', 'type': 'action', 'name': 'fetch_poke_details', 'connections': {'type': 'jump', 'node_id': '1019cbaa-68fe-40c6-bcb9-c3e08e58e7ef'}},
            '1019cbaa-68fe-40c6-bcb9-c3e08e58e7ef': {'node_id': '1019cbaa-68fe-40c6-bcb9-c3e08e58e7ef', 'type': 'action', 'name': 'py_ans_b', 'connections': None}}

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

        collection = pymongo_mock_client.get_database().get_collection(pytest.af_test_bot)
        data =  collection.find({"tag": "agentic_flow"})
        data_entries = list(data)
        assert len(data_entries) == 1
        assert data_entries[0]['data']
        assert data_entries[0]['data']['action'] == ['simple_action']
        assert data_entries[0]['data']['bot_response'] == [{'text': 'Action Executed'}]
        assert data_entries[0]['data']['user_input'] == 'action_rule'


