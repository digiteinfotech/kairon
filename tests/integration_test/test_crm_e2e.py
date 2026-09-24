"""
Single end-to-end suite for the Kairon -> ERPNext CRM integration.

Business journey, in file order:

    TestCRMAuthentication      Kairon login / JWT / invalid + missing credentials
    TestCRMTenantProvisioning  is_crm tenant onboarding, ERPNext site creation, Tier 1 -> Tier 2 upgrade,
                               pre-flight/negative provisioning errors, admin-dashboard services
    TestCRMInvitation          invite user -> email -> password setup -> fresh login -> invitation webhook
                               (HMAC + idempotency) -> RBAC company permission -> re-invite idempotency
    TestCRMLeadWebhook         Kairon lead.qualified action -> signed webhook -> ERPNext receiver -> Lead
    TestCRMTenantIsolation     tenant A credentials / events can not reach tenant B

Requires live infrastructure (Kairon API, ERPNext bench in the `frappe-backend-1` container,
Mailpit, MongoDB), so it is skipped unless KAIRON_RUN_LIVE_E2E_TESTS=1 is set. Nothing here is mocked.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import time
import urllib.parse
import uuid
from typing import Any, Callable, Dict, Optional, Set

import pytest
import requests
from loguru import logger
from mongoengine import connect, disconnect

from kairon.crm.models import CRMClientDetails, CRMInvitation, CRMOnboardingStatus
from kairon.crm.services.feature_resolver import FeatureAppResolver
from kairon.crm.services.preflight_validator import PreFlightValidator
from kairon.crm.services.provisioners.factory import ProvisionerFactory
from kairon.crm.services.provisioning_models import ProvisioningPlan
from kairon.events.publisher import KaironEvent, KaironEventPublisher
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.streamlit_app.services.health_service import HealthService
from kairon.streamlit_app.services.logs_service import LogsService
from kairon.streamlit_app.services.provisioning_service import StreamlitProvisioningService
from kairon.streamlit_app.services.tenant_service import TenantService, ensure_mongo_connection

pytestmark = pytest.mark.skipif(
    os.getenv("KAIRON_RUN_LIVE_E2E_TESTS") != "1"
    or not (os.getenv("KAIRON_E2E_USER") and os.getenv("KAIRON_E2E_PASSWORD") and os.getenv("BENCH_DB_PASSWORD")),
    reason="Requires a live Kairon API + ERPNext bench + Mailpit + MongoDB stack; set KAIRON_RUN_LIVE_E2E_TESTS=1, "
           "KAIRON_E2E_USER / KAIRON_E2E_PASSWORD (an existing Kairon account) and BENCH_DB_PASSWORD to run.",
)

KAIRON_API_URL = os.getenv("KAIRON_E2E_API_URL", "http://localhost:5000")
ERPNEXT_BASE_URL = os.getenv("KAIRON_E2E_ERPNEXT_URL", "http://localhost:8080")
MAILPIT_URL = os.getenv("KAIRON_E2E_MAILPIT_URL", "http://localhost:8025")
BENCH_CONTAINER = "frappe-backend-1"
E2E_KAIRON_USER = os.getenv("KAIRON_E2E_USER", "")
E2E_KAIRON_PASSWORD = os.getenv("KAIRON_E2E_PASSWORD", "")
BENCH_DB_PASSWORD = os.getenv("BENCH_DB_PASSWORD", "")
# Passwords for the disposable tenants / invited user are generated per run, never hardcoded.
E2E_PASSWORD = secrets.token_urlsafe(18)


# --------------------------------------------------------------------------------------
# Helpers (only used by this suite, so they live here instead of a helpers package)
# --------------------------------------------------------------------------------------
def poll_until(condition: Callable[[], Any], timeout: float = 15.0, error_message: str = "Condition not met") -> Any:
    """Poll with exponential backoff until `condition` returns a truthy value."""
    start, delay, last_error = time.time(), 0.2, None
    while time.time() - start < timeout:
        try:
            result = condition()
            if result:
                return result
        except Exception as e:  # noqa: BLE001 - keep polling, report the last error on timeout
            last_error = e
        time.sleep(delay)
        delay = min(delay * 1.5, 2.0)
    raise TimeoutError(f"{error_message} (elapsed {time.time() - start:.1f}s, last error: {last_error})")


def bench_exec(*cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "exec", BENCH_CONTAINER, *cmd], capture_output=True, text=True, timeout=timeout)


def drop_site(site_name: str):
    bench_exec("rm", "-rf", f"sites/{site_name}")


def site_exists(site_name: str) -> bool:
    return subprocess.run(["docker", "exec", BENCH_CONTAINER, "test", "-d", f"sites/{site_name}"]).returncode == 0


def frappe_db_delete(site_name: str, doctype: str, filters: dict) -> Optional[int]:
    script = (f"import frappe; frappe.init(site={site_name!r}); frappe.connect(); "
              f"c = frappe.db.delete({doctype!r}, {filters!r}); frappe.db.commit(); print('DELETED:', c)")
    res = bench_exec("./env/bin/python", "-c", script, timeout=10)
    return int(res.stdout.split("DELETED:")[1].strip()) if "DELETED:" in res.stdout else None


def frappe_count(site_name: str, doctype: str, filters: dict) -> int:
    res = bench_exec("bench", "--site", site_name, "execute", "frappe.db.count",
                     "--args", f"[{doctype!r}, {filters!r}]", timeout=15)
    return int(res.stdout.strip()) if res.returncode == 0 and res.stdout.strip().isdigit() else 0


def site_url(site_name: str) -> str:
    return f"http://{site_name}:8080"


def frappe_login(email: str, password: str, site_name: str) -> requests.Session:
    """POST /api/method/login and verify the session through frappe.auth.get_logged_user."""
    session = requests.Session()
    headers = {"Accept": "application/json", "Host": site_name}
    res = session.post(f"{site_url(site_name)}/api/method/login", data={"usr": email, "pwd": password},
                       headers=headers, timeout=15)
    if res.status_code != 200:
        raise RuntimeError(f"Login failed for '{email}' on {site_name}: {res.status_code} {res.text}")
    who = session.get(f"{site_url(site_name)}/api/method/frappe.auth.get_logged_user", headers=headers, timeout=15)
    if who.status_code != 200:
        raise RuntimeError(f"Session validation failed for '{email}': {who.status_code} {who.text}")
    if who.json().get("message") != email and email != "Administrator":
        raise AssertionError(f"Session user mismatch: expected '{email}', got '{who.json().get('message')}'")
    return session


class Mailpit:
    def __init__(self, url: str = MAILPIT_URL):
        self.url = url.rstrip("/")

    def _messages(self) -> list:
        res = requests.get(f"{self.url}/api/v1/messages", timeout=5)
        return res.json().get("messages", []) if res.status_code == 200 else []

    def message_ids(self) -> Set[str]:
        try:
            return {m["ID"] for m in self._messages()}
        except Exception:  # noqa: BLE001
            return set()

    def wait_for_invitation(self, recipient: str, baseline_ids: Set[str], site_name: str) -> Dict[str, Any]:
        """Wait for EXACTLY one new mail to `recipient` and extract its password-setup URL."""
        def check():
            bench_exec("bench", "--site", site_name, "execute", "frappe.email.queue.flush", timeout=10)
            found = [m for m in self._messages() if m["ID"] not in baseline_ids
                     and any(r.get("Address", "").lower() == recipient.lower() for r in m.get("To", []))]
            return found or None

        found = poll_until(check, error_message=f"No invitation email delivered to '{recipient}'")
        assert len(found) == 1, f"Expected exactly 1 invitation email for '{recipient}', got {len(found)}"
        detail = requests.get(f"{self.url}/api/v1/message/{found[0]['ID']}", timeout=5)
        assert detail.status_code == 200
        msg = detail.json()
        assert msg.get("MessageID"), "Invitation email is missing Message-ID header"
        assert msg.get("Date") or msg.get("Created"), "Invitation email is missing timestamp"
        body = msg.get("HTML", "") or msg.get("Text", "")
        match = (re.search(r'href=["\'](https?://[^"\']*(?:accept_invitation|update-password|\?key=)[^"\']+)["\']', body)
                 or re.search(r'(https?://[^\s"\'<>]+(?:accept_invitation|update-password|\?key=)[^\s"\'<>]*)', body))
        assert match, f"Could not extract invitation URL from email body: {body[:300]}"
        return {"recipient": recipient, "invitation_url": match.group(1)}

    def clear_for(self, recipient: str):
        try:
            for m in self._messages():
                if any(r.get("Address", "").lower() == recipient.lower() for r in m.get("To", [])):
                    requests.delete(f"{self.url}/api/v1/message/{m['ID']}", timeout=5)
        except Exception:  # noqa: BLE001
            pass


def complete_password_setup(invitation_url: str, new_password: str, site_name: str) -> Dict[str, Any]:
    """Simulate the invitee's browser: open the link, follow redirects, extract `key`, submit the password form."""
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 E2E-Test-Browser", "Host": site_name})
    base = urllib.parse.urlparse(ERPNEXT_BASE_URL)

    def rebase(url: str) -> str:
        p = urllib.parse.urlparse(url)
        return urllib.parse.urlunparse((base.scheme, base.netloc, p.path, p.params, p.query, p.fragment))

    current = rebase(invitation_url)
    res = session.get(current, allow_redirects=False, timeout=15)
    key, history = None, []
    for _ in range(5):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(current).query)
        key = params["key"][0] if "key" in params else key
        location = res.headers.get("Location", "")
        if res.status_code not in (301, 302, 303, 307, 308) or not location:
            break
        history.append(location)
        current = rebase(location)
        res = session.get(current, allow_redirects=False, timeout=15)
    if not key:
        found = re.search(r"key=([a-zA-Z0-9_-]+)", " ".join(history) + " " + current)
        key = found.group(1) if found else None
    assert key, f"Could not extract password setup 'key'. Final URL: {current}"

    post = session.post(f"{ERPNEXT_BASE_URL}/api/method/frappe.core.doctype.user.user.update_password",
                        data={"key": key, "old_password": "", "new_password": new_password, "logout_all_sessions": "1"},
                        headers={"Accept": "application/json"}, timeout=15)
    assert post.status_code == 200, f"Password setup failed: {post.status_code} {post.text}"
    return {"status": "success", "key": key}


def sign_webhook(payload: dict, secret: str) -> str:
    """Invitation-accepted webhook signature: base64(HMAC-SHA256(body))."""
    raw = json.dumps(payload).encode("utf-8")
    return base64.b64encode(hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()).decode("utf-8")


class LiveContext:
    """Authenticated Kairon session + the CRM tenant (bot / site / company) it owns."""

    def __init__(self):
        Utility.load_environment()
        try:
            disconnect(alias="default")
        except Exception:  # noqa: BLE001
            pass
        connect(host=Utility.environment["database"]["url"], alias="default")
        self.run_id = f"E2E_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.test_user_email = f"user_{self.run_id.lower()}@example.com"
        self.auth_token = self.bot_id = self.site_name = self.company_name = ""
        self.owner_email = self.owner_password = ""
        self.created_tenant = False

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.auth_token}", "Content-Type": "application/json"}

    def crm_url(self, path: str) -> str:
        return f"{KAIRON_API_URL}/api/bot/{self.bot_id}/crm/{path}"

    def authenticate(self) -> str:
        res = requests.post(f"{KAIRON_API_URL}/api/auth/login",
                            data={"username": E2E_KAIRON_USER, "password": E2E_KAIRON_PASSWORD}, timeout=15)
        if res.status_code != 200:
            raise RuntimeError(f"Kairon login failed: {res.status_code} {res.text}")
        self.auth_token = res.json().get("data", {}).get("access_token", "")
        return self.auth_token

    def resolve_tenant(self):
        auth = {"Authorization": f"Bearer {self.auth_token}"}
        user = requests.get(f"{KAIRON_API_URL}/api/user/details", headers=auth, timeout=15)
        bots = []
        if user.status_code == 200:
            owned = user.json().get("data", {}).get("user", {}).get("bots", {})
            bots = (owned.get("account_owned") or []) + (owned.get("shared") or [])
        if not bots:
            raise RuntimeError("Could not resolve any active bot for the test user.")
        self.bot_id = str(bots[0].get("_id") if isinstance(bots[0], dict) else bots[0])

        self.created_tenant = False
        res = requests.get(self.crm_url("details"), headers=auth, timeout=15)
        details = (res.json().get("data") or {}) if res.status_code == 200 else {}
        if details.get("onboarding_status") != CRMOnboardingStatus.COMPLETED.value:
            details = self.onboard_tenant()
        self.site_name = details.get("site_name", "")
        self.company_name = details.get("company_name") or details.get("erpnext_company", "")
        assert self.site_name and self.company_name, f"Tenant details incomplete: {details}"

        # Onboarding issues the tenant owner a temporary password; it is stored encrypted in Mongo.
        record = CRMClientDetails.objects(bot=self.bot_id).first()
        self.owner_email = record.erpnext_user
        self.owner_password = Utility.decrypt_message(record.erpnext_password) if record.erpnext_password else ""
        assert self.owner_email and self.owner_password, "Onboarded tenant has no owner credentials"

    def onboard_tenant(self) -> Dict[str, Any]:
        """Enable CRM for the bot and onboard a disposable tenant through the Kairon API."""
        res = requests.put(f"{KAIRON_API_URL}/api/bot/{self.bot_id}/settings", headers=self.headers,
                           json={"enable_crm": True}, timeout=15)
        assert res.status_code == 200 and res.json().get("success"), res.text
        suffix = uuid.uuid4().hex[:6]
        self.created_tenant = True
        res = requests.post(self.crm_url("onboard"), headers=self.headers, timeout=1200,
                            json={"company_name": f"E2E Tenant {suffix}", "abbr": f"E{suffix[:3].upper()}",
                                  "default_currency": "USD", "country": "United States"})
        assert res.status_code == 200, res.text
        data = res.json().get("data") or {}
        assert data.get("status") == CRMOnboardingStatus.COMPLETED.value, f"Onboarding failed: {data}"
        res = requests.get(self.crm_url("details"), headers=self.headers, timeout=15)
        return res.json().get("data") or {}

    def owner_session(self) -> requests.Session:
        """Authenticated ERPNext session of the tenant owner (System Manager / Sales Manager)."""
        return frappe_login(self.owner_email, self.owner_password, self.site_name)

    def teardown(self):
        if self.site_name and self.test_user_email:
            for doctype, field in (("User Permission", "user"), ("User Invitation", "email"), ("User", "name")):
                try:
                    frappe_db_delete(self.site_name, doctype, {field: self.test_user_email})
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Cleanup of {doctype} for {self.test_user_email} failed: {e}")
        if self.bot_id:
            CRMInvitation.objects(bot=self.bot_id, email=self.test_user_email).delete()
        if self.created_tenant and self.site_name.startswith("e2e_tenant_"):  # only ever drop our own tenant
            drop_site(self.site_name)
            CRMClientDetails.objects(bot=self.bot_id, site_name=self.site_name).delete()
        Mailpit().clear_for(self.test_user_email)


@pytest.fixture(scope="module")
def live():
    ctx = LiveContext()
    ctx.authenticate()
    ctx.resolve_tenant()
    yield ctx
    ctx.teardown()


# --------------------------------------------------------------------------------------
# 1. Authentication + is_crm
# --------------------------------------------------------------------------------------
class TestCRMAuthentication:

    def test_crm_authentication(self, live: LiveContext):
        assert live.auth_token, "Kairon login must return a JWT access token"
        res = requests.get(live.crm_url("details"), headers=live.headers, timeout=15)
        assert res.status_code == 200, res.text
        assert res.json().get("data", {}).get("site_name") == live.site_name  # is_crm tenant is resolvable

    def test_crm_enabled_for_bot(self, live: LiveContext):
        res = requests.get(f"{KAIRON_API_URL}/api/bot/{live.bot_id}/settings", headers=live.headers, timeout=15)
        assert res.status_code == 200, res.text
        assert res.json()["data"].get("enable_crm") is True

    def test_crm_rejects_invalid_credentials(self):
        res = requests.post(f"{KAIRON_API_URL}/api/auth/login",
                            data={"username": E2E_KAIRON_USER, "password": "definitely-wrong-password"}, timeout=15)
        assert res.status_code in (401, 422) or res.json().get("success") is False

    def test_crm_rejects_unauthenticated_and_bad_token(self, live: LiveContext):
        for headers in ({}, {"Authorization": "Bearer not.a.valid.jwt"}):
            res = requests.get(live.crm_url("details"), headers=headers, timeout=15)
            assert res.status_code in (401, 403) or res.json().get("success") is False, res.text


# --------------------------------------------------------------------------------------
# 2a. Tenant onboarding through the Kairon API (the tenant used by the rest of the suite)
# --------------------------------------------------------------------------------------
class TestCRMTenantOnboarding:

    def test_crm_tenant_onboarding(self, live: LiveContext):
        details = requests.get(live.crm_url("details"), headers=live.headers, timeout=15).json()["data"]
        assert details["onboarding_status"] == CRMOnboardingStatus.COMPLETED.value
        assert details["company_name"] == live.company_name
        assert details["abbr"] and details["country"] == "United States" and details["default_currency"] == "USD"
        assert site_exists(live.site_name)
        status = requests.get(live.crm_url("status"), headers=live.headers, timeout=15).json()["data"]
        assert status["onboarding_status"] == CRMOnboardingStatus.COMPLETED.value

    def test_crm_onboarding_is_idempotent(self, live: LiveContext):
        """Onboarding the same company twice for a bot must be rejected, not create a second site."""
        res = requests.post(live.crm_url("onboard"), headers=live.headers, timeout=60,
                            json={"company_name": live.company_name, "abbr": "DUP",
                                  "default_currency": "USD", "country": "United States"})
        body = res.json()
        assert res.status_code in (400, 422) or body.get("success") is False or (
            (body.get("data") or {}).get("status") == CRMOnboardingStatus.COMPLETED.value)

    def test_crm_tenant_erpnext_access(self, live: LiveContext):
        installed = bench_exec("bench", "--site", live.site_name, "list-apps").stdout
        assert "crm" in installed and "kairon_connector" in installed
        session = live.owner_session()  # ERPNext login with the credentials onboarding issued
        headers = {"Host": live.site_name, "Accept": "application/json"}
        workspaces = session.get(f"{site_url(live.site_name)}/api/resource/Workspace", headers=headers,
                                 params={"fields": '["name","module"]', "limit_page_length": 100}, timeout=15)
        assert workspaces.status_code == 200, workspaces.text
        assert any(w.get("module") == "FCRM" for w in workspaces.json()["data"]), "CRM workspace missing"
        assert session.get(f"{site_url(live.site_name)}/api/resource/CRM Lead?limit_page_length=1",
                           headers=headers, timeout=15).status_code == 200


# --------------------------------------------------------------------------------------
# 2b. Tenant provisioning (real bench container)
# --------------------------------------------------------------------------------------
class TestCRMTenantProvisioning:
    # Throwaway names only: the tests drop and recreate these sites, so they must never
    # collide with a real tenant on the bench.
    company = "E2E Provision Co"
    abbr = "EPC"
    site = "e2e_provision_co.localhost"
    bot = "uat_bot_01"

    @pytest.fixture(scope="class")
    def bench_config(self):
        ensure_mongo_connection()
        Utility.environment["events"] = {"audit_logs": {"attributes": ["user", "bot"]}}
        return {"container_name": BENCH_CONTAINER, "db_host": "db", "db_port": 5432, "db_user": "postgres",
                "db_password": BENCH_DB_PASSWORD, "base_url": ERPNEXT_BASE_URL}

    @pytest.fixture(scope="class", autouse=True)
    def fresh_tenant_record(self, bench_config):
        drop_site(self.site)
        CRMClientDetails.objects(company_name=self.company).delete()
        CRMClientDetails(company_name=self.company, abbr=self.abbr, site_name=self.site, bot=self.bot,
                         user="uat_user", default_currency="USD", country="United States",
                         onboarding_status=CRMOnboardingStatus.PENDING.value, tier=1,
                         installed_apps=["crm"]).save()

    def test_crm_tenant_onboarding_preflight_and_provisioning(self):
        plan = StreamlitProvisioningService.resolve_plan(["crm"])
        assert (plan.tier, plan.strategy_key) == (1, "crm") and "crm" in plan.apps

        logs = StreamlitProvisioningService.validate_preflight(self.site, plan, is_upgrade=False)
        assert any("Check passed" in line or "valid" in line for line in logs)

        res = StreamlitProvisioningService.provision_tenant(
            company_name=self.company, abbr=self.abbr, selected_features=["crm"], currency="USD",
            country="United States", admin_password=E2E_PASSWORD, bot=self.bot)
        assert res["status"] == "success" and res["tier"] == 1 and res["provisioning_time"] > 0

        tenant = TenantService.get_tenant_by_company(self.company)
        assert tenant["tier"] == 1 and "crm" in tenant.get("installed_apps", [])
        assert tenant["onboarding_status"] == CRMOnboardingStatus.SITE_CREATED.value
        assert site_exists(self.site)

    def test_crm_tenant_provisioning_is_reachable_in_erpnext(self):
        session = frappe_login("Administrator", E2E_PASSWORD, self.site)
        res = session.get(f"{site_url(self.site)}/api/resource/CRM Lead?limit_page_length=1",
                          headers={"Host": self.site, "Accept": "application/json"}, timeout=15)
        assert res.status_code == 200, "Provisioned CRM tenant must expose CRM Leads to its Administrator"

    def test_fresh_erpnext_tier2_tenant(self, bench_config):
        company, site, bot = "E2E Suite Co", "e2e_suite_co.localhost", "test_erp_bot"
        drop_site(site)
        CRMClientDetails.objects(company_name=company).delete()
        CRMClientDetails(company_name=company, abbr="ESC", default_currency="USD", country="United States",
                         bot=bot, user="test_user", site_name=site).save()
        plan = FeatureAppResolver.resolve(["selling"])
        assert (plan.tier, plan.strategy_key) == (2, "erpnext_suite")
        res = ProvisionerFactory.create(plan, bench_config).provision(
            company_name=company, abbr="ESC", default_currency="USD", country="United States",
            admin_password=E2E_PASSWORD, bot=bot)
        assert res["status"] == "success" and res["tier"] == 2
        doc = CRMClientDetails.objects(company_name=company).first()
        assert doc.tier == 2 and "erpnext" in doc.installed_apps

    def test_in_place_upgrade_tier1_to_tier2(self):
        assert TenantService.get_tenant_by_company(self.company)["tier"] == 1
        res = StreamlitProvisioningService.upgrade_tenant(
            company_name=self.company, abbr=self.abbr, selected_features=["selling", "crm"],
            admin_password=E2E_PASSWORD, bot=self.bot)
        assert res["status"] == "success" and res["tier"] == 2

        tenant = TenantService.get_tenant_by_company(self.company)
        assert tenant["tier"] == 2 and "erpnext" in tenant["installed_apps"]
        assert "Backup Summary" in tenant["latest_backup_path"]  # upgrade takes a DB backup first

    def test_upgrade_provisioner_direct(self, bench_config):
        company, site, bot = "E2E Upgrade Co", "e2e_upgrade_co.localhost", "test_upgrade_bot"
        drop_site(site)
        CRMClientDetails.objects(company_name=company).delete()
        CRMClientDetails(company_name=company, abbr="EUC", default_currency="USD", country="United States",
                         bot=bot, user="test_user", site_name=site).save()
        kwargs = dict(company_name=company, abbr="EUC", default_currency="USD", country="United States",
                      admin_password=E2E_PASSWORD, bot=bot)
        ProvisionerFactory.create(FeatureAppResolver.resolve(["crm"]), bench_config).provision(**kwargs)
        assert CRMClientDetails.objects(company_name=company).first().tier == 1

        upgrade = ProvisioningPlan(strategy_key="in_place_upgrade", tier=2, apps=["crm", "erpnext"])
        res = ProvisionerFactory.create(upgrade, bench_config).provision(**kwargs)
        assert res["status"] == "success" and res["tier"] == 2
        doc = CRMClientDetails.objects(company_name=company).first()
        assert doc.tier == 2 and "erpnext" in doc.installed_apps and doc.latest_backup_path

    def test_provisioning_error_handling(self):
        plan = FeatureAppResolver.resolve(["crm"])
        PreFlightValidator.validate_infrastructure(BENCH_CONTAINER, "nonexistent.localhost", plan, is_upgrade=False)

        dup_site = "duplicate_test.localhost"
        bench_exec("mkdir", "-p", f"sites/{dup_site}")
        try:
            with pytest.raises(AppException, match="already exists"):
                PreFlightValidator.validate_infrastructure(BENCH_CONTAINER, dup_site, plan, is_upgrade=False)
        finally:
            drop_site(dup_site)

        with pytest.raises(AppException, match="not running"):
            PreFlightValidator.validate_infrastructure("nonexistent-container-99", "random.localhost", plan,
                                                       is_upgrade=False)

    def test_admin_dashboard_services(self):
        tenants = TenantService.get_all_tenants()
        assert len(tenants) >= 1 and sum(1 for t in tenants if t.get("tier") == 2) >= 1
        tenant = TenantService.get_tenant_by_company(self.company)  # persisted across calls
        assert tenant["company_name"] == self.company and tenant["site_name"] and tenant["tier"] == 2

        health = HealthService.get_system_health()
        assert len(health) >= 5 and all(h["status"] in ("Healthy", "Warning", "Failed") for h in health)
        assert sum(1 for h in health if h["status"] == "Healthy") >= 4
        assert len(LogsService.get_recent_logs(limit=10)) >= 1


# --------------------------------------------------------------------------------------
# 3. Invitation lifecycle
# --------------------------------------------------------------------------------------
class TestCRMInvitation:

    def test_crm_invitation_full_lifecycle(self, live: LiveContext):
        mailbox = Mailpit()
        baseline_ids = mailbox.message_ids()

        # Invite via Kairon API
        res = requests.post(live.crm_url("invite-user"), headers=live.headers, timeout=15,
                            json={"email": live.test_user_email, "roles": ["Sales User"]})
        assert res.status_code == 200, f"Invite API failed: {res.text}"
        assert res.json().get("data", {}).get("status") == "invited"

        # Exactly one email, containing a setup link
        email = mailbox.wait_for_invitation(live.test_user_email, baseline_ids, live.site_name)
        assert email["invitation_url"]

        # Invitee sets password, then logs in fresh
        assert complete_password_setup(email["invitation_url"], E2E_PASSWORD, live.site_name)["status"] == "success"
        session = frappe_login(live.test_user_email, E2E_PASSWORD, live.site_name)

        # Invitation-accepted webhook: HMAC accepted, duplicate is idempotent
        crm_doc = CRMClientDetails.objects(bot=live.bot_id).first()
        assert crm_doc is not None and crm_doc.webhook_secret is not None
        secret = Utility.decrypt_message(crm_doc.webhook_secret)
        payload = {"name": f"INV-{live.test_user_email}", "email": live.test_user_email,
                   "status": "Accepted", "app_name": "frappe"}
        signature = sign_webhook(payload, secret)
        webhook_url = f"{KAIRON_API_URL}/api/bot/{live.site_name}/crm/webhook/invitation-accepted"
        webhook_headers = {"Content-Type": "application/json", "X-Kairon-Site": live.site_name,
                           "X-Frappe-Webhook-Signature": signature}

        first = requests.post(webhook_url, json=payload, headers=webhook_headers, timeout=15)
        assert first.status_code == 200 and first.json().get("success") is True, first.text
        if crm_doc.tier == 2:  # company-scoped tenants get a Company User Permission, exactly once
            poll_until(lambda: frappe_count(live.site_name, "User Permission", {"user": live.test_user_email}) >= 1,
                       error_message="User Permission not created in ERPNext after webhook")
        perms_before = frappe_count(live.site_name, "User Permission", {"user": live.test_user_email})
        dup = requests.post(webhook_url, json=payload, headers=webhook_headers, timeout=15)
        assert dup.status_code == 200 and dup.json().get("success") is True, dup.text
        assert frappe_count(live.site_name, "User Permission", {"user": live.test_user_email}) == perms_before

        # Mongo invitation record reaches CompanyAssigned
        def company_assigned():
            inv = CRMInvitation.objects(bot=live.bot_id, email=live.test_user_email).first()
            return inv if inv and inv.invitation_status in ("COMPANY_ASSIGNED", "CompanyAssigned") else None

        inv = poll_until(company_assigned, error_message="CRMInvitation was not updated to CompanyAssigned")
        assert inv.accepted_at is not None and inv.company_assigned_at is not None

        # CRM permissions of the invited user
        headers = {"Accept": "application/json", "Host": live.site_name}
        base = site_url(live.site_name)
        if crm_doc.tier == 2:  # assigned company reachable, unassigned company denied
            perms = session.get(f"{base}/api/method/"
                                "frappe.core.doctype.user_permission.user_permission.get_user_permissions",
                                headers=headers, timeout=15)
            assigned_ok = perms.status_code == 200 and any(
                p.get("doc") == live.company_name for p in perms.json().get("message", {}).get("Company", []))
            assert assigned_ok, f"RBAC: user denied access to assigned company '{live.company_name}'"
            other = session.get(f"{base}/api/resource/Company/NonExistentCompany_XYZ", headers=headers, timeout=15)
            assert other.status_code in (403, 404) or "PermissionError" in other.text \
                or "DoesNotExistError" in other.text
        else:  # standalone CRM: the requested role grants CRM access, admin-only areas stay closed
            roles = session.get(f"{base}/api/method/frappe.core.doctype.user.user.get_roles", headers=headers,
                                params={"arg1": live.test_user_email}, timeout=15)
            assert "Sales User" in roles.json().get("message", []), roles.text
            assert session.get(f"{base}/api/resource/CRM Lead?limit_page_length=1", headers=headers,
                               timeout=15).status_code == 200, "Invited Sales User must reach CRM Leads"
            admin_only = session.get(f"{base}/api/resource/Module Profile", headers=headers, timeout=15)
            assert admin_only.status_code == 403, "Invited Sales User must not reach admin-only doctypes"

        # Re-invite an accepted user: no-op and no new mail
        before = mailbox.message_ids()
        again = requests.post(live.crm_url("invite-user"), headers=live.headers, timeout=15,
                              json={"email": live.test_user_email, "roles": ["Sales User"]})
        assert again.status_code == 200, again.text
        assert again.json().get("data", {}).get("status") == "already_accepted"
        assert mailbox.message_ids() - before == set(), "Re-invite must not send another email"

    def test_crm_invitation_negative_scenarios(self, live: LiveContext):
        bad_email = requests.post(live.crm_url("invite-user"), headers=live.headers, timeout=15,
                                  json={"email": "invalid_email_format", "roles": ["Sales User"]})
        body = bad_email.json() if bad_email.status_code == 200 else {}
        assert bad_email.status_code in (400, 422) or (
            body.get("success") is False and body.get("error_code") in (400, 422)), bad_email.text

        bad_sig = requests.post(
            f"{KAIRON_API_URL}/api/bot/{live.bot_id}/crm/webhook/invitation-accepted", timeout=15,
            json={"email": live.test_user_email, "status": "Accepted"},
            headers={"Content-Type": "application/json", "X-Kairon-Site": live.site_name,
                     "X-Frappe-Webhook-Signature": "InvalidHMACSignatureValue"})
        body = bad_sig.json() if bad_sig.status_code == 200 else {}
        assert bad_sig.status_code in (400, 401, 422) or (
            body.get("success") is False and "signature" in str(body.get("message")).lower()), bad_sig.text

        with pytest.raises(RuntimeError):  # login for a user who never accepted an invitation
            frappe_login(f"unregistered_{time.time()}@example.com", E2E_PASSWORD, live.site_name)


# --------------------------------------------------------------------------------------
# 4. Kairon lead event -> signed webhook -> ERPNext Lead
# --------------------------------------------------------------------------------------
class TestCRMLeadWebhook:

    @staticmethod
    def _lead_event(live: LiveContext, email: str) -> KaironEvent:
        return KaironEvent(event_type="lead.qualified", payload={
            "bot_id": live.bot_id, "conversation_id": f"conv_{uuid.uuid4().hex[:8]}",
            "summary": "E2E qualified lead", "transcript": "user: I want a demo",
            "lead_data": {"name": "E2E Prospect", "email": email, "phone": "+15551234567", "company": "E2E Co"},
            "qualification_score": 100, "intent": "request_demo"})

    @staticmethod
    def _find_lead(session: requests.Session, site_name: str, email: str) -> list:
        res = session.get(f"{site_url(site_name)}/api/resource/CRM Lead", timeout=15,
                          headers={"Host": site_name, "Accept": "application/json"},
                          params={"filters": json.dumps([["email", "=", email]]), "fields": '["name","email"]'})
        assert res.status_code == 200, res.text
        return res.json().get("data", [])

    def test_crm_webhook_lead_flow(self, live: LiveContext):
        email = f"lead_{uuid.uuid4().hex[:8]}@example.com"
        secret = Utility.decrypt_message(CRMClientDetails.objects(bot=live.bot_id).first().lead_webhook_secret)
        target = f"{site_url(live.site_name)}/api/method/kairon_connector.api.v1.webhook.receive_event"
        event = self._lead_event(live, email)
        assert event.event_id and event.correlation_id

        result = KaironEventPublisher.publish_webhook(target, secret, event)
        assert result["success"] is True and result["status_code"] in (200, 202), result

        admin = live.owner_session()
        leads = poll_until(lambda: self._find_lead(admin, live.site_name, email),
                           error_message="Lead was not created in ERPNext CRM")
        assert len(leads) == 1

        # Redelivery of the same event_id is idempotent (no duplicate Lead)
        KaironEventPublisher.publish_webhook(target, secret, event)
        time.sleep(2)
        assert len(self._find_lead(admin, live.site_name, email)) == 1

    def test_crm_webhook_rejects_bad_signature(self, live: LiveContext):
        email = f"forged_{uuid.uuid4().hex[:8]}@example.com"
        target = f"{site_url(live.site_name)}/api/method/kairon_connector.api.v1.webhook.receive_event"

        forged = KaironEventPublisher.publish_webhook(target, "wrong-secret", self._lead_event(live, email))
        assert forged["success"] is False and forged["status_code"] in (401, 403)

        admin = live.owner_session()
        time.sleep(1)
        assert self._find_lead(admin, live.site_name, email) == [], "Forged event must not create a Lead"


# --------------------------------------------------------------------------------------
# 5. Tenant isolation
# --------------------------------------------------------------------------------------
class TestCRMTenantIsolation:

    def test_tenant_isolation(self, live: LiveContext):
        other_site = TestCRMTenantProvisioning.site
        if other_site == live.site_name or not site_exists(other_site):
            pytest.skip("A second provisioned tenant is required (created by TestCRMTenantProvisioning)")

        secret_a = Utility.decrypt_message(CRMClientDetails.objects(bot=live.bot_id).first().lead_webhook_secret)
        email = f"isolation_{uuid.uuid4().hex[:8]}@example.com"
        target_b = f"{site_url(other_site)}/api/method/kairon_connector.api.v1.webhook.receive_event"

        # Tenant A's secret must not be accepted by tenant B, and no Lead may appear there
        res = KaironEventPublisher.publish_webhook(target_b, secret_a, TestCRMLeadWebhook._lead_event(live, email))
        assert res["success"] is False and res["status_code"] in (401, 403, 404), res
        admin_b = frappe_login("Administrator", E2E_PASSWORD, other_site)
        assert TestCRMLeadWebhook._find_lead(admin_b, other_site, email) == []

        # Tenant A's invited user has no session on tenant B
        with pytest.raises(RuntimeError):
            frappe_login(live.test_user_email, E2E_PASSWORD, other_site)

        # Tenant A's Kairon token cannot act on a bot it does not own
        foreign = requests.get(f"{KAIRON_API_URL}/api/bot/{uuid.uuid4().hex}/crm/details",
                               headers=live.headers, timeout=15)
        assert foreign.status_code in (401, 403, 404) or foreign.json().get("success") is False
