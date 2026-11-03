from typing import Text

from loguru import logger

from kairon.crm.analytics.pipeline import LeadAnalysisPipeline
from kairon.crm.processor import CRMProcessor
from kairon.crm.services.admin_invitation import CRMAdminInvitationService
from kairon.events.definitions.base import EventsBase
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass
from kairon.shared.utils import Utility

SCHEDULE_EVENT_ID = "crm_lead_analysis"
SCHEDULE_CRON = "*/5 * * * *"
SYSTEM_BOT = "system"          # EventRequest requires a bot and user; this job spans every CRM-enabled bot
SYSTEM_USER = "kairon-system"


class CRMLeadAnalysisEvent(EventsBase):
    """
    Platform-wide, five-minute CRM job. One pass: analyses idle conversations of every CRM-enabled bot (per-bot leases
    make overlapping runs harmless), retries pending administrator invitations, and reconciles invitations whose
    acceptance webhook was missed. Each part is isolated, so one failing never blocks the others.
    """

    def __init__(self, bot: Text = SYSTEM_BOT, user: Text = SYSTEM_USER, **kwargs):
        self.bot = bot
        self.user = user

    def validate(self):
        return True

    def enqueue(self, **kwargs):
        payload = {"bot": SYSTEM_BOT, "user": SYSTEM_USER, "event_id": SCHEDULE_EVENT_ID}
        Utility.request_event_server(EventClass.crm_lead_analysis, payload)

    def execute(self, **kwargs):
        summary = {}
        for name, job in (("leads", lambda: LeadAnalysisPipeline().run_cycle()),
                          ("invitations", CRMAdminInvitationService.retry_pending),
                          ("reconciliation", CRMProcessor.reconcile_invitations)):
            try:
                summary[name] = job()
            except Exception as e:
                logger.error(f"[CRMLeadAnalysis] {name} sweep failed: {type(e).__name__}")
                summary[name] = {"error": type(e).__name__}
        logger.info(f"[CRMLeadAnalysis] cycle complete: {summary}")
        return summary

    @staticmethod
    def register_schedule(cron_exp: Text = SCHEDULE_CRON, timezone: Text = "UTC"):
        """Idempotently (re)registers the single platform job on the event server."""
        payload = {"bot": SYSTEM_BOT, "user": SYSTEM_USER, "event_id": SCHEDULE_EVENT_ID}
        try:
            Utility.request_event_server(EventClass.crm_lead_analysis, payload, method="PUT", is_scheduled=True,
                                         cron_exp=cron_exp, timezone=timezone)
        except AppException:
            Utility.request_event_server(EventClass.crm_lead_analysis, payload, method="POST", is_scheduled=True,
                                         cron_exp=cron_exp, timezone=timezone)
