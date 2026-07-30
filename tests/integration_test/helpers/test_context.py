import uuid
import datetime
import requests
from typing import Dict, Any


from kairon.shared.utils import Utility
from mongoengine import connect, disconnect

class E2ETestContext:
    def __init__(self, kairon_api_url: str = "http://localhost:5000", erpnext_base_url: str = "http://localhost:8080"):
        Utility.load_environment()
        try:
            disconnect(alias="default")
        except Exception:
            pass
        connect(host=Utility.environment["database"]["url"], alias="default")

        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        rand_str = uuid.uuid4().hex[:6]
        self.test_run_id: str = f"E2E_{timestamp}_{rand_str}"
        self.kairon_api_url: str = kairon_api_url.rstrip("/")
        self.erpnext_base_url: str = erpnext_base_url.rstrip("/")

        
        self.auth_token: str = ""
        self.bot_id: str = ""
        self.site_name: str = ""
        self.company_name: str = ""
        self.test_user_email: str = f"user_{self.test_run_id.lower()}@example.com"
        self.created_resources: Dict[str, Any] = {
            "users": [],
            "user_permissions": [],
            "user_invitations": [],
            "crm_invitations": [],
            "mailpit_message_ids": []
        }

    def authenticate_kairon(self, username: str = "new_admin@kairon.ai", password: str = "Password@123") -> str:
        url = f"{self.kairon_api_url}/api/auth/login"
        res = requests.post(url, data={"username": username, "password": password}, timeout=15)
        if res.status_code != 200:
            raise RuntimeError(f"Kairon login failed with status {res.status_code}: {res.text}")
        data = res.json().get("data", {})
        self.auth_token = data.get("access_token", "")
        return self.auth_token

    def resolve_tenant_details(self, bot_id: str = None) -> Dict[str, Any]:
        if not self.auth_token:
            self.authenticate_kairon()

        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # If bot_id is not specified, fetch user details to get available bot
        if not bot_id:
            user_res = requests.get(f"{self.kairon_api_url}/api/user/details", headers=headers, timeout=15)
            if user_res.status_code == 200:
                user_info = user_res.json().get("data", {}).get("user", {})
                bots = (user_info.get("bots", {}).get("account_owned") or []) + (user_info.get("bots", {}).get("shared") or [])
                if bots:
                    raw_bot = bots[0]
                    bot_id = raw_bot.get("_id") if isinstance(raw_bot, dict) else str(raw_bot)
        
        if not bot_id:
            raise RuntimeError("Could not resolve any active bot_id for the test user.")

        self.bot_id = str(bot_id)

        
        # Fetch CRM details from Kairon API endpoint
        crm_res = requests.get(f"{self.kairon_api_url}/api/bot/{self.bot_id}/crm/details", headers=headers, timeout=15)
        if crm_res.status_code != 200:
            raise RuntimeError(f"Failed to fetch CRM details for bot {self.bot_id}: {crm_res.text}")

        details = crm_res.json().get("data") or {}
        self.site_name = details.get("site_name", "")
        self.company_name = details.get("company_name") or details.get("erpnext_company", "")

        if not self.site_name or not self.company_name:
            raise RuntimeError(f"Tenant details incomplete for bot {self.bot_id}: site_name='{self.site_name}', company='{self.company_name}'")

        # Ensure default SMTP account (Mailpit) is configured on the target site for invitations
        try:
            from kairon.crm.services.erpnext_client import ERPNextClient
            client = ERPNextClient(self.erpnext_base_url, self.site_name)
            admin_pwd = details.get("erpnext_password") or "Password@123"
            try:
                admin_pwd = Utility.decrypt_message(admin_pwd)
            except Exception:
                pass
            client.login(admin_pwd)
            client.ensure_default_smtp_account()
        except Exception as e:
            print(f"[E2ETestContext] Warning: Could not ensure default SMTP account: {e}")

        return {
            "test_run_id": self.test_run_id,
            "bot_id": self.bot_id,
            "site_name": self.site_name,
            "company_name": self.company_name,
            "test_user_email": self.test_user_email
        }
