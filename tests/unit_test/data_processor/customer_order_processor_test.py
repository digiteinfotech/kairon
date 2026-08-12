import os

import pytest
from mongoengine import connect

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
        )
        assert result["status"] == "placed"
        assert result["order_details"]["item"] == "Pizza"
        assert "_id" in result

    def test_create_order_builds_filterable_attrs(self):
        result = CustomerOrderProcessor.create_order(
            bot=self.bot, sender_id=self.enc,
            persona_type="fnb",
            order_payload={"item": "Burger", "qty": 1, "nested": {"ignored": True}},
        )
        keys = {a["k"] for a in result["filterable_attrs"]}
        assert "item" in keys
        assert "qty" in keys
        assert "nested" not in keys

    def test_create_order_customer_not_found(self):
        with pytest.raises(AppException, match="Customer not found"):
            CustomerOrderProcessor.create_order(
                bot=self.bot, sender_id=_enc("no_customer"),
                persona_type="fnb",
                order_payload={"item": "Soda"},
            )

    def test_create_order_masks_sender_id_in_response(self):
        result = CustomerOrderProcessor.create_order(
            bot=self.bot, sender_id=self.enc,
            persona_type="fnb",
            order_payload={"item": "Tea", "qty": 3, "price": 50},
        )
        assert result["sender_id"] != "order_user1"
        assert Utility.decrypt_message(result["sender_id"]) == "order_user1"


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
        )

    def test_get_order_success(self):
        result = CustomerOrderProcessor.get_order(bot=self.bot, order_id=self.order["_id"])
        assert result["order_details"]["item"] == "Pasta"
        assert result["status"] == "placed"

    def test_get_order_not_found(self):
        from bson import ObjectId
        fake_id = str(ObjectId())
        with pytest.raises(AppException, match="Order not found"):
            CustomerOrderProcessor.get_order(bot=self.bot, order_id=fake_id)

    def test_get_order_wrong_bot(self):
        with pytest.raises(AppException, match="Order not found"):
            CustomerOrderProcessor.get_order(bot="wrong_bot", order_id=self.order["_id"])


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
        )

    def test_update_status_placed_to_confirmed(self):
        result = CustomerOrderProcessor.update_order_status(
            bot=self.bot, order_id=self.order["_id"], new_status="confirmed",
        )
        assert result["status"] == "confirmed"

    def test_update_status_invalid_transition(self):
        with pytest.raises(AppException, match="Invalid transition"):
            CustomerOrderProcessor.update_order_status(
                bot=self.bot, order_id=self.order["_id"], new_status="completed",
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
        )
        CustomerOrderProcessor.update_order_status(bot=bot, order_id=order["_id"], new_status="confirmed")
        CustomerOrderProcessor.update_order_status(bot=bot, order_id=order["_id"], new_status="in_progress")
        CustomerOrderProcessor.update_order_status(bot=bot, order_id=order["_id"], new_status="completed")
        with pytest.raises(AppException, match="Invalid transition"):
            CustomerOrderProcessor.update_order_status(bot=bot, order_id=order["_id"], new_status="cancelled")

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
        )
        result = CustomerOrderProcessor.update_order_status(
            bot=bot, order_id=order["_id"], new_status="cancelled",
        )
        assert result["status"] == "cancelled"


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
