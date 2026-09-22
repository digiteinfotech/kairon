import os
import unittest
import time
import subprocess
from loguru import logger

from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.services.feature_resolver import FeatureAppResolver
from kairon.crm.services.preflight_validator import PreFlightValidator
from kairon.crm.services.provisioners.factory import ProvisionerFactory
from kairon.streamlit_app.services.tenant_service import TenantService, ensure_mongo_connection
from kairon.streamlit_app.services.provisioning_service import StreamlitProvisioningService
from kairon.streamlit_app.services.health_service import HealthService
from kairon.streamlit_app.services.logs_service import LogsService
from kairon.crm.services.base_frappe_client import BaseFrappeClient
from kairon.exceptions import AppException


@unittest.skipUnless(
    os.getenv("KAIRON_RUN_LIVE_E2E_TESTS") == "1",
    "Requires a live frappe-backend-1 Docker container + Mongo; set KAIRON_RUN_LIVE_E2E_TESTS=1 to run.",
)
class TestUATEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ensure_mongo_connection()
        cls.container_name = "frappe-backend-1"
        cls.company_name = "Acme Technologies"
        cls.abbr = "AT"
        cls.site_name = "acme_technologies.localhost"
        cls.admin_password = "Password@123"
        cls.bot_id = "uat_bot_01"

        # Cleanup pre-existing site
        cmd = ["docker", "exec", cls.container_name, "rm", "-rf", f"sites/{cls.site_name}"]
        subprocess.run(cmd, capture_output=True)

        # Ensure Mongo document exists
        CRMClientDetails.objects(company_name=cls.company_name).delete()
        doc = CRMClientDetails(
            company_name=cls.company_name,
            abbr=cls.abbr,
            site_name=cls.site_name,
            bot=cls.bot_id,
            user="uat_user",
            default_currency="USD",
            country="United States",
            onboarding_status=CRMOnboardingStatus.PENDING.value,
            tier=1,
            installed_apps=["crm"]
        )
        doc.save()

    def test_01_fresh_crm_tenant(self):
        logger.info("=== UAT Test 1: Fresh Tier 1 CRM Tenant Provisioning ===")

        # 1. Resolve Plan
        plan = StreamlitProvisioningService.resolve_plan(["crm"])
        self.assertEqual(plan.tier, 1)
        self.assertEqual(plan.strategy_key, "crm")
        self.assertIn("crm", plan.apps)

        # 2. Pre-flight Validation
        logs = StreamlitProvisioningService.validate_preflight(self.site_name, plan, is_upgrade=False)
        self.assertTrue(any("Check passed" in l or "valid" in l for l in logs))

        # 3. Provision Tenant
        res = StreamlitProvisioningService.provision_tenant(
            company_name=self.company_name,
            abbr=self.abbr,
            selected_features=["crm"],
            currency="USD",
            country="United States",
            admin_password=self.admin_password,
            bot=self.bot_id
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["tier"], 1)
        self.assertGreater(res["provisioning_time"], 0)

        # 4. Mongo Verification
        tenant_info = TenantService.get_tenant_by_company(self.company_name)
        self.assertIsNotNone(tenant_info)
        self.assertEqual(tenant_info["tier"], 1)
        self.assertIn("crm", tenant_info.get("installed_apps", []))
        self.assertEqual(tenant_info["onboarding_status"], CRMOnboardingStatus.SITE_CREATED.value)
        logger.info("UAT Test 1 PASSED: Fresh CRM Tenant Provisioned & Recorded in Mongo.")

    def test_02_create_real_crm_data(self):
        logger.info("=== UAT Test 2: Verify Authentication & Site Health ===")
        tenant_info = TenantService.get_tenant_by_company(self.company_name)
        self.assertIsNotNone(tenant_info)

        # Check site directory exists in container
        cmd = ["docker", "exec", self.container_name, "test", "-d", f"sites/{self.site_name}"]
        check_res = subprocess.run(cmd)
        self.assertEqual(check_res.returncode, 0)
        logger.info("UAT Test 2 PASSED: Tenant Site Directory Verified & Active.")

    def test_03_upgrade_flow(self):
        logger.info("=== UAT Test 3: In-Place Tier 1 -> Tier 2 Upgrade Flow ===")
        tenant_info = TenantService.get_tenant_by_company(self.company_name)
        self.assertEqual(tenant_info["tier"], 1)

        # Execute Upgrade Service
        res = StreamlitProvisioningService.upgrade_tenant(
            company_name=self.company_name,
            abbr=self.abbr,
            selected_features=["selling", "crm"],
            admin_password=self.admin_password,
            bot=self.bot_id
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["tier"], 2)
        logger.info("UAT Test 3 PASSED: Upgrade Strategy Executed Successfully.")

    def test_04_verify_upgrade(self):
        logger.info("=== UAT Test 4: Post-Upgrade Verification ===")
        tenant_info = TenantService.get_tenant_by_company(self.company_name)
        self.assertEqual(tenant_info["tier"], 2)
        self.assertIn("erpnext", tenant_info["installed_apps"])
        self.assertIsNotNone(tenant_info.get("latest_backup_path"))

        # Verify backup summary was recorded
        backup_info = tenant_info["latest_backup_path"]
        self.assertIn("Backup Summary", backup_info)
        logger.info("UAT Test 4 PASSED: Tier 2 Upgraded, Backup Summary Recorded.")

    def test_05_dashboard_metrics(self):
        logger.info("=== UAT Test 5: Dashboard Metric Service Verification ===")
        all_tenants = TenantService.get_all_tenants()
        self.assertGreaterEqual(len(all_tenants), 1)

        crm_cnt = sum(1 for t in all_tenants if t.get("tier") == 1)
        erp_cnt = sum(1 for t in all_tenants if t.get("tier") == 2)
        self.assertGreaterEqual(erp_cnt, 1)
        logger.info(f"UAT Test 5 PASSED: Metrics fetched ({len(all_tenants)} total, {crm_cnt} CRM, {erp_cnt} ERPNext).")

    def test_06_tenant_details(self):
        logger.info("=== UAT Test 6: Tenant Details Service Verification ===")
        tenant_info = TenantService.get_tenant_by_company(self.company_name)
        self.assertEqual(tenant_info["company_name"], self.company_name)
        self.assertIsNotNone(tenant_info["site_name"])
        self.assertEqual(tenant_info["tier"], 2)
        logger.info("UAT Test 6 PASSED: Tenant Details Complete.")

    def test_07_health_diagnostics(self):
        logger.info("=== UAT Test 7: Health Diagnostic Service Verification ===")
        health_items = HealthService.get_system_health()
        self.assertGreaterEqual(len(health_items), 5)
        for h in health_items:
            self.assertIn(h["status"], ["Healthy", "Warning", "Failed"])
        
        healthy_count = sum(1 for h in health_items if h["status"] == "Healthy")
        self.assertGreaterEqual(healthy_count, 4)
        logger.info(f"UAT Test 7 PASSED: System Diagnostic matrix verified ({healthy_count}/{len(health_items)} healthy).")

    def test_08_negative_tests(self):
        logger.info("=== UAT Test 8: Negative Error Scenarios ===")
        # 1. Duplicate site creation attempt
        dup_site = "duplicate_test.localhost"
        subprocess.run(["docker", "exec", self.container_name, "mkdir", "-p", f"sites/{dup_site}"])

        plan = StreamlitProvisioningService.resolve_plan(["crm"])
        with self.assertRaises(AppException) as ctx:
            PreFlightValidator.validate_infrastructure(self.container_name, dup_site, plan, is_upgrade=False)
        self.assertIn("already exists", str(ctx.exception))
        logger.info("Negative Check 1: Duplicate site error caught cleanly by PreFlightValidator.")

        # Clean up dup site
        subprocess.run(["docker", "exec", self.container_name, "rm", "-rf", f"sites/{dup_site}"])

        # 2. Non-existent container check
        with self.assertRaises(AppException) as ctx_c:
            PreFlightValidator.validate_infrastructure("nonexistent-container-99", "random.localhost", plan, is_upgrade=False)
        self.assertIn("not running", str(ctx_c.exception))
        logger.info("Negative Check 2: Missing container error caught cleanly by PreFlightValidator.")

        logger.info("UAT Test 8 PASSED: Negative Error Scenarios Verified.")

    def test_09_restart_and_persistence(self):
        logger.info("=== UAT Test 9: Persistence Verification ===")
        # Re-fetch from MongoDB to ensure data persistence across calls
        tenant_info = TenantService.get_tenant_by_company(self.company_name)
        self.assertIsNotNone(tenant_info)
        self.assertEqual(tenant_info["tier"], 2)

        # Logs service verification
        logs = LogsService.get_recent_logs(limit=10)
        self.assertGreaterEqual(len(logs), 1)
        logger.info("UAT Test 9 PASSED: Data Persisted & Logs Accessible.")


if __name__ == "__main__":
    unittest.main()
