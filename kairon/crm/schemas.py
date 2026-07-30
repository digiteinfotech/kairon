from typing import List, Optional
from pydantic import BaseModel, root_validator
from kairon.shared.utils import Utility
from kairon.crm.constants import BUSINESS_MODULE_CATALOG, INFRASTRUCTURE_MODULE_NAMES


def validate_module_selection(selected_modules: Optional[List[str]]) -> Optional[List[str]]:
    if selected_modules is None:
        return None
    if isinstance(selected_modules, list) and len(selected_modules) == 0:
        raise ValueError("selected_modules cannot be an empty list. Specify at least one business module or omit the field.")

    cleaned = []
    for mod in selected_modules:
        if Utility.check_empty_string(mod):
            continue
        mod_clean = mod.strip()
        if mod_clean in INFRASTRUCTURE_MODULE_NAMES:
            raise ValueError(f"'{mod_clean}' is an infrastructure module and is always enabled.")
        if mod_clean not in BUSINESS_MODULE_CATALOG:
            valid_keys = ", ".join(sorted(BUSINESS_MODULE_CATALOG.keys()))
            raise ValueError(f"Invalid business module '{mod_clean}'. Valid modules: {valid_keys}")
        if mod_clean not in cleaned:
            cleaned.append(mod_clean)

    if not cleaned:
        raise ValueError("selected_modules must contain at least one valid business module.")
    return cleaned


class CRMOnboardRequest(BaseModel):
    company_name: str
    abbr: str
    default_currency: str
    country: str
    selected_modules: Optional[List[str]] = None

    @root_validator
    def validate_fields(cls, values):
        company_name = values.get("company_name")
        abbr = values.get("abbr")
        default_currency = values.get("default_currency")
        country = values.get("country")

        if Utility.check_empty_string(company_name):
            raise ValueError("company_name cannot be empty")
        if Utility.check_empty_string(abbr):
            raise ValueError("abbr cannot be empty")
        if Utility.check_empty_string(default_currency):
            raise ValueError("default_currency cannot be empty")
        if Utility.check_empty_string(country):
            raise ValueError("country cannot be empty")

        values["selected_modules"] = validate_module_selection(values.get("selected_modules"))
        return values


class CRMConfigureModulesRequest(BaseModel):
    selected_modules: List[str]

    @root_validator
    def validate_fields(cls, values):
        selected_modules = values.get("selected_modules")
        values["selected_modules"] = validate_module_selection(selected_modules)
        return values


class CRMCreateUserRequest(BaseModel):
    email: str
    role: str

    @root_validator
    def validate_fields(cls, values):
        email = values.get("email")
        role = values.get("role")

        if Utility.check_empty_string(email):
            raise ValueError("email cannot be empty")
        if Utility.check_empty_string(role):
            raise ValueError("role cannot be empty")

        return values


class CRMInviteUserRequest(BaseModel):
    """
    Request body for POST /api/bot/{bot}/crm/invite-user.
    Sends a native ERPNext UserInvitation — no manual user creation.
    """
    email: str
    roles: List[str]
    company_name: Optional[str] = None  # resolved from CRMClientDetails if omitted

    @root_validator
    def validate_fields(cls, values):
        email = values.get("email")
        roles = values.get("roles", [])

        if Utility.check_empty_string(email):
            raise ValueError("email cannot be empty")
        if not roles or all(Utility.check_empty_string(r) for r in roles):
            raise ValueError("at least one role must be specified")

        return values
