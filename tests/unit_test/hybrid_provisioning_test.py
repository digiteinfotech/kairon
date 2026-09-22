import unittest
from unittest.mock import MagicMock, patch
from kairon.exceptions import AppException
from kairon.crm.services.provisioning_models import ProvisioningPlan
from kairon.crm.services.feature_resolver import FeatureAppResolver
from kairon.crm.services.preflight_validator import PreFlightValidator
from kairon.crm.services.provisioners.factory import ProvisionerFactory
from kairon.crm.services.provisioners.crm_provisioner import CRMProvisioner
from kairon.crm.services.provisioners.erpnext_provisioner import ERPNextProvisioner
from kairon.crm.services.provisioners.upgrade_provisioner import AppUpgradeProvisioner
from kairon.crm.services.base_frappe_client import BaseFrappeClient
from kairon.crm.services.crm_client import CRMClient


class TestHybridProvisioning(unittest.TestCase):

    def test_feature_app_resolver_crm_only(self):
        plan = FeatureAppResolver.resolve(["crm"])
        assert plan.tier == 1
        assert plan.strategy_key == "crm"
        assert plan.apps == ["crm"]
        assert plan.home_page == "crm"
        assert "CRM Admin" in plan.default_roles

    def test_feature_app_resolver_pos_only(self):
        plan = FeatureAppResolver.resolve(["pos"])
        assert plan.tier == 2
        assert plan.strategy_key == "erpnext_suite"
        assert plan.apps == ["erpnext"]
        assert plan.home_page == "workspace/Point of Sale Workspace"

        assert "POS User" in plan.default_roles
        assert "POS Manager" in plan.default_roles
        assert "Stock User" in plan.default_roles



    def test_feature_app_resolver_hr_suite(self):
        plan = FeatureAppResolver.resolve(["hr", "crm"])
        assert plan.tier == 2
        assert plan.strategy_key == "erpnext_suite"
        assert "erpnext" in plan.apps
        assert "hrms" in plan.apps
        assert plan.home_page == "workspace/HR"
        assert "HR Manager" in plan.default_roles

    def test_provisioner_factory_resolution(self):
        plan_crm = ProvisioningPlan(strategy_key="crm", tier=1, apps=["crm"])
        prov_crm = ProvisionerFactory.create(plan_crm, {})
        assert isinstance(prov_crm, CRMProvisioner)

        plan_erp = ProvisioningPlan(strategy_key="erpnext_suite", tier=2, apps=["erpnext"])
        prov_erp = ProvisionerFactory.create(plan_erp, {})
        assert isinstance(prov_erp, ERPNextProvisioner)

        plan_upg = ProvisioningPlan(strategy_key="in_place_upgrade", tier=2, apps=["erpnext"])
        prov_upg = ProvisionerFactory.create(plan_upg, {})
        assert isinstance(prov_upg, AppUpgradeProvisioner)

    @patch("subprocess.run")
    def test_preflight_validator_infrastructure_success(self, mock_run):
        # Mock successful bench --version and directory checks
        def side_effect(cmd, capture_output=True, text=False, timeout=None):
            res = MagicMock()
            cmd_str = " ".join(cmd)
            if "test -d sites/" in cmd_str:
                res.returncode = 1  # Site does NOT exist -> OK
            elif "test -d apps/" in cmd_str:
                res.returncode = 0  # App repository exists -> OK
            else:
                res.returncode = 0
                res.stdout = "Frappe Bench 5.15.0"
            return res

        mock_run.side_effect = side_effect

        plan = ProvisioningPlan(strategy_key="crm", tier=1, apps=["crm"])
        # Should not raise AppException
        PreFlightValidator.validate_infrastructure("frappe-backend-1", "test.localhost", plan, is_upgrade=False)

    @patch("requests.Session.get")
    def test_base_frappe_client_ping(self, mock_get):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_get.return_value = mock_res

        client = BaseFrappeClient(site_url="http://test.localhost")
        assert client.ping() is True

    @patch("requests.Session.post")
    def test_crm_client_create_lead(self, mock_post):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"data": {"name": "LEAD-0001", "lead_name": "Acme Corp"}}
        mock_post.return_value = mock_res

        client = CRMClient(site_url="http://test.localhost", api_key="key", api_secret="secret")
        lead = client.create_lead("Acme Corp", "lead@acme.com")
        assert lead["name"] == "LEAD-0001"

    def test_product_isolation_service_pos(self):
        from kairon.crm.services.isolation_service import ProductIsolationService
        mock_client = MagicMock()
        mock_client.discover_business_modules.return_value = {
            "modules": [
                {"key": "crm", "frappe_module": "CRM", "workspace": "CRM"},
                {"key": "pos", "frappe_module": "Point of Sale", "workspace": "Point of Sale"},
                {"key": "hr", "frappe_module": "HR", "workspace": "HR"},
                {"key": "manufacturing", "frappe_module": "Manufacturing", "workspace": "Manufacturing"}
            ]
        }

        res = ProductIsolationService.apply_isolation(mock_client, "Acme POS", ["pos"])
        assert res["role_profile"] == "POS Admin"
        assert "Point of Sale" in res["allowed_modules"]
        assert "Stock" in res["allowed_modules"]
        assert "HR" in res["blocked_modules"]
        assert "CRM" in res["blocked_modules"]
        assert "Manufacturing" in res["blocked_modules"]
        mock_client.configure_workspace_visibility.assert_called_once()
        mock_client.create_or_update_module_profile.assert_called_once()
        mock_client.ensure_role_profile.assert_called_once_with("POS Admin", ["System Manager", "Desk User", "POS User", "POS Manager", "Stock User", "Accounts User"])



