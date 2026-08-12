from datetime import datetime
from typing import Text, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from mongoengine import DoesNotExist
from mongoengine.errors import NotUniqueError, ValidationError

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
    def _decrypt(sender_id: str) -> str:
        try:
            return Utility.decrypt_message(sender_id)
        except Exception as e:
            raise AppException(f"Invalid identifier: {e}")

    @staticmethod
    def _encrypt(plain_id: str) -> str:
        return Utility.encrypt_message(plain_id)

    @staticmethod
    def _mask_sender_id(doc: dict) -> dict:
        if doc.get("sender_id"):
            doc["sender_id"] = CustomerOrderProcessor._encrypt(doc["sender_id"])
        return doc


    @staticmethod
    def upsert_customer(bot: Text, sender_id: str, persona_type: Optional[str], payload: Dict) -> Dict:
        plain_id = CustomerOrderProcessor._decrypt(sender_id)
        payload.pop("sender_id", None)
        payload.pop("bot", None)
        payload.pop("customer_id", None)

        address_list_raw = payload.pop("address_list", [])

        try:
            customer = CustomerDetails.objects(bot=bot, sender_id=plain_id).get()
            for k, v in payload.items():
                setattr(customer, k, v)
            customer.persona_type = persona_type
        except DoesNotExist:
            customer = CustomerDetails(
                bot=bot,
                sender_id=plain_id,
                persona_type=persona_type,
                **{k: v for k, v in payload.items() if k not in ("bot", "sender_id")},
            )

        customer.address_list = [Address(**a) for a in address_list_raw]

        try:
            customer.save()
        except NotUniqueError:
            raise AppException("Customer with this identifier already exists for this bot")
        except ValidationError as e:
            raise AppException(str(e))

        result = customer.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_sender_id(result)

    @staticmethod
    def get_customer(bot: Text, sender_id: str) -> Dict:
        plain_id = CustomerOrderProcessor._decrypt(sender_id)
        try:
            customer = CustomerDetails.objects(bot=bot, sender_id=plain_id, status=True).get()
        except DoesNotExist:
            raise AppException("Customer not found")
        result = customer.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_sender_id(result)

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
            results.append(CustomerOrderProcessor._mask_sender_id(doc))
        return results

    @staticmethod
    def update_address(bot: Text, sender_id: str, address_payload: Dict) -> Dict:
        plain_id = CustomerOrderProcessor._decrypt(sender_id)
        try:
            customer = CustomerDetails.objects(bot=bot, sender_id=plain_id, status=True).get()
        except DoesNotExist:
            raise AppException("Customer not found")

        label = address_payload.get("label")
        existing = [a for a in customer.address_list if a.label != label]
        existing.append(Address(**address_payload))
        customer.address_list = existing
        customer.save()

        result = customer.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_sender_id(result)

    @staticmethod
    def delete_customer(bot: Text, sender_id: str) -> None:
        plain_id = CustomerOrderProcessor._decrypt(sender_id)
        updated = CustomerDetails.objects(bot=bot, sender_id=plain_id).update_one(
            set__status=False, set__updated_at=datetime.utcnow()
        )
        if not updated:
            raise AppException("Customer not found")


    @staticmethod
    def create_order(bot: Text, sender_id: str, persona_type: Optional[str], order_payload: Dict) -> Dict:
        plain_id = CustomerOrderProcessor._decrypt(sender_id)
        try:
            customer = CustomerDetails.objects(bot=bot, sender_id=plain_id, status=True).get()
        except DoesNotExist:
            raise AppException("Customer not found — cannot create orphan order")

        order = OrderDetails(
            bot=bot,
            persona_type=persona_type,
            customer_id=str(customer.id),
            sender_id=plain_id,
            order_details=order_payload,
        )
        try:
            order.save()
        except ValidationError as e:
            raise AppException(str(e))

        result = order.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_sender_id(result)

    @staticmethod
    def update_order_status(bot: Text, order_id: str, new_status: str) -> Dict:
        try:
            order = OrderDetails.objects(bot=bot, id=ObjectId(order_id)).get()
        except (DoesNotExist, InvalidId):
            raise AppException("Order not found")

        allowed = ORDER_STATUS_TRANSITIONS.get(order.status, [])
        if new_status not in allowed:
            raise AppException(
                f"Invalid transition: {order.status} → {new_status}. Allowed: {allowed}"
            )
        order.status = new_status
        try:
            order.save()
        except ValidationError as e:
            raise AppException(str(e))

        result = order.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_sender_id(result)

    @staticmethod
    def list_orders_for_customer(bot: Text, sender_id: str,
                                  page: int = 1, page_size: int = 20) -> List[Dict]:
        plain_id = CustomerOrderProcessor._decrypt(sender_id)
        skip = (page - 1) * page_size
        orders = (
            OrderDetails.objects(bot=bot, sender_id=plain_id)
            .order_by("-created_at")
            .skip(skip)
            .limit(page_size)
        )
        results = []
        for o in orders:
            doc = o.to_mongo().to_dict()
            doc["_id"] = str(doc["_id"])
            results.append(CustomerOrderProcessor._mask_sender_id(doc))
        return results

    @staticmethod
    def filter_orders(bot: Text, persona_type: Optional[str], filters: Dict,
                       page: int = 1, page_size: int = 20) -> List[Dict]:
        query = {"bot": bot}
        if persona_type:
            query["persona_type"] = persona_type
        for k, v in filters.items():
            if not isinstance(v, (str, int, float, bool)):
                raise AppException(f"Unsupported filter value for '{k}'; scalar values only")
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
            results.append(CustomerOrderProcessor._mask_sender_id(doc))
        return results

    @staticmethod
    def get_order(bot: Text, order_id: str) -> Dict:
        try:
            order = OrderDetails.objects(bot=bot, id=ObjectId(order_id)).get()
        except (DoesNotExist, InvalidId):
            raise AppException("Order not found")
        result = order.to_mongo().to_dict()
        result["_id"] = str(result["_id"])
        return CustomerOrderProcessor._mask_sender_id(result)
