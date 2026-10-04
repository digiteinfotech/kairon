from loguru import logger
from kairon.crm.services.provisioning_models import ProvisioningPlan
from kairon.crm.services.provisioners.base_provisioner import BaseProvisioner
from kairon.crm.services.provisioners.crm_provisioner import CRMProvisioner
from kairon.crm.services.provisioners.erpnext_provisioner import ERPNextProvisioner
from kairon.crm.services.provisioners.upgrade_provisioner import AppUpgradeProvisioner


class ProvisionerFactory:
    """
    Factory that instantiates the appropriate BaseProvisioner strategy
    based on the strategy_key inside ProvisioningPlan.
    
    Eliminates procedural 'if tier == 1:' branching in callers.
    """

    @classmethod
    def create(cls, plan: ProvisioningPlan, bench_config: dict) -> BaseProvisioner:
        key = plan.strategy_key.lower().strip()
        logger.info(f"[ProvisionerFactory] Creating provisioner strategy for key '{key}' (Tier {plan.tier})...")

        if key in ("crm", "helpdesk", "standalone"):
            return CRMProvisioner(plan, bench_config)
        elif key in ("erpnext_suite", "erpnext", "full_suite"):
            return ERPNextProvisioner(plan, bench_config)
        elif key in ("in_place_upgrade", "upgrade"):
            return AppUpgradeProvisioner(plan, bench_config)
        else:
            logger.warning(f"[ProvisionerFactory] Unknown strategy key '{key}'. Defaulting to CRMProvisioner for Tier 1, ERPNextProvisioner for Tier 2.")
            if plan.tier == 1:
                return CRMProvisioner(plan, bench_config)
            return ERPNextProvisioner(plan, bench_config)
