import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from mongoengine import connect
from mongoengine.errors import ValidationError

from kairon.shared.utils import Utility

Utility.load_system_metadata()

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.actions.definitions.store_page import ActionStorePage
from kairon.shared.actions.data_objects import StorePageAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.data.constant import STATUSES
from kairon.shared.models import StoryStepType


class TestActionStorePage:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']['url']))

    @pytest.fixture
    def tracker(self):
        tracker = MagicMock()
        tracker.sender_id = "test_sender"
        tracker.get_slot.return_value = "test_bot"
        tracker.get_intent_of_latest_message.return_value = "test_intent"
        tracker.latest_message = {"text": "show catalog"}
        return tracker

    @pytest.fixture
    def dispatcher(self):
        from rasa_sdk.executor import CollectingDispatcher
        return CollectingDispatcher()

    def _make_config(self, **kwargs):
        defaults = dict(
            name="test_store_page_action",
            page_name="product_page",
            identifier_slot="product_id",
            bot="test_catalog_bot",
            user="test_user",
        )
        defaults.update(kwargs)
        return StorePageAction(**defaults).save()

    # ─── retrieve_config ──────────────────────────────────────────────────────

    def test_retrieve_config_success(self):
        self._make_config(name="retrieve_ok", bot="bot_cat_retrieve")
        config = ActionStorePage("bot_cat_retrieve", "retrieve_ok").retrieve_config()
        assert config["name"] == "retrieve_ok"
        assert config["page_name"] == "product_page"
        assert config["identifier_slot"] == "product_id"

    def test_retrieve_config_not_found(self):
        with pytest.raises(ActionFailure, match="No StorePageAction found"):
            ActionStorePage("nonexistent_bot_xyz", "nonexistent_action_xyz").retrieve_config()

    # ─── execute: success ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_execute_success(self, tracker, dispatcher):
        self._make_config(name="exec_ok", bot="bot_cat_exec")
        tracker.get_slot.side_effect = lambda k: {"bot": "bot_cat_exec", "product_id": "P-001"}.get(k)

        with patch("kairon.shared.utils.Utility.encrypt_message",
                   return_value="enc_P-001") as mock_enc, \
             patch("kairon.shared.auth.Authentication.create_store_page_token",
                   return_value="tok_abc") as mock_tok, \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save") as mock_log:
            result = await ActionStorePage("bot_cat_exec", "exec_ok").execute(
                dispatcher, tracker, {}, action_call={}
            )

        mock_enc.assert_called_once_with("P-001")
        mock_tok.assert_called_once()
        assert result["user_identifier"] == "enc_P-001"
        assert result["temp_token"] == "tok_abc"
        assert result["store_page_name"] == "product_page"
        assert result["callback_identifier"] is None
        mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_slots_set_correctly(self, tracker, dispatcher):
        self._make_config(name="exec_slots", bot="bot_cat_slots")
        tracker.get_slot.side_effect = lambda k: {"bot": "bot_cat_slots", "product_id": "ITEM-42"}.get(k)

        with patch("kairon.shared.utils.Utility.encrypt_message",
                   return_value="enc_ITEM-42"), \
             patch("kairon.shared.auth.Authentication.create_store_page_token",
                   return_value="jwt_token"), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save"):
            result = await ActionStorePage("bot_cat_slots", "exec_slots").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["user_identifier"] == "enc_ITEM-42"
        assert result["temp_token"] == "jwt_token"
        assert result["store_page_name"] == "product_page"
        assert result["callback_identifier"] is None

    @pytest.mark.asyncio
    async def test_execute_with_callback_identifier_configured(self, tracker, dispatcher):
        self._make_config(name="exec_cb_id", bot="bot_cat_cb", callback_identifier="cb_slot")
        tracker.get_slot.side_effect = lambda k: {
            "bot": "bot_cat_cb", "product_id": "P-007", "cb_slot": "cb-value-123"
        }.get(k)

        with patch("kairon.shared.utils.Utility.encrypt_message", return_value="enc_P-007"), \
             patch("kairon.shared.auth.Authentication.create_store_page_token", return_value="tok_cb"), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save"):
            result = await ActionStorePage("bot_cat_cb", "exec_cb_id").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["callback_identifier"] == "cb-value-123"
        assert result["user_identifier"] == "enc_P-007"
        assert result["temp_token"] == "tok_cb"
        assert result["store_page_name"] == "product_page"

    @pytest.mark.asyncio
    async def test_execute_without_callback_identifier_sets_none(self, tracker, dispatcher):
        self._make_config(name="exec_no_cb", bot="bot_cat_no_cb")
        tracker.get_slot.side_effect = lambda k: {"bot": "bot_cat_no_cb", "product_id": "P-008"}.get(k)

        with patch("kairon.shared.utils.Utility.encrypt_message", return_value="enc_P-008"), \
             patch("kairon.shared.auth.Authentication.create_store_page_token", return_value="tok_no_cb"), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save"):
            result = await ActionStorePage("bot_cat_no_cb", "exec_no_cb").execute(
                dispatcher, tracker, {}, action_call={}
            )

        assert result["callback_identifier"] is None

    # ─── execute: slot empty / absent ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_execute_slot_empty_raises(self, tracker, dispatcher):
        self._make_config(name="exec_empty_slot", bot="bot_cat_empty")
        tracker.get_slot.side_effect = lambda k: "bot_cat_empty" if k == "bot" else None

        with patch("kairon.actions.definitions.store_page.ActionServerLogs") as mock_log_cls:
            with pytest.raises(ActionFailure, match="absent or empty"):
                await ActionStorePage("bot_cat_empty", "exec_empty_slot").execute(
                    dispatcher, tracker, {}, action_call={}
                )
        mock_log_cls.assert_called_once()
        log_kwargs = mock_log_cls.call_args.kwargs
        assert log_kwargs.get("exception") is not None
        assert "absent or empty" in log_kwargs["exception"]

    @pytest.mark.asyncio
    async def test_execute_slot_whitespace_raises(self, tracker, dispatcher):
        self._make_config(name="exec_ws_slot", bot="bot_cat_ws")
        tracker.get_slot.side_effect = lambda k: "bot_cat_ws" if k == "bot" else "   "

        with patch("kairon.actions.definitions.store_page.ActionServerLogs") as mock_log_cls:
            with pytest.raises(ActionFailure, match="absent or empty"):
                await ActionStorePage("bot_cat_ws", "exec_ws_slot").execute(
                    dispatcher, tracker, {}, action_call={}
                )
        mock_log_cls.assert_called_once()
        log_kwargs = mock_log_cls.call_args.kwargs
        assert log_kwargs.get("exception") is not None
        assert "absent or empty" in log_kwargs["exception"]

    # ─── execute: external error ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_execute_encrypt_error_logs_failure(self, tracker, dispatcher):
        self._make_config(name="exec_enc_err", bot="bot_cat_enc_err")
        tracker.get_slot.side_effect = lambda k: "bot_cat_enc_err" if k == "bot" else "P-999"

        with patch("kairon.shared.utils.Utility.encrypt_message",
                   side_effect=Exception("encryption failed")), \
             patch("kairon.shared.actions.data_objects.ActionServerLogs.save") as mock_log:
            result = await ActionStorePage("bot_cat_enc_err", "exec_enc_err").execute(
                dispatcher, tracker, {}, action_call={}
            )
        assert result == {}
        mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_config_not_found_raises(self, tracker, dispatcher):
        tracker.get_slot.return_value = "bot_missing"

        with patch("kairon.shared.actions.data_objects.ActionServerLogs.save"):
            with pytest.raises(ActionFailure):
                await ActionStorePage("bot_missing", "no_such_action_xyz").execute(
                    dispatcher, tracker, {}, action_call={}
                )

    # ─── enums / registration ─────────────────────────────────────────────────

    def test_action_type_enum_has_store_page_action(self):
        assert ActionType.store_page_action.value == "store_page_action"

    def test_story_step_type_enum_has_store_page_action(self):
        assert StoryStepType.store_page_action.value == "STORE_PAGE_ACTION"

    def test_action_factory_has_store_page_action(self):
        from kairon.actions.definitions.factory import ActionFactory
        assert ActionType.store_page_action.value in ActionFactory._ActionFactory__implementations

    # ─── model validation ─────────────────────────────────────────────────────

    def test_store_page_action_validate_empty_name(self):
        with pytest.raises(Exception):
            StorePageAction(name="", page_name="pg", identifier_slot="sl",
                          bot="b", user="u").validate()

    def test_store_page_action_validate_empty_page_name(self):
        with pytest.raises(Exception):
            StorePageAction(name="a", page_name="", identifier_slot="sl",
                          bot="b", user="u").validate()

    def test_store_page_action_validate_empty_identifier_slot(self):
        with pytest.raises(Exception):
            StorePageAction(name="a", page_name="pg", identifier_slot="",
                          bot="b", user="u").validate()
