from typing import Dict, Any, List, Optional
from services.api import ApiClient

class CrmService:
    @staticmethod
    def login(username: str, password: str) -> Dict[str, Any]:
        """Log in a user and obtain token details."""
        # RecaptchaVerifiedOAuth2PasswordRequestForm expects data parameter format
        payload = {
            "username": username,
            "password": password
        }
        res = ApiClient.post("api/auth/login", data=payload)
        data = res.get("data") or {}
        token = data.get("access_token")
        if token:
            ApiClient.set_token(token)
        return res

    @staticmethod
    def get_user_details() -> Dict[str, Any]:
        """Fetch logged-in user profile, including access control and bots."""
        res = ApiClient.get("api/user/details")
        data = res.get("data") or {}
        return data.get("user") or {}

    @staticmethod
    def get_bots() -> List[Dict[str, Any]]:
        """Extract lists of bots the current user can access."""
        user_info = CrmService.get_user_details()
        bots_dict = user_info.get("bots") or {}
        owned = bots_dict.get("account_owned") or []
        shared = bots_dict.get("shared") or []
        return owned + shared

    @staticmethod
    def get_bot_settings(bot_id: str) -> Dict[str, Any]:
        """Get current settings for a given chatbot, including CRM enablement status."""
        res = ApiClient.get(f"api/bot/{bot_id}/settings")
        return res.get("data", {})

    @staticmethod
    def enable_crm(bot_id: str, enable: bool = True) -> Dict[str, Any]:
        """Enable or disable CRM capabilities for a bot."""
        # Get current settings first to preserve analytics model
        try:
            current_settings = CrmService.get_bot_settings(bot_id)
            analytics_payload = current_settings.get("analytics", {})
        except Exception:
            analytics_payload = {"enable": False}

        payload = {
            "analytics": analytics_payload,
            "enable_crm": enable
        }
        return ApiClient.put(f"api/bot/{bot_id}/settings", json_data=payload)

    @staticmethod
    def onboard_crm(
        bot_id: str,
        company_name: str,
        country: str,
        currency: str,
        abbr: Optional[str] = None,
        selected_modules: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Trigger CRM provisioning workflow for a chatbot."""
        if not abbr:
            # Simple abbreviation generator if not provided
            abbr = "".join([w[0].upper() for w in company_name.split() if w])[:5]

        payload = {
            "company_name": company_name,
            "abbr": abbr,
            "default_currency": currency,
            "country": country
        }
        if selected_modules:
            payload["selected_modules"] = selected_modules
        return ApiClient.post(f"api/bot/{bot_id}/crm/onboard", json_data=payload)

    @staticmethod
    def get_available_modules(bot_id: str) -> Dict[str, Any]:
        """Fetch list of available ERPNext business modules for selection."""
        try:
            res = ApiClient.get(f"api/bot/{bot_id}/crm/available-modules")
            return res.get("data") or {}
        except Exception:
            return {}

    @staticmethod
    def get_selected_modules(bot_id: str) -> Dict[str, Any]:
        """Fetch currently selected ERPNext business modules for a bot."""
        try:
            res = ApiClient.get(f"api/bot/{bot_id}/crm/selected-modules")
            return res.get("data") or {}
        except Exception:
            return {}

    @staticmethod
    def configure_modules(bot_id: str, selected_modules: List[str]) -> Dict[str, Any]:
        """Update selected ERPNext business modules for a bot."""
        payload = {"selected_modules": selected_modules}
        return ApiClient.post(f"api/bot/{bot_id}/crm/configure-modules", json_data=payload)

    @staticmethod
    def reconcile_modules(bot_id: str) -> Dict[str, Any]:
        """Reconcile and repair ERPNext module configuration drift."""
        return ApiClient.post(f"api/bot/{bot_id}/crm/reconcile-modules")


    @staticmethod
    def get_crm_status(bot_id: str) -> Dict[str, Any]:
        """Retrieve dynamic progress status of CRM provisioning."""
        res = ApiClient.get(f"api/bot/{bot_id}/crm/status")
        return res.get("data", {})

    @staticmethod
    def get_users(bot_id: str) -> List[Dict[str, Any]]:
        """Fetch all ERPNext users."""
        res = ApiClient.get(f"api/bot/{bot_id}/crm/users")
        return res.get("data") or []

    @staticmethod
    def get_crm_details(bot_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the full CRM details document for a chatbot."""
        try:
            res = ApiClient.get(f"api/bot/{bot_id}/crm/details")
            return res.get("data")
        except Exception as e:
            # Return None if no CRM details exist for the bot
            if "No CRM configuration found" in str(e) or "422" in str(e):
                return None
            raise e

    @staticmethod
    def create_crm_user(bot_id: str, email: str, role: str = "CRM User") -> Dict[str, Any]:
        """Add an additional collaborator/user to the provisioned CRM instance."""
        payload = {
            "email": email,
            "role": role
        }
        return ApiClient.post(f"api/bot/{bot_id}/crm/create-user", json_data=payload)

    @staticmethod
    def invite_crm_user(bot_id: str, email: str, roles: List[str], company_name: Optional[str] = None) -> Dict[str, Any]:
        """Send a native ERPNext user invitation via Kairon's UserInvitation API."""
        payload = {
            "email": email,
            "roles": roles
        }
        if company_name:
            payload["company_name"] = company_name
        return ApiClient.post(f"api/bot/{bot_id}/crm/invite-user", json_data=payload)

    @staticmethod
    def delete_crm_project(bot_id: str, company_name: str) -> Dict[str, Any]:
        """Deletes CRM configuration details/project from chatbot settings."""
        return ApiClient.delete(f"api/bot/{bot_id}/crm/project", params={"company_name": company_name})

    @staticmethod
    def get_db_tables(bot_id: str) -> List[str]:
        """Retrieves list of all PostgreSQL database tables for the provisioned CRM site."""
        try:
            res = ApiClient.get(f"api/bot/{bot_id}/crm/tables")
            return res.get("data") or []
        except Exception:
            return []

    @staticmethod
    def get_table_content(bot_id: str, table_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves row content for a specific PostgreSQL database table."""
        try:
            res = ApiClient.get(f"api/bot/{bot_id}/crm/tables/{table_name}", params={"limit": limit})
            return res.get("data") or []
        except Exception:
            return []

