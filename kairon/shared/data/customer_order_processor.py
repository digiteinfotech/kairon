from datetime import datetime
from typing import Text, Dict, List, Optional, Any

import requests as http_requests
from bson import ObjectId
from bson.errors import InvalidId
from loguru import logger
from mongoengine import DoesNotExist
from mongoengine.errors import NotUniqueError, ValidationError

from kairon.exceptions import AppException
from kairon.shared.data.data_objects import (
    CustomerDetails,
    OrderDetails,
    Address,
    ORDER_STATUS_TRANSITIONS,
    StorePageMetadata,
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
    def _resolve_credential(param: dict, bot: str) -> str:
        from kairon.shared.actions.models import ActionParameterType
        from kairon.shared.actions.utils import ActionUtility
        parameter_type = param.get("parameter_type", ActionParameterType.value.value)
        value = param.get("value", "")
        if parameter_type == ActionParameterType.key_vault.value:
            return ActionUtility.get_secret_from_key_vault(value, bot) or ""
        if param.get("encrypt") and value:
            return Utility.decrypt_message(value)
        return value

    @staticmethod
    def register_customer_if_new(bot: str, plain_sender_id: str) -> None:
        try:
            if not CustomerDetails.objects(bot=bot, sender_id=plain_sender_id).first():
                CustomerDetails(bot=bot, sender_id=plain_sender_id).save()
        except NotUniqueError:
            pass
        except Exception as e:
            logger.warning(f"Failed to auto-register customer for bot {bot}: {e}")

    @staticmethod
    def _generate_store_page_url(bot: str, plain_sender_id: str, page_name: str) -> str:
        from kairon.shared.auth import Authentication
        catalog_base = Utility.environment.get("store_page").get("url")
        encrypted_id = Utility.encrypt_message(plain_sender_id)
        token = Authentication.create_store_page_token(
            data={"sub": plain_sender_id, "bot": bot},
            access_limit=[
                "/api/bot/.+/customer_data/.*",
                "/api/bot/.+/store_page/metadata",
                "/api/bot/.+/data/collection/.*",
            ],
        )
        return f"{catalog_base}/{page_name}/{bot}/{encrypted_id}/{token}"

    @staticmethod
    def _create_razorpay_payment_link(api_key: str, api_secret: str, order_id: str,
                                      order_details: dict, callback_url: str, callback_identifier: str) -> Dict[str, Any]:
        amount = order_details.get("amount", 0)
        currency = order_details.get("currency", "INR")
        payload = {
            "amount": int(float(amount) * 100),
            "currency": currency,
            "customer": {
                "name": order_details.get("name", ""),
                "contact": order_details.get("contact", ""),
                "email": order_details.get("email", ""),
            },
            "callback_url": callback_url,
            "callback_method": "get",
            "reference_id": order_id,
            "notify": {"sms": True, "email": True},
            "notes": {
                "kairon_id": callback_identifier,
                "kairon_order_id": order_id
            },
        }
        resp = http_requests.post(
            "https://api.razorpay.com/v1/payment_links",
            json=payload,
            auth=(api_key, api_secret),
            timeout=30,
        )
        if not resp.ok:
            raise AppException(f"Razorpay API error {resp.status_code}: {resp.text}")
        return resp.json()

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
    def create_order(bot: Text, sender_id: str, persona_type: Optional[str], order_payload: Dict, callback_identifier: str) -> Dict:
        plain_id = CustomerOrderProcessor._decrypt(sender_id)
        try:
            customer = CustomerDetails.objects(bot=bot, sender_id=plain_id, status=True).get()
        except DoesNotExist:
            raise AppException("Customer not found")

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

        order_id = str(order.id)
        payment_id = None
        payment_link = None

        try:
            metadata = StorePageMetadata.objects(bot=bot).get()
            store_config = metadata.config or {}
        except DoesNotExist:
            store_config = {}

        if store_config.get("payment_enabled"):
            from kairon.shared.actions.data_objects import StorePageAction, RazorpayAction
            try:
                store_page = StorePageAction.objects(bot=bot, status=True).get()
                page_name = store_page.page_name
            except DoesNotExist:
                page_name = "catalog"
            try:
                action = RazorpayAction.objects(bot=bot, status=True).get()
            except DoesNotExist:
                raise AppException("Razorpay action not configured")

            action_dict = action.to_mongo().to_dict()
            api_key = CustomerOrderProcessor._resolve_credential(action_dict.get("api_key", {}), bot)
            api_secret = CustomerOrderProcessor._resolve_credential(action_dict.get("api_secret", {}), bot)

            callback_url = CustomerOrderProcessor._generate_store_page_url(bot, plain_id, page_name)

            try:
                razorpay_resp = CustomerOrderProcessor._create_razorpay_payment_link(
                    api_key, api_secret, order_id, order_payload, callback_url, callback_identifier
                )
                payment_id = razorpay_resp.get("id", "")
                payment_link = razorpay_resp.get("short_url", "")
                OrderDetails.objects(id=order.id).update_one(
                    set__additional_info={"payment_id": payment_id, "payment_link": payment_link}
                )
            except AppException:
                raise
            except Exception as e:
                logger.warning(f"Razorpay payment link creation failed for order {order_id}: {e}")

        return {"order_id": order_id, "payment_id": payment_id, "payment_link": payment_link}

    @staticmethod
    def update_order(bot: Text, order_id: str, payload: Dict) -> Dict:
        try:
            order = OrderDetails.objects(bot=bot, id=ObjectId(order_id)).get()
        except (DoesNotExist, InvalidId):
            raise AppException("Order not found")

        if "order_details" in payload:
            order.order_details = payload["order_details"]
        if "additional_info" in payload:
            existing = order.additional_info or {}
            existing.update(payload["additional_info"])
            order.additional_info = existing

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
