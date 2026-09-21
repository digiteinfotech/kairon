import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.shared.utils import Utility

Utility.load_environment()

from kairon.exceptions import AppException
from kairon.shared.data.data_models import (
    AddressRequest,
    CreateOrderRequest,
    FilterOrdersRequest,
    UpdateOrderStatusRequest,
    UpsertCustomerRequest,
)

# Route handler imports (test them as plain async functions)
from kairon.api.app.routers.bot.customer_orders import (
    create_order,
    delete_customer,
    filter_orders,
    get_customer,
    get_order,
    list_customers,
    list_orders_for_customer,
    update_address,
    update_order_status,
    upsert_customer,
)
from kairon.api.app.routers.bot.bot import get_store_page_metadata, save_store_page_metadata
from kairon.shared.data.data_models import StorePageMetadataRequest
from kairon.api.app.routers.bot.data import (
    list_collection_data,
    get_collection_metadata,
    get_collection_data,
    get_collection_data_with_timestamp,
    get_collection_data_with_id,
    get_all_collections,
    get_collection_filter_count,
)

BOT = "router_test_bot"

# Minimal User stand-in used by list_customers (get_current_user_and_bot path)
_MOCK_USER = MagicMock()
_MOCK_USER.get_bot.return_value = BOT

# Claims dict returned by validate_store_page_token
_MOCK_CLAIMS = {"sub": "27830000001", "bot": BOT}


class TestUpsertCustomerRouter:

    @pytest.mark.asyncio
    async def test_upsert_customer_success(self):
        req = UpsertCustomerRequest(sender_id="enc_id", persona_type="fnb", name="Alice")
        expected = {"_id": "abc", "name": "Alice", "sender_id": "enc2"}
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.upsert_customer",
            return_value=expected,
        ) as mock_proc:
            result = await upsert_customer(bot=BOT, request_data=req, current_user=_MOCK_CLAIMS)
        mock_proc.assert_called_once_with(
            bot=BOT,
            sender_id="enc_id",
            persona_type="fnb",
            payload={"name": "Alice"},
        )
        assert result.data == expected

    @pytest.mark.asyncio
    async def test_upsert_customer_propagates_exception(self):
        req = UpsertCustomerRequest(sender_id="bad_enc", persona_type=None)
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.upsert_customer",
            side_effect=AppException("Invalid identifier"),
        ):
            with pytest.raises(AppException, match="Invalid identifier"):
                await upsert_customer(bot=BOT, request_data=req, current_user=_MOCK_CLAIMS)


class TestGetCustomerRouter:

    @pytest.mark.asyncio
    async def test_get_customer_success(self):
        expected = {"_id": "xyz", "name": "Bob", "sender_id": "enc_bob"}
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.get_customer",
            return_value=expected,
        ) as mock_proc:
            result = await get_customer(bot=BOT, sender_id="enc_bob", current_user=_MOCK_CLAIMS)
        mock_proc.assert_called_once_with(bot=BOT, sender_id="enc_bob")
        assert result.data == expected

    @pytest.mark.asyncio
    async def test_get_customer_not_found_raises(self):
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.get_customer",
            side_effect=AppException("Customer not found"),
        ):
            with pytest.raises(AppException, match="Customer not found"):
                await get_customer(bot=BOT, sender_id="enc_missing", current_user=_MOCK_CLAIMS)


class TestListCustomersRouter:

    @pytest.mark.asyncio
    async def test_list_customers_delegates_to_processor(self):
        expected = [{"_id": "1"}, {"_id": "2"}]
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.list_customers",
            return_value=expected,
        ) as mock_proc:
            result = await list_customers(
                bot=BOT, persona_type="fnb", page=1, page_size=10, current_user=_MOCK_USER
            )
        mock_proc.assert_called_once_with(bot=BOT, persona_type="fnb", page=1, page_size=10)
        assert result.data == expected

    @pytest.mark.asyncio
    async def test_list_customers_uses_bot_from_path(self):
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.list_customers",
            return_value=[],
        ) as mock_proc:
            await list_customers(bot=BOT, persona_type=None, page=2, page_size=5, current_user=_MOCK_USER)
        mock_proc.assert_called_once_with(bot=BOT, persona_type=None, page=2, page_size=5)


class TestUpdateAddressRouter:

    @pytest.mark.asyncio
    async def test_update_address_success(self):
        addr = AddressRequest(label="home", address="123 St", is_default=True)
        expected = {"_id": "c1", "address_list": [{"label": "home"}]}
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.update_address",
            return_value=expected,
        ) as mock_proc:
            result = await update_address(
                bot=BOT, sender_id="enc_u1", request_data=addr, current_user=_MOCK_CLAIMS
            )
        mock_proc.assert_called_once_with(
            bot=BOT,
            sender_id="enc_u1",
            address_payload={"label": "home", "address": "123 St", "is_default": True},
        )
        assert result.data == expected


class TestDeleteCustomerRouter:

    @pytest.mark.asyncio
    async def test_delete_customer_success(self):
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.delete_customer",
        ) as mock_proc:
            result = await delete_customer(bot=BOT, sender_id="enc_del", current_user=_MOCK_CLAIMS)
        mock_proc.assert_called_once_with(bot=BOT, sender_id="enc_del")
        assert result.message == "Customer deleted"

    @pytest.mark.asyncio
    async def test_delete_customer_not_found_raises(self):
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.delete_customer",
            side_effect=AppException("Customer not found"),
        ):
            with pytest.raises(AppException, match="Customer not found"):
                await delete_customer(bot=BOT, sender_id="enc_gone", current_user=_MOCK_CLAIMS)


class TestCreateOrderRouter:

    @pytest.mark.asyncio
    async def test_create_order_success(self):
        req = CreateOrderRequest(sender_id="enc_s", persona_type="fnb", callback_identifier="test_cb", order_details={"item": "X"})
        expected = {"order_id": "o1", "payment_id": None, "payment_link": None}
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.create_order",
            return_value=expected,
        ) as mock_proc:
            result = await create_order(bot=BOT, request_data=req, current_user=_MOCK_CLAIMS)
        mock_proc.assert_called_once_with(
            bot=BOT,
            sender_id="enc_s",
            persona_type="fnb",
            callback_identifier="test_cb",
            order_payload={"item": "X"},
        )
        assert result.data == expected

    @pytest.mark.asyncio
    async def test_create_order_customer_not_found_raises(self):
        req = CreateOrderRequest(sender_id="enc_none", callback_identifier="test_cb", order_details={"item": "Y"})
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.create_order",
            side_effect=AppException("Customer not found"),
        ):
            with pytest.raises(AppException, match="Customer not found"):
                await create_order(bot=BOT, request_data=req, current_user=_MOCK_CLAIMS)


class TestGetOrderRouter:

    @pytest.mark.asyncio
    async def test_get_order_success(self):
        expected = {"_id": "o99", "status": "placed", "order_details": {"item": "Z"}}
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.get_order",
            return_value=expected,
        ) as mock_proc:
            result = await get_order(bot=BOT, order_id="o99", current_user=_MOCK_CLAIMS)
        mock_proc.assert_called_once_with(bot=BOT, order_id="o99")
        assert result.data == expected

    @pytest.mark.asyncio
    async def test_get_order_not_found_raises(self):
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.get_order",
            side_effect=AppException("Order not found"),
        ):
            with pytest.raises(AppException, match="Order not found"):
                await get_order(bot=BOT, order_id="missing_id", current_user=_MOCK_CLAIMS)


class TestUpdateOrderStatusRouter:

    @pytest.mark.asyncio
    async def test_update_status_success(self):
        req = UpdateOrderStatusRequest(status="confirmed")
        expected = {"_id": "o1", "status": "confirmed"}
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.update_order_status",
            return_value=expected,
        ) as mock_proc:
            result = await update_order_status(
                bot=BOT, order_id="o1", request_data=req, current_user=_MOCK_CLAIMS
            )
        mock_proc.assert_called_once_with(bot=BOT, order_id="o1", new_status="confirmed")
        assert result.data == expected

    @pytest.mark.asyncio
    async def test_update_status_invalid_transition_raises(self):
        req = UpdateOrderStatusRequest(status="completed")
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.update_order_status",
            side_effect=AppException("Invalid transition"),
        ):
            with pytest.raises(AppException, match="Invalid transition"):
                await update_order_status(
                    bot=BOT, order_id="o1", request_data=req, current_user=_MOCK_CLAIMS
                )


class TestListOrdersForCustomerRouter:

    @pytest.mark.asyncio
    async def test_list_orders_delegates_to_processor(self):
        expected = [{"_id": "o1"}, {"_id": "o2"}]
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.list_orders_for_customer",
            return_value=expected,
        ) as mock_proc:
            result = await list_orders_for_customer(
                bot=BOT, sender_id="enc_s", page=1, page_size=10, current_user=_MOCK_CLAIMS
            )
        mock_proc.assert_called_once_with(bot=BOT, sender_id="enc_s", page=1, page_size=10)
        assert result.data == expected


class TestFilterOrdersRouter:

    @pytest.mark.asyncio
    async def test_filter_orders_delegates_to_processor(self):
        req = FilterOrdersRequest(persona_type="fnb", filters={"item": "Pizza"}, page=1, page_size=20)
        expected = [{"_id": "o5"}]
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.filter_orders",
            return_value=expected,
        ) as mock_proc:
            result = await filter_orders(bot=BOT, request_data=req, current_user=_MOCK_CLAIMS)
        mock_proc.assert_called_once_with(
            bot=BOT,
            persona_type="fnb",
            filters={"item": "Pizza"},
            page=1,
            page_size=20,
        )
        assert result.data == expected

    @pytest.mark.asyncio
    async def test_filter_orders_empty_filters(self):
        req = FilterOrdersRequest()
        with patch(
            "kairon.api.app.routers.bot.customer_orders.CustomerOrderProcessor.filter_orders",
            return_value=[],
        ) as mock_proc:
            result = await filter_orders(bot=BOT, request_data=req, current_user=_MOCK_CLAIMS)
        mock_proc.assert_called_once_with(
            bot=BOT, persona_type=None, filters={}, page=1, page_size=20
        )
        assert result.data == []


class TestGetStorePageMetadataRouter:

    @pytest.mark.asyncio
    async def test_get_store_page_metadata_with_store_page_token(self):
        """Store page token (CustomerDetails) path — uses bot from path param."""
        expected = {"store_name": "My Shop", "logo_url": "https://example.com/logo.png"}
        mock_customer = MagicMock()
        with patch(
            "kairon.api.app.routers.bot.bot.mongo_processor.get_store_page_metadata",
            return_value=expected,
        ) as mock_proc:
            result = await get_store_page_metadata(bot=BOT, current_user=mock_customer)
        mock_proc.assert_called_once_with(BOT)
        assert result.data == expected

    @pytest.mark.asyncio
    async def test_get_store_page_metadata_with_user_token(self):
        """Regular user token (User) path — uses bot from path param."""
        expected = {"store_name": "Bot Store"}
        with patch(
            "kairon.api.app.routers.bot.bot.mongo_processor.get_store_page_metadata",
            return_value=expected,
        ) as mock_proc:
            result = await get_store_page_metadata(bot=BOT, current_user=_MOCK_USER)
        mock_proc.assert_called_once_with(BOT)
        assert result.data == expected

    @pytest.mark.asyncio
    async def test_get_store_page_metadata_not_found_raises(self):
        from kairon.exceptions import AppException
        with patch(
            "kairon.api.app.routers.bot.bot.mongo_processor.get_store_page_metadata",
            side_effect=AppException("Store page metadata not found"),
        ):
            with pytest.raises(AppException, match="Store page metadata not found"):
                await get_store_page_metadata(bot=BOT, current_user=_MOCK_USER)


_DATA_PROC = "kairon.api.app.routers.bot.data.DataProcessor"


class TestCollectionDataRouter:

    @pytest.mark.asyncio
    async def test_list_collection_data_with_store_page_token(self):
        expected = [{"name": "menu"}, {"name": "items"}]
        with patch(f"{_DATA_PROC}.list_collection_data", return_value=expected) as mock_proc:
            result = await list_collection_data(bot=BOT, current_user=MagicMock())
        mock_proc.assert_called_once_with(BOT)
        assert result["data"] == expected

    @pytest.mark.asyncio
    async def test_list_collection_data_with_user_token(self):
        with patch(f"{_DATA_PROC}.list_collection_data", return_value=[]) as mock_proc:
            result = await list_collection_data(bot=BOT, current_user=_MOCK_USER)
        mock_proc.assert_called_once_with(BOT)
        assert result["data"] == []

    @pytest.mark.asyncio
    async def test_get_collection_metadata_success(self):
        expected = {"fields": ["name", "price"]}
        with patch(f"{_DATA_PROC}.get_crud_metadata", return_value=expected) as mock_proc:
            result = await get_collection_metadata(bot=BOT, collection_name="menu", current_user=MagicMock())
        mock_proc.assert_called_once_with(bot=BOT, collection_name="menu")
        assert result["data"] == expected

    @pytest.mark.asyncio
    async def test_get_collection_metadata_raises(self):
        with patch(f"{_DATA_PROC}.get_crud_metadata", side_effect=AppException("Collection not found")):
            with pytest.raises(AppException, match="Collection not found"):
                await get_collection_metadata(bot=BOT, collection_name="missing", current_user=MagicMock())

    @pytest.mark.asyncio
    async def test_get_collection_data_success(self):
        rows = [{"data": {"name": "Burger", "price": 10}}]
        with patch(f"{_DATA_PROC}.get_collection_data", return_value=rows):
            with patch("kairon.api.app.routers.bot.data.CollectionData") as mock_cd:
                mock_cd.objects.return_value.count.return_value = 1
                result = await get_collection_data(
                    bot=BOT, collection_name="menu",
                    key=[], value=[], start_idx=0, page_size=10,
                    current_user=MagicMock(),
                )
        assert result["data"]["logs"] == rows
        assert result["data"]["total"] == 1

    @pytest.mark.asyncio
    async def test_get_collection_data_with_timestamp_success(self):
        rows = [{"data": {"name": "Pizza"}}]
        with patch(f"{_DATA_PROC}.get_collection_data_with_timestamp", return_value=rows) as mock_proc:
            result = await get_collection_data_with_timestamp(
                bot=BOT, collection_name="menu",
                filters="{}", start_time=None, end_time=None,
                current_user=MagicMock(),
            )
        mock_proc.assert_called_once_with(bot=BOT, data_filter="{}", collection_name="menu", start_time=None, end_time=None)
        assert result["data"] == rows

    @pytest.mark.asyncio
    async def test_get_collection_data_with_id_success(self):
        expected = {"_id": "abc123", "data": {"name": "Burger"}}
        with patch(f"{_DATA_PROC}.get_collection_data_with_id", return_value=expected) as mock_proc:
            result = await get_collection_data_with_id(bot=BOT, collection_id="abc123", current_user=MagicMock())
        mock_proc.assert_called_once_with(BOT, collection_id="abc123")
        assert result["data"] == expected

    @pytest.mark.asyncio
    async def test_get_collection_data_with_id_raises(self):
        with patch(f"{_DATA_PROC}.get_collection_data_with_id", side_effect=AppException("Record not found")):
            with pytest.raises(AppException, match="Record not found"):
                await get_collection_data_with_id(bot=BOT, collection_id="bad_id", current_user=MagicMock())

    @pytest.mark.asyncio
    async def test_get_all_collections_success(self):
        expected = ["menu", "items", "specials"]
        with patch(f"{_DATA_PROC}.get_all_collections", return_value=expected) as mock_proc:
            result = await get_all_collections(bot=BOT, current_user=MagicMock())
        mock_proc.assert_called_once_with(BOT)
        assert result.data == expected

    @pytest.mark.asyncio
    async def test_get_collection_filter_count_success(self):
        with patch(f"{_DATA_PROC}.get_collection_filter_data_count", return_value=42) as mock_proc:
            result = await get_collection_filter_count(
                bot=BOT, collection_name="menu", filters=None, current_user=MagicMock()
            )
        mock_proc.assert_called_once_with(BOT, "menu", None)
        assert result.data == {"count": 42}

    @pytest.mark.asyncio
    async def test_get_collection_filter_count_raises(self):
        with patch(f"{_DATA_PROC}.get_collection_filter_data_count", side_effect=AppException("Invalid filters")):
            with pytest.raises(AppException, match="Invalid filters"):
                await get_collection_filter_count(
                    bot=BOT, collection_name="menu", filters="{bad}", current_user=MagicMock()
                )


class TestSaveStorePageMetadataRouter:

    @pytest.mark.asyncio
    async def test_save_store_page_metadata_success(self):
        request = StorePageMetadataRequest(config={"payment_enabled": True, "currency": "INR"})
        with patch(
            "kairon.api.app.routers.bot.bot.mongo_processor.save_store_page_metadata"
        ) as mock_proc:
            result = await save_store_page_metadata(request=request, current_user=_MOCK_USER)
        mock_proc.assert_called_once_with(
            bot=BOT,
            user=_MOCK_USER.get_user(),
            config={"payment_enabled": True, "currency": "INR"},
        )
        assert result.message == "Store page metadata saved successfully"

    @pytest.mark.asyncio
    async def test_save_store_page_metadata_empty_config(self):
        request = StorePageMetadataRequest(config={})
        with patch(
            "kairon.api.app.routers.bot.bot.mongo_processor.save_store_page_metadata"
        ) as mock_proc:
            result = await save_store_page_metadata(request=request, current_user=_MOCK_USER)
        mock_proc.assert_called_once_with(bot=BOT, user=_MOCK_USER.get_user(), config={})
        assert result.message == "Store page metadata saved successfully"

    @pytest.mark.asyncio
    async def test_save_store_page_metadata_processor_raises(self):
        request = StorePageMetadataRequest(config={"payment_enabled": True})
        with patch(
            "kairon.api.app.routers.bot.bot.mongo_processor.save_store_page_metadata",
            side_effect=AppException("DB error"),
        ):
            with pytest.raises(AppException, match="DB error"):
                await save_store_page_metadata(request=request, current_user=_MOCK_USER)


class TestSaveStorePageMetadataProcessor:

    def setup_method(self):
        from mongoengine import connect
        from kairon.shared.utils import Utility
        connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
        self.bot = "test_save_metadata_proc_bot"
        self.user = "test_user"
        from kairon.shared.data.data_objects import StorePageMetadata
        StorePageMetadata.objects(bot=self.bot).delete()

    def teardown_method(self):
        from kairon.shared.data.data_objects import StorePageMetadata
        StorePageMetadata.objects(bot=self.bot).delete()

    def test_save_creates_new_record(self):
        from kairon.shared.data.processor import MongoProcessor
        from kairon.shared.data.data_objects import StorePageMetadata
        processor = MongoProcessor()
        processor.save_store_page_metadata(self.bot, self.user, {"payment_enabled": True})
        doc = StorePageMetadata.objects(bot=self.bot).get()
        assert doc.config == {"payment_enabled": True}
        assert doc.user == self.user

    def test_save_upserts_existing_record(self):
        from kairon.shared.data.processor import MongoProcessor
        from kairon.shared.data.data_objects import StorePageMetadata
        processor = MongoProcessor()
        processor.save_store_page_metadata(self.bot, self.user, {"payment_enabled": False})
        processor.save_store_page_metadata(self.bot, self.user, {"payment_enabled": True, "currency": "INR"})
        assert StorePageMetadata.objects(bot=self.bot).count() == 1
        doc = StorePageMetadata.objects(bot=self.bot).get()
        assert doc.config == {"payment_enabled": True, "currency": "INR"}

    def test_save_then_get_roundtrip(self):
        from kairon.shared.data.processor import MongoProcessor
        processor = MongoProcessor()
        config = {"payment_enabled": True, "store_name": "My Shop"}
        processor.save_store_page_metadata(self.bot, self.user, config)
        result = processor.get_store_page_metadata(self.bot)
        assert result["config"] == config
        assert result["bot"] == self.bot
