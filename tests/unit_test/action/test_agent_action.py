import json
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


def env(text):
    return {"type": "markdown", "data": [{"type": "markdown", "children": [{"text": text}]}]}


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
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
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
        assert call_kwargs["request_body"]["max_iterations"] == 5
        assert call_kwargs["request_body"]["metadata"] == {}
        mock_log.assert_called_once()
        assert result["kairon_action_response"] == "Here is your answer"
        assert [m.get("custom") for m in dispatcher.messages] == [env("Here is your answer")]
        assert all(not m.get("text") for m in dispatcher.messages)

    @pytest.mark.asyncio
    async def test_execute_response_non_dict(self, tracker, dispatcher):
        self._make_config(name="exec_str_resp", bot="bot_str_resp")

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=("plain string response", 200, None, None)), \
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
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
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
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
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
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
    async def test_execute_non_200_logs_failure(self, tracker, dispatcher):
        self._make_config(name="exec_non200", bot="bot_non200_agent")

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=({"error": "internal server error"}, 500, None, None)), \
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
                   return_value="mock_token"), \
             patch("kairon.actions.definitions.agent_action.ActionUtility.trigger_action_failure_mail"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs") as mock_log_cls:
            mock_log_cls.return_value.save = MagicMock()
            result = await ActionAgent("bot_non200_agent", "exec_non200").execute(
                dispatcher, tracker, {}, action_call={}
            )

        call_kwargs = mock_log_cls.call_args[1]
        assert call_kwargs["status"] == STATUSES.FAIL.value
        assert "non-200 status code:500" in call_kwargs["exception"]
        assert result["kairon_action_response"] == "I have failed to process your request."

    @pytest.mark.asyncio
    async def test_execute_dispatch_bot_response_false(self, tracker, dispatcher):
        self._make_config(name="exec_no_dispatch_agent", bot="bot_no_dispatch_agent",
                          dispatch_bot_response=False)

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=({"output": "answer"}, 200, None, None)), \
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
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
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
                   return_value="test_bearer_token") as mock_token, \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs.save"):
            await ActionAgent("bot_auth_check", "exec_auth_check").execute(
                dispatcher, tracker, {}, action_call={}
            )

        mock_token.assert_called_once_with("bot_auth_check", "auth_sender")
        assert captured_headers.get("Authorization") == "Bearer test_bearer_token"

    # ─── properties ───────────────────────────────────────────────────────────

    @pytest.mark.parametrize("text,expected", [
        ("a\n\nb", "a\nb"),
        ("a\n\n\n\nb", "a\nb"),
        ("a\r\n\r\nb", "a\nb"),
        ("a\nb", "a\nb"),
        ("a\n\n\n\n\n\n\n\n\n\nb\n\nc", "a\nb\nc"),
        ("no breaks", "no breaks"),
        ("", ""),
    ])
    def test_single_dispatch_text(self, text, expected):
        assert ActionAgent._single_dispatch_text(text) == expected
        assert "\n\n" not in ActionAgent._single_dispatch_text(text)

    @pytest.mark.asyncio
    async def test_execute_dispatches_one_envelope_with_normalized_text_in_slot(self, tracker, dispatcher):
        self._make_config(name="exec_single", bot="bot_exec_single")
        tracker.sender_id = "sender_single"
        original = "first\n\nsecond\n\nthird"

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=({"output": original}, 200, None, None)), \
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
                   return_value="mock_token"), \
             patch("kairon.actions.definitions.agent_action.ActionUtility.trigger_action_failure_mail"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs.save"):
            result = await ActionAgent("bot_exec_single", "exec_single").execute(
                dispatcher, tracker, {}, action_call={})

        assert [m["custom"] for m in dispatcher.messages] == [env("first\nsecond\nthird")]
        assert result["kairon_action_response"] == "first\nsecond\nthird"

    @pytest.mark.asyncio
    async def test_is_success_true_on_success(self, tracker, dispatcher):
        self._make_config(name="exec_prop_ok", bot="bot_prop_ok")

        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=({"output": "yes"}, 200, None, None)), \
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
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


    # ─── markdown response ───────────────────────────────────────────────────────

    async def _run(self, tracker, dispatcher, name, bot, response, **cfg):
        AgentActionConfig.objects(bot=bot, name=name).delete()
        self._make_config(name=name, bot=bot, **cfg)
        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=response), \
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
                   return_value="tok"), \
             patch("kairon.actions.definitions.agent_action.ActionUtility.trigger_action_failure_mail") as mail, \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs") as log_cls:
            log_cls.return_value.save = MagicMock()
            result = await ActionAgent(bot, name).execute(dispatcher, tracker, {}, action_call={})
        return result, log_cls.call_args[1], mail

    @pytest.mark.asyncio
    async def test_envelope_exact_shape_single_message(self, tracker, dispatcher):
        result, log, mail = await self._run(
            tracker, dispatcher, "env_shape", "bot_env_shape", ({"output": "Hello"}, 200, None, None))
        assert len(dispatcher.messages) == 1
        message = dispatcher.messages[0]
        assert message["custom"] == env("Hello")
        assert not message.get("text")
        assert len(message["custom"]["data"]) == 1
        assert len(message["custom"]["data"][0]["children"]) == 1
        mail.assert_not_called()

    @pytest.mark.asyncio
    async def test_envelope_keeps_markdown_syntax(self, tracker, dispatcher):
        await self._run(tracker, dispatcher, "env_md", "bot_env_md",
                        ({"output": "**bold**\n- item"}, 200, None, None))
        assert dispatcher.messages[0]["custom"] == env("**bold**\n- item")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw,expected", [
        ("a\r\nb", "a\nb"),
        ("a\n\n\n\nb", "a\nb"),
        ("a\r\n\r\n\r\nb", "a\nb"),
        ("no breaks", "no breaks"),
    ])
    async def test_envelope_text_normalized(self, tracker, dispatcher, raw, expected):
        result, log, _ = await self._run(
            tracker, dispatcher, "env_norm", "bot_env_norm", ({"output": raw}, 200, None, None))
        text = dispatcher.messages[0]["custom"]["data"][0]["children"][0]["text"]
        assert text == expected
        assert "\n\n" not in text and "\r" not in text

    @pytest.mark.asyncio
    async def test_whitespace_only_output_is_sent(self, tracker, dispatcher):
        result, _, _ = await self._run(
            tracker, dispatcher, "env_ws", "bot_env_ws", ({"output": "   "}, 200, None, None))
        assert [m["custom"] for m in dispatcher.messages] == [env("   ")]
        assert result["kairon_action_response"] == "   "

    @pytest.mark.asyncio
    @pytest.mark.parametrize("response", [
        ({"output": ""}, 200, None, None),
        ({"other": "x"}, 200, None, None),
        ({"output": None}, 200, None, None),
    ])
    async def test_empty_output_sends_nothing(self, tracker, dispatcher, response):
        result, log, mail = await self._run(tracker, dispatcher, "env_empty", "bot_env_empty", response)
        assert dispatcher.messages == []
        assert result["kairon_action_response"] == ""
        assert not log["bot_response"]
        assert log["status"] == STATUSES.SUCCESS.value
        mail.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_string_output_is_stringified(self, tracker, dispatcher):
        result, _, _ = await self._run(
            tracker, dispatcher, "env_num", "bot_env_num", ({"output": 42}, 200, None, None))
        assert [m["custom"] for m in dispatcher.messages] == [env("42")]
        assert result["kairon_action_response"] == "42"

    @pytest.mark.asyncio
    async def test_dispatch_default_on_when_setting_absent(self, tracker, dispatcher):
        AgentActionConfig.objects(bot="bot_env_default", name="env_default").delete()
        self._make_config(name="env_default", bot="bot_env_default")
        raw = AgentActionConfig.objects(bot="bot_env_default", name="env_default").get().to_mongo().to_dict()
        raw.pop("dispatch_bot_response", None)
        with patch.object(ActionAgent, "retrieve_config", return_value=raw), \
             patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   return_value=({"output": "hi"}, 200, None, None)), \
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
                   return_value="tok"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs.save"):
            await ActionAgent("bot_env_default", "env_default").execute(dispatcher, tracker, {}, action_call={})
        assert [m["custom"] for m in dispatcher.messages] == [env("hi")]

    @pytest.mark.asyncio
    async def test_dispatch_off_failure_sends_nothing(self, tracker, dispatcher):
        AgentActionConfig.objects(bot="bot_env_off_fail", name="env_off_fail").delete()
        self._make_config(name="env_off_fail", bot="bot_env_off_fail", dispatch_bot_response=False)
        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   side_effect=Exception("boom")), \
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
                   return_value="tok"), \
             patch("kairon.actions.definitions.agent_action.ActionUtility.trigger_action_failure_mail"), \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs.save"):
            await ActionAgent("bot_env_off_fail", "env_off_fail").execute(dispatcher, tracker, {}, action_call={})
        assert dispatcher.messages == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["exception", "status"])
    async def test_failure_is_plain_text_and_mails_once(self, tracker, dispatcher, kind):
        AgentActionConfig.objects(bot=f"bot_env_fail_{kind}", name=f"env_fail_{kind}").delete()
        self._make_config(name=f"env_fail_{kind}", bot=f"bot_env_fail_{kind}")
        patch_kwargs = ({"side_effect": Exception("boom")} if kind == "exception"
                        else {"return_value": ({"error": "x"}, 500, None, None)})
        with patch("kairon.actions.definitions.agent_action.ActionUtility.execute_request_async",
                   **patch_kwargs), \
             patch("kairon.actions.definitions.agent_action.IntegrationProcessor.create_agent_action_token",
                   return_value="tok"), \
             patch("kairon.actions.definitions.agent_action.ActionUtility.trigger_action_failure_mail") as mail, \
             patch("kairon.actions.definitions.agent_action.ActionServerLogs") as log_cls:
            log_cls.return_value.save = MagicMock()
            result = await ActionAgent(f"bot_env_fail_{kind}", f"env_fail_{kind}").execute(
                dispatcher, tracker, {}, action_call={})
        assert len(dispatcher.messages) == 1
        assert dispatcher.messages[0]["text"] == "I have failed to process your request."
        assert not dispatcher.messages[0].get("custom")
        mail.assert_called_once()
        assert result["kairon_action_response"] == "I have failed to process your request."
        log = log_cls.call_args[1]
        assert log["bot_response"] == "I have failed to process your request."
        assert log["status"] == STATUSES.FAIL.value

    @pytest.mark.asyncio
    async def test_log_records_envelope_and_raw_api_response(self, tracker, dispatcher):
        result, log, _ = await self._run(
            tracker, dispatcher, "env_log", "bot_env_log", ({"output": "Hello"}, 200, None, None))
        assert log["bot_response"] == "Hello"
        assert log["api_response"] == str({"output": "Hello"})
        assert log["status"] == STATUSES.SUCCESS.value
        assert result["kairon_action_response"] == "Hello"

    @pytest.mark.asyncio
    async def test_two_configs_both_send_envelope(self, tracker, dispatcher):
        await self._run(tracker, dispatcher, "env_cfg_a", "bot_env_cfg_a", ({"output": "A"}, 200, None, None))
        await self._run(tracker, dispatcher, "env_cfg_b", "bot_env_cfg_b", ({"output": "B"}, 200, None, None),
                        agent_name="Other Agent", agent_id="other-id")
        assert [m["custom"] for m in dispatcher.messages] == [env("A"), env("B")]

    # ─── markdown message ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_markdown_sends_one_markdown_message(self, tracker, dispatcher):
        result, log, mail = await self._run(
            tracker, dispatcher, "wa_md", "bot_wa_md", ({"output": "Hello"}, 200, None, None))
        assert len(dispatcher.messages) == 1
        message = dispatcher.messages[0]
        assert message["custom"] == env("Hello")
        assert not message.get("text")
        assert len(message["custom"]["data"]) == 1
        assert len(message["custom"]["data"][0]["children"]) == 1
        assert result["kairon_action_response"] == "Hello"
        assert log["bot_response"] == "Hello"
        mail.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw,expected", [("a\r\n\r\nb", "a\nb"), ("**b**\n- i", "**b**\n- i"),
                                              ("   ", "   ")])
    async def test_markdown_markdown_data_normalized(self, tracker, dispatcher, raw, expected):
        await self._run(tracker, dispatcher, "wa_norm", "bot_wa_norm", ({"output": raw}, 200, None, None))
        assert [m["custom"] for m in dispatcher.messages] == [env(expected)]

    @pytest.mark.asyncio
    async def test_markdown_non_string_output(self, tracker, dispatcher):
        await self._run(tracker, dispatcher, "wa_int", "bot_wa_int", ({"output": 42}, 200, None, None))
        assert [m["custom"] for m in dispatcher.messages] == [env("42")]

    @pytest.mark.asyncio
    async def test_markdown_dispatch_off_sends_nothing_slot_keeps_message(self, tracker, dispatcher):
        result, _, _ = await self._run(tracker, dispatcher, "wa_off", "bot_wa_off",
                                       ({"output": "Hello"}, 200, None, None), dispatch_bot_response=False)
        assert dispatcher.messages == []
        assert result["kairon_action_response"] == "Hello"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("response", [({"output": ""}, 200, None, None), ({}, 200, None, None),
                                          ({"output": None}, 200, None, None)])
    async def test_markdown_empty_output_sends_nothing(self, tracker, dispatcher, response):
        result, log, _ = await self._run(tracker, dispatcher, "wa_empty", "bot_wa_empty", response)
        assert dispatcher.messages == []
        assert result["kairon_action_response"] == ""
        assert not log["bot_response"]

    @pytest.mark.asyncio
    async def test_markdown_failure_is_plain_text_and_mails_once(self, tracker, dispatcher):
        result, log, mail = await self._run(
            tracker, dispatcher, "wa_fail", "bot_wa_fail", ({"error": "x"}, 500, None, None))
        assert [m.get("text") for m in dispatcher.messages] == ["I have failed to process your request."]
        assert not dispatcher.messages[0].get("custom")
        assert result["kairon_action_response"] == "I have failed to process your request."
        assert log["bot_response"] == "I have failed to process your request."
        mail.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("channel", ["whatsapp", "telegram", None])
    async def test_same_markdown_message_on_every_channel(self, tracker, dispatcher, channel):
        tracker.get_latest_input_channel.return_value = channel
        await self._run(tracker, dispatcher, "any_ch", "bot_any_ch", ({"output": "Hi"}, 200, None, None))
        assert [m["custom"] for m in dispatcher.messages] == [env("Hi")]

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


class TestAgentChatHistory:

    @staticmethod
    def _tracker(events):
        tracker = MagicMock()
        tracker.events = events
        return tracker

    def test_chat_history_fewer_than_limit_returns_all_without_current_message(self):
        events = [
            {"event": "user", "text": "u1"},
            {"event": "bot", "text": "b1"},
            {"event": "user", "text": "current"},
        ]
        assert ActionAgent._get_chat_history(self._tracker(events)) == [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "b1"},
        ]

    def test_chat_history_more_than_limit_returns_last_five(self):
        events = []
        for i in range(6):
            events += [{"event": "user", "text": f"u{i}"}, {"event": "bot", "text": f"b{i}"}]
        events.append({"event": "user", "text": "current"})
        history = ActionAgent._get_chat_history(self._tracker(events))
        assert len(history) == 5
        assert history[-1] == {"role": "assistant", "content": "b5"}
        assert history[0] == {"role": "assistant", "content": "b3"}

    def test_chat_history_ignores_earlier_sessions(self):
        events = [
            {"event": "user", "text": "old"},
            {"event": "session_started"},
            {"event": "user", "text": "current"},
        ]
        assert ActionAgent._get_chat_history(self._tracker(events)) == []

    def test_build_message_without_history_returns_user_message(self):
        assert ActionAgent._build_message("hi", []) == "hi"

    def test_build_message_prefixes_history(self):
        history = [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "b1"}]
        assert ActionAgent._build_message("hi", history) == (
            "Conversation history:\nuser: u1\nassistant: b1\n\nCurrent message: hi"
        )
