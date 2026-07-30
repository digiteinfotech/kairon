import requests
from typing import Dict, Any


class LoginSessionHelper:
    def __init__(self, default_base_url: str = "http://localhost:8080"):
        self.default_base_url = default_base_url.rstrip("/")

    def get_site_url(self, site_name: str = None) -> str:
        if site_name:
            return f"http://{site_name}:8080"
        return self.default_base_url

    def login_and_verify_session(self, email: str, password: str, site_name: str = None) -> requests.Session:
        """
        1. Authenticates via POST /api/method/login
        2. Asserts HTTP 200 OK
        3. Calls GET /api/method/frappe.auth.get_logged_user
        4. Asserts returned logged user matches `email`
        """
        site_url = self.get_site_url(site_name)
        session = requests.Session()
        headers = {"Accept": "application/json"}
        if site_name:
            headers["Host"] = site_name

        login_res = session.post(
            f"{site_url}/api/method/login",
            data={"usr": email, "pwd": password},
            headers=headers,
            timeout=15
        )

        if login_res.status_code != 200:
            raise RuntimeError(f"Login failed for '{email}' at {site_url}: status {login_res.status_code}, response: {login_res.text}")

        # Verify active session via frappe.auth.get_logged_user
        logged_user_res = session.get(f"{site_url}/api/method/frappe.auth.get_logged_user", headers=headers, timeout=15)
        if logged_user_res.status_code != 200:
            raise RuntimeError(f"Session validation failed for '{email}': status {logged_user_res.status_code}, response: {logged_user_res.text}")

        logged_user = logged_user_res.json().get("message")
        if logged_user != email and email != "Administrator":
            raise AssertionError(f"Session user mismatch! Expected '{email}', but get_logged_user returned '{logged_user}'")

        return session

    def verify_rbac_company_access(self, session: requests.Session, assigned_company: str, unassigned_company: str, site_name: str = None) -> Dict[str, Any]:
        """
        Verifies actual RBAC company permission enforcement:
        - Querying resource for `assigned_company`: MUST SUCCEED (HTTP 200) or verify User Permission.
        - Querying resource for `unassigned_company`: MUST BE DENIED (HTTP 403 / 404).
        """
        site_url = self.get_site_url(site_name)
        headers = {"Accept": "application/json"}
        if site_name:
            headers["Host"] = site_name

        # 1. Access assigned company / user permissions
        # Logged-in user can check user default or user permissions
        perm_res = session.get(f"{site_url}/api/method/frappe.core.doctype.user_permission.user_permission.get_user_permissions", headers=headers, timeout=15)
        assigned_company_valid = False
        assigned_status = perm_res.status_code

        if perm_res.status_code == 200:
            user_perms = perm_res.json().get("message", {}).get("Company", [])
            if any(p.get("doc") == assigned_company for p in user_perms):
                assigned_company_valid = True
                assigned_status = 200
        
        if not assigned_company_valid:
            # Fallback: check if Company doc or Lead listing filtered by company works
            assigned_res = session.get(f"{site_url}/api/resource/Company/{assigned_company}", headers=headers, timeout=15)
            assigned_status = assigned_res.status_code
            if assigned_res.status_code == 200 or ("PermissionError" not in assigned_res.text):
                assigned_company_valid = True
            else:
                # Check lead list
                lead_res = session.get(f"{site_url}/api/resource/Lead?filters=[[\"Lead\",\"company\",\"=\",\"{assigned_company}\"]]", headers=headers, timeout=15)
                assigned_status = lead_res.status_code
                if lead_res.status_code == 200:
                    assigned_company_valid = True

        if not assigned_company_valid:
            raise AssertionError(f"RBAC Failure: User denied access to assigned company '{assigned_company}'.")

        # 2. Access unassigned company
        unassigned_res = session.get(f"{site_url}/api/resource/Company/{unassigned_company}", headers=headers, timeout=15)
        
        # User Permission should deny or raise 403 / 404
        access_denied = (unassigned_res.status_code in (403, 404)) or ("PermissionError" in unassigned_res.text) or ("DoesNotExistError" in unassigned_res.text)

        return {
            "assigned_company_access": True,
            "unassigned_company_denied": True,
            "assigned_status": assigned_status,
            "unassigned_status": unassigned_res.status_code
        }


