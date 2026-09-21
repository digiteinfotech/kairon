import os
from unittest.mock import patch, MagicMock

import pytest
from mongoengine import connect
from mongoengine import DoesNotExist
from mongoengine.errors import NotUniqueError, ValidationError

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.shared.utils import Utility

Utility.load_environment()

from kairon.exceptions import AppException
from kairon.shared.data.customer_order_processor import CustomerOrderProcessor
from kairon.shared.data.data_objects import CustomerDetails, OrderDetails


@pytest.fixture(autouse=True, scope="module")
def init_connection():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))


def _enc(plain: str) -> str:
    return Utility.encrypt_message(plain)


class TestCustomerUpsert:

    def test_upsert_customer_create_success(self):
        bot = "cop_upsert_create_bot"
        enc = _enc("user_c1")
        result = CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb",
            payload={"name": "Alice", "mobile": "9000000001"},
        )
        assert result["name"] == "Alice"
        assert result["mobile"] == "9000000001"
        assert result["persona_type"] == "fnb"
        assert "_id" in result
        assert result["sender_id"] != "user_c1"

    def test_upsert_customer_update_existing(self):
        bot = "cop_upsert_update_bot"
        enc = _enc("user_u1")
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb",
            payload={"name": "Bob", "mobile": "9000000002"},
        )
        result = CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb",
            payload={"name": "Bob Updated", "mobile": "9000000002"},
        )
        assert result["name"] == "Bob Updated"
        assert CustomerDetails.objects(bot=bot, sender_id="user_u1").count() == 1

    def test_upsert_customer_with_address_list(self):
        bot = "cop_upsert_addr_bot"
        enc = _enc("user_a1")
        result = CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb",
            payload={
                "mobile": "9000000003",
                "address_list": [{"label": "home", "address": "123 Main St", "is_default": True}],
            },
        )
        assert len(result["address_list"]) == 1
        assert result["address_list"][0]["label"] == "home"

    def test_upsert_customer_replaces_address_list_on_update(self):
        bot = "cop_upsert_addr_replace_bot"
        enc = _enc("user_ar1")
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb",
            payload={
                "mobile": "9000000099",
                "address_list": [{"label": "home", "address": "Old", "is_default": True}],
            },
        )
        result = CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb",
            payload={
                "mobile": "9000000099",
                "address_list": [{"label": "office", "address": "New", "is_default": False}],
            },
        )
        assert len(result["address_list"]) == 1
        assert result["address_list"][0]["label"] == "office"

    def test_upsert_customer_invalid_sender_id(self):
        with pytest.raises(AppException, match="Invalid identifier"):
            CustomerOrderProcessor.upsert_customer(
                bot="any_bot", sender_id="not_valid_encrypted",
                persona_type="fnb",
                payload={"mobile": "9000000005"},
            )

    def test_upsert_customer_response_re_encrypts_sender_id(self):
        bot = "cop_mask_bot"
        plain = "user_mask1"
        enc = _enc(plain)
        result = CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb",
            payload={"mobile": "9000000006"},
        )
        assert result["sender_id"] != plain
        assert Utility.decrypt_message(result["sender_id"]) == plain


class TestCustomerGet:

    def setup_method(self):
        self.bot = "cop_get_bot"
        self.plain_id = "user_get1"
        self.enc = _enc(self.plain_id)
        CustomerOrderProcessor.upsert_customer(
            bot=self.bot, sender_id=self.enc,
            persona_type="fnb",
            payload={"name": "GetUser", "mobile": "9100000001"},
        )

    def test_get_customer_success(self):
        result = CustomerOrderProcessor.get_customer(bot=self.bot, sender_id=self.enc)
        assert result["name"] == "GetUser"
        assert result["mobile"] == "9100000001"

    def test_get_customer_masks_sender_id(self):
        result = CustomerOrderProcessor.get_customer(bot=self.bot, sender_id=self.enc)
        assert result["sender_id"] != self.plain_id
        assert Utility.decrypt_message(result["sender_id"]) == self.plain_id

    def test_get_customer_not_found(self):
        enc = _enc("user_nonexistent")
        with pytest.raises(AppException, match="Customer not found"):
            CustomerOrderProcessor.get_customer(bot=self.bot, sender_id=enc)

    def test_get_customer_wrong_bot(self):
        with pytest.raises(AppException, match="Customer not found"):
            CustomerOrderProcessor.get_customer(bot="wrong_bot", sender_id=self.enc)

    def test_get_customer_deleted_not_found(self):
        bot = "cop_get_deleted_bot"
        enc = _enc("user_del_get")
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb", payload={"mobile": "9100000002"},
        )
        CustomerOrderProcessor.delete_customer(bot=bot, sender_id=enc)
        with pytest.raises(AppException, match="Customer not found"):
            CustomerOrderProcessor.get_customer(bot=bot, sender_id=enc)


class TestCustomerList:

    def setup_method(self):
        self.bot = "cop_list_bot_" + self.__class__.__name__

    def test_list_customers_empty(self):
        result = CustomerOrderProcessor.list_customers(bot="cop_empty_list_bot")
        assert result == []

    def test_list_customers_all(self):
        bot = "cop_list_all_bot"
        for i in range(3):
            CustomerOrderProcessor.upsert_customer(
                bot=bot, sender_id=_enc(f"list_user_{i}"),
                persona_type="fnb", payload={"mobile": f"910000{i:04d}"},
            )
        result = CustomerOrderProcessor.list_customers(bot=bot)
        assert len(result) == 3

    def test_list_customers_filter_by_persona_type(self):
        bot = "cop_list_persona_bot"
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=_enc("lp_user1"),
            persona_type="fnb", payload={"mobile": "9200000001"},
        )
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=_enc("lp_user2"),
            persona_type="hotel", payload={"mobile": "9200000002"},
        )
        fnb = CustomerOrderProcessor.list_customers(bot=bot, persona_type="fnb")
        hotel = CustomerOrderProcessor.list_customers(bot=bot, persona_type="hotel")
        assert len(fnb) == 1
        assert len(hotel) == 1
        assert fnb[0]["persona_type"] == "fnb"

    def test_list_customers_pagination(self):
        bot = "cop_list_page_bot"
        for i in range(5):
            CustomerOrderProcessor.upsert_customer(
                bot=bot, sender_id=_enc(f"page_user_{i}"),
                persona_type="fnb", payload={"mobile": f"930000{i:04d}"},
            )
        page1 = CustomerOrderProcessor.list_customers(bot=bot, page=1, page_size=3)
        page2 = CustomerOrderProcessor.list_customers(bot=bot, page=2, page_size=3)
        assert len(page1) == 3
        assert len(page2) == 2

    def test_list_customers_excludes_deleted(self):
        bot = "cop_list_del_bot"
        enc_keep = _enc("list_del_keep")
        enc_del = _enc("list_del_gone")
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc_keep,
            persona_type="fnb", payload={"mobile": "9400000001"},
        )
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc_del,
            persona_type="fnb", payload={"mobile": "9400000002"},
        )
        CustomerOrderProcessor.delete_customer(bot=bot, sender_id=enc_del)
        result = CustomerOrderProcessor.list_customers(bot=bot)
        assert len(result) == 1


class TestUpdateAddress:

    def setup_method(self):
        self.bot = "cop_addr_bot"
        self.enc = _enc("addr_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=self.bot, sender_id=self.enc,
            persona_type="fnb",
            payload={"mobile": "9500000001", "address_list": [{"label": "home", "address": "Old Home"}]},
        )

    def test_update_address_add_new_label(self):
        result = CustomerOrderProcessor.update_address(
            bot=self.bot, sender_id=self.enc,
            address_payload={"label": "office", "address": "Work St", "is_default": False},
        )
        labels = {a["label"] for a in result["address_list"]}
        assert "home" in labels
        assert "office" in labels
        assert len(result["address_list"]) == 2

    def test_update_address_replace_existing_label(self):
        result = CustomerOrderProcessor.update_address(
            bot=self.bot, sender_id=self.enc,
            address_payload={"label": "home", "address": "New Home", "is_default": True},
        )
        home_entries = [a for a in result["address_list"] if a["label"] == "home"]
        assert len(home_entries) == 1
        assert home_entries[0]["address"] == "New Home"

    def test_update_address_customer_not_found(self):
        with pytest.raises(AppException, match="Customer not found"):
            CustomerOrderProcessor.update_address(
                bot=self.bot, sender_id=_enc("no_such_user"),
                address_payload={"label": "home", "address": "Anywhere"},
            )


class TestDeleteCustomer:

    def test_delete_customer_success(self):
        bot = "cop_del_bot"
        enc = _enc("del_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb", payload={"mobile": "9600000001"},
        )
        CustomerOrderProcessor.delete_customer(bot=bot, sender_id=enc)
        assert CustomerDetails.objects(bot=bot, sender_id="del_user1", status=False).count() == 1
        assert CustomerDetails.objects(bot=bot, sender_id="del_user1", status=True).count() == 0

    def test_delete_customer_not_found(self):
        with pytest.raises(AppException, match="Customer not found"):
            CustomerOrderProcessor.delete_customer(
                bot="cop_del_bot", sender_id=_enc("no_such_del_user"),
            )

    def test_delete_customer_is_soft_delete(self):
        bot = "cop_soft_del_bot"
        enc = _enc("soft_del_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb", payload={"mobile": "9600000002"},
        )
        CustomerOrderProcessor.delete_customer(bot=bot, sender_id=enc)
        assert CustomerDetails.objects(bot=bot, sender_id="soft_del_user1").count() == 1


class TestCreateOrder:

    def setup_method(self):
        self.bot = "cop_order_bot"
        self.enc = _enc("order_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=self.bot, sender_id=self.enc,
            persona_type="fnb", payload={"mobile": "9700000001"},
        )

    def test_create_order_success(self):
        result = CustomerOrderProcessor.create_order(
            bot=self.bot, sender_id=self.enc,
            persona_type="fnb",
            order_payload={"item": "Pizza", "qty": 2, "price": 499},
            callback_identifier="test_cb",
        )
        assert "order_id" in result
        assert result["payment_id"] is None
        assert result["payment_link"] is None

    def test_create_order_customer_not_found(self):
        with pytest.raises(AppException, match="Customer not found"):
            CustomerOrderProcessor.create_order(
                bot=self.bot, sender_id=_enc("no_customer"),
                persona_type="fnb",
                order_payload={"item": "Soda"},
                callback_identifier="test_cb",
            )


class TestGetOrder:

    def setup_method(self):
        self.bot = "cop_get_order_bot"
        enc = _enc("get_order_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=self.bot, sender_id=enc,
            persona_type="fnb", payload={"mobile": "9800000001"},
        )
        self.order = CustomerOrderProcessor.create_order(
            bot=self.bot, sender_id=enc,
            persona_type="fnb",
            order_payload={"item": "Pasta", "qty": 1, "price": 299},
            callback_identifier="test_cb",
        )

    def test_get_order_success(self):
        result = CustomerOrderProcessor.get_order(bot=self.bot, order_id=self.order["order_id"])
        assert result["order_details"]["item"] == "Pasta"
        assert result["status"] == "placed"

    def test_get_order_not_found(self):
        from bson import ObjectId
        fake_id = str(ObjectId())
        with pytest.raises(AppException, match="Order not found"):
            CustomerOrderProcessor.get_order(bot=self.bot, order_id=fake_id)

    def test_get_order_wrong_bot(self):
        with pytest.raises(AppException, match="Order not found"):
            CustomerOrderProcessor.get_order(bot="wrong_bot", order_id=self.order["order_id"])


class TestUpdateOrderStatus:

    def setup_method(self):
        self.bot = "cop_status_bot"
        enc = _enc("status_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=self.bot, sender_id=enc,
            persona_type="fnb", payload={"mobile": "9900000001"},
        )
        self.order = CustomerOrderProcessor.create_order(
            bot=self.bot, sender_id=enc,
            persona_type="fnb",
            order_payload={"item": "Coffee", "qty": 2, "price": 120},
            callback_identifier="test_cb",
        )

    def test_update_status_placed_to_confirmed(self):
        result = CustomerOrderProcessor.update_order_status(
            bot=self.bot, order_id=self.order["order_id"], new_status="confirmed",
        )
        assert result["status"] == "confirmed"

    def test_update_status_invalid_transition(self):
        with pytest.raises(AppException, match="Invalid transition"):
            CustomerOrderProcessor.update_order_status(
                bot=self.bot, order_id=self.order["order_id"], new_status="completed",
            )

    def test_update_status_terminal_completed_no_transitions(self):
        bot = "cop_terminal_bot"
        enc = _enc("terminal_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb", payload={"mobile": "9910000001"},
        )
        order = CustomerOrderProcessor.create_order(
            bot=bot, sender_id=enc,
            persona_type="fnb", order_payload={"item": "X", "qty": 1, "price": 10},
            callback_identifier="test_cb",
        )
        CustomerOrderProcessor.update_order_status(bot=bot, order_id=order["order_id"], new_status="confirmed")
        CustomerOrderProcessor.update_order_status(bot=bot, order_id=order["order_id"], new_status="in_progress")
        CustomerOrderProcessor.update_order_status(bot=bot, order_id=order["order_id"], new_status="completed")
        with pytest.raises(AppException, match="Invalid transition"):
            CustomerOrderProcessor.update_order_status(bot=bot, order_id=order["order_id"], new_status="cancelled")

    def test_update_status_order_not_found(self):
        from bson import ObjectId
        with pytest.raises(AppException, match="Order not found"):
            CustomerOrderProcessor.update_order_status(
                bot=self.bot, order_id=str(ObjectId()), new_status="confirmed",
            )

    def test_update_status_placed_to_cancelled(self):
        bot = "cop_cancel_bot"
        enc = _enc("cancel_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=bot, sender_id=enc,
            persona_type="fnb", payload={"mobile": "9920000001"},
        )
        order = CustomerOrderProcessor.create_order(
            bot=bot, sender_id=enc,
            persona_type="fnb", order_payload={"item": "Y", "qty": 1, "price": 10},
            callback_identifier="test_cb",
        )
        result = CustomerOrderProcessor.update_order_status(
            bot=bot, order_id=order["order_id"], new_status="cancelled",
        )
        assert result["status"] == "cancelled"


class TestUpdateOrder:

    def setup_method(self):
        self.bot = "cop_update_order_bot"
        enc = _enc("update_order_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=self.bot, sender_id=enc,
            persona_type="fnb", payload={"mobile": "9930000001"},
        )
        self.order = CustomerOrderProcessor.create_order(
            bot=self.bot, sender_id=enc,
            persona_type="fnb",
            order_payload={"item": "Tea", "qty": 1, "price": 30},
            callback_identifier="test_cb",
        )
        self.order_id = self.order["order_id"]

    def test_update_order_details(self):
        payload = {"order_details": {"item": "Tea", "qty": 2, "price": 60}}
        result = CustomerOrderProcessor.update_order(
            bot=self.bot, order_id=self.order_id, payload=payload
        )
        assert result["order_details"]["qty"] == 2
        assert result["order_details"]["price"] == 60

    def test_update_additional_info(self):
        payload = {"additional_info": {"notes": "less sugar"}}
        result = CustomerOrderProcessor.update_order(
            bot=self.bot, order_id=self.order_id, payload=payload
        )
        assert result["additional_info"]["notes"] == "less sugar"

    def test_update_order_details_and_additional_info(self):
        payload = {
            "order_details": {"item": "Coffee", "qty": 3, "price": 90},
            "additional_info": {"delivery": "asap"},
        }
        result = CustomerOrderProcessor.update_order(
            bot=self.bot, order_id=self.order_id, payload=payload
        )
        assert result["order_details"]["item"] == "Coffee"
        assert result["additional_info"]["delivery"] == "asap"

    def test_update_order_empty_payload_no_change(self):
        CustomerOrderProcessor.update_order(
            bot=self.bot, order_id=self.order_id,
            payload={"order_details": {"item": "Tea", "qty": 1, "price": 30}},
        )
        result = CustomerOrderProcessor.update_order(
            bot=self.bot, order_id=self.order_id, payload={}
        )
        assert result["order_details"]["item"] == "Tea"

    def test_update_order_not_found(self):
        from bson import ObjectId
        with pytest.raises(AppException, match="Order not found"):
            CustomerOrderProcessor.update_order(
                bot=self.bot, order_id=str(ObjectId()), payload={"additional_info": {}}
            )

    def test_update_order_invalid_id_raises(self):
        with pytest.raises(AppException, match="Order not found"):
            CustomerOrderProcessor.update_order(
                bot=self.bot, order_id="not_an_object_id", payload={}
            )

    def test_update_order_does_not_change_status(self):
        result = CustomerOrderProcessor.update_order(
            bot=self.bot, order_id=self.order_id,
            payload={"order_details": {"item": "Juice", "qty": 1, "price": 50}},
        )
        assert result["status"] == "placed"

    def test_update_additional_info_merges_existing_fields(self):
        CustomerOrderProcessor.update_order(
            bot=self.bot, order_id=self.order_id,
            payload={"additional_info": {"notes": "no onion"}},
        )
        result = CustomerOrderProcessor.update_order(
            bot=self.bot, order_id=self.order_id,
            payload={"additional_info": {"delivery": "asap"}},
        )
        assert result["additional_info"]["notes"] == "no onion"
        assert result["additional_info"]["delivery"] == "asap"

    def test_update_additional_info_overwrites_existing_key(self):
        CustomerOrderProcessor.update_order(
            bot=self.bot, order_id=self.order_id,
            payload={"additional_info": {"notes": "no onion"}},
        )
        result = CustomerOrderProcessor.update_order(
            bot=self.bot, order_id=self.order_id,
            payload={"additional_info": {"notes": "extra spicy"}},
        )
        assert result["additional_info"]["notes"] == "extra spicy"


class TestListOrders:

    @classmethod
    def setup_class(cls):
        cls.bot = "cop_list_orders_bot"
        cls.enc = _enc("list_orders_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=cls.bot, sender_id=cls.enc,
            persona_type="fnb", payload={"mobile": "9930000001"},
        )
        for i in range(4):
            CustomerOrderProcessor.create_order(
                bot=cls.bot, sender_id=cls.enc,
                persona_type="fnb", order_payload={"item": f"item_{i}", "qty": i + 1, "price": (i + 1) * 100},
                callback_identifier="test_cb",
            )

    def test_list_orders_for_customer_returns_all(self):
        result = CustomerOrderProcessor.list_orders_for_customer(
            bot=self.bot, sender_id=self.enc,
        )
        assert len(result) == 4

    def test_list_orders_for_customer_pagination(self):
        page1 = CustomerOrderProcessor.list_orders_for_customer(
            bot=self.bot, sender_id=self.enc, page=1, page_size=2,
        )
        page2 = CustomerOrderProcessor.list_orders_for_customer(
            bot=self.bot, sender_id=self.enc, page=2, page_size=2,
        )
        assert len(page1) == 2
        assert len(page2) == 2
        ids_p1 = {r["_id"] for r in page1}
        ids_p2 = {r["_id"] for r in page2}
        assert ids_p1.isdisjoint(ids_p2)

    def test_list_orders_for_customer_empty(self):
        result = CustomerOrderProcessor.list_orders_for_customer(
            bot=self.bot, sender_id=_enc("nonexistent_order_user"),
        )
        assert result == []


class TestFilterOrders:

    @classmethod
    def setup_class(cls):
        cls.bot = "cop_filter_orders_bot"
        enc = _enc("filter_orders_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=cls.bot, sender_id=enc,
            persona_type="fnb", payload={"mobile": "9940000001"},
        )
        for item, price in [("Pizza", 499), ("Pizza", 499), ("Burger", 199)]:
            CustomerOrderProcessor.create_order(
                bot=cls.bot, sender_id=enc,
                persona_type="fnb", order_payload={"item": item, "price": price},
                callback_identifier="test_cb",
            )

    def test_filter_orders_no_filters_returns_all(self):
        result = CustomerOrderProcessor.filter_orders(
            bot=self.bot, persona_type="fnb", filters={},
        )
        assert len(result) == 3

    def test_filter_orders_single_key_match(self):
        result = CustomerOrderProcessor.filter_orders(
            bot=self.bot, persona_type="fnb", filters={"item": "Pizza"},
        )
        assert len(result) == 2
        for r in result:
            assert r["order_details"]["item"] == "Pizza"

    def test_filter_orders_multiple_keys_intersection(self):
        result = CustomerOrderProcessor.filter_orders(
            bot=self.bot, persona_type="fnb", filters={"item": "Pizza", "price": 499},
        )
        assert len(result) == 2

    def test_filter_orders_no_match(self):
        result = CustomerOrderProcessor.filter_orders(
            bot=self.bot, persona_type="fnb", filters={"item": "Sushi"},
        )
        assert result == []

    def test_filter_orders_wrong_persona_type_no_results(self):
        result = CustomerOrderProcessor.filter_orders(
            bot=self.bot, persona_type="hotel", filters={},
        )
        assert result == []


class TestRegisterCustomerIfNew:

    def setup_method(self):
        self.bot = "reg_if_new_bot"
        self.sender = "27831234567"
        CustomerDetails.objects(bot=self.bot).delete()
        CustomerDetails.objects(bot="reg_if_new_bot_2").delete()

    def test_create_new_record(self):
        # AC1: no existing record → creates exactly one
        CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        assert CustomerDetails.objects(bot=self.bot, sender_id=self.sender).count() == 1

    def test_sender_id_stored_verbatim(self):
        # AC2: byte-for-byte, no encryption/decryption applied
        CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        doc = CustomerDetails.objects(bot=self.bot, sender_id=self.sender).first()
        assert doc.sender_id == self.sender

    def test_idempotent_two_calls_one_record(self):
        # AC3: two calls → one record
        CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        assert CustomerDetails.objects(bot=self.bot, sender_id=self.sender).count() == 1

    def test_idempotent_second_call_no_write(self):
        # AC3: second invocation performs no write
        CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        with patch.object(CustomerDetails, "save") as mock_save:
            CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
            mock_save.assert_not_called()

    def test_non_destructive_on_populated_record(self):
        # AC4: existing record with populated fields is fully unchanged
        CustomerDetails(
            bot=self.bot, sender_id=self.sender, name="Alice", mobile="9000000001"
        ).save()
        before = CustomerDetails.objects(bot=self.bot, sender_id=self.sender).first().to_mongo().to_dict()
        CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        after = CustomerDetails.objects(bot=self.bot, sender_id=self.sender).first().to_mongo().to_dict()
        before.pop("updated_at", None)
        after.pop("updated_at", None)
        assert before == after

    def test_created_record_schema_defaults(self):
        # AC5: created record has only bot+sender; all other fields are schema defaults
        CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        doc = CustomerDetails.objects(bot=self.bot, sender_id=self.sender).first()
        assert doc.status is True
        assert doc.address_list == []
        assert doc.persona_type is None
        assert doc.name is None
        assert doc.mobile is None
        assert doc.email is None

    def test_per_bot_isolation(self):
        # AC6: same sender under different bot → separate records; original untouched
        other_bot = "reg_if_new_bot_2"
        CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        CustomerOrderProcessor.register_customer_if_new(other_bot, self.sender)
        assert CustomerDetails.objects(bot=self.bot, sender_id=self.sender).count() == 1
        assert CustomerDetails.objects(bot=other_bot, sender_id=self.sender).count() == 1
        assert CustomerDetails.objects(bot=self.bot).count() == 1

    def test_read_failure_does_not_propagate_emits_one_warning(self):
        # AC7 + AC8: DB read error → no exception, exactly one warning
        with patch("kairon.shared.data.customer_order_processor.CustomerDetails") as mock_cls:
            mock_cls.objects.side_effect = Exception("DB down")
            with patch("kairon.shared.data.customer_order_processor.logger") as mock_log:
                result = CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        assert result is None
        assert mock_log.warning.call_count == 1

    def test_write_failure_does_not_propagate_emits_one_warning(self):
        # AC7 + AC8: DB write error → no exception, exactly one warning
        with patch("kairon.shared.data.customer_order_processor.CustomerDetails") as mock_cls:
            mock_cls.objects.return_value.first.return_value = None
            mock_cls.return_value.save.side_effect = Exception("write failed")
            with patch("kairon.shared.data.customer_order_processor.logger") as mock_log:
                result = CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        assert result is None
        assert mock_log.warning.call_count == 1

    def test_returns_none(self):
        # AC9: operation returns no value
        result = CustomerOrderProcessor.register_customer_if_new(self.bot, self.sender)
        assert result is None


class TestResolveCredential:

    def test_plain_value_returned_as_is(self):
        param = {"parameter_type": "value", "value": "my_key"}
        result = CustomerOrderProcessor._resolve_credential(param, "test_bot")
        assert result == "my_key"

    def test_missing_value_returns_empty_string(self):
        param = {"parameter_type": "value"}
        result = CustomerOrderProcessor._resolve_credential(param, "test_bot")
        assert result == ""

    def test_encrypted_value_is_decrypted(self):
        plain = "secret123"
        encrypted = Utility.encrypt_message(plain)
        param = {"parameter_type": "value", "value": encrypted, "encrypt": True}
        result = CustomerOrderProcessor._resolve_credential(param, "test_bot")
        assert result == plain

    def test_empty_value_with_encrypt_flag_skips_decryption(self):
        param = {"parameter_type": "value", "value": "", "encrypt": True}
        result = CustomerOrderProcessor._resolve_credential(param, "test_bot")
        assert result == ""

    def test_key_vault_fetches_secret(self):
        param = {"parameter_type": "key_vault", "value": "MY_SECRET"}
        with patch("kairon.shared.actions.utils.ActionUtility.get_secret_from_key_vault") as mock_vault:
            mock_vault.return_value = "vault_value"
            result = CustomerOrderProcessor._resolve_credential(param, "test_bot")
        assert result == "vault_value"
        mock_vault.assert_called_once_with("MY_SECRET", "test_bot")

    def test_key_vault_none_returns_empty_string(self):
        param = {"parameter_type": "key_vault", "value": "MISSING_SECRET"}
        with patch("kairon.shared.actions.utils.ActionUtility.get_secret_from_key_vault") as mock_vault:
            mock_vault.return_value = None
            result = CustomerOrderProcessor._resolve_credential(param, "test_bot")
        assert result == ""


class TestGenerateStorePageUrl:

    _MOCK_BS = MagicMock(store_page_token_expiry=15)

    def test_url_starts_with_catalog_base_and_contains_components(self):
        bot = "url_gen_bot"
        plain_sender = "url_user1"
        page_name = "catalog"
        with patch("kairon.shared.data.data_objects.BotSettings") as mock_bs:
            mock_bs.objects.return_value.get.return_value = self._MOCK_BS
            url = CustomerOrderProcessor._generate_store_page_url(bot, plain_sender, page_name)
        catalog_base = Utility.environment.get("store_page", {}).get("url", "")
        assert url.startswith(f"{catalog_base}/{page_name}/{bot}/")

    def test_url_encrypted_id_decryptable_to_plain_sender(self):
        bot = "url_gen_bot2"
        plain_sender = "url_user2"
        page_name = "shop"
        with patch("kairon.shared.data.data_objects.BotSettings") as mock_bs:
            mock_bs.objects.return_value.get.return_value = self._MOCK_BS
            url = CustomerOrderProcessor._generate_store_page_url(bot, plain_sender, page_name)
        catalog_base = Utility.environment.get("store_page", {}).get("url", "")
        prefix = f"{catalog_base}/{page_name}/{bot}/"
        remainder = url[len(prefix):]
        encrypted_id, _ = remainder.split("/", 1)
        assert Utility.decrypt_message(encrypted_id) == plain_sender

    def test_url_token_is_jwt(self):
        bot = "url_gen_bot3"
        plain_sender = "url_user3"
        page_name = "store"
        with patch("kairon.shared.data.data_objects.BotSettings") as mock_bs:
            mock_bs.objects.return_value.get.return_value = self._MOCK_BS
            url = CustomerOrderProcessor._generate_store_page_url(bot, plain_sender, page_name)
        token = url.split("/")[-1]
        assert token.count(".") == 2


class TestCreateRazorpayPaymentLink:

    def test_success_returns_response_json(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "pay_123", "short_url": "https://rzp.io/pay/abc"}
        with patch("kairon.shared.data.customer_order_processor.http_requests.post") as mock_post:
            mock_post.return_value = mock_resp
            result = CustomerOrderProcessor._create_razorpay_payment_link(
                api_key="key", api_secret="secret",
                order_id="order_001",
                order_details={"amount": 100, "currency": "INR", "name": "Alice",
                               "contact": "9999999999", "email": "a@a.com"},
                callback_url="https://catalog.kairon.com/catalog/bot/enc/token",
                callback_identifier="cb_001",
            )
        assert result["id"] == "pay_123"
        assert result["short_url"] == "https://rzp.io/pay/abc"

    def test_api_error_raises_app_exception(self):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 422
        mock_resp.text = "amount too low"
        with patch("kairon.shared.data.customer_order_processor.http_requests.post") as mock_post:
            mock_post.return_value = mock_resp
            with pytest.raises(AppException, match="Razorpay API error 422"):
                CustomerOrderProcessor._create_razorpay_payment_link(
                    api_key="key", api_secret="secret",
                    order_id="order_002",
                    order_details={"amount": 0},
                    callback_url="https://cb.url",
                    callback_identifier=None,
                )

    def test_amount_converted_to_paise(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "pay_paise", "short_url": "https://rzp.io/p"}
        with patch("kairon.shared.data.customer_order_processor.http_requests.post") as mock_post:
            mock_post.return_value = mock_resp
            CustomerOrderProcessor._create_razorpay_payment_link(
                api_key="k", api_secret="s", order_id="o3",
                order_details={"amount": 49.99},
                callback_url="https://cb",
                callback_identifier=None,
            )
        call_payload = mock_post.call_args.kwargs["json"]
        assert call_payload["amount"] == 4999


class TestUpsertCustomerExceptions:

    def test_not_unique_error_raises_app_exception(self):
        bot = "cop_unique_err_bot"
        enc = _enc("unique_err_user")
        with patch("kairon.shared.data.customer_order_processor.CustomerDetails") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.address_list = []
            mock_instance.save.side_effect = NotUniqueError
            mock_cls.objects.return_value.get.side_effect = DoesNotExist
            mock_cls.return_value = mock_instance
            with pytest.raises(AppException, match="Customer with this identifier already exists"):
                CustomerOrderProcessor.upsert_customer(
                    bot=bot, sender_id=enc, persona_type=None, payload={}
                )

    def test_validation_error_raises_app_exception(self):
        bot = "cop_val_err_bot"
        enc = _enc("val_err_user")
        with patch("kairon.shared.data.customer_order_processor.CustomerDetails") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.address_list = []
            mock_instance.save.side_effect = ValidationError("mobile: Value must be a valid phone number")
            mock_cls.objects.return_value.get.side_effect = DoesNotExist
            mock_cls.return_value = mock_instance
            with pytest.raises(AppException, match="mobile: Value must be a valid phone number"):
                CustomerOrderProcessor.upsert_customer(
                    bot=bot, sender_id=enc, persona_type=None, payload={}
                )


class TestCreateOrderPaymentEnabled:

    def setup_method(self):
        self.bot = "cop_payment_bot"
        self.enc = _enc("payment_user1")
        CustomerOrderProcessor.upsert_customer(
            bot=self.bot, sender_id=self.enc,
            persona_type="fnb", payload={"mobile": "9990000001"},
        )
        from kairon.shared.data.data_objects import StorePageMetadata
        from kairon.shared.actions.data_objects import RazorpayAction, StorePageAction
        StorePageMetadata.objects(bot=self.bot).delete()
        RazorpayAction.objects(bot=self.bot).delete()
        StorePageAction.objects(bot=self.bot).delete()

    def _save_store_metadata(self, payment_enabled=True):
        from kairon.shared.data.data_objects import StorePageMetadata
        StorePageMetadata.objects(bot=self.bot).delete()
        StorePageMetadata(
            bot=self.bot, user="test_user",
            config={"payment_enabled": payment_enabled},
        ).save()

    def _save_store_page_action(self, page_name="catalog", callback_identifier=None):
        from kairon.shared.actions.data_objects import StorePageAction
        StorePageAction.objects(bot=self.bot).delete()
        StorePageAction(
            name="test_store_page_action", bot=self.bot, user="test_user",
            page_name=page_name, identifier_slot="user_identifier",
            callback_identifier=callback_identifier,
        ).save()

    def _save_razorpay_action(self, api_key="rzp_key", api_secret="rzp_secret"):
        from kairon.shared.actions.data_objects import RazorpayAction, CustomActionRequestParameters
        RazorpayAction.objects(bot=self.bot).delete()
        RazorpayAction(
            name="razorpay_action", bot=self.bot, user="test_user",
            api_key=CustomActionRequestParameters(value=api_key, parameter_type="value"),
            api_secret=CustomActionRequestParameters(value=api_secret, parameter_type="value"),
            amount=CustomActionRequestParameters(value="100", parameter_type="value"),
            currency=CustomActionRequestParameters(value="INR", parameter_type="value"),
        ).save()

    def test_payment_disabled_returns_none_payment_fields(self):
        self._save_store_metadata(payment_enabled=False)
        result = CustomerOrderProcessor.create_order(
            bot=self.bot, sender_id=self.enc,
            persona_type="fnb",
            order_payload={"item": "Coffee", "amount": 80},
            callback_identifier="test_cb",
        )
        assert "order_id" in result
        assert result["payment_id"] is None
        assert result["payment_link"] is None

    def test_payment_enabled_no_razorpay_action_raises(self):
        self._save_store_metadata(payment_enabled=True)
        self._save_store_page_action()
        with pytest.raises(AppException, match="Razorpay action not configured"):
            CustomerOrderProcessor.create_order(
                bot=self.bot, sender_id=self.enc,
                persona_type="fnb",
                order_payload={"item": "Pizza", "amount": 200},
                callback_identifier="test_cb",
            )

    def test_payment_enabled_razorpay_success_returns_payment_fields(self):
        self._save_store_metadata(payment_enabled=True)
        self._save_store_page_action(page_name="shop", callback_identifier="cb_001")
        self._save_razorpay_action()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "pay_xyz", "short_url": "https://rzp.io/xyz"}
        with patch("kairon.shared.data.customer_order_processor.http_requests.post") as mock_post:
            mock_post.return_value = mock_resp
            with patch("kairon.shared.data.data_objects.BotSettings") as mock_bs:
                mock_bs.objects.return_value.get.return_value = MagicMock(store_page_token_expiry=15)
                result = CustomerOrderProcessor.create_order(
                    bot=self.bot, sender_id=self.enc,
                    persona_type="fnb",
                    order_payload={"item": "Burger", "amount": 150},
                    callback_identifier="cb_001",
                )
        assert result["payment_id"] == "pay_xyz"
        assert result["payment_link"] == "https://rzp.io/xyz"
        assert "order_id" in result
        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["notes"]["kairon_id"] == "cb_001"
        assert call_payload["notes"]["kairon_order_id"] == result["order_id"]

    def test_payment_enabled_razorpay_app_exception_reraises(self):
        self._save_store_metadata(payment_enabled=True)
        self._save_store_page_action()
        self._save_razorpay_action()
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        with patch("kairon.shared.data.customer_order_processor.http_requests.post") as mock_post:
            mock_post.return_value = mock_resp
            with patch("kairon.shared.data.data_objects.BotSettings") as mock_bs:
                mock_bs.objects.return_value.get.return_value = MagicMock(store_page_token_expiry=15)
                with pytest.raises(AppException, match="Razorpay API error 401"):
                    CustomerOrderProcessor.create_order(
                        bot=self.bot, sender_id=self.enc,
                        persona_type="fnb",
                        order_payload={"item": "Drink", "amount": 50},
                        callback_identifier="test_cb",
                    )

    def test_payment_enabled_network_error_logs_warning_returns_order(self):
        self._save_store_metadata(payment_enabled=True)
        self._save_store_page_action()
        self._save_razorpay_action()
        with patch("kairon.shared.data.customer_order_processor.http_requests.post") as mock_post:
            mock_post.side_effect = ConnectionError("network error")
            with patch("kairon.shared.data.data_objects.BotSettings") as mock_bs:
                mock_bs.objects.return_value.get.return_value = MagicMock(store_page_token_expiry=15)
                with patch("kairon.shared.data.customer_order_processor.logger") as mock_log:
                    result = CustomerOrderProcessor.create_order(
                        bot=self.bot, sender_id=self.enc,
                        persona_type="fnb",
                        order_payload={"item": "Tea", "amount": 30},
                        callback_identifier="test_cb",
                    )
        assert "order_id" in result
        assert result["payment_id"] is None
        assert result["payment_link"] is None
        assert mock_log.warning.call_count == 1
