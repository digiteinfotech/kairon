from datetime import datetime
from typing import Text, Dict, List, Optional

from bson import ObjectId
from mongoengine import DoesNotExist
from mongoengine.errors import NotUniqueError

from kairon.exceptions import AppException
from kairon.shared.data.data_objects import (
    CustomerDetails,
    OrderDetails,
    Address,
    ORDER_STATUS_TRANSITIONS,
)
from kairon.shared.utils import Utility


class CustomerOrderProcessor:

    @staticmethod
    def _decrypt(encrypted_id: str) -> str:
        try:
            return Utility.decrypt_message(encrypted_id)
        except Exception as e:
            raise AppException(f"Invalid identifier: {e}")

    @staticmethod
    def _encrypt(plain_id: str) -> str:
        return Utility.encrypt_message(plain_id)

    @staticmethod
    def _mask_user_id(doc: dict) -> dict:
        if doc.get("user_id"):
            doc["user_id"] = CustomerOrderProcessor._encrypt(doc["user_id"])
        return doc

    # ------------------------------------------------------------------ #
    # customer_details                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def upsert_customer(bot: Text, user: Text, encrypted_id: str, persona_type: str, payload: Dict) -> Dict:
        plain_id = CustomerOrderProcessor._decrypt(encrypted_id)
        payload.pop("user_id", None)
        payload.pop("bot", None)
        payload.pop("customer_id", None)

        address_list_raw = payload.pop("address_list", [])

        try:
            customer = CustomerDetails.objects(bot=bot, user_id=plain_id).get()
            for k, v in payload.items():
                setattr(customer, k, v)
            customer.persona_type = persona_type
            customer.user = user
        except DoesNotExist:
            customer = CustomerDetails(
                bot=bot,
                user_id=plain_id,
                persona_type=persona_type,
                user=user,
                **{k: v for k, v in payload.items() if k not in ("user", "bot", "user_id")},
            )


        customer.address_list = [Address(**a) for a in address_list_raw]

        try:
            customer.save()
        except NotUniqueError:
            raise AppException("Customer with this identifier already exists for another bot")

        result = customer.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_user_id(result)

    @staticmethod
    def get_customer(bot: Text, encrypted_id: str) -> Dict:
        plain_id = CustomerOrderProcessor._decrypt(encrypted_id)
        try:
            customer = CustomerDetails.objects(bot=bot, user_id=plain_id, status=True).get()
        except DoesNotExist:
            raise AppException("Customer not found")
        result = customer.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_user_id(result)

    @staticmethod
    def list_customers(bot: Text, persona_type: Optional[str] = None,
                       page: int = 1, page_size: int = 20) -> List[Dict]:
        filters = {"bot": bot, "status": True}
        if persona_type:
            filters["persona_type"] = persona_type
        skip = (page - 1) * page_size
        customers = CustomerDetails.objects(**filters).skip(skip).limit(page_size)
        results = []
        for c in customers:
            doc = c.to_mongo().to_dict()
            doc["_id"] = str(doc["_id"])
            results.append(CustomerOrderProcessor._mask_user_id(doc))
        return results

    @staticmethod
    def update_address(bot: Text, encrypted_id: str, address_payload: Dict) -> Dict:
        plain_id = CustomerOrderProcessor._decrypt(encrypted_id)
        try:
            customer = CustomerDetails.objects(bot=bot, user_id=plain_id, status=True).get()
        except DoesNotExist:
            raise AppException("Customer not found")

        label = address_payload.get("label")
        existing = [a for a in customer.address_list if a.label != label]
        existing.append(Address(**address_payload))
        customer.address_list = existing
        customer.save()

        result = customer.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_user_id(result)

    @staticmethod
    def delete_customer(bot: Text, encrypted_id: str) -> None:
        plain_id = CustomerOrderProcessor._decrypt(encrypted_id)
        updated = CustomerDetails.objects(bot=bot, user_id=plain_id).update_one(
            set__status=False, set__updated_at=datetime.utcnow()
        )
        if not updated:
            raise AppException("Customer not found")

    # ------------------------------------------------------------------ #
    # order_details                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_order(bot: Text, user: Text, encrypted_id: str, persona_type: str, order_payload: Dict) -> Dict:
        plain_id = CustomerOrderProcessor._decrypt(encrypted_id)
        try:
            customer = CustomerDetails.objects(bot=bot, user_id=plain_id, status=True).get()
        except DoesNotExist:
            raise AppException("Customer not found — cannot create orphan order")

        order = OrderDetails(
            bot=bot,
            persona_type=persona_type,
            customer_id=str(customer.id),
            user_id=plain_id,
            user=user,
            order_details=order_payload,
        )
        order.save()

        result = order.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_user_id(result)

    @staticmethod
    def update_order_status(bot: Text, order_id: str, new_status: str) -> Dict:
        try:
            order = OrderDetails.objects(bot=bot, id=ObjectId(order_id)).get()
        except (DoesNotExist, Exception):
            raise AppException("Order not found")

        allowed = ORDER_STATUS_TRANSITIONS.get(order.status, [])
        if new_status not in allowed:
            raise AppException(
                f"Invalid transition: {order.status} → {new_status}. Allowed: {allowed}"
            )
        order.status = new_status
        order.save()

        result = order.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_user_id(result)

    @staticmethod
    def list_orders_for_customer(bot: Text, encrypted_id: str,
                                  page: int = 1, page_size: int = 20) -> List[Dict]:
        plain_id = CustomerOrderProcessor._decrypt(encrypted_id)
        skip = (page - 1) * page_size
        orders = (
            OrderDetails.objects(bot=bot, user_id=plain_id)
            .order_by("-created_at")
            .skip(skip)
            .limit(page_size)
        )
        results = []
        for o in orders:
            doc = o.to_mongo().to_dict()
            doc["_id"] = str(doc["_id"])
            results.append(CustomerOrderProcessor._mask_user_id(doc))
        return results

    @staticmethod
    def filter_orders(bot: Text, persona_type: str, filters: Dict,
                       page: int = 1, page_size: int = 20) -> List[Dict]:
        query = {"bot": bot, "persona_type": persona_type}
        and_conditions = [
            {"filterable_attrs": {"$elemMatch": {"k": k, "v": v}}}
            for k, v in filters.items()
        ]
        if and_conditions:
            query["$and"] = and_conditions

        skip = (page - 1) * page_size
        orders = OrderDetails.objects(__raw__=query).order_by("-created_at").skip(skip).limit(page_size)
        results = []
        for o in orders:
            doc = o.to_mongo().to_dict()
            doc["_id"] = str(doc["_id"])
            results.append(CustomerOrderProcessor._mask_user_id(doc))
        return results

    @staticmethod
    def get_order(bot: Text, order_id: str) -> Dict:
        try:
            order = OrderDetails.objects(bot=bot, id=ObjectId(order_id)).get()
        except (DoesNotExist, Exception):
            raise AppException("Order not found")
        result = order.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_user_id(result)
