import json
import requests
from typing import Dict, Any, Optional
from loguru import logger
from kairon.exceptions import AppException


class BaseFrappeClient:
    """
    Base REST API Client for core Frappe Framework interfaces.
    Handles session authentication, API key generation, user management,
    webhook setup, and system cache operations.
    """

    def __init__(self, site_url: str, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.site_url = site_url.rstrip('/')
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()

    def get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key and self.api_secret:
            headers["Authorization"] = f"token {self.api_key}:{self.api_secret}"
        return headers

    def ping(self) -> bool:
        """Pings the Frappe site ping method."""
        try:
            res = self.session.get(f"{self.site_url}/api/method/ping", headers=self.get_headers(), timeout=10)
            return res.status_code == 200
        except Exception as e:
            logger.warning(f"[BaseFrappeClient] Ping failed for {self.site_url}: {e}")
            return False

    def login(self, usr: str, pwd: str) -> bool:
        """Session-based login to Frappe framework."""
        url = f"{self.site_url}/api/method/login"
        payload = {"usr": usr, "pwd": pwd}
        res = self.session.post(url, data=payload, timeout=15)
        if res.status_code == 200:
            logger.info(f"[BaseFrappeClient] Session login successful for {usr}")
            return True
        logger.error(f"[BaseFrappeClient] Session login failed for {usr}: {res.text}")
        return False

    def generate_keys(self, user_email: str) -> Dict[str, str]:
        """Generates api_key and api_secret for a given user via Frappe core API."""
        url = f"{self.site_url}/api/method/frappe.core.doctype.user.user.generate_keys"
        payload = json.dumps({"user": user_email})
        res = self.session.post(url, data=payload, headers=self.get_headers(), timeout=15)
        if res.status_code == 200:
            data = res.json().get("message", {})
            return {
                "api_key": data.get("api_key"),
                "api_secret": data.get("api_secret")
            }
        raise AppException(f"[BaseFrappeClient] Failed to generate API keys for {user_email}: {res.text}")

    def create_user(self, email: str, first_name: str, roles: list) -> Dict[str, Any]:
        """Creates a standard user in Frappe and assigns roles."""
        url = f"{self.site_url}/api/resource/User"
        payload = json.dumps({
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "roles": [{"role": r} for r in roles]
        })
        res = self.session.post(url, data=payload, headers=self.get_headers(), timeout=15)
        if res.status_code in (200, 201):
            return res.json().get("data", {})
        raise AppException(f"[BaseFrappeClient] Failed to create user {email}: {res.text}")

    def clear_cache(self) -> bool:
        """Triggers clear cache on Frappe framework."""
        url = f"{self.site_url}/api/method/frappe.sessions.clear"
        res = self.session.post(url, headers=self.get_headers(), timeout=15)
        return res.status_code == 200
