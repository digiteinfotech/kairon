from dataclasses import dataclass, field
from typing import List


@dataclass
class ProvisioningPlan:
    """
    Data model representing the resolved target state for site provisioning.
    Decouples feature requests from specific Frappe/ERPNext application installation logic.
    """
    strategy_key: str                     # e.g., "crm", "helpdesk", "erpnext_suite", "in_place_upgrade"
    tier: int                             # 1 (Standalone App) or 2 (Full ERP Suite)
    apps: List[str] = field(default_factory=list)             # Target app keys to install, e.g. ["crm"] or ["erpnext", "hrms"]
    home_page: str = "crm"                # Landing route/workspace default
    default_roles: List[str] = field(default_factory=list)     # Initial roles to grant integration/admin users
    dependencies: List[str] = field(default_factory=list)      # Framework/base dependencies
    upgrade_supported: bool = True        # True if Tier 1 site can be upgraded in-place to Tier 2
