import os

import pytest
from mongoengine import connect
from mongoengine.errors import ValidationError

from kairon.shared.utils import Utility

os.environ["system_file"] = "./tests/testing_data/system.yaml"

Utility.load_environment()

from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import AgentActionConfig, Actions
from kairon.shared.actions.models import ActionType
from kairon.shared.data.action_serializer import ActionSerializer
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import StoryStepType


@pytest.fixture(autouse=True, scope='module')
def init_connection():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment['database']['url']))


class TestMongoProcessorAgentActionCRUD:

    @pytest.fixture(autouse=True)
    def processor(self):
        return MongoProcessor()

    # ─── add ──────────────────────────────────────────────────────────────────

    def test_add_agent_action_success(self, processor):
        bot = "test_agent_crud_bot"
        action = {"name": "agent_add_ok", "agent_name": "My Agent", "agent_id": "uuid-001"}
        processor.add_agent_action(action, bot, "user1")
        assert AgentActionConfig.objects(bot=bot, name="agent_add_ok", status=True).count() == 1
        assert Actions.objects(bot=bot, name="agent_add_ok", status=True).count() == 1

    def test_add_agent_action_duplicate_raises(self, processor):
        bot = "test_agent_dup_bot"
        action = {"name": "agent_dup", "agent_name": "My Agent", "agent_id": "uuid-002"}
        processor.add_agent_action(action, bot, "user1")
        with pytest.raises(AppException):
            processor.add_agent_action(action, bot, "user1")

    def test_add_agent_action_empty_name_raises(self, processor):
        action = {"name": "", "agent_name": "My Agent", "agent_id": "uuid-003"}
        with pytest.raises((AppException, ValidationError)):
            processor.add_agent_action(action, "bot_empty_name", "user1")

    def test_add_agent_action_empty_agent_id_raises(self, processor):
        action = {"name": "valid_name_for_empty_id", "agent_name": "My Agent", "agent_id": ""}
        with pytest.raises((AppException, ValidationError)):
            processor.add_agent_action(action, "bot_empty_id", "user1")

    def test_add_agent_action_dispatch_bot_response_default_true(self, processor):
        bot = "test_agent_default_dispatch_bot"
        action = {"name": "agent_default_dispatch", "agent_name": "My Agent", "agent_id": "uuid-004"}
        processor.add_agent_action(action, bot, "user1")
        doc = AgentActionConfig.objects(bot=bot, name="agent_default_dispatch", status=True).get()
        assert doc.dispatch_bot_response is True

    # ─── edit ─────────────────────────────────────────────────────────────────

    def test_edit_agent_action_success(self, processor):
        bot = "test_agent_edit_bot"
        processor.add_agent_action(
            {"name": "agent_edit_ok", "agent_name": "Old Name", "agent_id": "uuid-old"},
            bot, "user1"
        )
        processor.edit_agent_action(
            {"name": "agent_edit_ok", "agent_name": "New Name", "agent_id": "uuid-new",
             "dispatch_bot_response": False},
            bot, "user1"
        )
        doc = AgentActionConfig.objects(bot=bot, name="agent_edit_ok", status=True).get()
        assert doc.agent_name == "New Name"
        assert doc.agent_id == "uuid-new"
        assert doc.dispatch_bot_response is False

    def test_edit_agent_action_not_found_raises(self, processor):
        with pytest.raises(AppException):
            processor.edit_agent_action(
                {"name": "no_such_agent", "agent_name": "X", "agent_id": "y"},
                "bot_missing_agent_edit", "user1"
            )

    # ─── list ─────────────────────────────────────────────────────────────────

    def test_list_agent_action_empty(self, processor):
        result = list(processor.list_agent_action("bot_empty_agent_list"))
        assert result == []

    def test_list_agent_action_with_doc_id(self, processor):
        bot = "test_agent_list_id_bot"
        processor.add_agent_action(
            {"name": "agent_list_id", "agent_name": "Agent", "agent_id": "uuid-list"},
            bot, "user1"
        )
        result = list(processor.list_agent_action(bot, with_doc_id=True))
        assert len(result) == 1
        assert "_id" in result[0]
        assert isinstance(result[0]["_id"], str)
        assert "bot" not in result[0]
        assert "user" not in result[0]
        assert "timestamp" not in result[0]
        assert "status" not in result[0]

    def test_list_agent_action_without_doc_id(self, processor):
        bot = "test_agent_list_noid_bot"
        processor.add_agent_action(
            {"name": "agent_list_noid", "agent_name": "Agent", "agent_id": "uuid-noid"},
            bot, "user1"
        )
        result = list(processor.list_agent_action(bot, with_doc_id=False))
        assert len(result) == 1
        assert "_id" not in result[0]

    def test_list_agent_action_filters_by_bot(self, processor):
        bot_a = "test_agent_filter_a"
        bot_b = "test_agent_filter_b"
        processor.add_agent_action(
            {"name": "agent_filter_a", "agent_name": "A", "agent_id": "uuid-a"}, bot_a, "u"
        )
        processor.add_agent_action(
            {"name": "agent_filter_b", "agent_name": "B", "agent_id": "uuid-b"}, bot_b, "u"
        )
        result_a = list(processor.list_agent_action(bot_a, with_doc_id=False))
        assert len(result_a) == 1
        assert result_a[0]["name"] == "agent_filter_a"

    # ─── delete ───────────────────────────────────────────────────────────────

    def test_delete_agent_action_success(self, processor):
        bot = "test_agent_del_bot"
        processor.add_agent_action(
            {"name": "agent_del_ok", "agent_name": "Agent", "agent_id": "uuid-del"}, bot, "u"
        )
        assert AgentActionConfig.objects(bot=bot, name="agent_del_ok", status=True).count() == 1
        assert Actions.objects(bot=bot, name="agent_del_ok", status=True).count() == 1
        processor.delete_agent_action("agent_del_ok", bot, "u")
        assert AgentActionConfig.objects(bot=bot, name="agent_del_ok", status=True).count() == 0
        assert Actions.objects(bot=bot, name="agent_del_ok", status=True).count() == 0

    def test_delete_agent_action_not_found_raises(self, processor):
        with pytest.raises(AppException):
            processor.delete_agent_action("no_such_agent_del", "bot_del_missing_agent", "u")


class TestStoryStepTypeAgentActionIntegration:

    def test_story_step_type_enum_has_agent_action(self):
        assert StoryStepType.agent_action.value == "AGENT_ACTION"

    def test_action_type_enum_has_agent_action(self):
        assert ActionType.agent_action.value == "agent_action"

    def test_action_serializer_lookup_has_agent_action(self):
        assert ActionType.agent_action.value in ActionSerializer.action_lookup
        entry = ActionSerializer.action_lookup[ActionType.agent_action.value]
        assert entry.get("db_model") is not None
        assert entry.get("validation_model") is not None

    def test_action_serializer_get_collection_infos_includes_agent_action(self):
        action_info, _ = ActionSerializer.get_collection_infos()
        assert ActionType.agent_action.value in action_info

    def test_action_factory_registration(self):
        from kairon.actions.definitions.factory import ActionFactory
        assert ActionType.agent_action.value in ActionFactory._ActionFactory__implementations

    def test_agent_action_config_validate_empty_name_raises(self):
        with pytest.raises(ValidationError):
            AgentActionConfig(
                name="", agent_name="Agent", agent_id="some-id", bot="b", user="u"
            ).validate()

    def test_agent_action_config_validate_empty_agent_id_raises(self):
        with pytest.raises(ValidationError):
            AgentActionConfig(
                name="valid", agent_name="Agent", agent_id="", bot="b", user="u"
            ).validate()


class TestActionSerializerAgentActionRoundTrip:

    @pytest.fixture(autouse=True)
    def processor(self):
        return MongoProcessor()

    def test_serialize_agent_action_produces_correct_structure(self, processor):
        bot = "test_agent_serial_bot"
        processor.add_agent_action(
            {"name": "agent_serial_ok", "agent_name": "Serial Agent", "agent_id": "uuid-serial"},
            bot, "user1"
        )
        result, _ = ActionSerializer.serialize(bot)
        assert ActionType.agent_action.value in result
        entries = result[ActionType.agent_action.value]
        assert len(entries) >= 1
        entry = next(e for e in entries if e["name"] == "agent_serial_ok")
        assert entry["agent_name"] == "Serial Agent"
        assert entry["agent_id"] == "uuid-serial"

    def test_deserialize_agent_action_creates_doc(self, processor):
        new_bot = "test_agent_deserial_bot"
        data = {
            ActionType.agent_action.value: [
                {"name": "agent_deser_ok", "agent_name": "Deser Agent", "agent_id": "uuid-deser"}
            ]
        }
        ActionSerializer.deserialize(new_bot, "user1", data)
        assert AgentActionConfig.objects(bot=new_bot, name="agent_deser_ok", status=True).count() == 1

    def test_deserialize_agent_action_skips_if_exists(self, processor):
        bot = "test_agent_deser_dup_bot"
        data = {
            ActionType.agent_action.value: [
                {"name": "agent_deser_dup", "agent_name": "Dup Agent", "agent_id": "uuid-dup"}
            ]
        }
        ActionSerializer.deserialize(bot, "user1", data)
        ActionSerializer.deserialize(bot, "user1", data)
        assert AgentActionConfig.objects(bot=bot, name="agent_deser_dup", status=True).count() == 1

    def test_import_export_round_trip(self, processor):
        src_bot = "test_agent_rt_src"
        dst_bot = "test_agent_rt_dst"
        processor.add_agent_action(
            {"name": "agent_rt", "agent_name": "RT Agent", "agent_id": "uuid-rt",
             "dispatch_bot_response": False},
            src_bot, "user1"
        )
        serialized, _ = ActionSerializer.serialize(src_bot)
        ActionSerializer.deserialize(dst_bot, "user1", serialized)
        result = list(processor.list_agent_action(dst_bot, with_doc_id=False))
        entry = next((r for r in result if r["name"] == "agent_rt"), None)
        assert entry is not None
        assert entry["agent_name"] == "RT Agent"
        assert entry["agent_id"] == "uuid-rt"
        assert entry["dispatch_bot_response"] is False

    def test_deserialize_agent_action_partial_record_inserted(self, processor):
        bot = "test_agent_invalid_deser_bot"
        data = {
            ActionType.agent_action.value: [
                {"name": "bad_agent"}
            ]
        }
        ActionSerializer.deserialize(bot, "user1", data)
        assert AgentActionConfig.objects(bot=bot, name="bad_agent").count() == 1
