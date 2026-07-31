import os

import pytest
from mongoengine import connect
from mongoengine.errors import ValidationError

from kairon.shared.utils import Utility

os.environ["system_file"] = "./tests/testing_data/system.yaml"

Utility.load_environment()

from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import StorePageAction, Actions
from kairon.shared.actions.models import ActionType
from kairon.shared.data.action_serializer import ActionSerializer
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import StoryStepType


@pytest.fixture(autouse=True, scope='module')
def init_connection():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment['database']['url']))


class TestMongoProcessorStorePageActionCRUD:

    @pytest.fixture(autouse=True)
    def processor(self):
        return MongoProcessor()

    # ─── add ──────────────────────────────────────────────────────────────────

    def test_add_store_page_action_success(self, processor):
        bot = "test_cat_crud_bot"
        action = {"name": "cat_add_ok", "page_name": "page1", "identifier_slot": "slot1"}
        processor.add_store_page_action(action, bot, "user1")
        assert StorePageAction.objects(bot=bot, name="cat_add_ok", status=True).count() == 1
        assert Actions.objects(bot=bot, name="cat_add_ok", status=True).count() == 1

    def test_add_store_page_action_duplicate_raises(self, processor):
        bot = "test_cat_crud_bot"
        action = {"name": "cat_add_dup", "page_name": "page1", "identifier_slot": "slot1"}
        processor.add_store_page_action(action, bot, "user1")
        with pytest.raises(AppException):
            processor.add_store_page_action(action, bot, "user1")

    def test_add_store_page_action_invalid_name_raises(self, processor):
        action = {"name": "invalid-name!", "page_name": "p", "identifier_slot": "s"}
        with pytest.raises(AppException):
            processor.add_store_page_action(action, "bot_inv", "user1")

    # ─── edit ─────────────────────────────────────────────────────────────────

    def test_edit_store_page_action_success(self, processor):
        bot = "test_cat_edit_bot"
        processor.add_store_page_action(
            {"name": "cat_edit_ok", "page_name": "old_page", "identifier_slot": "old_slot"},
            bot, "user1"
        )
        processor.edit_store_page_action(
            {"name": "cat_edit_ok", "page_name": "new_page", "identifier_slot": "new_slot"},
            bot, "user1"
        )
        doc = StorePageAction.objects(bot=bot, name="cat_edit_ok", status=True).get()
        assert doc.page_name == "new_page"
        assert doc.identifier_slot == "new_slot"

    def test_edit_store_page_action_not_found_raises(self, processor):
        with pytest.raises(AppException, match="not found"):
            processor.edit_store_page_action(
                {"name": "no_such_cat_action", "page_name": "p", "identifier_slot": "s"},
                "bot_missing_edit", "user1"
            )

    # ─── list ─────────────────────────────────────────────────────────────────

    def test_list_store_page_action_empty(self, processor):
        result = list(processor.list_store_page_action("bot_empty_cat_list"))
        assert result == []

    def test_list_store_page_action_with_doc_id(self, processor):
        bot = "test_cat_list_id_bot"
        processor.add_store_page_action(
            {"name": "cat_list_id", "page_name": "pg", "identifier_slot": "sl"},
            bot, "user1"
        )
        result = list(processor.list_store_page_action(bot, with_doc_id=True))
        assert len(result) == 1
        assert "_id" in result[0]
        assert isinstance(result[0]["_id"], str)
        assert "bot" not in result[0]
        assert "user" not in result[0]
        assert "timestamp" not in result[0]
        assert "status" not in result[0]

    def test_list_store_page_action_without_doc_id(self, processor):
        bot = "test_cat_list_noid_bot"
        processor.add_store_page_action(
            {"name": "cat_list_noid", "page_name": "pg", "identifier_slot": "sl"},
            bot, "user1"
        )
        result = list(processor.list_store_page_action(bot, with_doc_id=False))
        assert len(result) == 1
        assert "_id" not in result[0]

    def test_list_store_page_action_filters_by_bot(self, processor):
        bot_a = "test_cat_filter_bot_a"
        bot_b = "test_cat_filter_bot_b"
        processor.add_store_page_action(
            {"name": "cat_filter_a", "page_name": "pg", "identifier_slot": "sl"}, bot_a, "u"
        )
        processor.add_store_page_action(
            {"name": "cat_filter_b", "page_name": "pg", "identifier_slot": "sl"}, bot_b, "u"
        )
        result_a = list(processor.list_store_page_action(bot_a, with_doc_id=False))
        assert len(result_a) == 1
        assert result_a[0]["name"] == "cat_filter_a"

    # ─── delete ───────────────────────────────────────────────────────────────

    def test_delete_store_page_action_success(self, processor):
        bot = "test_cat_del_bot"
        processor.add_store_page_action(
            {"name": "cat_del_ok", "page_name": "pg", "identifier_slot": "sl"}, bot, "u"
        )
        assert StorePageAction.objects(bot=bot, name="cat_del_ok").count() == 1
        processor.delete_store_page_action("cat_del_ok", bot, "u")
        assert StorePageAction.objects(bot=bot, name="cat_del_ok", status=True).count() == 0

    def test_delete_store_page_action_not_found_raises(self, processor):
        with pytest.raises(AppException, match="not found"):
            processor.delete_store_page_action("no_such_del_cat", "bot_del_missing", "u")


class TestStoryStepTypeStorePageActionIntegration:

    def test_story_step_type_enum_has_store_page_action(self):
        assert StoryStepType.store_page_action.value == "CATALOG_ACTION"

    def test_action_type_enum_has_store_page_action(self):
        assert ActionType.store_page_action.value == "store_page_action"

    def test_action_serializer_lookup_has_store_page_action(self):
        assert ActionType.store_page_action.value in ActionSerializer.action_lookup
        entry = ActionSerializer.action_lookup[ActionType.store_page_action.value]
        assert entry.get("db_model") is not None
        assert entry.get("validation_model") is not None

    def test_action_serializer_get_collection_infos_includes_store_page_action(self):
        action_info, _ = ActionSerializer.get_collection_infos()
        assert ActionType.store_page_action.value in action_info

    def test_action_factory_registration(self):
        from kairon.actions.definitions.factory import ActionFactory
        assert ActionType.store_page_action.value in ActionFactory._ActionFactory__implementations


class TestActionSerializerStorePageActionRoundTrip:

    @pytest.fixture(autouse=True)
    def processor(self):
        return MongoProcessor()

    def test_serialize_store_page_action_produces_correct_structure(self, processor):
        bot = "test_cat_serial_bot"
        processor.add_store_page_action(
            {"name": "cat_serial_ok", "page_name": "shop", "identifier_slot": "item_id"},
            bot, "user1"
        )
        result = ActionSerializer.serialize(bot)
        assert ActionType.store_page_action.value in result
        entries = result[ActionType.store_page_action.value]
        assert len(entries) >= 1
        entry = next(e for e in entries if e["name"] == "cat_serial_ok")
        assert entry["page_name"] == "shop"
        assert entry["identifier_slot"] == "item_id"

    def test_deserialize_store_page_action_creates_doc(self, processor):
        new_bot = "test_cat_deserial_bot"
        data = {
            ActionType.store_page_action.value: [
                {"name": "cat_deser_ok", "page_name": "shop", "identifier_slot": "item_id"}
            ]
        }
        ActionSerializer.deserialize(new_bot, "user1", data)
        assert StorePageAction.objects(bot=new_bot, name="cat_deser_ok", status=True).count() == 1

    def test_deserialize_store_page_action_skips_if_exists(self, processor):
        bot = "test_cat_deser_dup_bot"
        data = {
            ActionType.store_page_action.value: [
                {"name": "cat_deser_dup", "page_name": "shop", "identifier_slot": "item_id"}
            ]
        }
        ActionSerializer.deserialize(bot, "user1", data)
        ActionSerializer.deserialize(bot, "user1", data)
        assert StorePageAction.objects(bot=bot, name="cat_deser_dup", status=True).count() == 1

    def test_import_export_round_trip(self, processor):
        src_bot = "test_cat_rt_src"
        dst_bot = "test_cat_rt_dst"
        processor.add_store_page_action(
            {"name": "cat_rt", "page_name": "rt_page", "identifier_slot": "rt_slot"},
            src_bot, "user1"
        )
        serialized = ActionSerializer.serialize(src_bot)
        ActionSerializer.deserialize(dst_bot, "user1", serialized)
        result = list(processor.list_store_page_action(dst_bot, with_doc_id=False))
        cat_entry = next((r for r in result if r["name"] == "cat_rt"), None)
        assert cat_entry is not None
        assert cat_entry["page_name"] == "rt_page"
        assert cat_entry["identifier_slot"] == "rt_slot"

    def test_deserialize_store_page_action_invalid_data_raises(self, processor):
        bot = "test_cat_deser_invalid"
        data = {
            ActionType.store_page_action.value: [
                {"name": "bad_cat", "page_name": ""}
            ]
        }
        with pytest.raises(Exception):
            ActionSerializer.deserialize(bot, "user1", data)
