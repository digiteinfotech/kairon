import json
import requests
import subprocess
import urllib3
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from loguru import logger
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.crm.constants import (
    REQUIRED_INTEGRATION_USER_ROLES,
    BUSINESS_MODULE_CATALOG,
    INFRASTRUCTURE_MODULE_NAMES,
)


class WorkspaceVerificationEntry(BaseModel):
    module_key: str
    workspace_name: str
    expected_hidden: bool
    actual_hidden: bool
    matches: bool


class ModuleVerificationReport(BaseModel):
    site: str
    expected_selected_modules: List[str]
    expected_blocked_modules: List[str]
    actual_blocked_modules: List[str]
    profile_matches: bool
    workspaces: List[WorkspaceVerificationEntry]
    workspaces_match: bool
    is_fully_consistent: bool
    security_note: str = (
        "Workspace hiding and Module Profile block UI views only. "
        "They do not prevent direct API or URL access to underlying DocTypes. "
        "Role-based permissions govern data access security."
    )


class ERPNextClient:
    """
    Handles all REST API communication with ERPNext.
    Responsible for idempotent creation of resources and authentication.
    Does NOT contain infrastructure or Bench CLI logic.

    Authentication strategy:
    - Legacy provisioning flow: session-based (login with admin password).
    - Invitation and post-provisioning flows: stateless token auth using the
      dedicated kairon-crm integration user's api_key:api_secret.
    """

    def __init__(self, base_url: str, host_header: str):
        """
        :param base_url: The URL to reach the Frappe web server (e.g. http://localhost:8000)
        :param host_header: The Host header to route to the correct site (e.g. validtestcompany.localhost)
        """
        self.base_url = base_url.rstrip("/")
        self.host_header = host_header
        self.site_name = host_header
        self.session = requests.Session()
        # Defaults to verifying certs; only disable when the operator explicitly
        # opts out via crm.bench.ssl_verify (e.g. a self-signed local bench). A
        # hardcoded `verify = False` would silently accept any certificate on a
        # remote HTTPS deployment, exposing credentials to an active attacker.
        crm_config = Utility.environment.get("crm", {})
        ssl_verify = crm_config.get("bench", {}).get("ssl_verify", True)
        self.session.verify = ssl_verify
        if not ssl_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session.headers.update({
            "Host": self.host_header,
            "Accept": "application/json"
        })

    def _log_api_op(self, operation: str, resource: str, success: bool, status_code: Optional[int] = None, error: Optional[str] = None):
        log_msg = f"[ERPNextClient] Site: {self.host_header} | Op: {operation} | Resource: {resource} | Success: {success} | HTTP: {status_code}"
        if error:
            log_msg += f" | Error: {error}"
        if success:
            logger.info(log_msg)
        else:
            logger.error(log_msg)

    # ─────────────────────────────────────────────────────────────
    # Authentication
    # ─────────────────────────────────────────────────────────────

    def login(self, admin_password: str) -> bool:
        """
        Authenticates with ERPNext using the Administrator account (session-based).
        Used only during the provisioning workflow where the in-memory admin password
        is available. All post-provisioning calls use token auth instead.
        """
        url = f"{self.base_url}/api/method/login"
        payload = {"usr": "Administrator", "pwd": admin_password}
        try:
            response = self.session.post(url, data=payload, timeout=15)
            if response.status_code != 200:
                self._log_api_op("login", "Administrator", False, response.status_code, response.text)
                raise AppException(f"Failed to login to ERPNext: HTTP {response.status_code}")
            self._log_api_op("login", "Administrator", True, response.status_code)
            return True
        except requests.RequestException as e:
            self._log_api_op("login", "Administrator", False, error=str(e))
            raise AppException(f"Network error during ERPNext login: {str(e)}")

    def authenticate_with_token(self, api_key: str, api_secret: str):
        """
        Sets stateless token auth header for the dedicated integration user.
        Clears session cookies to ensure token header is used exclusively.
        """
        self.session.cookies.clear()
        self.session.headers.update({
            "Authorization": f"token {api_key}:{api_secret}"
        })

    # ─────────────────────────────────────────────────────────────
    # Integration User Setup & Permission Validation
    # ─────────────────────────────────────────────────────────────

    def create_integration_user(self, email: str) -> None:
        """
        Idempotently creates the dedicated kairon-crm integration user with
        REQUIRED_INTEGRATION_USER_ROLES ("System Manager" and "Workspace Manager").
        Skips creation if the user already exists, but updates roles if required roles are missing.
        """
        required_roles = REQUIRED_INTEGRATION_USER_ROLES
        if self.check_user_exists(email):
            logger.info(f"[ERPNextClient] Integration user '{email}' already exists. Verifying roles.")
            # Ensure integration user has all REQUIRED_INTEGRATION_USER_ROLES
            url = f"{self.base_url}/api/resource/User/{email}"
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                user_data = resp.json().get("data", {})
                existing_roles = [r.get("role") for r in user_data.get("roles", [])]
                missing = [r for r in required_roles if r not in existing_roles]
                if missing:
                    logger.info(f"[ERPNextClient] Integration user '{email}' missing roles {missing}. Updating.")
                    new_roles = user_data.get("roles", []) + [{"role": r} for r in missing]
                    self.session.put(url, json={"roles": new_roles}, timeout=15)
            return

        url = f"{self.base_url}/api/resource/User"
        payload = {
            "email": email,
            "first_name": "Kairon",
            "last_name": "CRM",
            "enabled": 1,
            "send_welcome_email": 0,
            "roles": [{"role": r} for r in required_roles]
        }
        response = self.session.post(url, json=payload, timeout=15)
        if response.status_code not in (200, 201):
            self._log_api_op("create_integration_user", email, False, response.status_code, response.text)
            raise AppException(f"Failed to create integration user '{email}': HTTP {response.status_code}")
        self._log_api_op("create_integration_user", email, True, response.status_code)

    def validate_integration_permissions(self) -> bool:
        """
        Validates that the currently authenticated integration user has all required permissions:
        - GET Module Def
        - GET Workspace
        - PUT Workspace
        - GET/POST/PUT Module Profile
        - PUT User

        Aborts provisioning immediately if any permission check fails.
        """
        ops = []
        try:
            # 1. GET Module Def
            r1 = self.session.get(f"{self.base_url}/api/resource/Module Def?limit=1", timeout=10)
            ops.append(("GET", "Module Def", r1.status_code == 200, r1.status_code, r1.text if r1.status_code != 200 else None))

            # 2. GET Workspace
            r2 = self.session.get(f"{self.base_url}/api/resource/Workspace?limit=1", timeout=10)
            ops.append(("GET", "Workspace", r2.status_code == 200, r2.status_code, r2.text if r2.status_code != 200 else None))

            # 3. PUT Workspace (dry-run update on existing workspace)
            if r2.status_code == 200 and r2.json().get("data"):
                ws_name = r2.json()["data"][0]["name"]
                # GET detailed workspace
                r_detail = self.session.get(f"{self.base_url}/api/resource/Workspace/{ws_name}", timeout=10)
                if r_detail.status_code == 200:
                    d_val = r_detail.json().get("data", {})
                    curr_hidden = d_val.get("is_hidden", 0) if isinstance(d_val, dict) else 0
                    r3 = self.session.put(f"{self.base_url}/api/resource/Workspace/{ws_name}", json={"is_hidden": curr_hidden}, timeout=10)
                    ops.append(("PUT", f"Workspace/{ws_name}", r3.status_code == 200, r3.status_code, r3.text if r3.status_code != 200 else None))
                else:
                    ops.append(("PUT", f"Workspace/{ws_name}", False, r_detail.status_code, r_detail.text))
            else:
                ops.append(("PUT", "Workspace", False, r2.status_code, "No workspace available to test PUT"))

            # 4. Module Profile permissions check (GET list)
            r4 = self.session.get(f"{self.base_url}/api/resource/Module Profile?limit=1", timeout=10)
            ops.append(("GET/POST/PUT", "Module Profile", r4.status_code == 200, r4.status_code, r4.text if r4.status_code != 200 else None))

            # 5. User permissions check (GET current user)
            r5 = self.session.get(f"{self.base_url}/api/resource/User?limit=1", timeout=10)
            ops.append(("GET/PUT", "User", r5.status_code == 200, r5.status_code, r5.text if r5.status_code != 200 else None))

            all_passed = True
            failed_ops = []
            for op, resource, success, status_code, err in ops:
                self._log_api_op(f"perm_check_{op}", resource, success, status_code, err)
                if not success:
                    logger.error(f"[ERPNextClient] Permission check failed for {op} {resource}: HTTP {status_code} - {err}")
                    failed_ops.append(f"{op} {resource} (HTTP {status_code})")
                    all_passed = False

            if not all_passed:
                logger.error(f"[ERPNextClient] Integration permission validation failed for operations: {', '.join(failed_ops)}")

            return all_passed

        except Exception as e:
            self._log_api_op("validate_integration_permissions", "System", False, error=str(e))
            return False

    def generate_keys_for_user(self, email: str) -> dict:
        """
        Generates (or regenerates) a Frappe API key+secret pair for the given user.
        Uses native HTTP API first (running in Gunicorn), falling back to container Python.
        Returns { api_key, api_secret }
        """
        url = f"{self.base_url}/api/method/frappe.core.doctype.user.user.generate_keys"
        try:
            response = self.session.post(url, json={"user": email}, timeout=15)
            if response.status_code == 200:
                data = response.json().get("message", {})
                if data.get("api_key") and data.get("api_secret"):
                    self._log_api_op("generate_keys", email, True, 200, "Generated via HTTP API")
                    return {"api_key": data["api_key"], "api_secret": data["api_secret"]}
        except Exception as e:
            logger.warning(f"[ERPNextClient] HTTP key generation attempt failed, trying container fallback: {e}")

        # Fallback to Container Python execution
        try:
            from kairon.crm.services.bench_executor import BenchExecutor
            crm_config = Utility.environment.get("crm", {})
            bench_config = crm_config.get("bench", {})
            container_name = BenchExecutor()._resolve_container_name(bench_config)

            script = f"""
import frappe, json
frappe.init(site={json.dumps(self.site_name)})
frappe.connect()
user = {json.dumps(email)}
from frappe.core.doctype.user.user import generate_keys
keys = generate_keys(user)
frappe.db.commit()
print(json.dumps(keys))
"""
            cmd = [
                "docker", "exec", "-w", "/home/frappe/frappe-bench/sites", "-i", container_name,
                "/home/frappe/frappe-bench/env/bin/python", "-c", script
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode == 0:
                out = res.stdout.strip()
                if "{" in out and "}" in out:
                    json_part = out[out.find("{"):out.rfind("}") + 1]
                    data = json.loads(json_part)
                    if data.get("api_key") and data.get("api_secret"):
                        try:
                            BenchExecutor().reload_gunicorn_workers(container_name)
                        except Exception as reload_err:
                            logger.debug(f"[ERPNextClient] Worker reload after key generation failed: {reload_err}")
                        self._log_api_op("generate_keys", email, True, 200, "Generated via container python")
                        return {"api_key": data["api_key"], "api_secret": data["api_secret"]}
        except Exception as e:
            logger.warning(f"[ERPNextClient] Container key generation fallback failed: {e}")

        raise AppException(f"Failed to generate API keys for '{email}'")

    def ensure_invitation_webhook(self, kairon_url: str, site_name: str, webhook_secret: str, bot: str) -> str:
        # Route is mounted under /api/bot/{bot}/crm (see kairon/api/app/main.py's
        # crm_router prefix) -- the /bot/{bot} segment is required, not optional.
        request_url = f"{kairon_url.rstrip('/')}/api/bot/{bot}/crm/webhook/invitation-accepted"

        # Check for existing webhook
        filters = json.dumps([
            ["Webhook", "webhook_doctype", "=", "User Invitation"],
            ["Webhook", "webhook_docevent", "=", "on_update"],
            ["Webhook", "request_url", "=", request_url],
        ])
        check_url = f"{self.base_url}/api/resource/Webhook"
        check_resp = self.session.get(check_url, params={"filters": filters, "fields": '["name"]'}, timeout=15)
        if check_resp.status_code == 200:
            existing = check_resp.json().get("data", [])
            if existing:
                name = existing[0]["name"]
                # Update the secret on the existing webhook -- ProvisioningService
                # generates and persists a fresh webhook_secret on every run, so a
                # reused webhook must be kept in sync or its signature checks fail.
                self.session.put(
                    f"{self.base_url}/api/resource/Webhook/{name}",
                    json={"webhook_secret": webhook_secret},
                    timeout=15,
                )
                self._log_api_op("ensure_webhook", name, True, check_resp.status_code, "Reusing existing webhook")
                return name

        # Create webhook
        payload = {
            "name": f"Kairon User Invitation Webhook ({site_name})",
            "webhook_doctype": "User Invitation",
            "webhook_docevent": "on_update",
            "condition": "doc.status == 'Accepted'",
            "request_url": request_url,
            "request_method": "POST",
            "webhook_secret": webhook_secret,
            "enabled": 1,
            "webhook_headers": [
                {"key": "X-Kairon-Site", "value": site_name}
            ]
        }
        create_resp = self.session.post(f"{self.base_url}/api/resource/Webhook", json=payload, timeout=15)
        if create_resp.status_code not in (200, 201):
            self._log_api_op("ensure_webhook", site_name, False, create_resp.status_code, create_resp.text)
            raise AppException(f"Failed to create invitation webhook: HTTP {create_resp.status_code}")

        name = create_resp.json().get("data", {}).get("name", "")
        self._log_api_op("ensure_webhook", name, True, create_resp.status_code)
        return name

    def set_lead_webhook_secret(self, webhook_secret: str) -> None:
        """
        Configures the kairon_connector app's inbound event-gateway secret
        (single doctype 'Kairon Settings' -> webhook_secret) on this freshly
        provisioned site, so Kairon's outbound event publisher can sign
        lead/conversation-sync events that this site's
        /api/method/kairon_connector.api.v1.webhook.receive_event will accept.

        Called once, immediately after kairon_connector is installed during
        initial provisioning -- not a rotation mechanism.
        """
        # Frappe's REST update route is /api/resource/{doctype}/{name}; for a
        # Single DocType the document name is the doctype name itself.
        url = f"{self.base_url}/api/resource/Kairon Settings/Kairon Settings"
        resp = self.session.put(url, json={"webhook_secret": webhook_secret}, timeout=15)
        if resp.status_code not in (200, 201):
            self._log_api_op("set_lead_webhook_secret", "Kairon Settings", False, resp.status_code, resp.text)
            raise AppException(f"Failed to configure Kairon Connector webhook secret: HTTP {resp.status_code}")
        self._log_api_op("set_lead_webhook_secret", "Kairon Settings", True, resp.status_code)

    # ─────────────────────────────────────────────────────────────
    # Dynamic Module Discovery
    # ─────────────────────────────────────────────────────────────

    def discover_business_modules(self) -> dict:
        """
        Discovers installed business modules live from ERPNext.
        Filters out INFRASTRUCTURE_MODULE_NAMES.
        Falls back to BUSINESS_MODULE_CATALOG if ERPNext API fails.

        Returns:
          {
             "source": "live" | "static_fallback",
             "modules": [
                {
                   "key": str,
                   "workspace": str,
                   "frappe_module": str,
                   "description": str
                }
             ]
          }
        """
        try:
            mod_url = f"{self.base_url}/api/resource/Module Def"
            mod_params = {
                "fields": json.dumps(["name", "app_name", "restrict_to_domain"]),
                "limit_page_length": 500
            }
            mod_resp = self.session.get(mod_url, params=mod_params, timeout=10)

            ws_url = f"{self.base_url}/api/resource/Workspace"
            ws_params = {
                "fields": json.dumps(["name", "title", "module", "is_hidden", "public"]),
                "filters": json.dumps([["public", "=", 1]]),
                "limit_page_length": 500
            }
            ws_resp = self.session.get(ws_url, params=ws_params, timeout=10)

            if mod_resp.status_code == 200 and ws_resp.status_code == 200:
                raw_mods = mod_resp.json().get("data", [])
                raw_wss = ws_resp.json().get("data", [])

                # Map workspace name/module
                ws_map = {w.get("module") or w.get("name"): w.get("name") for w in raw_wss if w.get("name")}

                discovered = []
                for m in raw_mods:
                    mod_name = m.get("name")
                    app_name = m.get("app_name", "")
                    if not mod_name:
                        continue
                    if app_name == "frappe" or mod_name in INFRASTRUCTURE_MODULE_NAMES:
                        continue

                    # Match with catalog key or use name as key
                    mod_key = mod_name
                    ws_name = ws_map.get(mod_name, mod_name)
                    desc = f"{mod_name} module"

                    if mod_name in BUSINESS_MODULE_CATALOG:
                        catalog_entry = BUSINESS_MODULE_CATALOG[mod_name]
                        ws_name = catalog_entry["workspace"]
                        desc = catalog_entry["description"]
                    else:
                        # Check if any catalog key matches frappe_module
                        for k, cat in BUSINESS_MODULE_CATALOG.items():
                            if cat["frappe_module"] == mod_name:
                                mod_key = k
                                ws_name = cat["workspace"]
                                desc = cat["description"]
                                break

                    discovered.append({
                        "key": mod_key,
                        "workspace": ws_name,
                        "frappe_module": mod_name,
                        "description": desc
                    })

                # Deduplicate by key
                unique_discovered = {}
                for d in discovered:
                    if d["key"] not in unique_discovered:
                        unique_discovered[d["key"]] = d

                discovered_list = list(unique_discovered.values())
                if discovered_list:
                    self._log_api_op("discover_modules", "live", True, 200)
                    return {"source": "live", "modules": discovered_list}

        except Exception as e:
            logger.warning(f"[ERPNextClient] Live module discovery failed: {e}. Falling back to static catalog.")

        # Fallback to static catalog
        self._log_api_op("discover_modules", "static_fallback", True)
        fallback_modules = [
            {
                "key": key,
                "workspace": cat["workspace"],
                "frappe_module": cat["frappe_module"],
                "description": cat["description"]
            }
            for key, cat in BUSINESS_MODULE_CATALOG.items()
        ]
        return {"source": "static_fallback", "modules": fallback_modules}

    # ─────────────────────────────────────────────────────────────
    # Workspace Visibility Control (Layer 1)
    # ─────────────────────────────────────────────────────────────

    def get_workspace_visibility(self, workspace_names: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        Gets current is_hidden status for specified workspaces or all public workspaces.
        Returns dict: { workspace_name: is_hidden_bool }
        """
        url = f"{self.base_url}/api/resource/Workspace"
        filters = [["public", "=", 1]]
        if workspace_names:
            filters.append(["name", "in", workspace_names])

        params = {
            "fields": json.dumps(["name", "is_hidden"]),
            "filters": json.dumps(filters),
            "limit_page_length": 500
        }
        resp = self.session.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            self._log_api_op("get_workspace_visibility", "Workspace", False, resp.status_code, resp.text)
            return {}

        result = {}
        for item in resp.json().get("data", []):
            result[item["name"]] = bool(item.get("is_hidden", 0))
        return result

    def _set_workspace_visibility(self, workspace_name: str, is_hidden: int, public: int, label: str) -> bool:
        """Shared implementation for hide_workspace/show_workspace: sets is_hidden/public via
        REST, falling back to a direct DB write inside the bench container if the REST call
        doesn't stick (e.g. cached bootinfo)."""
        url = f"{self.base_url}/api/resource/Workspace/{workspace_name}"
        resp = self.session.put(url, json={"is_hidden": is_hidden, "public": public}, timeout=15)
        success = resp.status_code == 200
        try:
            from kairon.crm.services.bench_executor import BenchExecutor
            crm_config = Utility.environment.get("crm", {})
            bench_config = crm_config.get("bench", {})
            container_name = BenchExecutor()._resolve_container_name(bench_config)
            script = (
                f"import frappe; frappe.init(site={json.dumps(self.site_name)}); frappe.connect(); "
                f"frappe.db.set_value('Workspace', {json.dumps(workspace_name)}, "
                f"{{'is_hidden': {is_hidden}, 'public': {public}}}); frappe.db.commit(); frappe.clear_cache()"
            )
            cmd = ["docker", "exec", "-w", "/home/frappe/frappe-bench/sites", "-i", container_name, "/home/frappe/frappe-bench/env/bin/python", "-c", script]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            success = res.returncode == 0
        except Exception as e:
            logger.debug(f"[ERPNextClient] {label} container fallback failed: {e}")
        self._log_api_op(label, workspace_name, success, resp.status_code if not success else 200)
        return success

    def hide_workspace(self, workspace_name: str) -> bool:
        """Sets is_hidden = 1 and public = 0 on Workspace document."""
        return self._set_workspace_visibility(workspace_name, 1, 0, "hide_workspace")

    def show_workspace(self, workspace_name: str) -> bool:
        """Sets is_hidden = 0 and public = 1 on Workspace document."""
        return self._set_workspace_visibility(workspace_name, 0, 1, "show_workspace")


    def clear_cache(self) -> bool:
        """
        Clears ERPNext site cache via container Python / Bench command to update bootinfo/Redis.
        """
        try:
            from kairon.crm.services.bench_executor import BenchExecutor
            crm_config = Utility.environment.get("crm", {})
            bench_config = crm_config.get("bench", {})
            container_name = BenchExecutor()._resolve_container_name(bench_config)

            cmd = [
                "docker", "exec", container_name,
                "bench", "--site", self.site_name, "clear-cache"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self._log_api_op("clear_cache", self.site_name, res.returncode == 0, 200 if res.returncode == 0 else 500)
            return res.returncode == 0
        except Exception as e:
            logger.warning(f"[ERPNextClient] Container clear_cache fallback due to: {e}")

        # HTTP Fallback
        url = f"{self.base_url}/api/method/frappe.sessions.clear_cache"
        resp = self.session.post(url, timeout=10)
        return resp.status_code == 200

    def set_default_workspace_for_all_users(self, workspace_name: str):
        """
        Sets default_workspace field on all existing Users to target workspace_name
        and updates site desktop:home_page default.
        This prevents Desk route redirection flicker loops when 'Home' is hidden.
        """
        try:
            url = f"{self.base_url}/api/resource/User"
            params = {
                "fields": json.dumps(["name", "email", "default_workspace"]),
                "limit_page_length": 500
            }
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                users = resp.json().get("data", [])
                for u in users:
                    user_email = u.get("name")
                    if user_email and user_email != "Guest":
                        if u.get("default_workspace") != workspace_name:
                            put_url = f"{self.base_url}/api/resource/User/{user_email}"
                            self.session.put(put_url, json={"default_workspace": workspace_name}, timeout=10)
                self._log_api_op("set_default_workspace_all", workspace_name, True, 200)

            from kairon.crm.services.bench_executor import BenchExecutor
            crm_config = Utility.environment.get("crm", {})
            bench_config = crm_config.get("bench", {})
            container_name = BenchExecutor()._resolve_container_name(bench_config)

            script = f"""
import frappe
frappe.init(site={json.dumps(self.site_name)})
frappe.connect()
frappe.db.set_default('desktop:home_page', {json.dumps(f'workspace/{workspace_name}')})
frappe.db.commit()
"""
            cmd = [
                "docker", "exec", "-w", "/home/frappe/frappe-bench/sites", "-i", container_name,
                "/home/frappe/frappe-bench/env/bin/python", "-c", script
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except Exception as e:
            logger.warning(f"[ERPNextClient] Failed to set default workspace for users: {e}")

    def configure_workspace_visibility(self, selected_module_keys: List[str], catalog: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
        """
        Idempotently hides ALL public workspaces except those belonging to selected_module_keys.
        Also sets default_workspace on users to prevent Desk reload/flicker loops.
        Returns dict: { workspace_name: is_hidden_status }
        """
        if catalog is None:
            disc = self.discover_business_modules()
            catalog = {m["key"]: m for m in disc["modules"]}

        selected_workspaces = set()
        for mod_key in selected_module_keys:
            if mod_key in catalog:
                selected_workspaces.add(catalog[mod_key]["workspace"])
            else:
                selected_workspaces.add(mod_key)

        url = f"{self.base_url}/api/resource/Workspace"
        params = {
            "fields": json.dumps(["name", "title", "module", "is_hidden"]),
            "filters": json.dumps([["public", "=", 1]]),
            "limit_page_length": 500
        }
        resp = self.session.get(url, params=params, timeout=15)
        all_workspaces = resp.json().get("data", []) if resp.status_code == 200 else []

        results = {}
        target_default_workspace = None

        if all_workspaces:
            for ws in all_workspaces:
                ws_name = ws.get("name")
                if not ws_name:
                    continue

                if ws_name in selected_workspaces:
                    self.show_workspace(ws_name)
                    results[ws_name] = False
                    if not target_default_workspace:
                        target_default_workspace = ws_name
                else:
                    self.hide_workspace(ws_name)
                    results[ws_name] = True
        else:
            for mod_key, mod_meta in catalog.items():
                ws_name = mod_meta["workspace"]
                if mod_key in selected_module_keys:
                    self.show_workspace(ws_name)
                    results[ws_name] = False
                    if not target_default_workspace:
                        target_default_workspace = ws_name
                else:
                    self.hide_workspace(ws_name)
                    results[ws_name] = True

        if not target_default_workspace and selected_workspaces:
            target_default_workspace = list(selected_workspaces)[0]

        if target_default_workspace:
            self.set_default_workspace_for_all_users(target_default_workspace)

        # Clear ERPNext cache so bootinfo/Redis is updated immediately
        self.clear_cache()

        return results

    # ─────────────────────────────────────────────────────────────
    # Module Profile Management (Layer 2)
    # ─────────────────────────────────────────────────────────────

    def create_or_update_module_profile(self, profile_name: str, blocked_module_names: List[str]) -> str:
        """
        Idempotently creates or updates a Module Profile doc in ERPNext.
        blocked_module_names are exact frappe_module names to place in block_modules child table.
        """
        url = f"{self.base_url}/api/resource/Module Profile/{profile_name}"
        get_resp = self.session.get(url, timeout=10)

        block_modules_payload = [{"module": m} for m in sorted(list(set(blocked_module_names)))]

        if get_resp.status_code == 200:
            # Profile exists: update it
            update_payload = {"block_modules": block_modules_payload}
            put_resp = self.session.put(url, json=update_payload, timeout=15)
            if put_resp.status_code != 200:
                self._log_api_op("update_module_profile", profile_name, False, put_resp.status_code, put_resp.text)
                raise AppException(f"Failed to update Module Profile '{profile_name}': HTTP {put_resp.status_code}")
            self._log_api_op("update_module_profile", profile_name, True, put_resp.status_code)
            return profile_name
        else:
            # Create new profile
            create_url = f"{self.base_url}/api/resource/Module Profile"
            create_payload = {
                "module_profile_name": profile_name,
                "block_modules": block_modules_payload
            }
            post_resp = self.session.post(create_url, json=create_payload, timeout=15)
            if post_resp.status_code not in (200, 201):
                self._log_api_op("create_module_profile", profile_name, False, post_resp.status_code, post_resp.text)
                raise AppException(f"Failed to create Module Profile '{profile_name}': HTTP {post_resp.status_code}")
            self._log_api_op("create_module_profile", profile_name, True, post_resp.status_code)
            return profile_name

    def assign_module_profile_to_user(self, email: str, profile_name: str) -> bool:
        """
        Assigns a Module Profile to an existing ERPNext user.
        """
        url = f"{self.base_url}/api/resource/User/{email}"
        resp = self.session.put(url, json={"module_profile": profile_name}, timeout=15)
        success = resp.status_code == 200
        self._log_api_op("assign_module_profile", email, success, resp.status_code, resp.text if not success else None)
        if not success:
            raise AppException(f"Failed to assign Module Profile '{profile_name}' to user '{email}': HTTP {resp.status_code}")
        return True

    def get_all_roles(self) -> list:
        """Fetches all role names present in target system."""
        try:
            url = f"{self.base_url}/api/resource/Role"
            resp = self.session.get(url, params={"limit_page_length": 500}, timeout=15)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return [r.get("name") for r in data if "name" in r]
        except Exception as e:
            logger.warning(f"[ERPNextClient] Failed to fetch roles: {e}")
        return []

    def ensure_role_profile(self, profile_name: str, roles: list) -> str:
        """
        Idempotently creates or updates a native Frappe Role Profile DocType.
        """
        url = f"{self.base_url}/api/resource/Role Profile/{profile_name}"
        get_resp = self.session.get(url, timeout=10)

        existing_system_roles = set(self.get_all_roles())
        if existing_system_roles:
            valid_roles = [r for r in roles if r in existing_system_roles]
        else:
            valid_roles = roles
        if not valid_roles:
            valid_roles = roles

        roles_payload = [{"role": r} for r in valid_roles]

        if get_resp.status_code == 200:
            put_resp = self.session.put(url, json={"roles": roles_payload}, timeout=15)
            if put_resp.status_code != 200:
                self._log_api_op("update_role_profile", profile_name, False, put_resp.status_code, put_resp.text)
                logger.warning(f"Failed to update Role Profile '{profile_name}': HTTP {put_resp.status_code}")
                return profile_name
            self._log_api_op("update_role_profile", profile_name, True, put_resp.status_code)
            return profile_name
        else:
            create_url = f"{self.base_url}/api/resource/Role Profile"
            payload = {
                "role_profile": profile_name,
                "roles": roles_payload
            }
            post_resp = self.session.post(create_url, json=payload, timeout=15)
            if post_resp.status_code not in (200, 201):
                self._log_api_op("create_role_profile", profile_name, False, post_resp.status_code, post_resp.text)
                logger.warning(f"Failed to create Role Profile '{profile_name}': HTTP {post_resp.status_code}")
                return profile_name
            self._log_api_op("create_role_profile", profile_name, True, post_resp.status_code)
            return profile_name


    # ─────────────────────────────────────────────────────────────
    # Company, User Management & Role Assignment
    # ─────────────────────────────────────────────────────────────

    def check_company_exists(self, company_name: str) -> bool:
        url = f"{self.base_url}/api/resource/Company/{company_name}"
        response = self.session.get(url, timeout=15)
        return response.status_code == 200

    def create_warehouse_type_if_missing(self, name: str):
        url = f"{self.base_url}/api/resource/Warehouse Type/{name}"
        res = self.session.get(url, timeout=15)
        if res.status_code == 200:
            return
        post_url = f"{self.base_url}/api/resource/Warehouse Type"
        res_post = self.session.post(post_url, json={"name": name}, timeout=15)
        if res_post.status_code not in (200, 201):
            logger.warning(f"[ERPNextClient] Could not create Warehouse Type '{name}': HTTP {res_post.status_code}")

    def create_company(self, company_name: str, abbr: str, default_currency: str, country: str):
        """
        Idempotently creates a company in ERPNext.
        """
        for w_type in ["Transit", "Bonded", "Supplier", "Customer", "Standard"]:
            self.create_warehouse_type_if_missing(w_type)

        if self.check_company_exists(company_name):
            logger.info(f"[ERPNextClient] Company '{company_name}' already exists. Skipping creation.")
            return

        url = f"{self.base_url}/api/resource/Company"
        payload = {
            "company_name": company_name,
            "abbr": abbr,
            "default_currency": default_currency,
            "country": country
        }
        response = self.session.post(url, json=payload, timeout=15)
        if response.status_code not in (200, 201):
            self._log_api_op("create_company", company_name, False, response.status_code, response.text)
            raise AppException(f"Failed to create Company: HTTP {response.status_code}")
        self._log_api_op("create_company", company_name, True, response.status_code)

    def check_user_exists(self, email: str) -> bool:
        url = f"{self.base_url}/api/resource/User/{email}"
        response = self.session.get(url, timeout=15)
        return response.status_code == 200

    def create_erpnext_user(self, email: str, first_name: str, last_name: str, send_welcome_email: bool = True, password: str = None):
        """
        Idempotently creates a user in ERPNext.
        """
        if self.check_user_exists(email):
            logger.info(f"[ERPNextClient] User '{email}' already exists. Skipping creation.")
            return

        url = f"{self.base_url}/api/resource/User"
        payload = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "send_welcome_email": 1 if send_welcome_email else 0,
            "enabled": 1
        }
        if password:
            payload["new_password"] = password

        response = self.session.post(url, json=payload, timeout=15)
        if response.status_code not in (200, 201):
            self._log_api_op("create_user", email, False, response.status_code, response.text)
            raise AppException(f"Failed to create User: HTTP {response.status_code}")
        self._log_api_op("create_user", email, True, response.status_code)

        # The User doctype's insert-time welcome-email hook does not reliably fire via
        # the REST create path on every Frappe build (send_welcome_email persisted 1,
        # but no Email Queue entry was created -- verified empirically). Explicitly
        # trigger the same reset-password-link email via Frappe's own whitelisted
        # 'reset_password' method so the user genuinely receives a set-new-password
        # link rather than silently getting no email at all.
        if send_welcome_email and not password:
            reset_url = f"{self.base_url}/api/method/frappe.core.doctype.user.user.reset_password"
            reset_resp = self.session.post(reset_url, data={"user": email}, timeout=15)
            if reset_resp.status_code != 200:
                logger.warning(f"[ERPNextClient] Welcome/reset-password email trigger failed for '{email}': HTTP {reset_resp.status_code}")
            else:
                self._log_api_op("send_welcome_email", email, True, reset_resp.status_code)

    def assign_roles_and_company(self, email: str, roles: list, company: str, module_profile: Optional[str] = None, default_workspace: Optional[str] = None, role_profile: Optional[str] = None):
        """
        Assigns roles (or a role_profile), a default company, optionally a module_profile, and default_workspace to an existing user.
        """
        url = f"{self.base_url}/api/resource/User/{email}"
        response = self.session.get(url, timeout=15)
        if response.status_code != 200:
            raise AppException(f"Failed to fetch User {email} for role assignment.")

        user_data = response.json().get("data", {})
        existing_roles = [r.get("role") for r in user_data.get("roles", [])]

        payload = {}
        if role_profile:
            payload["role_profile_name"] = role_profile
            payload["role_profiles"] = [{"role_profile": role_profile}]
        else:
            new_roles = user_data.get("roles", [])
            for r in roles:
                if r not in existing_roles:
                    new_roles.append({"role": r})
            payload["roles"] = new_roles


        if module_profile:
            payload["module_profile"] = module_profile
        if default_workspace:
            payload["default_workspace"] = default_workspace


        update_response = self.session.put(url, json=payload, timeout=15)
        if update_response.status_code != 200:
            self._log_api_op("assign_roles_and_company", email, False, update_response.status_code, update_response.text)
            raise AppException(f"Failed to assign roles to User {email}.")

        # Set default company via User Permission -- only when a company was supplied.
        # Tier 1 standalone sites (no erpnext) have no 'Company' DocType, so callers
        # pass company=None there and this step is correctly skipped.
        if company:
            self.assign_company_permission(email, company)
        self._log_api_op("assign_roles_and_company", email, True, update_response.status_code)

    def assign_company_permission(self, email: str, company: str):
        user_perm_url = f"{self.base_url}/api/resource/User Permission"
        filters = json.dumps([
            ["User Permission", "user", "=", email],
            ["User Permission", "allow", "=", "Company"],
            ["User Permission", "for_value", "=", company],
        ])
        check = self.session.get(user_perm_url, params={"filters": filters, "fields": '["name"]'}, timeout=15)
        if check.status_code == 200 and check.json().get("data"):
            logger.info(f"[ERPNextClient] User Permission for company '{company}' and user '{email}' already exists.")
            return

        perm_payload = {
            "user": email,
            "allow": "Company",
            "for_value": company,
            "is_default": 1,
            "apply_to_all_doctypes": 1
        }
        perm_response = self.session.post(user_perm_url, json=perm_payload, timeout=15)
        if perm_response.status_code not in (200, 201):
            if "already exists" in perm_response.text or perm_response.status_code == 409:
                logger.info("[ERPNextClient] User Permission already exists (conflict). Skipping.")
                return
            self._log_api_op("assign_company_permission", email, False, perm_response.status_code, perm_response.text)
            raise AppException(f"Failed to set default company for User {email}.")

        self._log_api_op("assign_company_permission", email, True, perm_response.status_code)

    # ─────────────────────────────────────────────────────────────
    # Verification & Reconciliation Reporting
    # ─────────────────────────────────────────────────────────────

    def verify_module_configuration(
        self,
        selected_module_keys: List[str],
        profile_name: Optional[str] = None,
        user_email: Optional[str] = None
    ) -> ModuleVerificationReport:
        """
        Compares expected module visibility against actual ERPNext state.
        Returns a structured ModuleVerificationReport.
        """
        disc = self.discover_business_modules()
        catalog = {m["key"]: m for m in disc["modules"]}

        expected_selected = [k for k in selected_module_keys if k in catalog]
        expected_blocked_frappe_modules = [
            m["frappe_module"] for k, m in catalog.items() if k not in expected_selected
        ]

        # 1. Check Module Profile
        actual_blocked_modules = []
        profile_matches = True
        if profile_name:
            url = f"{self.base_url}/api/resource/Module Profile/{profile_name}"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                p_data = resp.json().get("data", {})
                raw_blocks = p_data.get("block_modules", [])
                actual_blocked_modules = [b.get("module") for b in raw_blocks if b.get("module")]

            expected_set = set(expected_blocked_frappe_modules)
            actual_set = set(actual_blocked_modules)
            profile_matches = (expected_set == actual_set)

        # 2. Check Workspaces
        ws_names = [m["workspace"] for m in catalog.values()]
        ws_visibility = self.get_workspace_visibility(ws_names)

        ws_entries = []
        workspaces_match = True
        for mod_key, meta in catalog.items():
            ws_name = meta["workspace"]
            expected_hidden = (mod_key not in expected_selected)
            actual_hidden = ws_visibility.get(ws_name, False)
            matches = (expected_hidden == actual_hidden)
            if not matches:
                workspaces_match = False
            ws_entries.append(WorkspaceVerificationEntry(
                module_key=mod_key,
                workspace_name=ws_name,
                expected_hidden=expected_hidden,
                actual_hidden=actual_hidden,
                matches=matches
            ))

        is_fully_consistent = profile_matches and workspaces_match

        return ModuleVerificationReport(
            site=self.host_header,
            expected_selected_modules=expected_selected,
            expected_blocked_modules=expected_blocked_frappe_modules,
            actual_blocked_modules=actual_blocked_modules,
            profile_matches=profile_matches,
            workspaces=ws_entries,
            workspaces_match=workspaces_match,
            is_fully_consistent=is_fully_consistent
        )

    # ─────────────────────────────────────────────────────────────
    # Invitation & User Query Methods
    # ─────────────────────────────────────────────────────────────

    def ensure_default_smtp_account(self, smtp_server: str = "mailpit", smtp_port: int = 1025):
        if self.check_smtp_configured():
            logger.info("[ERPNextClient] Outgoing Email Account is already configured.")
            return

        url = f"{self.base_url}/api/resource/Email Account"
        payload = {
            "email_id": "notifications@mailpit.local",
            "email_account_name": "Notifications",
            "enable_outgoing": 1,
            "default_outgoing": 1,
            "enable_incoming": 0,
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "use_tls": 0,
            "use_ssl": 0,
            "no_smtp_authentication": 1,
            "awaiting_password": 0
        }
        res = self.session.post(url, json=payload, timeout=15)
        if res.status_code in (200, 201):
            logger.info("[ERPNextClient] Default outgoing Email Account created successfully.")
        else:
            logger.warning(f"[ERPNextClient] Failed to create Email Account: Status {res.status_code}")

    def check_smtp_configured(self) -> bool:
        url = f"{self.base_url}/api/resource/Email Account"
        filters = json.dumps([
            ["Email Account", "default_outgoing", "=", 1],
            ["Email Account", "awaiting_password", "=", 0],
        ])
        response = self.session.get(url, params={"filters": filters, "fields": '["name"]'}, timeout=15)
        if response.status_code != 200:
            logger.warning(f"[ERPNextClient] Could not check SMTP config. Status: {response.status_code}")
            return False
        return len(response.json().get("data", [])) > 0

    def get_users(self) -> list:
        url = f"{self.base_url}/api/resource/User"
        fields = '["name", "email", "first_name", "last_name", "enabled", "creation", "role_profile_name"]'
        filters = '[["name", "not in", ["Administrator", "Guest"]]]'
        try:
            response = self.session.get(
                url, params={"fields": fields, "filters": filters, "limit_page_length": 100}, timeout=10
            )
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            logger.error(f"[ERPNextClient] Failed to fetch users: {e}")
            return []

    def invite_user(self, email: str, roles: list, redirect_to_path: str, app_name: str) -> dict:
        url = f"{self.base_url}/api/method/frappe.core.api.user_invitation.invite_by_email"
        payload = {
            "emails": email,
            "roles": roles,
            "redirect_to_path": redirect_to_path,
            "app_name": app_name,
        }
        response = self.session.post(url, json=payload, timeout=30)

        if response.status_code == 417:
            error_msg = response.json().get("exc_type", "") + ": " + response.json().get("message", "")
            if "Role" in error_msg or "role" in error_msg:
                raise AppException(f"Invalid role specified: {error_msg}")
            raise AppException(f"ERPNext invitation error: {error_msg}")

        if response.status_code != 200:
            self._log_api_op("invite_user", email, False, response.status_code, response.text)
            raise AppException(f"Failed to send invitation: HTTP {response.status_code}")

        result = response.json().get("message", {})
        self._log_api_op("invite_user", email, True, response.status_code)
        return result

    def get_invitation_status(self, email: str, app_name: str) -> Optional[dict]:
        url = f"{self.base_url}/api/resource/User Invitation"
        filters = json.dumps([
            ["User Invitation", "email", "=", email],
            ["User Invitation", "app_name", "=", app_name],
        ])
        fields = json.dumps(["name", "email", "status", "app_name", "email_sent_at"])
        response = self.session.get(url, params={"filters": filters, "fields": fields, "order_by": "creation desc", "limit": 1}, timeout=15)
        if response.status_code != 200:
            logger.warning(f"[ERPNextClient] get_invitation_status failed. Status: {response.status_code}")
            return None
        data = response.json().get("data", [])
        return data[0] if data else None

    def cancel_invitation(self, name: str, app_name: str) -> dict:
        url = f"{self.base_url}/api/method/frappe.core.api.user_invitation.cancel_invitation"
        response = self.session.patch(url, json={"name": name, "app_name": app_name}, timeout=15)
        if response.status_code != 200:
            self._log_api_op("cancel_invitation", name, False, response.status_code, response.text)
            raise AppException(f"Failed to cancel invitation '{name}': HTTP {response.status_code}")
        return response.json().get("message", {})

    def get_pending_invitations(self, app_name: str) -> list:
        url = f"{self.base_url}/api/method/frappe.core.api.user_invitation.get_pending_invitations"
        response = self.session.get(url, params={"app_name": app_name}, timeout=15)
        if response.status_code != 200:
            logger.warning(f"[ERPNextClient] get_pending_invitations failed. Status: {response.status_code}")
            return []
        return response.json().get("message", [])

    def verify_user_login(self, email: str, password: str) -> bool:
        session = requests.Session()
        session.headers.update({"Host": self.host_header, "Accept": "application/json"})
        url = f"{self.base_url}/api/method/login"
        try:
            response = session.post(url, data={"usr": email, "pwd": password}, timeout=15)
            return response.status_code == 200
        except Exception:
            return False
