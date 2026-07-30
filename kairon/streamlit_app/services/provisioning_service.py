import time
from typing import List, Dict, Any
from loguru import logger

from kairon.crm.services.feature_resolver import FeatureAppResolver
from kairon.crm.services.preflight_validator import PreFlightValidator
from kairon.crm.services.provisioners.factory import ProvisionerFactory
from kairon.crm.services.provisioning_models import ProvisioningPlan
from kairon.crm.services.bench_executor import BenchExecutor


class StreamlitProvisioningService:

    @staticmethod
    def resolve_plan(selected_features: List[str]) -> ProvisioningPlan:
        """Resolves feature list to ProvisioningPlan."""
        return FeatureAppResolver.resolve(selected_features)

    @staticmethod
    def validate_preflight(site_name: str, plan: ProvisioningPlan, selected_features: List[str] = None, is_upgrade: bool = False) -> List[str]:
        """Runs Phase 0 pre-flight validation and returns step log messages."""
        logs = []
        logs.append(f"[PreFlightValidator] Validating configuration & matrix schema...")
        if selected_features is None:
            selected_features = ["crm"]
        PreFlightValidator.validate_configuration(selected_features)
        logs.append(f"[PreFlightValidator] Configuration schema valid.")

        container_name = getattr(BenchExecutor, "CONTAINER_NAME", "frappe-backend-1")
        logs.append(f"[PreFlightValidator] Validating container '{container_name}' infrastructure...")
        PreFlightValidator.validate_infrastructure(container_name, site_name, plan, is_upgrade=is_upgrade)
        logs.append(f"[PreFlightValidator] Infrastructure pre-flight check passed successfully.")
        return logs

    @staticmethod
    def provision_tenant(
        company_name: str,
        abbr: str,
        selected_features: List[str],
        currency: str,
        country: str,
        admin_password: str,
        bot: str,
        user_email: str = None
    ) -> Dict[str, Any]:
        """Calls the backend strategy provisioner service directly."""
        plan = FeatureAppResolver.resolve(selected_features)
        bench_config = {
            "container_name": getattr(BenchExecutor, "CONTAINER_NAME", "frappe-backend-1"),
            "db_host": getattr(BenchExecutor, "DB_HOST", "db"),
            "db_port": getattr(BenchExecutor, "DB_PORT", 5432),
            "db_user": getattr(BenchExecutor, "DB_USER", "postgres"),
            "db_password": getattr(BenchExecutor, "DB_PASSWORD", "beb703c0c"),
            "base_url": getattr(BenchExecutor, "BASE_URL", "http://localhost")
        }

        from kairon.streamlit_app.services.tenant_service import ensure_mongo_connection
        from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus

        ensure_mongo_connection()
        clean_name = "".join(c if c.isalnum() else "_" for c in company_name.lower())
        site_name = f"{clean_name}.localhost"

        doc = CRMClientDetails.objects(company_name__iexact=company_name.strip()).first()
        if not doc:
            doc = CRMClientDetails(
                company_name=company_name.strip(),
                abbr=abbr,
                site_name=site_name,
                bot=bot,
                user=user_email if user_email else bot,
                country=country,
                default_currency=currency,
                onboarding_status=CRMOnboardingStatus.PENDING.value
            )
            doc.save()

        provisioner = ProvisionerFactory.create(plan, bench_config)
        start_time = time.time()
        res = provisioner.provision(
            company_name=company_name,
            abbr=abbr,
            default_currency=currency,
            country=country,
            admin_password=admin_password,
            bot=bot
        )
        elapsed = round(time.time() - start_time, 2)
        res["provisioning_time"] = elapsed
        return res

    @staticmethod
    def upgrade_tenant(
        company_name: str,
        abbr: str,
        selected_features: List[str],
        admin_password: str,
        bot: str,
        user_email: str = None
    ) -> Dict[str, Any]:
        """Calls the backend upgrade provisioner strategy directly."""
        from kairon.streamlit_app.services.tenant_service import TenantService
        
        # Verify ownership
        tenant_doc = TenantService.get_tenant_by_company(company_name, user_email)
        if not tenant_doc:
            return {"status": "error", "message": "Access Denied: You do not have permission to upgrade this tenant."}

        upgrade_plan = ProvisioningPlan(strategy_key="in_place_upgrade", tier=2, apps=["crm", "erpnext"])
        bench_config = {
            "container_name": getattr(BenchExecutor, "CONTAINER_NAME", "frappe-backend-1"),
            "db_host": getattr(BenchExecutor, "DB_HOST", "db"),
            "db_port": getattr(BenchExecutor, "DB_PORT", 5432),
            "db_user": getattr(BenchExecutor, "DB_USER", "postgres"),
            "db_password": getattr(BenchExecutor, "DB_PASSWORD", "beb703c0c"),
            "base_url": getattr(BenchExecutor, "BASE_URL", "http://localhost")
        }

        provisioner = ProvisionerFactory.create(upgrade_plan, bench_config)
        start_time = time.time()
        res = provisioner.provision(
            company_name=company_name,
            abbr=abbr,
            default_currency="USD",
            country="United States",
            admin_password=admin_password,
            bot=bot
        )
        elapsed = round(time.time() - start_time, 2)
        res["provisioning_time"] = elapsed
        return res
