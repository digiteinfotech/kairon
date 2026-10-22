import re
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


EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+'\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")                      # ISO 4217 code, as ERPNext's Currency names
COUNTRY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z .,'()\-]{1,59}$")   # English country name, as ERPNext's Country names
COMPANY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_ ]{1,100}$")
MAX_EMAIL_LENGTH = 254


def normalize_email(email: Optional[str]) -> str:
    """Trimmed, lower-cased address. ERPNext user names are the lower-cased email."""
    return (email or "").strip().lower()


def validate_email_address(email: Optional[str], label: str = "email") -> str:
    email = normalize_email(email)
    if not email:
        raise ValueError(f"{label} cannot be empty")
    if len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email) or ".." in email:
        raise ValueError(f"{label} is not a valid email address")
    return email


class CRMOnboardRequest(BaseModel):
    company_name: str
    abbr: str
    default_currency: str
    country: str
    crm_admin_email: str
    selected_modules: Optional[List[str]] = None

    @root_validator
    def validate_fields(cls, values):
        company_name = values.get("company_name")
        abbr = values.get("abbr")
        default_currency = values.get("default_currency")
        country = values.get("country")

        if Utility.check_empty_string(company_name):
            raise ValueError("company_name cannot be empty")
        if not COMPANY_NAME_PATTERN.match(company_name.strip()):
            raise ValueError("company_name can only contain letters, numbers, spaces and underscores (max 100)")
        if Utility.check_empty_string(abbr):
            raise ValueError("abbr cannot be empty")
        if not re.fullmatch(r"[A-Za-z0-9]{1,10}", abbr.strip()):
            raise ValueError("abbr must be 1-10 letters or numbers")
        if Utility.check_empty_string(default_currency):
            raise ValueError("default_currency cannot be empty")
        if not CURRENCY_PATTERN.match(default_currency.strip()):
            raise ValueError("default_currency must be a 3-letter ISO currency code, e.g. INR")
        if Utility.check_empty_string(country):
            raise ValueError("country cannot be empty")
        if not COUNTRY_PATTERN.match(country.strip()):
            raise ValueError("country must be a country name, e.g. India")
        values["crm_admin_email"] = validate_email_address(values.get("crm_admin_email"), "crm_admin_email")

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


class CRMManagedUserInviteRequest(BaseModel):
    """POST /crm/users/invite: invite a new user to the tenant with permitted roles."""
    email: str
    roles: List[str]
    first_name: Optional[str] = None

    @root_validator
    def validate_fields(cls, values):
        values["email"] = validate_email_address(values.get("email"))
        roles = values.get("roles") or []
        if not roles:
            raise ValueError("at least one role must be specified")
        values["roles"] = [r.strip() for r in roles if isinstance(r, str) and r.strip()]
        return values


class CRMUserEnabledRequest(BaseModel):
    enabled: bool


class CRMLeadPromptRequest(BaseModel):
    prompt: str
    enabled: bool = True
    min_confidence: float = 0.7

    @root_validator
    def validate_fields(cls, values):
        prompt = (values.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt cannot be empty")
        if len(prompt) > 4000:
            raise ValueError("prompt must be at most 4000 characters")
        if not 0.0 <= values.get("min_confidence", 0.7) <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        values["prompt"] = prompt
        return values


class CRMLeadPromptTestRequest(BaseModel):
    prompt: Optional[str] = None            # omitted => test the saved prompt
    conversation: List[dict]                # [{"user": "...", "bot": "..."}]


class CRMEnabledRequest(BaseModel):
    enabled: bool
