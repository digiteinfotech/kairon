import requests
import time
from datetime import datetime

from fastapi import HTTPException
from typing import Any, Dict, List, Optional
from loguru import logger

from kairon.exceptions import AppException
from kairon.shared.data.constant import RE_ALPHA_NUM
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.pos.constants import POSType, PageType, OnboardingStatus
from kairon.shared.pos.data_objects import POSClientDetails
from kairon.shared.utils import Utility


BASE_URL = Utility.environment["pos"]["odoo"]["odoo_url"]
MASTER_PASSWORD = Utility.environment["pos"]["odoo"]["odoo_master_password"]


class POSProcessor:

    def _raise_if_error(self, resp: requests.Response, context: str = "Odoo request"):
        """Raise HTTPException if non-200 or invalid JSON-RPC response."""
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"{context}: HTTP {resp.status_code} - {resp.text}")

        try:
            data = resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{context}: invalid JSON response: {e}")

        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise HTTPException(status_code=400, detail=f"{context} - {msg}")

        return data

    def pos_login(self, client_name: str, bot: str) -> Dict[str, Any]:
        """
        Authenticate against Odoo and return {'uid','session_id','result'}.
        Uses /web/session/authenticate JSON endpoint.
        """
        if not MongoProcessor.is_pos_enabled(bot):
            raise AppException("point of sale is not enabled")

        client_details = POSProcessor.get_client_details(bot)
        username = client_details.get("username")
        password = client_details.get("password")
        url = f"{BASE_URL}/web/session/authenticate"
        payload = {
            "jsonrpc": "2.0",
            "params": {"db": client_name, "login": username, "password": password}
        }

        resp = requests.post(url, json=payload)
        data = self._raise_if_error(resp, "Login")

        result = data.get("result")
        if not result or result.get("uid") is None:
            raise HTTPException(status_code=401, detail="Invalid Odoo credentials")

        session_id = resp.cookies.get("session_id")
        if not session_id:
            raise HTTPException(status_code=401, detail="Login succeeded but session cookie missing")

        return {"uid": result.get("uid"), "session_id": session_id}

    @staticmethod
    def save_client_details(
            client_name: str,
            username: str,
            password: str,
            bot: str,
            user: str,
            pos_type: POSType = POSType.odoo.value
    ):
        """
        Save Odoo Client Configuration Details.

        :param client_name: Name of the client (unique)
        :param username: Odoo admin username
        :param password: Odoo admin password
        :param bot: Bot ID
        :param user: User who is saving
        :param pos_type: POS Type
        :return: Saved client details as dict
        """

        if (
                Utility.check_empty_string(client_name)
                or Utility.check_empty_string(username)
                or Utility.check_empty_string(password)
                or Utility.check_empty_string(bot)
                or Utility.check_empty_string(user)
        ):
            raise AppException("Client Name, Username, Password, Bot and User cannot be empty.")

        if not Utility.special_match(client_name, search=RE_ALPHA_NUM):
            raise AppException("Client name can only contain letters, numbers, spaces and underscores.")

        Utility.is_exist(
            POSClientDetails,
            exp_message="Client name already exists.",
            client_name__iexact=client_name.strip(),
            check_base_fields=False,
        )
        client_details = {
            "username": username.strip(),
            "password": Utility.encrypt_message(password.strip()),
        }

        record = (
            POSClientDetails(
                pos_type=pos_type,
                client_name=client_name.strip(),
                config=client_details,
                bot=bot.strip(),
                user=user.strip(),
            )
            .save()
            .to_mongo()
            .to_dict()
        )
        return record

    @staticmethod
    def get_client_details(bot: str):
        """
        Get Odoo client details for the current bot.
        Decrypt the stored password before returning.
        """

        record = POSClientDetails.objects(bot=bot, pos_type=POSType.odoo.value).first()

        if not record:
            raise AppException("No POS client configuration found for this bot.")

        data = record.to_mongo().to_dict()

        config = data.get("config", {})

        if "password" in config:
            config["password"] = Utility.decrypt_message(config["password"])

        config["client_name"] = data["client_name"]

        return config

    def onboarding_client(
            self, client_name: str, bot: str, user: str, pos_type: POSType = POSType.odoo.value,
            admin_password: str = MASTER_PASSWORD, admin_username: str = "admin",
            demo: bool = False, lang: str = "en_US"
    ):

        if not MongoProcessor.is_pos_enabled(bot):
            raise AppException("point of sale is not enabled")

        url = f"{BASE_URL}/jsonrpc"

        list_payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "db",
                "method": "list",
                "args": []
            },
            "id": 1
        }

        dbs = requests.post(url, json=list_payload).json().get("result", [])
        if client_name in dbs:
            return {"success": False, "message": f"Client {client_name} already exists"}

        POSProcessor.save_client_details(
            client_name=client_name,
            pos_type=pos_type,
            username=admin_username,
            password=admin_password,
            bot=bot,
            user=user,
        )

        create_payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "db",
                "method": "create_database",
                "args": [
                    admin_password,
                    client_name,
                    demo,
                    lang,
                    admin_password,
                    admin_username
                ],
            },
            "id": 2
        }

        resp = requests.post(url, json=create_payload).json()

        if "error" in resp:
            raise HTTPException(400, detail=resp["error"]["data"]["message"])

        logger.info(f"Client '{client_name}' created.")

        POSProcessor.update_onboarding_status(bot, client_name, OnboardingStatus.client_db_created)

        data = self.pos_login(client_name=client_name, bot=bot)

        session_id = data.get("session_id")

        logger.info(f"User logged in, Session id: {session_id}")

        self.activate_module(session_id, "point_of_sale")

        logger.info("point_of_sale Activated")

        POSProcessor.update_onboarding_status(bot, client_name, OnboardingStatus.completed)

        return {"message": f"Client '{client_name}' created and POS Activated"}

    @staticmethod
    def update_onboarding_status(bot: str, client_name: str, status: OnboardingStatus):
        record = POSClientDetails.objects(bot=bot, client_name=client_name).first()
        if not record:
            raise AppException("POS Client not found")

        record.onboarding_status = status.value
        record.save()

    @staticmethod
    def delete_client_details(client_name: str):
        """
        Delete stored Odoo Client Configuration Details.

        :param client_name: Name of the client (unique)
        :return: success or error message
        """

        if Utility.check_empty_string(client_name):
            raise AppException("Client name cannot be empty.")

        record = POSClientDetails.objects(client_name__iexact=client_name.strip()).first()

        if not record:
            raise HTTPException(400, detail=f"Client '{client_name}' not found in stored details.")

        record.delete()
        return {"success": True, "message": f"Client '{client_name}' details removed successfully."}

    def drop_client(self, client_name: str, admin_password: str = MASTER_PASSWORD):
        url = f"{BASE_URL}/jsonrpc"

        list_payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "db",
                "method": "list",
                "args": []
            },
            "id": 1
        }
        dbs = requests.post(url, json=list_payload).json().get("result", [])
        if client_name not in dbs:
            raise HTTPException(400, detail=f"Client '{client_name}' not found")

        drop_payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "db",
                "method": "drop",
                "args": [
                    admin_password,
                    client_name
                ],
            },
            "id": 2
        }

        resp = requests.post(url, json=drop_payload).json()

        if "error" in resp:
            raise HTTPException(400, detail=resp["error"]["data"]["message"])

        self.delete_client_details(client_name)

        return {"message": f"Client '{client_name}' deleted successfully"}

    def jsonrpc_call(self, session_id: str, model: str, method: str, args: Optional[list] = None, kwargs: Optional[dict] = None) -> Any:
        """
        Generic JSON-RPC call to /web/dataset/call_kw
        Requires a valid session_id cookie (stateless).
        Returns the "result" or raises HTTPException on error.
        """
        url = f"{BASE_URL}/web/dataset/call_kw"
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "model": model,
                "method": method,
                "args": args or [],
                "kwargs": kwargs or {}
            }
        }
        sess = requests.Session()
        sess.cookies.set("session_id", session_id)
        resp = sess.post(url, json=payload)
        data = self._raise_if_error(resp, f"JSON-RPC {model}.{method}")
        return data.get("result")

    def jsonrpc_search_read(self, session_id: str, model: str, domain: List[list], fields: List[str], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Helper: search_read via JSON-RPC using model.search_read semantics."""
        kwargs = {"fields": fields}
        if limit:
            kwargs["limit"] = limit

        return self.jsonrpc_call(session_id, model, "search_read", args=[domain], kwargs=kwargs)

    def get_pos_products(self, session_id: str):
        try:
            domain = [["available_in_pos", "=", True]]

            products = self.jsonrpc_call(
                session_id=session_id,
                model="product.template",
                method="search_read",
                args=[domain],
                kwargs={
                    "fields": [
                        "id", "name", "list_price",
                        "barcode", "available_in_pos"
                    ]
                }
            )
            return products

        except Exception as e:
            raise HTTPException(500, detail=f"Odoo error: {e}")

    def toggle_product_in_pos(self, session_id: str, product_id: int) -> Dict[str, Any]:
        """
        Toggle product.template.available_in_pos boolean using session.
        """
        try:
            product = self.jsonrpc_call(session_id, "product.template", "read", args=[[product_id]], kwargs={"fields": ["id", "name", "available_in_pos"]})
            if not product or len(product) == 0:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
            current = product[0].get("available_in_pos", False)
            new_state = not current

            self.jsonrpc_call(session_id, "product.template", "write", args=[[product_id], {"available_in_pos": new_state}])

            return {"product_id": product_id, "name": product[0]["name"], "available_in_pos": new_state}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error toggling product: {e}")

    def activate_module(self, session_id: str, module_name: str):
        try:
            module_ids = self.jsonrpc_call(
                session_id,
                "ir.module.module",
                "search",
                args=[[["name", "=", module_name]]]
            )

            if not module_ids:
                raise HTTPException(status_code=400, detail=f"Module '{module_name}' not found.")

            module = self.jsonrpc_call(
                session_id,
                "ir.module.module",
                "read",
                args=[module_ids, ["state"]]
            )[0]

            state = module.get("state")

            if state in ("installed", "to upgrade"):
                raise HTTPException(status_code=400, detail=f"Module '{module_name}' is already installed.")

            if state in ("to install", "uninstalled"):
                self.jsonrpc_call(
                    session_id,
                    "ir.module.module",
                    "button_immediate_install",
                    args=[module_ids]
                )
                return True, f"Module '{module_name}' installed successfully."

            raise HTTPException(status_code=400, detail=f"Unknown module state: {state}")

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error installing module '{module_name}': {e}")

    def list_pos_orders(self, session_id: str, status: str | None = None):
        """
        List POS orders with optional status filtering.
        If status=None → return all orders.
        """

        try:
            allowed_states = ["draft", "paid", "done", "invoiced", "cancel"]

            domain = []
            if status:
                if status not in allowed_states:
                    raise HTTPException(status_code=400, detail="Invalid status value")
                domain.append(["state", "=", status])

            order_ids = self.jsonrpc_call(
                session_id,
                "pos.order",
                "search",
                args=[domain]
            )

            if not order_ids:
                return []

            orders = self.jsonrpc_call(
                session_id,
                "pos.order",
                "read",
                args=[order_ids],
                kwargs={
                    "fields": [
                        "name",
                        "date_order",
                        "amount_total",
                        "state",
                        "partner_id",
                        "session_id",
                        "company_id"
                    ]
                }
            )

            return orders

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching POS orders: {e}")

    def jsonrpc_get_uid(self, session_id: str) -> int:
        return self.jsonrpc_call(
            session_id=session_id,
            model="res.users",
            method="search",
            args=[[["id", "!=", 0]]],
            kwargs={"limit": 1}
        )[0]

    def create_pos_order(self, session_id: str, products: list, partner_id: int = None):
        """
        Create POS order using JSON-RPC (create_from_ui)
        with check for available_in_pos for every product.
        """

        if not partner_id:
            partner_id = self.jsonrpc_call(
                session_id=session_id,
                model="res.partner",
                method="create",
                args=[{"name": "POS Customer", "customer_rank": 1}]
            )

        for p in products:
            product_id = p["product_id"]

            product_data = self.jsonrpc_call(
                session_id=session_id,
                model="product.product",
                method="read",
                args=[[product_id]],
                kwargs={"fields": ["available_in_pos", "name"]}
            )

            if not product_data:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

            prod = product_data[0]

            if not prod.get("available_in_pos", False):
                raise HTTPException(
                    status_code=400,
                    detail=f"Product '{prod['name']}' (ID {product_id}) is not available in POS"
                )

        pos_configs = self.jsonrpc_call(
            session_id=session_id,
            model="pos.config",
            method="search_read",
            args=[[["active", "=", True]]],
            kwargs={"limit": 1}
        )

        if not pos_configs:
            raise AppException("No POS Config found")

        config = pos_configs[0]
        config_id = config["id"]
        company_id = config["company_id"][0] if config.get("company_id") else False

        open_session = self.jsonrpc_call(
            session_id=session_id,
            model="pos.session",
            method="search_read",
            args=[
                [
                    ["config_id", "=", config_id],
                    ["state", "in", ["opened", "opening_control"]]
                ]
            ],
            kwargs={"limit": 1}
        )

        if open_session:
            session_id_odoo = open_session[0]["id"]
            sequence_number = open_session[0].get("sequence_number", 1)
        else:
            session_id_odoo = self.jsonrpc_call(
                session_id=session_id,
                model="pos.session",
                method="create",
                args=[{"config_id": config_id}]
            )

            self.jsonrpc_call(
                session_id=session_id,
                model="pos.session",
                method="action_pos_session_open",
                args=[[session_id_odoo]]
            )

            sequence_number = 1

        pay_method = self.jsonrpc_call(
            session_id=session_id,
            model="pos.payment.method",
            method="search_read",
            args=[[["is_cash_count", "=", True]]],
            kwargs={"limit": 1}
        )

        if not pay_method:
            pay_method = self.jsonrpc_call(
                session_id=session_id,
                model="pos.payment.method",
                method="search_read",
                args=[[[]]],
                kwargs={"limit": 1}
            )

        if not pay_method:
            raise HTTPException(status_code=400, detail="No POS payment methods found")

        payment_method_id = pay_method[0]["id"]

        order_lines = []
        total = 0.0

        for p in products:
            subtotal = p["qty"] * p["unit_price"]
            total += subtotal

            order_lines.append([0, 0, {
                "product_id": p["product_id"],
                "qty": p["qty"],
                "price_unit": p["unit_price"],
                "price_subtotal": subtotal,
                "price_subtotal_incl": subtotal
            }])

        order_data = {
            "name": f"POS/{int(time.time())}",
            "sequence_number": sequence_number,
            "session_id": session_id_odoo,
            "pos_session_id": session_id_odoo,
            "config_id": config_id,
            "company_id": company_id,
            "date_order": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            "user_id": self.jsonrpc_get_uid(session_id),
            "fiscal_position_id": False,
            "partner_id": partner_id or False,
            "amount_total": total,
            "amount_paid": total,
            "amount_return": 0.0,
            "amount_tax": 0.0,
            "lines": order_lines,
            "statement_ids": [[0, 0, {
                "amount": total,
                "payment_method_id": payment_method_id,
                "name": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }]],
        }

        payload = [{"data": order_data}]

        order_ids = self.jsonrpc_call(
            session_id=session_id,
            model="pos.order",
            method="create_from_ui",
            args=[payload]
        )

        order_id = order_ids[0] if isinstance(order_ids, list) else order_ids

        return {"order_id": order_id, "status": "created"}

    def accept_pos_order(self, session_id: str, order_id: int) -> Dict[str, Any]:
        """
        Accept a POS order: tries to create payment and invoice it.
        """
        try:
            order = self.jsonrpc_call(session_id, "pos.order", "read", args=[[order_id]], kwargs={"fields": ["amount_total", "partner_id", "state", "session_id"]})
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            order = order[0]
            if order["state"] not in ["draft", "paid"]:
                raise HTTPException(status_code=400, detail=f"Cannot accept order. order already in '{order['state']}' state.")

            methods = self.jsonrpc_call(session_id, "pos.payment.method", "search_read", args=[[["is_cash_count", "=", True]]], kwargs={"limit": 1})
            if not methods:
                raise HTTPException(status_code=404, detail="No POS payment method found")
            payment_method_id = methods[0]["id"]

            payment_data = {"amount": order["amount_total"], "payment_method_id": payment_method_id, "pos_order_id": order_id}
            self.jsonrpc_call(session_id, "pos.payment", "create", args=[payment_data])

            self.jsonrpc_call(session_id, "pos.order", "action_pos_order_paid", args=[[order_id]])

            try:
                self.jsonrpc_call(session_id, "pos.order", "action_pos_order_invoice", args=[[order_id]])
                return {"order_id": order_id, "accepted": True}
            except Exception:
                return {"order_id": order_id, "accepted": True, "invoiced": False}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error accepting POS order: {e}")

    def reject_pos_order(self, session_id: str, order_id: int) -> Dict[str, Any]:
        """
        Cancel a POS order (action_pos_order_cancel).
        """
        try:
            order = self.jsonrpc_call(session_id, "pos.order", "read", args=[[order_id]], kwargs={"fields": ["state"]})
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            order = order[0]
            if order["state"] not in ["draft", "paid"]:
                raise HTTPException(status_code=400, detail=f"Cannot cancel order. order already in '{order['state']}' state.")

            self.jsonrpc_call(session_id, "pos.order", "action_pos_order_cancel", args=[[order_id]])
            return {"order_id": order_id, "status": "cancelled"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error rejecting POS order: {e}")



