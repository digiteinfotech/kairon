"""
CRM Module Configuration Constants.

Version note: Permission model validated against Frappe v15 / ERPNext v15.
  - Workspace DocType: permissions defined in frappe/desk/doctype/workspace/workspace.json
    Only "Workspace Manager" and "Desk User" roles have any permission.
    The validate() hook additionally enforces is_workspace_manager() for public workspaces.
  - Module Def DocType: permissions in frappe/core/doctype/module_def/module_def.json
    Read granted to "All" role. Write requires "System Manager".
  - Module Profile DocType: permissions in frappe/core/doctype/module_profile/module_profile.json
    All operations require "System Manager".

If future ERPNext versions change these permission requirements, update REQUIRED_INTEGRATION_USER_ROLES
and, if API paths change, the relevant methods in ERPNextClient. No other files should need changes.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Integration User Roles — single source of truth
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_INTEGRATION_USER_ROLES = [
    "System Manager",    # Module Def write, Module Profile CRUD, User write
    "Workspace Manager", # Workspace DocType read/write + is_workspace_manager() app check
]


# ─────────────────────────────────────────────────────────────────────────────
# Business Module Catalog (static fallback)
# ─────────────────────────────────────────────────────────────────────────────
# Used when ERPNext live discovery is unavailable.
# Keys are Kairon's canonical module identifiers.
# workspace: exact document name in the ERPNext Workspace DocType
# frappe_module: exact document name in the ERPNext Module Def DocType

BUSINESS_MODULE_CATALOG = {
    "CRM": {
        "workspace": "CRM",
        "frappe_module": "CRM",
        "description": "Lead and opportunity management",
    },
    "POS": {
        "workspace": "Point of Sale",
        "frappe_module": "Point of Sale",
        "description": "Point of sale transactions",
    },

    "Buying": {
        "workspace": "Buying",
        "frappe_module": "Buying",
        "description": "Purchase orders and supplier management",
    },
    "Selling": {
        "workspace": "Selling",
        "frappe_module": "Selling",
        "description": "Sales orders and quotations",
    },
    "Manufacturing": {
        "workspace": "Manufacturing",
        "frappe_module": "Manufacturing",
        "description": "Production planning and work orders",
    },
    "HR": {
        "workspace": "HR",
        "frappe_module": "HR",
        "description": "Human resources and employee management",
    },
    "Projects": {
        "workspace": "Projects",
        "frappe_module": "Projects",
        "description": "Project tasks and time tracking",
    },
    "Assets": {
        "workspace": "Assets",
        "frappe_module": "Asset",
        "description": "Asset management and depreciation",
    },
    "Support": {
        "workspace": "Support",
        "frappe_module": "Support",
        "description": "Customer support and issue tracking",
    },
    "Quality": {
        "workspace": "Quality",
        "frappe_module": "Quality Management",
        "description": "Quality inspections and non-conformance",
    },
    "Payroll": {
        "workspace": "Payroll",
        "frappe_module": "Payroll",
        "description": "Payroll processing and salary slips",
    },
    "Maintenance": {
        "workspace": "Maintenance",
        "frappe_module": "Maintenance",
        "description": "Equipment maintenance and scheduling",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Infrastructure Modules — always enabled, never user-selectable
# ─────────────────────────────────────────────────────────────────────────────
# These module names match the 'name' field in ERPNext's Module Def DocType.
# Frappe framework modules (app_name = "frappe") are always excluded.
# Certain ERPNext structural modules (app_name = "erpnext") are also excluded
# because ERPNext depends on them for core Company, GL, and inventory operations.

INFRASTRUCTURE_MODULE_NAMES = frozenset({
    # Frappe framework — app_name = "frappe"
    "Core",
    "Email",
    "Desk",
    "Custom",
    "Website",
    "Geo",
    "Printing",
    "Workflow",
    "Integrations",
    "Contacts",
    "Automation",
    # ERPNext structural — app_name = "erpnext" but required dependencies
    "Accounts",
    "Stock",
    "Setup",
    "Utilities",
    "Regional",
    "ERPNext Integrations",
})
