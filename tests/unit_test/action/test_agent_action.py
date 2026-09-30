import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from mongoengine import connect

from kairon.shared.utils import Utility

Utility.load_system_metadata()

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.actions.definitions.agent_action import ActionAgent
from kairon.shared.actions.data_objects import AgentActionConfig
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.data.constant import STATUSES


class TestActionAgent:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']['url']))

    @pytest.fixture
    def tracker(self):
        tracker = MagicMock()
        tracker.sender_id = "test_sender"
        tracker.get_slot.return_value = None
        tracker.get_intent_of_latest_message.return_value = "test_intent"
        tracker.latest_message = {"text": "hello agent"}
        tracker.current_slot_values.return_value = {}
        return tracker

    @pytest.fixture
    def dispatcher(self):
        from rasa_sdk.executor import CollectingDispatcher
        return CollectingDispatcher()

    def _make_config(self, **kwargs):
        defaults = dict(
            name="test_agent_action",
            agent_name="Test Agent",
            agent_id="agent-uuid-123",
            dispatch_bot_response=True,
            bot="test_bot",
            user="test_user",
        )
        defaults.update(kwargs)
        return AgentActionConfig(**defaults).save()

    # ─── retrieve_config ──────────────────────────────────────────────────────

    def test_retrieve_config_success(self):
        self._make_config(name="retrieve_ok", bot="bot_retrieve_agent")
        config = ActionAgent("bot_retrieve_agent", "retrieve_ok").retrieve_config()
        assert config["name"] == "retrieve_ok"
        assert config["agent_id"] == "agent-uuid-123"
        assert config["agent_name"] == "Test Agent"

    def test_retrieve_config_not_found(self):
        with pytest.raises(ActionFailure, match="No AgentAction found"):
            ActionAgent("nonexistent_bot", "nonexistent_action").retrieve_config()

    # ─── _get_user_message ────────────────────────────────────────────────────

    def test_get_user_message_plain_text(self):
        tracker = MagicMock()
        tracker.latest_message = {"text": "hello"}
        assert ActionAgent._get_user_message(tracker) == "hello"

    def test_get_user_message_intent_format_with_entity(self):
        tracker = MagicMock()
        tracker.latest_message = {"text": "/greet"}
        tracker.get_latest_entity_values.return_value = iter(["hi there"])
        assert ActionAgent._get_user_message(tracker) == "hi there"

    def test_get_user_message_intent_format_no_entity_falls_back(self):
        tracker = MagicMock()
        tracker.latest_message = {"text": "/greet"}
        tracker.get_latest_entity_values.return_value = iter([])
        assert ActionAgent._get_user_message(tracker) == "/greet"

    def test_get_user_message_empty_returns_empty(self):
        tracker = MagicMock()
        tracker.latest_message = {"text": ""}
        assert ActionAgent._get_user_message(tracker) == ""

    # ─── execute ──────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_execute_success(self, tracker, dispatcher):
        self._make_config(name="exec_ok", bot="bot_exec_agent")
        tracker.sender_id = "sender_exec"

        mock_response = {"output": "Here is your answer"}

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=(mock_response, 200, None, None)) as mock_http, \
             patch("kairon.actions.definitions.agent_action.Authentication.create_access_token",
                   return_value="mock_token"), \
             patch("kairon.actions.definitions.agent_action.ActionUtility.trigger_action_failure_mail"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs.save") as mock_log:
            result = await ActionAgent("bot_exec_agent", "exec_ok").execute(
                dispatcher, tracker, {}, action_call={}
            )

        mock_http.assert_called_once()
        call_kwargs = mock_http.call_args[1]
        assert call_kwargs["request_method"] == "POST"
        assert "agents/bot_exec_agent/agent-uuid-123/run/sender_exec/simple" in call_kwargs["http_url"]
        assert call_kwargs["request_body"]["message"] == "hello agent"
        assert call_kwargs["request_body"]["max_iterations"] == 1
        mock_log.assert_called_once()
        assert result["kairon_action_response"] == "Here is your answer"
        assert any("Here is your answer" in m.get("text", "") for m in dispatcher.messages)

    @pytest.mark.asyncio
    async def test_execute_response_non_dict(self, tracker, dispatcher):
        self._make_config(name="exec_str_resp", bot="bot_str_resp")

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=("plain string response", 200, None, None)), \
             patch("kairon.actions.definitions.agent_action.Authentication.create_access_token",
                   return_value="mock_token"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs.save"):
            result = await ActionAgent("bot_str_resp", "exec_str_resp").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["kairon_action_response"] == "plain string response"

    @pytest.mark.asyncio
    async def test_execute_response_dict_no_output_key(self, tracker, dispatcher):
        self._make_config(name="exec_no_output", bot="bot_no_output")

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=({"result": "something"}, 200, None, None)), \
             patch("kairon.actions.definitions.agent_action.Authentication.create_access_token",
                   return_value="mock_token"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs.save"):
            result = await ActionAgent("bot_no_output", "exec_no_output").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["kairon_action_response"] == ""

    @pytest.mark.asyncio
    async def test_execute_http_error_logs_failure(self, tracker, dispatcher):
        self._make_config(name="exec_http_err", bot="bot_http_err_agent")

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   side_effect=Exception("connection refused")), \
             patch("kairon.actions.definitions.agent_action.Authentication.create_access_token",
                   return_value="mock_token"), \
             patch("kairon.actions.definitions.agent_action.ActionUtility.trigger_action_failure_mail"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs") as mock_log_cls:
            mock_log_cls.return_value.save = MagicMock()
            result = await ActionAgent("bot_http_err_agent", "exec_http_err").execute(
                dispatcher, tracker, {}, action_call={}
            )

        call_kwargs = mock_log_cls.call_args[1]
        assert call_kwargs["status"] == STATUSES.FAIL.value
        assert "connection refused" in call_kwargs["exception"]
        assert result["kairon_action_response"] == "I have failed to process your request."

    @pytest.mark.asyncio
    async def test_execute_dispatch_bot_response_false(self, tracker, dispatcher):
        self._make_config(name="exec_no_dispatch_agent", bot="bot_no_dispatch_agent",
                          dispatch_bot_response=False)

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=({"output": "answer"}, 200, None, None)), \
             patch("kairon.actions.definitions.agent_action.Authentication.create_access_token",
                   return_value="mock_token"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs.save"):
            result = await ActionAgent("bot_no_dispatch_agent", "exec_no_dispatch_agent").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["kairon_action_response"] == "answer"
        assert len(dispatcher.messages) == 0

    @pytest.mark.asyncio
    async def test_execute_config_not_found_raises(self, tracker, dispatcher):
        with pytest.raises(ActionFailure, match="No AgentAction found"):
            await ActionAgent("bot_missing_config", "nonexistent_action_cfg").execute(
                dispatcher, tracker, {}, action_call={}
            )

    @pytest.mark.asyncio
    async def test_execute_bearer_token_in_headers(self, tracker, dispatcher):
        self._make_config(name="exec_auth_check", bot="bot_auth_check")
        tracker.sender_id = "auth_sender"

        captured_headers = {}

        async def capture_request(**kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return ({"output": "ok"}, 200, None, None)

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   side_effect=capture_request), \
             patch("kairon.actions.definitions.agent_action.Authentication.create_access_token",
                   return_value="test_bearer_token"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs.save"):
            await ActionAgent("bot_auth_check", "exec_auth_check").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert captured_headers.get("Authorization") == "Bearer test_bearer_token"

    # ─── properties ───────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_is_success_true_on_success(self, tracker, dispatcher):
        self._make_config(name="exec_prop_ok", bot="bot_prop_ok")

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=({"output": "yes"}, 200, None, None)), \
             patch("kairon.actions.definitions.agent_action.Authentication.create_access_token",
                   return_value="tok"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs.save"):
            action = ActionAgent("bot_prop_ok", "exec_prop_ok")
            await action.execute(dispatcher, tracker, {}, action_call={})

        assert action.is_success is True
        assert action.response == "yes"

    @pytest.mark.asyncio
    async def test_is_success_false_on_failure(self, tracker, dispatcher):
        action = ActionAgent("bot_prop_fail", "nonexistent_for_props")
        with pytest.raises(ActionFailure):
            await action.execute(dispatcher, tracker, {}, action_call={})

        assert action.is_success is False
        assert action.response is None

    # ─── enum/model validation ────────────────────────────────────────────────

    def test_action_type_enum_has_agent_action(self):
        assert hasattr(ActionType, "agent_action")
        assert ActionType.agent_action.value == "agent_action"

    def test_agent_action_config_validate_empty_name(self):
        from mongoengine.errors import ValidationError
        with pytest.raises(ValidationError):
            AgentActionConfig(
                name="", agent_name="Agent", agent_id="some-id",
                bot="bot", user="user"
            ).validate()

    def test_agent_action_config_validate_empty_agent_id(self):
        from mongoengine.errors import ValidationError
        with pytest.raises(ValidationError):
            AgentActionConfig(
                name="valid_name", agent_name="Agent", agent_id="",
                bot="bot", user="user"
            ).validate()
