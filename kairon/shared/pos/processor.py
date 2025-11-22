import requests
import time
from datetime import datetime

from fastapi import HTTPException
from typing import Any, Dict, List, Optional

from kairon.exceptions import AppException
from kairon.shared.data.constant import RE_ALPHA_NUM
from kairon.shared.pos.data_objects import OdooClientDetails
from kairon.shared.utils import Utility


BASE_URL = Utility.environment["pos"]["odoo_url"]


class OdooProcessor:

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

    def odoo_login(self, db_name: str, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate against Odoo and return {'uid','session_id','result'}.
        Uses /web/session/authenticate JSON endpoint.
        """
        url = f"{BASE_URL}/web/session/authenticate"
        payload = {
            "jsonrpc": "2.0",
            "params": {"db": db_name, "login": username, "password": password}
        }

        resp = requests.post(url, json=payload)
        data = self._raise_if_error(resp, "Login")

        result = data.get("result")
        if not result or result.get("uid") is None:
            raise HTTPException(status_code=401, detail="Invalid Odoo credentials")

        session_id = resp.cookies.get("session_id")
        if not session_id:
            raise HTTPException(status_code=401, detail="Login succeeded but session cookie missing")

        return {"uid": result.get("uid"), "session_id": session_id, "result": result}

    def get_session_info(self, session_id: str):
        url = f"{BASE_URL}/web/session/get_session_info"
        print(url)
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {}
        }

        headers = {
            "Content-Type": "application/json",
            "Cookie": f"session_id={session_id}"
        }
        try:
            resp = requests.post(url, json=payload, headers=headers)
            data = resp.json()

            if "error" in data:
                raise HTTPException(400, f"Odoo Error: {data['error']}")

            return data["result"]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching POS session info: {e}")

    @staticmethod
    def save_client_details(
            client_name: str,
            username: str,
            password: str,
            bot: str,
            user: str,
            company: str = None,
    ):
        """
        Save Odoo Client Configuration Details.

        :param client_name: Name of the client (unique)
        :param username: Odoo admin username
        :param password: Odoo admin password
        :param bot: Bot ID
        :param user: User who is saving
        :param company: Optional company name
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
            OdooClientDetails,
            exp_message="Client name already exists.",
            client_name__iexact=client_name.strip(),
            check_base_fields=False,
        )

        record = (
            OdooClientDetails(
                client_name=client_name.strip(),
                username=username.strip(),
                password=Utility.encrypt_message(password.strip()),
                company=company.strip() if company else None,
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
        Get Odoo client details for the current bot & user.
        Decrypt the stored password before returning.
        """

        record = OdooClientDetails.objects(bot=bot).first()

        if not record:
            raise AppException("No Odoo client configuration found for this bot.")

        data = record.to_mongo().to_dict()

        data["password"] = Utility.decrypt_message(data["password"])

        data["_id"] = str(data["_id"])

        return data

    def create_database(
            self, db_name: str, bot: str, user: str, company: str = None,
            admin_username: str = "admin", admin_password: str = "admin",
            demo: bool = False, lang: str = "en_US"
    ):

        OdooProcessor.save_client_details(
            client_name=db_name,
            username=admin_username,
            password=admin_password,
            bot=bot,
            user=user,
            company=company,
        )

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
        if db_name in dbs:
            return {"success": False, "message": f"Client {db_name} already exists"}

        create_payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "db",
                "method": "create_database",
                "args": [
                    admin_password,
                    db_name,
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
            return {"success": False, "message": resp["error"]["data"]["message"]}

        return {"success": True, "message": f"Client '{db_name}' created."}

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

    def get_pos_users(self, session_id: str):
        """
        Return all users along with their POS role (user/manager/none).
        """

        try:
            pos_user_group = self.get_group_id(session_id, "point_of_sale.group_pos_user")
            pos_manager_group = self.get_group_id(session_id, "point_of_sale.group_pos_manager")

            users = self.jsonrpc_call(
                session_id,
                "res.users",
                "search_read",
                args=[[]],
                kwargs={
                    "fields": [
                        "id", "name", "login", "active",
                        "groups_id", "partner_id"
                    ]
                }
            )

            for user in users:
                group_ids = user.pop("groups_id", [])
                user.pop("partner_id", [])

                if pos_manager_group in group_ids:
                    user["pos_role"] = "manager"
                elif pos_user_group in group_ids:
                    user["pos_role"] = "user"
                else:
                    user["pos_role"] = "none"

            return users

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching users: {e}")

    def get_group_id(self, session_id: str, xml_id: str) -> int:
        module, name = xml_id.split(".")

        data = self.jsonrpc_call(
            session_id=session_id,
            model="ir.model.data",
            method="search_read",
            args=[[["module", "=", module], ["name", "=", name]]],
            kwargs={"fields": ["res_id"], "limit": 1}
        )

        if not data:
            raise AppException(f"Group XML-ID '{xml_id}' not found")

        return data[0]["res_id"]

    def create_user(
            self,
            session_id: str,
            login: str,
            password: str,
            name: str,
            partner_id: int = None,
            pos_role: str = "user"  # user / manager
    ):
        """
        Create Odoo user with POS access using JSON-RPC session_id.
        pos_role = "user" or "manager"
        """

        existing_users = self.jsonrpc_call(
            session_id=session_id,
            model="res.users",
            method="search_read",
            args=[[["login", "=", login]]],
            kwargs={"fields": ["id"], "limit": 1}
        )

        if existing_users:
            return {
                "message": f"User {login} already exists",
                "user_id": existing_users[0]["id"]
            }

        if not partner_id:
            partner_id = self.jsonrpc_call(
                session_id=session_id,
                model="res.partner",
                method="create",
                args=[{"name": name}]
            )

        base_internal_user = self.get_group_id(session_id, "base.group_user")

        if pos_role == "manager":
            pos_group = self.get_group_id(session_id, "point_of_sale.group_pos_manager")
        else:
            pos_group = self.get_group_id(session_id, "point_of_sale.group_pos_user")

        groups = [base_internal_user, pos_group]

        user_vals = {
            "name": name,
            "login": login,
            "partner_id": partner_id,
            "groups_id": [(6, 0, groups)]
        }

        user_id = self.jsonrpc_call(
            session_id=session_id,
            model="res.users",
            method="create",
            args=[user_vals]
        )

        self.jsonrpc_call(
            session_id=session_id,
            model="res.users",
            method="write",
            args=[[user_id], {"password": password}]
        )

        return {
            "message": f"User created with login {login} and POS {pos_role} access",
            "user_id": user_id
        }

    def delete_user(self, session_id: str, user_id: int):
        """
        Delete user via JSON-RPC using existing session_id.
        """

        user = self.jsonrpc_call(
            session_id=session_id,
            model="res.users",
            method="search_read",
            args=[[["id", "=", user_id]]],
            kwargs={"fields": ["id"], "limit": 1}
        )

        if not user:
            raise HTTPException(status_code=404, detail=f"User not found with user_id: {user_id}")

        try:
            self.jsonrpc_call(
                session_id=session_id,
                model="res.users",
                method="unlink",
                args=[[user_id]]
            )

            return {"message": "User deleted", "user_id": user_id}

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Unable to delete user: {e}")

    def update_user_role(self, session_id: str, user_id: int, pos_role: str):
        """
        Update only the POS role of the user.
        """

        if pos_role not in ["user", "manager"]:
            raise HTTPException(status_code=400, detail="Invalid role. Use 'user' or 'manager'.")

        user = self.jsonrpc_call(
            session_id=session_id,
            model="res.users",
            method="search_read",
            args=[[["id", "=", user_id]]],
            kwargs={"fields": ["id"], "limit": 1}
        )

        if not user:
            raise HTTPException(status_code=404, detail=f"User not found with user_id: {user_id}")

        base_internal_user = self.get_group_id(session_id, "base.group_user")

        if pos_role == "manager":
            pos_group = self.get_group_id(session_id, "point_of_sale.group_pos_manager")
        else:
            pos_group = self.get_group_id(session_id, "point_of_sale.group_pos_user")

        self.jsonrpc_call(
            session_id=session_id,
            model="res.users",
            method="write",
            args=[[user_id], {"groups_id": [(6, 0, [base_internal_user, pos_group])]}]
        )

        return {
            "message": f"POS role updated to {pos_role}",
            "user_id": user_id
        }

    def uninstall_module_with_session(self, session_id: str, module_name: str) -> Dict[str, Any]:
        """
        Uninstall a module by name using session_id:
          1) Search module by name in ir.module.module
          2) Check if installed
          3) Call button_immediate_uninstall
        """
        try:
            module_ids = self.jsonrpc_call(
                session_id,
                "ir.module.module",
                "search",
                args=[[["name", "=", module_name]]]
            )

            if not module_ids:
                return {"success": False, "message": f"Module {module_name} not found"}

            module_data = self.jsonrpc_call(
                session_id,
                "ir.module.module",
                "read",
                args=[module_ids, ["state"]]
            )

            state = module_data[0].get("state")

            if state != "installed":
                return {"success": False,
                        "message": f"Module '{module_name}' is not installed (current state: {state})"}

            res = self.jsonrpc_call(
                session_id,
                "ir.module.module",
                "button_immediate_uninstall",
                args=[module_ids]
            )

            return {"success": True, "message": f"Module '{module_name}' uninstalled successfully",
                    "odoo_response": res}

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error uninstalling module: {e}")

    def install_module(self, session_id: str, module_name: str):
        try:
            module_ids = self.jsonrpc_call(
                session_id,
                "ir.module.module",
                "search",
                args=[[["name", "=", module_name]]]
            )

            if not module_ids:
                return False, f"Module '{module_name}' not found."

            module = self.jsonrpc_call(
                session_id,
                "ir.module.module",
                "read",
                args=[module_ids, ["state"]]
            )[0]

            state = module.get("state")

            if state in ("installed", "to upgrade"):
                return True, f"Module '{module_name}' is already installed."

            if state in ("to install", "uninstalled"):
                self.jsonrpc_call(
                    session_id,
                    "ir.module.module",
                    "button_immediate_install",
                    args=[module_ids]
                )
                return True, f"Module '{module_name}' installed successfully."

            return False, f"Unknown module state: {state}"

        except Exception as e:
            return False, f"Error installing module '{module_name}': {e}"

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



