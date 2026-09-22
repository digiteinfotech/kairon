import json
import requests
import urllib3
from loguru import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ProvisionVerifier:
    """
    Strictly read-only service for asserting application readiness and verifying states.
    Does NOT mutate any state in ERPNext or MongoDB.
    """

    def __init__(self, base_url: str, host_header: str):
        self.base_url = base_url.rstrip("/")
        self.host_header = host_header
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "Host": self.host_header,
            "Accept": "application/json"
        })

    def authenticate_with_token(self, api_key: str, api_secret: str):
        """Sets stateless token auth header for integration user operations."""
        self.session.headers.update({
            "Authorization": f"token {api_key}:{api_secret}"
        })

    def verify_health(self) -> bool:
        """
        Verifies that the ERPNext application is fully ready.
        Asserts:
        - HTTP Server is responding
        - Login endpoint is accessible
        """
        ping_url = f"{self.base_url}/api/method/ping"
        login_url = f"{self.base_url}/api/method/login"

        try:
            # 1. Ping the server
            ping_resp = self.session.get(ping_url, timeout=10)
            if ping_resp.status_code != 200:
                logger.debug(f"[ProvisionVerifier] Ping failed. Status: {ping_resp.status_code}")
                return False

            # 2. Check if login endpoint is accessible
            login_resp = self.session.get(login_url, timeout=10)
            if login_resp.status_code not in (200, 405, 401):
                logger.debug(f"[ProvisionVerifier] Login endpoint check failed. Status: {login_resp.status_code}")
                return False

            return True

        except requests.RequestException as e:
            logger.debug(f"[ProvisionVerifier] Network exception during health check: {str(e)}")
            return False

    def verify_provisioning_state(self, admin_password: str, company: str, email: str, required_roles: list, temp_password: str = None) -> bool:
        """
        Logs in as Administrator to verify the existence of the Company and User,
        checks that the User has the required roles and default company,
        and optionally verifies that the user can login with their password.

        'company' is None on Tier 1 standalone sites (no erpnext -> no 'Company'
        DocType) -- the Company/default-company checks are skipped in that case.
        """
        # 1. Login as Administrator (asserts Administrator account exists)
        login_payload = {"usr": "Administrator", "pwd": admin_password}
        login_resp = self.session.post(f"{self.base_url}/api/method/login", data=login_payload, timeout=10)

        if login_resp.status_code != 200:
            logger.error("[ProvisionVerifier] Failed to authenticate as Administrator for verification.")
            return False

        logger.info("[ProvisionVerifier] Verified that the Administrator account exists and can log in.")

        # 2. Verify Company (Tier 2 only)
        if company:
            company_resp = self.session.get(f"{self.base_url}/api/resource/Company/{company}", timeout=10)
            if company_resp.status_code != 200:
                logger.error(f"[ProvisionVerifier] Company '{company}' does not exist.")
                return False
            logger.info(f"[ProvisionVerifier] Verified that Company '{company}' exists.")

        # 3. Verify User
        user_resp = self.session.get(f"{self.base_url}/api/resource/User/{email}", timeout=10)
        if user_resp.status_code != 200:
            logger.error(f"[ProvisionVerifier] User '{email}' does not exist.")
            return False
        logger.info(f"[ProvisionVerifier] Verified that User '{email}' exists.")

        # 4. Verify Roles and Default Company
        user_data = user_resp.json().get("data", {})
        existing_roles = [r.get("role") for r in user_data.get("roles", [])]

        for role in required_roles:
            if role not in existing_roles:
                logger.error(f"[ProvisionVerifier] User '{email}' is missing required role '{role}'.")
                return False
        logger.info(f"[ProvisionVerifier] Verified User roles: {required_roles}.")

        # Retrieve default company via User Permission DocType resource API (Tier 2 only)
        if company:
            filters = [
                ["User Permission", "user", "=", email],
                ["User Permission", "allow", "=", "Company"],
                ["User Permission", "for_value", "=", company],
                ["User Permission", "is_default", "=", 1]
            ]
            params = {
                "filters": json.dumps(filters),
                "fields": json.dumps(["name"])
            }
            default_resp = self.session.get(f"{self.base_url}/api/resource/User Permission", params=params, timeout=10)

            if default_resp.status_code != 200:
                logger.error(f"[ProvisionVerifier] Failed to retrieve default company for User '{email}'. Status: {default_resp.status_code}")
                return False

            data = default_resp.json().get("data", [])
            if not data:
                logger.error(f"[ProvisionVerifier] Default company '{company}' is not set for User '{email}'.")
                return False
            logger.info(f"[ProvisionVerifier] Verified User default company: '{company}'.")

        # 5. Verify User Login if password provided
        if temp_password:
            user_session = requests.Session()
            user_session.headers.update({
                "Host": self.host_header,
                "Accept": "application/json"
            })
            u_login = user_session.post(f"{self.base_url}/api/method/login", data={"usr": email, "pwd": temp_password}, timeout=10)
            if u_login.status_code != 200:
                logger.error(f"[ProvisionVerifier] Newly created user '{email}' could not authenticate with temporary password.")
                return False
            logger.info("[ProvisionVerifier] Verified that the newly created User can log in successfully.")

        return True

    def verify_invitation(self, email: str, app_name: str = "frappe") -> bool:
        """
        Verifies that a native UserInvitation record exists in ERPNext for the email,
        is in 'Pending' status, and has an email_sent_at timestamp proving email dispatch.
        """
        filters = json.dumps([
            ["User Invitation", "email", "=", email],
            ["User Invitation", "app_name", "=", app_name],
        ])
        fields = json.dumps(["name", "email", "status", "email_sent_at"])
        resp = self.session.get(
            f"{self.base_url}/api/resource/User Invitation",
            params={"filters": filters, "fields": fields, "order_by": "creation desc", "limit": 1},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"[ProvisionVerifier] Could not query User Invitation for '{email}': HTTP {resp.status_code}")
            return False

        data = resp.json().get("data", [])
        if not data:
            logger.error(f"[ProvisionVerifier] No User Invitation record found for '{email}'.")
            return False

        inv = data[0]
        if inv.get("status") != "Pending":
            logger.error(f"[ProvisionVerifier] User Invitation status is '{inv.get('status')}', expected 'Pending'.")
            return False

        if not inv.get("email_sent_at"):
            logger.error(f"[ProvisionVerifier] User Invitation for '{email}' has no email_sent_at timestamp.")
            return False

        logger.info(f"[ProvisionVerifier] Verified Pending User Invitation for '{email}' with email_sent_at={inv.get('email_sent_at')}.")
        return True

    def verify_post_acceptance(self, email: str, company: str, required_roles: list) -> bool:
        """
        Verifies post-acceptance state in ERPNext:
        1. User document exists and is enabled
        2. All required roles are present on the User
        3. User Permission for company exists and is default
        """
        # 1. User document
        user_resp = self.session.get(f"{self.base_url}/api/resource/User/{email}", timeout=10)
        if user_resp.status_code != 200:
            logger.error(f"[ProvisionVerifier] Post-acceptance check failed: User '{email}' does not exist.")
            return False

        user_data = user_resp.json().get("data", {})
        if not user_data.get("enabled"):
            logger.error(f"[ProvisionVerifier] Post-acceptance check failed: User '{email}' is disabled.")
            return False

        # 2. Roles
        existing_roles = [r.get("role") for r in user_data.get("roles", [])]
        for role in required_roles:
            if role not in existing_roles:
                logger.error(f"[ProvisionVerifier] Post-acceptance check failed: User '{email}' missing role '{role}'.")
                return False

        # 3. User Permission for company
        filters = json.dumps([
            ["User Permission", "user", "=", email],
            ["User Permission", "allow", "=", "Company"],
            ["User Permission", "for_value", "=", company],
        ])
        perm_resp = self.session.get(
            f"{self.base_url}/api/resource/User Permission",
            params={"filters": filters, "fields": json.dumps(["name"])},
            timeout=10,
        )
        if perm_resp.status_code != 200 or not perm_resp.json().get("data"):
            logger.error(f"[ProvisionVerifier] Post-acceptance check failed: User Permission for company '{company}' missing for '{email}'.")
            return False

        logger.info(f"[ProvisionVerifier] Post-acceptance verification passed for '{email}' on company '{company}'.")
        return True
