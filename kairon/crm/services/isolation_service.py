from typing import Dict, Any, List
from loguru import logger


class ProductIsolationService:
    """
    Dedicated enterprise service encapsulating Product Isolation logic:
    - Workspace Visibility
    - Module Profile generation (via Whitelisted allowed_modules paradigm)
    - Role Profile creation & assignment
    """

    @classmethod
    def apply_isolation(cls, client, company_name: str, selected_modules: List[str]) -> Dict[str, Any]:
        from kairon.crm.services.feature_resolver import FeatureAppResolver
        matrix = FeatureAppResolver.load_matrix()

        # Discover Frappe modules
        disc = client.discover_business_modules()
        catalog = {m["key"]: m for m in disc["modules"]}

        # 1. Calculate allowed modules (Whitelisting approach)
        allowed_frappe_modules = set()
        explicit_workspaces = []
        role_profile_to_assign = None

        for mod in selected_modules:
            if mod in matrix:
                config = matrix[mod]
                if "allowed_modules" in config:
                    allowed_frappe_modules.update(config["allowed_modules"])
                if "workspaces" in config:
                    explicit_workspaces.extend(config["workspaces"])
                if "role_profile_name" in config and not role_profile_to_assign:
                    role_profile_to_assign = config["role_profile_name"]
            
            # Add mapped frappe module from catalog if present
            if mod in catalog:
                allowed_frappe_modules.add(catalog[mod]["frappe_module"])

        # Default fallback allowed modules if none explicitly specified
        if not allowed_frappe_modules:
            allowed_frappe_modules = {m["frappe_module"] for m in catalog.values()}

        # 2. Derive blocked modules as complement of allowed_modules
        all_frappe_modules = {m["frappe_module"] for m in catalog.values()}
        # Include standard non-catalog Frappe/ERPNext modules for total coverage
        all_frappe_modules.update({
            "CRM", "HR", "Manufacturing", "Projects", "Buying", "Selling",
            "Assets", "Support", "Quality Management", "Payroll", "Maintenance",
            "Healthcare", "Education", "Agriculture", "Non Profit"
        })
        blocked_modules = list(all_frappe_modules - allowed_frappe_modules)

        # 3. Apply Workspace Visibility
        workspaces_to_allow = explicit_workspaces if explicit_workspaces else selected_modules
        client.configure_workspace_visibility(workspaces_to_allow, catalog=catalog)


        # 4. Create/Update Module Profile
        profile_name = f"Kairon Profile ({company_name})"
        client.create_or_update_module_profile(profile_name, blocked_modules)

        # 5. Ensure Role Profile if specified
        if role_profile_to_assign:
            plan = FeatureAppResolver.resolve(selected_modules)
            client.ensure_role_profile(role_profile_to_assign, plan.default_roles)

        logger.info(f"[ProductIsolationService] Applied isolation for {company_name}: allowed={allowed_frappe_modules}, role_profile={role_profile_to_assign}")

        return {
            "module_profile": profile_name,
            "role_profile": role_profile_to_assign,
            "allowed_modules": list(allowed_frappe_modules),
            "blocked_modules": blocked_modules
        }
