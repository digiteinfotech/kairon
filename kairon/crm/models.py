from datetime import datetime
from enum import Enum
from mongoengine import StringField, DateTimeField, IntField, BooleanField, ListField
from mongoengine.errors import ValidationError

from kairon.shared.utils import Utility
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import auditlogger


class CRMOnboardingStatus(str, Enum):
    PENDING = "PENDING"
    PROJECT_CREATED = "PROJECT_CREATED"
    BENCH_RUNNING = "BENCH_RUNNING"
    SITE_CREATED = "SITE_CREATED"
    SITE_HEALTHY = "SITE_HEALTHY"
    COMPANY_CREATED = "COMPANY_CREATED"
    USER_CREATED = "USER_CREATED"
    COMPLETED = "COMPLETED"

    UPGRADING_TO_TIER_2 = "UPGRADING_TO_TIER_2"

    FAILED_PROJECT = "FAILED_PROJECT"
    FAILED_BENCH = "FAILED_BENCH"
    FAILED_HEALTH = "FAILED_HEALTH"
    FAILED_COMPANY = "FAILED_COMPANY"
    FAILED_USER = "FAILED_USER"
    FAILED_VERIFICATION = "FAILED_VERIFICATION"
    FAILED_UPGRADE = "FAILED_UPGRADE"


@auditlogger.log
class CRMClientDetails(Auditlog):
    company_name = StringField(required=True)
    abbr = StringField(required=True)
    default_currency = StringField(required=True)
    country = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    onboarding_status = StringField(
        required=True,
        default=CRMOnboardingStatus.PENDING.value,
        choices=[status.value for status in CRMOnboardingStatus],
    )
    project_id = StringField()
    postgres_host = StringField()
    postgres_port = IntField(default=5432)
    db_name = StringField(default="postgres")
    db_user = StringField(default="postgres")
    db_password = StringField()
    site_name = StringField()
    timestamp = DateTimeField(default=datetime.utcnow)

    # Operational Metadata & Atomic Lock
    lock = BooleanField(default=False)
    lock_timestamp = DateTimeField()
    provisioning_id = StringField()
    workflow_started_at = DateTimeField()
    workflow_completed_at = DateTimeField()
    attempt_number = IntField(default=0)
    last_retry = DateTimeField()
    last_error = StringField()
    latest_backup_path = StringField()

    # Provisioned App & Tier Metadata
    tier = IntField(default=2)                                 # 1 (Standalone) or 2 (Full ERP Suite)
    installed_apps = ListField(StringField(), default=list)    # e.g., ["crm"] or ["crm", "erpnext"]

    # Provisioned ERPNext Metadata
    erpnext_site = StringField()
    erpnext_owner_email = StringField()
    erpnext_user = StringField()
    erpnext_password = StringField()
    erpnext_company = StringField()
    erpnext_roles = ListField(StringField(), default=list)

    # CRM Integration Credentials (encrypted, scoped to dedicated integration user)
    kairon_integration_user = StringField()  # e.g. kairon-crm@{site_name}
    kairon_api_key = StringField()           # encrypted Frappe api_key
    kairon_api_secret = StringField()        # encrypted Frappe api_secret
    webhook_secret = StringField()           # encrypted, verifies X-Frappe-Webhook-Signature (ERPNext -> Kairon invitation-accepted)
    lead_webhook_secret = StringField()      # encrypted, signs Kairon -> kairon_connector lead/conversation-sync events

    # Module Selection
    selected_modules = ListField(StringField(), default=list)  # business module keys chosen at onboarding
    module_profile_name = StringField()                        # ERPNext Module Profile doc name for this site

    meta = {
        "strict": False,
        "indexes": [
            {"fields": ["bot", "company_name"], "unique": True},
        ]
    }


    def validate(self, clean=True):
        if Utility.check_empty_string(self.company_name):
            raise ValidationError("Company Name is required")
        if Utility.check_empty_string(self.abbr):
            raise ValidationError("Abbr is required")
        if Utility.check_empty_string(self.default_currency):
            raise ValidationError("Default Currency is required")
        if Utility.check_empty_string(self.country):
            raise ValidationError("Country is required")


class CRMInvitationStatus(str, Enum):
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    EXPIRED = "Expired"
    CANCELLED = "Cancelled"
    COMPANY_ASSIGNED = "CompanyAssigned"


@auditlogger.log
class CRMInvitation(Auditlog):
    """
    Lightweight audit record for each ERPNext user invitation.
    Stores only Kairon-relevant metadata — never duplicates ERPNext's own state.
    The authoritative invitation state always lives in the ERPNext UserInvitation DocType.
    """
    bot = StringField(required=True)
    user = StringField(required=True, default="SYSTEM")
    site_name = StringField(required=True)
    company = StringField(required=True)
    email = StringField(required=True)
    roles = ListField(StringField(), default=list)
    invitation_status = StringField(
        required=True,
        default=CRMInvitationStatus.PENDING.value,
        choices=[s.value for s in CRMInvitationStatus],
    )
    # ERPNext's internal UserInvitation document name (for cancel/resend operations)
    erpnext_invitation_id = StringField()
    invited_at = DateTimeField(default=datetime.utcnow)
    accepted_at = DateTimeField()
    cancelled_at = DateTimeField()
    company_assigned_at = DateTimeField()
    last_error = StringField()

    meta = {
        "indexes": [
            {"fields": ["bot", "email"]},
            {"fields": ["invitation_status"]},
            {"fields": ["site_name", "email"]},
        ]
    }
