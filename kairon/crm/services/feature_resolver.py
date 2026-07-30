import os
import yaml
from typing import List, Dict, Any
from loguru import logger
from kairon.exceptions import AppException
from kairon.crm.services.provisioning_models import ProvisioningPlan


class FeatureAppResolver:
    """
    Resolver that maps user-selected features (e.g. 'crm', 'hr', 'selling')
    to a concrete ProvisioningPlan based on provisioning_matrix.yaml.
    """

    _matrix_cache: Dict[str, Any] = None

    @classmethod
    def load_matrix(cls) -> Dict[str, Any]:
        if cls._matrix_cache is not None:
            return cls._matrix_cache

        matrix_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "provisioning_matrix.yaml"
        )
        if not os.path.exists(matrix_path):
            raise AppException(f"Provisioning matrix configuration not found at {matrix_path}")

        try:
            with open(matrix_path, "r") as f:
                data = yaml.safe_load(f)
                cls._matrix_cache = data.get("provisioning_matrix", {})
                return cls._matrix_cache
        except Exception as e:
            raise AppException(f"Failed to parse provisioning matrix YAML: {e}")

    @classmethod
    def resolve(cls, selected_features: List[str]) -> ProvisioningPlan:
        """
        Resolves a list of requested feature keys into a single ProvisioningPlan.
        
        Rules:
        1. If no features specified, defaults to Tier 1 'crm'.
        2. If any requested feature requires Tier 2 (e.g., HR, Selling, Accounts), plan tier becomes 2.
        3. Apps and dependencies are deduplicated while preserving order.
        """
        matrix = cls.load_matrix()

        if not selected_features:
            selected_features = ["crm"]

        resolved_apps: List[str] = []
        resolved_roles: List[str] = []
        resolved_deps: List[str] = ["frappe"]
        max_tier = 1
        upgrade_supported = True
        primary_home_page = None
        strategy_key = "crm"

        for feature in selected_features:
            key = feature.lower().strip()
            if key not in matrix:
                logger.warning(f"[FeatureAppResolver] Unknown feature '{key}', ignoring.")
                continue

            config = matrix[key]
            tier = config.get("tier", 1)
            if tier > max_tier:
                max_tier = tier
                strategy_key = "erpnext_suite"

            if not config.get("upgrade_supported", True):
                upgrade_supported = False

            if not primary_home_page:
                primary_home_page = config.get("home_page")

            for app in config.get("required_apps", []):
                if app not in resolved_apps:
                    resolved_apps.append(app)

            for role in config.get("default_roles", []):
                if role not in resolved_roles:
                    resolved_roles.append(role)

            for dep in config.get("dependencies", []):
                if dep not in resolved_deps:
                    resolved_deps.append(dep)

        if not resolved_apps:
            resolved_apps = ["crm"]

        if not primary_home_page:
            primary_home_page = "crm" if max_tier == 1 else "workspace/CRM"

        plan = ProvisioningPlan(
            strategy_key=strategy_key if max_tier == 2 else (resolved_apps[0] if resolved_apps else "crm"),
            tier=max_tier,
            apps=resolved_apps,
            home_page=primary_home_page,
            default_roles=resolved_roles,
            dependencies=resolved_deps,
            upgrade_supported=upgrade_supported
        )

        logger.info(f"[FeatureAppResolver] Resolved plan for features {selected_features}: {plan}")
        return plan
