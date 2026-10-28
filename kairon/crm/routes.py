from fastapi import APIRouter, Security, Query, Request, Header

from kairon.api.models import Response
from kairon.shared.constants import ADMIN_ACCESS
from kairon.shared.models import User
from kairon.crm.auth import get_crm_user_and_bot
from kairon.crm.processor import CRMProcessor
from kairon.crm.analytics.processor import LeadQualificationProcessor
from kairon.crm.services.admin_invitation import CRMAdminInvitationService
from kairon.crm.services.user_management import CRMUserManagement
from kairon.crm.schemas import (
    CRMManagedUserInviteRequest,
    CRMUserEnabledRequest,
    CRMEnabledRequest,
    CRMLeadPromptRequest,
    CRMLeadPromptTestRequest,
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
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Initiates automated ERPNext site provisioning for a tenant bot.

    - **Request Schema**: `CRMOnboardRequest` (company_name, abbr, default_currency, country, crm_admin_email, selected_modules)
    - **Response Schema**: `Response` wrapping `{ status, site_name, company, erpnext_user, accepted, provisioned, failed }` (`temporary_password` only when the deployment opts in). `success` only means the request was accepted; read `provisioned`/`failed`/`status` for the real outcome.
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
        crm_admin_email=req.crm_admin_email,
    )
    outcome = CRMProcessor.onboarding_outcome(result)
    # The one-time ERPNext password is NOT returned by default. A deployment that still needs it (clients that
    # display it) can opt in with crm.bench.onboard_return_temporary_password=true (BENCH_ONBOARD_RETURN_TEMP_PASSWORD).
    if not CRMProcessor.returns_temporary_password():
        outcome.pop("temporary_password", None)
    # `success` means the request was accepted and a run was attempted. The provisioning result is
    # `data.provisioned` / `data.failed` / `data.status`; the message states it so no caller reads a failed
    # run as a created tenant.
    if outcome["provisioned"]:
        message = "CRM tenant provisioned successfully"
    elif outcome["failed"]:
        message = f"CRM onboarding request accepted but provisioning failed ({outcome['status']})"
    else:
        message = f"CRM onboarding request accepted; provisioning is {outcome.get('status') or 'in progress'}"
    return Response(data=outcome, message=message)


@router.post("/validate", response_model=Response)
def validate_tenant_config(
    req: CRMOnboardRequest,
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Validates a tenant configuration without provisioning anything.

    - **Request Schema**: `CRMOnboardRequest` (same body as `/onboard`)
    - **Response Schema**: `Response` wrapping `{ valid, company_exists, onboarding_status }`
    - **Possible Error Responses**: CRM not enabled for the bot, empty/invalid company fields (422/400).
    - **Security Note**: Requires `ADMIN_ACCESS`. Read-only; no site, DB or Mongo record is created.
    """
    CRMProcessor.assert_staff_allowed(current_user.email)
    result = CRMProcessor.validate_tenant_config(
        bot=current_user.get_bot(),
        company_name=req.company_name,
        abbr=req.abbr,
        default_currency=req.default_currency,
        country=req.country,
    )
    return Response(data=result)


@router.post("/metering-sync", response_model=Response)
def sync_metering_metadata(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Re-sends the tenant's final provisioning state to Kairon Metering (retry for a failed handoff).

    - **Response Schema**: `Response` wrapping `{ synced, event_id, reason }`; `reason` is null when synced,
      `not_configured` when no Metering URL/secret is set, otherwise a short delivery failure description.
    - **Possible Error Responses**: no CRM configuration, or provisioning has not finished.
    - **Security Note**: Requires `ADMIN_ACCESS`. Sends metadata only (no credentials); safe to repeat
      because Metering ignores duplicate event ids.
    """
    result = CRMProcessor.sync_metering_metadata(current_user.get_bot())
    return Response(data=result)


@router.get("/available-modules", response_model=Response)
def get_available_modules(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
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
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
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
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
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
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
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
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
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
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
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
    bot: str,
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
        bot=bot,
    )
    return Response(data=result, message="Webhook processed successfully")


@router.post("/login-link", response_model=Response)
def create_login_link(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Returns a signed, single-use link (valid 60 seconds) that logs the tenant's creator into the ERPNext/CRM tenant.

    - **Response Schema**: `Response` wrapping `{ login_url, expires_in }`. The link is a credential: do not log or store it.
    - **Possible Error Responses**: tenant not COMPLETED, or the caller is not the user who created the tenant.
    - **Security Note**: Requires `ADMIN_ACCESS`. The signature uses the tenant's webhook secret, which is never returned.
    """
    return Response(data=CRMProcessor.build_login_link(current_user.get_bot(), current_user.email))


@router.get("/status", response_model=Response)
def get_onboarding_status(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Returns current onboarding lifecycle status for the tenant bot.

    - **Request Schema**: None
    - **Response Schema**: `Response` wrapping `{ onboarding_status, status (Pending|Provisioning|Configuring|Verifying|Ready|Failed),
      ready, failed, company_name, crm_admin_email, tenant_url, attempt_number, invitation: { status, attempts, sent_at, next_attempt_at, last_error } }`.
      `ready` is true only for a verified tenant. Invitation delivery never affects `status`.
    - **Security Note**: Requires `ADMIN_ACCESS`.
    """
    return Response(data=CRMProcessor.get_provisioning_status(current_user.get_bot()))


@router.get("/details", response_model=Response)
def get_crm_details(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Returns full provisioning metadata, database connection info, and web access URLs for the tenant CRM.

    - **Request Schema**: None
    - **Response Schema**: `Response` wrapping `CRMClientDetails` dict (allowlisted fields only: company fields, onboarding_status, site_name, site_url, tier, installed_apps, selected_modules, timestamps). Credentials (Administrator password, DB password, Frappe API key/secret, webhook secrets) and raw provisioning errors are never included.
    - **Security Note**: Admin authorization required (`ADMIN_ACCESS`).
    """
    details = CRMProcessor.get_crm_public_details(current_user.get_bot())
    return Response(data=details)


@router.get("/users", response_model=Response)
def get_erpnext_users(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
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


@router.delete("/project", response_model=Response)
def delete_project(
    company_name: str = Query(..., description="Company name"),
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
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



@router.post("/admin-invitation/resend", response_model=Response)
def resend_admin_invitation(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Re-sends the CRM administrator's invitation email (one attempt, 60 s cooldown).

    - **Response Schema**: `Response` wrapping `{ attempted, invitation_status, attempts }`. `attempted=false` means the
      cooldown, a concurrent attempt or the tenant state prevented a send.
    - **Security Note**: `ADMIN_ACCESS` plus the optional staff allowlist. A fresh single-use setup link is generated for
      each send; nothing secret is returned or stored.
    """
    CRMProcessor.assert_staff_allowed(current_user.email)
    return Response(data=CRMAdminInvitationService.send(current_user.get_bot(), force=True))


@router.get("/managed-users", response_model=Response)
def list_managed_users(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Users of this bot's tenant with roles and account/invitation status, read through the tenant's kairon_connector.

    - **Response Schema**: `Response` wrapping a list of `{ email, first_name, last_name, enabled, status
      (Active|Invited|Not signed in|Disabled), roles, created, last_login }`. Administrator, Guest and the integration
      user are never listed.
    - **Possible Error Responses**: tenant not ready; connector unreachable or rejecting the signed request.
    - **Security Note**: `ADMIN_ACCESS` + optional staff allowlist. The tenant is resolved from the caller's bot only.
    """
    CRMProcessor.assert_staff_allowed(current_user.email)
    return Response(data=CRMUserManagement.list_users(current_user.get_bot()))


@router.get("/users/assignable-roles", response_model=Response)
def get_assignable_roles(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """Roles that may be granted through user management (never System Manager / Administrator)."""
    CRMProcessor.assert_staff_allowed(current_user.email)
    return Response(data={"roles": CRMUserManagement.assignable_roles()})


@router.post("/users/invite", response_model=Response)
def invite_managed_user(
    req: CRMManagedUserInviteRequest,
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Invites a new user to the tenant through the tenant's kairon_connector.

    - **Request Schema**: `CRMManagedUserInviteRequest` (email, roles, first_name?)
    - **Response Schema**: `Response` wrapping `{ email, roles, status: "invited", email_delivery: "sent"|"failed" }`
    - **Possible Error Responses**: tenant not ready, role not permitted, user already exists.
    - **Security Note**: `ADMIN_ACCESS` + staff allowlist; roles are checked here and again by the connector.
    """
    CRMProcessor.assert_staff_allowed(current_user.email)
    return Response(data=CRMUserManagement.invite_user(
        current_user.get_bot(), current_user.get_user(), req.email, req.roles, req.first_name))


@router.get("/users/{email}", response_model=Response)
def get_managed_user(
    email: str,
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """Account and roles of one tenant user (via the connector)."""
    CRMProcessor.assert_staff_allowed(current_user.email)
    return Response(data=CRMUserManagement.get_user(current_user.get_bot(), email))


@router.post("/users/{email}/resend-invitation", response_model=Response)
def resend_managed_user_invitation(
    email: str,
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """Sends the user a fresh single-use setup link (60 s cooldown)."""
    CRMProcessor.assert_staff_allowed(current_user.email)
    return Response(data=CRMUserManagement.resend_invitation(current_user.get_bot(), current_user.get_user(), email))


@router.put("/users/{email}/enabled", response_model=Response)
def set_managed_user_enabled(
    email: str,
    req: CRMUserEnabledRequest,
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """Enables or disables a tenant user. The CRM administrator cannot be disabled here."""
    CRMProcessor.assert_staff_allowed(current_user.email)
    return Response(data=CRMUserManagement.set_enabled(current_user.get_bot(), current_user.get_user(), email, req.enabled))


@router.get("/lead-qualification/prompt", response_model=Response)
def get_lead_prompt(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """Active lead-qualification prompt for this bot/company, or null when none is configured."""
    return Response(data=LeadQualificationProcessor.get_prompt(current_user.get_bot()))


@router.put("/lead-qualification/prompt", response_model=Response)
def save_lead_prompt(
    req: CRMLeadPromptRequest,
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Creates or updates the prompt. Changing the text increments `version`; every analysis records the version it used.
    The prompt is scoped to the caller's bot and is never applied to another bot's conversations.
    """
    return Response(data=LeadQualificationProcessor.save_prompt(
        current_user.get_bot(), current_user.get_user(), req.prompt, req.enabled, req.min_confidence))


@router.get("/lead-qualification/prompt/revisions", response_model=Response)
def list_lead_prompt_revisions(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    return Response(data=LeadQualificationProcessor.list_revisions(current_user.get_bot()))


@router.post("/lead-qualification/prompt/test", response_model=Response)
def test_lead_prompt(
    req: CRMLeadPromptTestRequest,
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """Runs the prompt on a sample conversation. Read-only: nothing is stored and nothing is sent to ERPNext."""
    return Response(data=LeadQualificationProcessor.test_prompt(
        current_user.get_bot(), current_user.get_user(), req.prompt, req.conversation))


@router.get("/lead-qualification/status", response_model=Response)
def get_lead_analysis_status(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """Last run, watermark and per-status counts for this bot's analytics job."""
    return Response(data=LeadQualificationProcessor.job_status(current_user.get_bot()))


@router.get("/lead-qualification/failed", response_model=Response)
def get_failed_leads(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """Permanently failed analyses/deliveries (the dead-letter view): sender id, attempts and short error only."""
    return Response(data=LeadQualificationProcessor.failed_leads(current_user.get_bot()))


@router.post("/lead-qualification/retry-failed", response_model=Response)
def retry_failed_leads(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """Requeues dead-lettered rows for the next scheduled run."""
    return Response(data=LeadQualificationProcessor.retry_failed(current_user.get_bot()))


@router.get("/enabled", response_model=Response)
def get_crm_enabled(
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """Whether CRM is enabled for this bot: `{ enabled: bool }`."""
    return Response(data={"enabled": CRMProcessor.is_crm_enabled(current_user.get_bot())})


@router.put("/enabled", response_model=Response)
def set_crm_enabled(
    req: CRMEnabledRequest,
    current_user: User = Security(
        get_crm_user_and_bot, scopes=ADMIN_ACCESS
    ),
):
    """
    Turns CRM on or off for this bot (a simple toggle). Changes only `enable_crm`; no tenant is created or removed, and
    an existing tenant is preserved when disabling. Provisioning is a separate step (`POST /onboard`).
    """
    CRMProcessor.assert_staff_allowed(current_user.email)
    return Response(data=CRMProcessor.set_crm_enabled(current_user.get_bot(), current_user.get_user(), req.enabled))
