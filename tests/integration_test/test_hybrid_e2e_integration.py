import os
import unittest
import time
import subprocess
from loguru import logger

from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.services.provisioning_models import ProvisioningPlan
from kairon.crm.services.feature_resolver import FeatureAppResolver
from kairon.crm.services.preflight_validator import PreFlightValidator
from kairon.crm.services.provisioners.factory import ProvisionerFactory
from kairon.crm.services.provisioners.crm_provisioner import CRMProvisioner
from kairon.crm.services.provisioners.erpnext_provisioner import ERPNextProvisioner
from kairon.crm.services.provisioners.upgrade_provisioner import AppUpgradeProvisioner
from kairon.crm.services.base_frappe_client import BaseFrappeClient
from kairon.crm.services.crm_client import CRMClient
from kairon.crm.services.erpnext_client import ERPNextClient


class TestHybridE2EIntegration(unittest.TestCase):
    """
    Live Integration Test Suite against frappe-backend-1 Docker container.
    Tests Scenario 1 (CRM Tenant), Scenario 2 (ERPNext Tenant), Scenario 3 (Upgrade Path),
    Scenario 4 (Failure/Locking), and Scenario 5 (Concurrency & Diagnostics).
    """

    @classmethod
    def setUpClass(cls):
        import mongoengine
        from kairon.shared.utils import Utility
        try:
            import mongomock
            mongoengine.connect('kairon_test', is_mock=True)
        except Exception:
            mongoengine.connect('kairon_test', host='mongodb://localhost:27017/kairon_test')

        Utility.environment["events"] = {
            "audit_logs": {
                "attributes": ["user", "bot"]
            }
        }

        cls.container_name = "frappe-backend-1"
        cls.admin_password = "Password@123"
        cls.bench_config = {
            "container_name": cls.container_name,
            "db_host": "db",
            "db_port": 5432,
            "db_user": "postgres",
            "db_password": "beb703c0c",
            "base_url": "http://localhost:80"
        }

    def _clean_site(self, site_name: str):
        """Helper to drop bench site if exists."""
        cmd = ["docker", "exec", self.container_name, "rm", "-rf", f"sites/{site_name}"]
        subprocess.run(cmd, capture_output=True)

    def _get_or_create_doc(self, company_name: str, abbr: str, bot: str, site_name: str) -> CRMClientDetails:
        doc = CRMClientDetails.objects(company_name=company_name).first()
        if not doc:
            doc = CRMClientDetails(
                company_name=company_name,
                abbr=abbr,
                default_currency="USD",
                country="United States",
                bot=bot,
                user="test_user",
                site_name=site_name
            )
            doc.save()
        return doc

    def test_01_preflight_validation(self):
        logger.info("=== Running Scenario 0: Pre-flight Validation ===")
        plan = FeatureAppResolver.resolve(["crm"])
        self.assertEqual(plan.tier, 1)
        self.assertEqual(plan.strategy_key, "crm")

        # Validate container & bench availability
        PreFlightValidator.validate_infrastructure(self.container_name, "nonexistent.localhost", plan, is_upgrade=False)
        logger.info("Scenario 0 PASSED")

    def test_02_fresh_crm_tenant(self):
        logger.info("=== Running Scenario 1: Fresh Tier 1 CRM Tenant ===")
        company_name = "Acme Standalone CRM"
        site_name = "acme_standalone_crm.localhost"
        self._clean_site(site_name)

        # Create mongo record
        doc = self._get_or_create_doc(company_name, "ASC", "test_crm_bot", site_name)

        plan = FeatureAppResolver.resolve(["crm"])
        provisioner = ProvisionerFactory.create(plan, self.bench_config)
        res = provisioner.provision(
            company_name=company_name,
            abbr="ASC",
            default_currency="USD",
            country="United States",
            admin_password=self.admin_password,
            bot="test_crm_bot"
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["tier"], 1)

        # Reload doc
        doc = CRMClientDetails.objects(company_name=company_name).first()
        self.assertEqual(doc.tier, 1)
        self.assertIn("crm", doc.installed_apps)
        self.assertEqual(doc.onboarding_status, CRMOnboardingStatus.SITE_CREATED.value)
        logger.info("Scenario 1 PASSED: Tier 1 CRM Tenant Provisioned")

    def test_03_fresh_erpnext_tenant(self):
        logger.info("=== Running Scenario 2: Fresh Tier 2 ERPNext Tenant ===")
        company_name = "Acme Suite ERP"
        site_name = "acme_suite_erp.localhost"
        self._clean_site(site_name)

        doc = self._get_or_create_doc(company_name, "ASE", "test_erp_bot", site_name)

        plan = FeatureAppResolver.resolve(["selling"])
        self.assertEqual(plan.tier, 2)
        self.assertEqual(plan.strategy_key, "erpnext_suite")

        provisioner = ProvisionerFactory.create(plan, self.bench_config)
        res = provisioner.provision(
            company_name=company_name,
            abbr="ASE",
            default_currency="USD",
            country="United States",
            admin_password=self.admin_password,
            bot="test_erp_bot"
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["tier"], 2)

        doc = CRMClientDetails.objects(company_name=company_name).first()
        self.assertEqual(doc.tier, 2)
        self.assertIn("erpnext", doc.installed_apps)
        logger.info("Scenario 2 PASSED: Tier 2 ERPNext Tenant Provisioned")

    def test_04_upgrade_path(self):
        logger.info("=== Running Scenario 3: In-Place Upgrade (Tier 1 -> Tier 2) ===")
        company_name = "Upgradeable Tenant"
        site_name = "upgradeable_tenant.localhost"
        self._clean_site(site_name)

        # Step 1: Provision as Tier 1 Standalone CRM
        doc = self._get_or_create_doc(company_name, "UT", "test_upgrade_bot", site_name)

        tier1_plan = FeatureAppResolver.resolve(["crm"])
        tier1_provisioner = ProvisionerFactory.create(tier1_plan, self.bench_config)
        tier1_provisioner.provision(
            company_name=company_name,
            abbr="UT",
            default_currency="USD",
            country="United States",
            admin_password=self.admin_password,
            bot="test_upgrade_bot"
        )

        doc = CRMClientDetails.objects(company_name=company_name).first()
        self.assertEqual(doc.tier, 1)

        # Step 2: Execute In-Place Upgrade to Tier 2
        upgrade_plan = ProvisioningPlan(strategy_key="in_place_upgrade", tier=2, apps=["crm", "erpnext"])
        upgrade_provisioner = ProvisionerFactory.create(upgrade_plan, self.bench_config)
        upgrade_res = upgrade_provisioner.provision(
            company_name=company_name,
            abbr="UT",
            default_currency="USD",
            country="United States",
            admin_password=self.admin_password,
            bot="test_upgrade_bot"
        )

        self.assertEqual(upgrade_res["status"], "success")
        self.assertEqual(upgrade_res["tier"], 2)

        doc = CRMClientDetails.objects(company_name=company_name).first()
        self.assertEqual(doc.tier, 2)
        self.assertIn("erpnext", doc.installed_apps)
        self.assertIsNotNone(doc.latest_backup_path)
        logger.info(f"Scenario 3 PASSED: Upgrade complete with DB backup: {doc.latest_backup_path}")
