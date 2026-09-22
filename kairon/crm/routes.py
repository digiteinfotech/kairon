from fastapi import APIRouter, Security, Query, Request, Header

from kairon.api.models import Response
from kairon.shared.constants import ADMIN_ACCESS
from kairon.shared.auth import Authentication
from kairon.shared.models import User
from kairon.crm.processor import CRMProcessor
from kairon.crm.schemas import (
    CRMOnboardRequest,
    CRMCreateUserRequest,
    CRMInviteUserRequest,
    CRMConfigureModulesRequest,
)

router = APIRouter()
crm_processor = CRMProcessor()


@router.post("/onboard", response_model=Response)
def onboard_company(
    req: CRMOnboardRequest,
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Initiates automated ERPNext site provisioning for a tenant bot.

    - **Request Schema**: `CRMOnboardRequest` (company_name, abbr, default_currency, country, selected_modules)
    - **Response Schema**: `Response` wrapping `{ status, site_name, company, erpnext_user, temporary_password }`
    - **Possible Error Responses**:
      - 400 Bad Request: Missing or invalid company parameters.
      - 422 Unprocessable Entity: Empty module selection or forbidden system module request.
      - 500 Internal Server Error: Provisioning error (recorded in `last_error`).
    - **Security Note**: Requires `ADMIN_ACCESS` token. Only authorized tenant admins may provision CRM instances.
    - **Expected Behavior**: Performs atomic lock, creates site in Bench, initializes Fernet encryption key, reloads Gunicorn, creates integration user, configures module profiles, and provisions administrator user.
    """
    result = crm_processor.onboard_company(
        company_name=req.company_name,
        abbr=req.abbr,
        default_currency=req.default_currency,
        country=req.country,
        bot=current_user.get_bot(),
        current_user=current_user,
        selected_modules=req.selected_modules,
    )
    return Response(data=result, message="CRM onboarding initiated successfully")


@router.get("/available-modules", response_model=Response)
def get_available_modules(
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Retrieves available business modules for tenant module selection.

    - **Request Schema**: None (Path param bot extracted from Security context).
    - **Response Schema**: `Response` wrapping `{ modules: [...], total_count }`
    - **Possible Error Responses**:
      - 401 Unauthorized: Invalid or expired access token.
      - 404 Not Found: Tenant CRM client configuration not initialized.
    - **Security Note**: Scoped to bot admin token (`ADMIN_ACCESS`).
    - **Expected Behavior**: Performs live discovery against installed ERPNext workspaces; falls back to static catalog if site offline.
    """
    result = CRMProcessor.get_available_modules(bot=current_user.get_bot())
    return Response(data=result)


@router.get("/selected-modules", response_model=Response)
def get_selected_modules(
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Fetches the list of active/selected modules for the provisioned CRM instance.

    - **Request Schema**: None
    - **Response Schema**: `Response` wrapping `{ selected_modules: [...], module_profile_name }`
    - **Possible Error Responses**:
      - 404 Not Found: Bot CRM details missing.
    - **Security Note**: Admin token required (`ADMIN_ACCESS`).
    - **Expected Behavior**: Returns stored module selection array from `CRMClientDetails`.
    """
    result = CRMProcessor.get_selected_modules(bot=current_user.get_bot())
    return Response(data=result)


@router.post("/configure-modules", response_model=Response)
def configure_modules(
    req: CRMConfigureModulesRequest,
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Updates selected business modules and synchronizes Module Profile & Workspace visibility.

    - **Request Schema**: `CRMConfigureModulesRequest` (selected_modules: List[str])
    - **Response Schema**: `Response` wrapping `{ selected_modules, workspace_visibility }`
    - **Possible Error Responses**:
      - 400 Bad Request: Invalid module selection or attempting to disable required infrastructure.
      - 502 Bad Gateway: ERPNext REST API communication failure.
    - **Security Note**: Enforces admin authorization (`ADMIN_ACCESS`).
    - **Expected Behavior**: Updates ERPNext `Module Profile`, sets `is_hidden = 1` on non-selected workspaces, sets user default workspace, and flushes site cache.
    """
    result = CRMProcessor.configure_modules(
        bot=current_user.get_bot(),
        user=current_user.get_user(),
        selected_modules=req.selected_modules,
    )
    return Response(data=result, message="Module configuration updated successfully")


@router.post("/reconcile-modules", response_model=Response)
def reconcile_modules(
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Detects and repairs configuration drift between Kairon DB and ERPNext site.

    - **Request Schema**: None
    - **Response Schema**: `Response` wrapping `{ status, drifted, repaired, selected_modules }`
    - **Possible Error Responses**:
      - 500 Internal Server Error: Reconciliation execution failure.
    - **Security Note**: Protected by `ADMIN_ACCESS` security dependency.
    - **Expected Behavior**: Compares live ERPNext Module Profile & Workspace visibility with Kairon state; repairs any discrepancy automatically.
    """
    result = CRMProcessor.reconcile_modules(
        bot=current_user.get_bot(),
        user=current_user.get_user(),
    )
    return Response(data=result, message="Module configuration reconciliation completed")


@router.post("/create-user", response_model=Response)
def create_crm_user(
    req: CRMCreateUserRequest,
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Creates a new user directly in the provisioned ERPNext instance.

    - **Request Schema**: `CRMCreateUserRequest` (email: EmailStr, role: str)
    - **Response Schema**: `Response` wrapping `{ email, role, status }`
    - **Possible Error Responses**:
      - 400 Bad Request: Invalid email or role requested.
      - 409 Conflict: User email already exists on the ERPNext instance.
    - **Security Note**: Scoped to `ADMIN_ACCESS`.
    - **Expected Behavior**: Invokes `ERPNextClient.create_user`, assigns company permissions, roles, and current tenant Module Profile.
    """
    result = CRMProcessor.create_crm_user(
        bot=current_user.get_bot(),
        user=current_user.get_user(),
        email=req.email,
        role=req.role,
    )
    return Response(data=result, message="CRM user creation initiated")


@router.post("/invite-user", response_model=Response)
def invite_erpnext_user(
    req: CRMInviteUserRequest,
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Sends an invitation email to a new user to join the tenant ERPNext CRM instance.

    - **Request Schema**: `CRMInviteUserRequest` (email: EmailStr, roles: List[str], company_name: str)
    - **Response Schema**: `Response` wrapping `{ email, status, message }`
    - **Possible Error Responses**:
      - 400 Bad Request: Missing user credentials or invalid roles.
    - **Security Note**: Requires `ADMIN_ACCESS`.
    - **Expected Behavior**: Creates user record in ERPNext with invitation flag and dispatches email via configured Mailpit/SMTP relay.
    """
    result = CRMProcessor.invite_erpnext_user(
        bot=current_user.get_bot(),
        email=req.email,
        roles=req.roles,
        company_name=req.company_name,
        user=current_user.get_user(),
    )
    return Response(data=result, message="ERPNext user invitation processed")


@router.post("/webhook/invitation-accepted", response_model=Response)
async def handle_invitation_webhook(
    request: Request,
    x_kairon_site: str = Header(..., alias="X-Kairon-Site"),
    x_frappe_webhook_signature: str = Header(..., alias="X-Frappe-Webhook-Signature"),
):
    """
    Public webhook endpoint triggered by ERPNext when an invited user accepts their invitation.

    - **Request Schema**: Standard Frappe Webhook JSON payload + `X-Kairon-Site` & `X-Frappe-Webhook-Signature` headers.
    - **Response Schema**: `Response` wrapping `{ status, user_email, site_name }`
    - **Possible Error Responses**:
      - 401 Unauthorized: Invalid HMAC SHA-256 webhook signature.
    - **Security Note**: Validated via secret HMAC-SHA256 signature verification.
    - **Expected Behavior**: Validates signature, verifies user document status, and completes user onboarding synchronization.
    """
    raw_body = await request.body()
    payload = await request.json()
    result = CRMProcessor.handle_invitation_webhook(
        site_name=x_kairon_site,
        raw_body=raw_body,
        signature_header=x_frappe_webhook_signature,
        payload=payload,
    )
    return Response(data=result, message="Webhook processed successfully")


@router.get("/status", response_model=Response)
def get_onboarding_status(
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Returns current onboarding lifecycle status for the tenant bot.

    - **Request Schema**: None
    - **Response Schema**: `Response` wrapping `{ onboarding_status: str }`
    - **Security Note**: Requires `ADMIN_ACCESS`.
    """
    details = CRMProcessor.get_crm_details(current_user.get_bot())
    return Response(
        data={"onboarding_status": details.get("onboarding_status")}
    )


@router.get("/details", response_model=Response)
def get_crm_details(
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Returns full provisioning metadata, database connection info, and web access URLs for the tenant CRM.

    - **Request Schema**: None
    - **Response Schema**: `Response` wrapping `CRMClientDetails` dict (status, site_url, site_name, db_name, last_error, selected_modules).
    - **Security Note**: Admin authorization required (`ADMIN_ACCESS`).
    """
    details = CRMProcessor.get_crm_details(current_user.get_bot())
    return Response(data=details)


@router.get("/users", response_model=Response)
def get_erpnext_users(
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Retrieves list of registered users on the tenant's ERPNext instance.

    - **Request Schema**: None
    - **Response Schema**: `Response` wrapping list of ERPNext user records.
    - **Security Note**: Scoped to `ADMIN_ACCESS`.
    """
    users = CRMProcessor.get_erpnext_users(current_user.get_bot())
    return Response(data=users)


@router.get("/tables", response_model=Response)
def get_db_tables(
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Inspector tool: Lists database tables in the tenant's dedicated PostgreSQL database.

    - **Request Schema**: None
    - **Response Schema**: `Response` wrapping list of table names (e.g., `tabCompany`, `tabUser`).
    - **Security Note**: Restricted to bot administrators (`ADMIN_ACCESS`).
    """
    tables = CRMProcessor.get_db_tables(current_user.get_bot())
    return Response(data=tables)


@router.get("/tables/{table_name}", response_model=Response)
def get_table_content(
    table_name: str,
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Inspector tool: Fetches raw content of a specific PostgreSQL database table.

    - **Request Schema**: Path parameter `table_name: str`, Query parameter `limit: int` (default 50).
    - **Response Schema**: `Response` wrapping rows list.
    - **Security Note**: Restricted to bot administrators (`ADMIN_ACCESS`). Sanitizes table_name to prevent SQL injection.
    """
    content = CRMProcessor.get_table_content(
        bot=current_user.get_bot(),
        table_name=table_name,
        limit=limit
    )
    return Response(data=content)


@router.delete("/project", response_model=Response)
def delete_project(
    company_name: str = Query(..., description="Company name"),
    current_user: User = Security(
        Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Teardown endpoint: Deletes CRM client details metadata.

    - **Request Schema**: Query parameter `company_name: str`
    - **Response Schema**: `Response` wrapping `{ success: True }`
    - **Security Note**: High privilege admin operation (`ADMIN_ACCESS`).
    """
    result = CRMProcessor.delete_crm_details(current_user.get_bot(), company_name)
    return Response(data=result)

