from datetime import datetime
from enum import Enum
from mongoengine import StringField, DateTimeField, IntField, BooleanField, ListField
from mongoengine.errors import ValidationError

from kairon.exceptions import AppException
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


class CRMAdminInvitationStatus(str, Enum):
    NOT_SENT = "NOT_SENT"      # tenant not ready yet, nothing to send
    PENDING = "PENDING"        # tenant ready; waiting for (re)delivery
    SENDING = "SENDING"        # claimed by exactly one worker
    SENT = "SENT"              # accepted by the mail provider (not a read receipt)
    FAILED = "FAILED"          # last attempt failed; retried until max attempts


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

    # CRM administrator: the person who administers the tenant (not necessarily the bot owner) and who receives
    # the invitation once the tenant is verified ready.
    crm_admin_email = StringField()

    # Administrator invitation delivery state. Independent of `onboarding_status`: a failed email never fails
    # provisioning. Holds diagnostics only, never the setup link or any credential.
    invitation_status = StringField(
        default=CRMAdminInvitationStatus.NOT_SENT.value,
        choices=[s.value for s in CRMAdminInvitationStatus],
    )
    invitation_attempts = IntField(default=0)
    invitation_provisioning_id = StringField()   # provisioning run the invitation belongs to (duplicate guard)
    invitation_claimed_at = DateTimeField()      # when SENDING was claimed (stale-claim recovery)
    invitation_last_attempt_at = DateTimeField()
    invitation_sent_at = DateTimeField()
    invitation_next_attempt_at = DateTimeField()
    invitation_last_error = StringField()        # short error class/message, no secrets

    # Metering handoff state (metadata only; see kairon/crm/metering_sync.py)
    metering_synced = BooleanField(default=False)
    metering_synced_at = DateTimeField()
    metering_event_id = StringField()

    meta = {
        "strict": False,
        "indexes": [
            {"fields": ["bot", "company_name"], "unique": True},
        ]
    }

    # mongoengine builds `meta` indexes lazily on first use, so a unique `site_name` index declared there would make every
    # CRM query fail on a database that already holds duplicates. It is created by `ensure_site_name_index` instead.
    SITE_NAME_INDEX = "site_name_unique_sparse"

    @classmethod
    def duplicate_site_names(cls) -> list:
        """`[{"site_name", "count"}]` for site names used by more than one record. Records without a site name are ignored."""
        pipeline = [
            {"$match": {"site_name": {"$type": "string", "$ne": ""}}},
            {"$group": {"_id": "$site_name", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$sort": {"_id": 1}},
        ]
        return [{"site_name": row["_id"], "count": row["count"]} for row in cls._get_collection().aggregate(pipeline)]

    @classmethod
    def has_site_name_index(cls) -> bool:
        return cls.SITE_NAME_INDEX in cls._get_collection().index_information()

    @classmethod
    def ensure_site_name_index(cls) -> dict:
        """
        Idempotently creates the sparse unique index on `site_name` (a tenant's hostname is its identity, and the
        check-then-write clash test alone lets two bots race to one name). Refuses, and changes nothing, when duplicates
        already exist: records are never deleted or rewritten here, an operator resolves them first.
        """
        from pymongo.errors import PyMongoError
        duplicates = cls.duplicate_site_names()
        if duplicates:
            listed = ", ".join(f"{d['site_name']} (x{d['count']})" for d in duplicates[:10])
            raise AppException(f"Cannot create the unique site_name index: {len(duplicates)} site name(s) are used by more "
                               f"than one tenant record: {listed}. Resolve them, then run this again.")
        try:
            cls._get_collection().create_index([("site_name", 1)], name=cls.SITE_NAME_INDEX, unique=True, sparse=True)
        except PyMongoError as e:
            raise AppException(f"Could not create the site_name index: {type(e).__name__}")
        return {"index": cls.SITE_NAME_INDEX, "duplicates": 0}

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
