import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from babel.messages.jslexer import uni_escape_re
from mongoengine import connect

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.catalog_sync.catalog_sync_log_processor import CatalogSyncLogProcessor
from kairon.shared.catalog_sync.data_objects import CatalogSyncLogs
from kairon.shared.cognition.data_objects import CognitionSchema, CollectionData
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.data.constant import SYNC_STATUS, SyncType
from kairon.shared.data.data_objects import BotSettings, BotSyncConfig


class TestCatalogSyncLogProcessor:

    @pytest.fixture(scope='session', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))


    def test_add_log(self):
        bot = 'test'
        user = 'test'
        provider = "petpooja"
        sync_type = "push_menu"
        CatalogSyncLogProcessor.add_log(bot, user, provider = provider, sync_type = sync_type,raw_payload={"item":"Test raw payload"})
        log = CatalogSyncLogs.objects(bot=bot).get().to_mongo().to_dict()
        assert not log.get('exception')
        assert log['execution_id']
        assert log['raw_payload']
        assert log['sync_type']
        assert log['start_timestamp']
        assert not log.get('end_timestamp')
        assert not log.get('processed_payload')
        assert log['sync_status'] == SYNC_STATUS.INITIATED.value

    def test_add_log_exception(self):
        bot = 'test'
        user = 'test'
        CatalogSyncLogProcessor.add_log(bot, user, sync_status=SYNC_STATUS.FAILED.value,
                                        exception="Push menu processing is disabled for this bot",
                                        status="Failure")
        log = CatalogSyncLogs.objects(bot=bot).get().to_mongo().to_dict()
        assert log.get('exception') == "Push menu processing is disabled for this bot"
        assert log['execution_id']
        assert log['raw_payload']
        assert log['sync_type']
        assert log['start_timestamp']
        assert log.get('end_timestamp')
        assert log['sync_status'] == SYNC_STATUS.FAILED.value


    def test_add_log_validation_errors(self):
        bot = 'test'
        user = 'test'
        provider = "petpooja"
        sync_type = "push_menu"
        CatalogSyncLogProcessor.add_log(bot, user, provider = provider, sync_type = sync_type,raw_payload={"item":"Test raw payload"},
                                        sync_status=SYNC_STATUS.FAILED.value,
                                        exception="Validation Failed",
                                        status="Failure",
                                        validation_errors={
                                            "Header mismatch": "Expected headers ['order_id', 'order_priority', 'sales', 'profit'] but found ['order_id', 'order_priority', 'revenue', 'sales'].",
                                            "Missing columns": "{'profit'}.",
                                            "Extra columns": "{'revenue'}."
                                        }
                                        )
        log = list(CatalogSyncLogProcessor.get_logs(bot))
        assert log[0].get('exception') == "Validation Failed"
        assert log[0]['execution_id']
        assert log[0]['raw_payload']
        assert log[0]['sync_type']
        assert log[0]['start_timestamp']
        assert log[0]["validation_errors"]
        assert log[0].get('end_timestamp')
        assert log[0]['sync_status'] == SYNC_STATUS.FAILED.value

    def test_add_log_success(self):
        bot = 'test'
        user = 'test'
        provider = "petpooja"
        sync_type = "push_menu"
        CatalogSyncLogProcessor.add_log(bot, user, provider = provider, sync_type = sync_type,raw_payload={"item":"Test raw payload"})
        CatalogSyncLogProcessor.add_log(bot, user, sync_status=SYNC_STATUS.COMPLETED.value, status="Success")
        log = list(CatalogSyncLogProcessor.get_logs(bot))
        assert not log[0].get('exception')
        assert log[0]['execution_id']
        assert log[0]['raw_payload']
        assert log[0]['sync_type']
        assert log[0]['start_timestamp']
        assert not log[0]["validation_errors"]
        assert log[0]["status"] == 'Success'
        assert log[0]['sync_status'] == SYNC_STATUS.COMPLETED.value

    def test_is_event_in_progress_false(self):
        bot = 'test'
        assert not CatalogSyncLogProcessor.is_sync_in_progress(bot)

    def test_is_event_in_progress_true(self):
        bot = 'test'
        user = 'test'
        provider = "petpooja"
        sync_type = "push_menu"
        CatalogSyncLogProcessor.add_log(bot, user, provider=provider, sync_type=sync_type,
                                        raw_payload={"item": "Test raw payload"})
        assert CatalogSyncLogProcessor.is_sync_in_progress(bot, False)

        with pytest.raises(Exception):
            CatalogSyncLogProcessor.is_sync_in_progress(bot)

    def test_get_logs(self):
        bot = 'test'
        logs = list(CatalogSyncLogProcessor.get_logs(bot))
        assert len(logs) == 4

    def test_is_limit_exceeded_exception(self, monkeypatch):
        bot = 'test'
        try:
            bot_settings = BotSettings.objects(bot=bot).get()
            bot_settings.catalog_sync_limit_per_day = 0
        except:
            bot_settings = BotSettings(bot=bot, catalog_sync_limit_per_day=0, user="test")
        bot_settings.save()
        with pytest.raises(Exception):
            assert CatalogSyncLogProcessor.is_limit_exceeded(bot)

    def test_is_limit_exceeded(self, monkeypatch):
        bot = 'test'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.catalog_sync_limit_per_day = 3
        bot_settings.save()
        assert CatalogSyncLogProcessor.is_limit_exceeded(bot, False)

    def test_is_limit_exceeded_false(self, monkeypatch):
        bot = 'test'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.catalog_sync_limit_per_day = 6
        bot_settings.save()
        assert not CatalogSyncLogProcessor.is_limit_exceeded(bot)

    def test_catalog_collection_exists_true(self):
        bot = "test"
        user = "test"

        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo",
            branch_name="Branch A",
            branch_bot=bot,
            user=user
        ).save()

        expected_collection = "test_restaurant_branch_a_catalog"

        CognitionSchema(
            bot=bot,
            user=user,
            collection_name=expected_collection
        ).save()

        assert CatalogSyncLogProcessor.is_catalog_collection_exists(bot) is True

        BotSyncConfig.objects.delete()
        CognitionSchema.objects.delete()

    def test_catalog_collection_exists_false(self):
        bot = "test"
        user = "test"

        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo",
            branch_name="Branch A",
            branch_bot=bot,
            user=user
        ).save()

        assert CatalogSyncLogProcessor.is_catalog_collection_exists(bot) is False

        BotSyncConfig.objects.delete()
        CognitionSchema.objects.delete()

    def test_create_catalog_collection(self):
        bot = "test_bot"
        user = "test_user"

        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo_provider",
            branch_name="Test Branch",
            branch_bot=bot,
            user=user
        ).save()

        BotSettings(
            bot=bot,
            user=user,
            cognition_columns_per_collection_limit=5,
            llm_settings={'enable_faq': True}
        ).save()

        metadata_id = CatalogSyncLogProcessor.create_catalog_collection(bot, user)

        assert metadata_id is not None

        catalog_name = "test_restaurant_test_branch_catalog"
        created_schema = CognitionSchema.objects(collection_name=catalog_name).first()
        assert created_schema is not None
        assert created_schema.collection_name == catalog_name

        BotSyncConfig.objects.delete()
        BotSettings.objects.delete()
        CognitionSchema.objects.delete()

    def test_validate_item_ids(self):
        push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload.json")

        with push_menu_payload_path.open("r", encoding="utf-8") as f:
            push_menu_payload = json.load(f)

        try:
            CatalogSyncLogProcessor.validate_item_ids(push_menu_payload)
            itemid_missing = False
        except Exception as e:
            itemid_missing = True

        assert itemid_missing is False

    def test_validate_item_ids_missing_itemid(self):
        push_menu_payload_path = Path("tests/testing_data/catalog_sync/catalog_sync_push_menu_payload_invalid.json")

        with push_menu_payload_path.open("r", encoding="utf-8") as f:
            push_menu_payload = json.load(f)

        with pytest.raises(Exception):
            CatalogSyncLogProcessor.validate_item_ids(push_menu_payload)

    def test_validate_item_toggle_request_valid(self):
        file_path = Path("tests/testing_data/catalog_sync/catalog_sync_item_toggle_payload.json")
        with file_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        CatalogSyncLogProcessor.validate_item_toggle_request(payload)

    def test_validate_item_toggle_request_missing_instock(self):
        file_path = Path("tests/testing_data/catalog_sync/catalog_sync_item_toggle_payload_invalid_missing_instock.json")
        with file_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        with pytest.raises(Exception, match="Missing required field: 'inStock'"):
            CatalogSyncLogProcessor.validate_item_toggle_request(payload)

    def test_validate_item_toggle_request_nonboolean_instock(self):
        file_path = Path("tests/testing_data/catalog_sync/catalog_sync_item_toggle_payload_invalid_nonboolean_instock.json")
        with file_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        with pytest.raises(Exception, match="'inStock' must be a boolean"):
            CatalogSyncLogProcessor.validate_item_toggle_request(payload)

    def test_validate_item_toggle_request_missing_itemid(self):
        file_path = Path("tests/testing_data/catalog_sync/catalog_sync_item_toggle_payload_invalid_missing_itemid.json")
        with file_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        with pytest.raises(Exception, match="Missing required field: 'itemID'"):
            CatalogSyncLogProcessor.validate_item_toggle_request(payload)

    def test_sync_type_allowed_valid_push_menu(self):
        bot = "test_bot"
        user = "test_user"
        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo",
            branch_name="Branch",
            branch_bot=bot,
            user=user,
            process_push_menu=True,
            process_item_toggle=False
        ).save()

        CatalogSyncLogProcessor.is_sync_type_allowed(bot, SyncType.push_menu)

        BotSyncConfig.objects.delete()

    def test_sync_type_allowed_valid_item_toggle(self):
        bot = "test_bot"
        user = "test_user"
        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo",
            branch_name="Branch",
            branch_bot=bot,
            user=user,
            process_push_menu=False,
            process_item_toggle=True
        ).save()

        CatalogSyncLogProcessor.is_sync_type_allowed(bot, SyncType.item_toggle)

        BotSyncConfig.objects.delete()

    def test_sync_type_push_menu_not_allowed(self):
        bot = "test_bot"
        user = "test_user"
        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo",
            branch_name="Branch",
            branch_bot=bot,
            user=user,
            process_push_menu=False,
            process_item_toggle=True
        ).save()

        with pytest.raises(Exception, match="Push menu processing is disabled for this bot"):
            CatalogSyncLogProcessor.is_sync_type_allowed(bot, SyncType.push_menu)

        BotSyncConfig.objects.delete()

    def test_sync_type_item_toggle_not_allowed(self):
        bot = "test_bot"
        user = "test_user"
        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo",
            branch_name="Branch",
            branch_bot=bot,
            user=user,
            process_push_menu=True,
            process_item_toggle=False
        ).save()

        with pytest.raises(Exception, match="Item toggle is disabled for this bot"):
            CatalogSyncLogProcessor.is_sync_type_allowed(bot, SyncType.item_toggle)

        BotSyncConfig.objects.delete()

    def test_sync_type_config_missing(self):
        bot = "test_bot"
        BotSyncConfig.objects.delete()

        with pytest.raises(Exception, match="No bot sync config found for bot"):
            CatalogSyncLogProcessor.is_sync_type_allowed(bot, SyncType.push_menu)

    def test_ai_enabled_true(self):
        bot = "test_bot"
        user = "test_user"

        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo",
            branch_name="Branch",
            branch_bot=bot,
            user=user,
            ai_enabled=True
        ).save()

        result = CatalogSyncLogProcessor.is_ai_enabled(bot)
        assert result is True

        BotSyncConfig.objects.delete()

    def test_ai_enabled_false(self):
        bot = "test_bot"
        user = "test_user"

        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo",
            branch_name="Branch",
            branch_bot=bot,
            user=user,
            ai_enabled=False
        ).save()

        result = CatalogSyncLogProcessor.is_ai_enabled(bot)
        assert result is False

        BotSyncConfig.objects.delete()

    def test_ai_enabled_no_config(self):
        bot = "test_bot"
        BotSyncConfig.objects.delete()

        with pytest.raises(Exception, match="No bot sync config found for bot"):
            CatalogSyncLogProcessor.is_ai_enabled(bot)

    def test_meta_enabled_true(self):
        bot = "test_bot"
        user = "test_user"

        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo",
            branch_name="Branch",
            branch_bot=bot,
            user=user,
            meta_enabled=True
        ).save()

        result = CatalogSyncLogProcessor.is_meta_enabled(bot)
        assert result is True

        BotSyncConfig.objects.delete()

    def test_meta_enabled_false(self):
        bot = "test_bot"
        user = "test_user"

        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo",
            branch_name="Branch",
            branch_bot=bot,
            user=user,
            meta_enabled=False
        ).save()

        result = CatalogSyncLogProcessor.is_meta_enabled(bot)
        assert result is False

        BotSyncConfig.objects.delete()

    def test_meta_enabled_no_config(self):
        bot = "test_bot"
        BotSyncConfig.objects.delete()

        with pytest.raises(Exception, match="No bot sync config found for bot"):
            CatalogSyncLogProcessor.is_meta_enabled(bot)

    def test_get_execution_id_for_bot_returns_latest_pending(self):
        bot = "test_bot"
        user = "test_user"

        CatalogSyncLogs(
            execution_id="completed_1",
            raw_payload={"item":"Test raw payload"},
            bot=bot,
            user=user,
            provider="demo",
            sync_type="push_menu",
            sync_status=SYNC_STATUS.COMPLETED.value,
            start_timestamp=datetime.utcnow() - timedelta(minutes=10)
        ).save()

        CatalogSyncLogs(
            execution_id="failed_1",
            raw_payload={"item":"Test raw payload"},
            bot=bot,
            user=user,
            provider="demo",
            sync_type="push_menu",
            sync_status=SYNC_STATUS.FAILED.value,
            start_timestamp=datetime.utcnow() - timedelta(minutes=5)
        ).save()

        CatalogSyncLogs(
            execution_id="valid_pending_1",
            raw_payload={"item":"Test raw payload"},
            bot=bot,
            user=user,
            provider="demo",
            sync_type="push_menu",
            sync_status=SYNC_STATUS.PREPROCESSING.value,
            start_timestamp=datetime.utcnow()
        ).save()

        execution_id = CatalogSyncLogProcessor.get_execution_id_for_bot(bot)
        assert execution_id == "valid_pending_1"

        CatalogSyncLogs.objects.delete()

    def test_get_execution_id_for_bot_returns_none_if_all_completed_or_failed(self):
        bot = "test_bot"
        user = "test_user"

        CatalogSyncLogs(
            execution_id="completed_2",
            raw_payload={"item":"Test raw payload"},
            bot=bot,
            user=user,
            provider="demo",
            sync_type="push_menu",
            sync_status=SYNC_STATUS.COMPLETED.value,
            start_timestamp=datetime.utcnow()
        ).save()

        CatalogSyncLogs(
            execution_id="failed_2",
            raw_payload={"item":"Test raw payload"},
            bot=bot,
            user=user,
            provider="demo",
            sync_type="push_menu",
            sync_status=SYNC_STATUS.FAILED.value,
            start_timestamp=datetime.utcnow()
        ).save()

        execution_id = CatalogSyncLogProcessor.get_execution_id_for_bot(bot)
        assert execution_id is None

        CatalogSyncLogs.objects.delete()

    def test_validate_image_configurations_when_catalog_images_exists(self):
        bot = "test_bot"
        user = "test_user"

        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo_provider",
            branch_name="Test Branch",
            branch_bot=bot,
            user=user
        ).save()

        CollectionData(
            collection_name="test_restaurant_test_branch_catalog_images",
            data={
                "image_type": "global",
                "image_url": "http://example.com/global_fallback.jpg",
                "image_base64": ""
            },
            user=user,
            bot=bot,
            status=True,
            timestamp=datetime.utcnow()
        ).save()

        CatalogSyncLogProcessor.validate_image_configurations(bot, user)

        BotSyncConfig.objects.delete()
        CollectionData.objects.delete()

    def test_validate_image_configurations_when_catalog_images_missing_global_fallback(self):
        bot = "test_bot"
        user = "test_user"

        BotSyncConfig(
            parent_bot=bot,
            restaurant_name="Test Restaurant",
            provider="demo_provider",
            branch_name="Test Branch",
            branch_bot=bot,
            user=user
        ).save()

        with pytest.raises(Exception, match="Global fallback image URL not found"):
            CatalogSyncLogProcessor.validate_image_configurations(bot, user)

        BotSyncConfig.objects.delete()
        CollectionData.objects.delete()