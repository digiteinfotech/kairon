from typing import Text, Dict, Any
from urllib.parse import urlparse, urlunparse

from loguru import logger
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, TriggerInfo
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import KaironSystemSlots
from kairon.shared.data.constant import STATUSES
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.request_context import get_request_id
from kairon.shared.utils import Utility
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.processor import CRMProcessor
from kairon.events.publisher import KaironEvent, KaironEventPublisher


class ActionERPNextCRMLeadQualified(ActionsBase):
    """
    Publishes a `lead.qualified` event to the bot's provisioned ERPNext CRM tenant
    (via kairon_connector's webhook receiver) when a conversation reaches the
    qualification point the bot's flow designer wired this action to.

    This mirrors the existing ActionPipedriveLeads / ActionHubspotForms pattern of
    pushing conversation-collected lead data to an external CRM as an explicit flow
    step -- Kairon has no automatic lead-scoring mechanism, so "qualified" means
    "the flow reached the point where this action runs", exactly like the other two.
    Unlike those two, ERPNext is Kairon's first-party CRM integration (kairon/crm/),
    so its target site and shared secret are resolved from the existing
    CRMClientDetails record written once at provisioning time, rather than from a
    new user-configured action doctype.
    """

    ALREADY_QUALIFIED_SLOT = "kairon_lead_qualified_sent"
    # A lead needs at least one real contact channel to be actionable for sales;
    # everything else (name/company/budget/etc.) is best-effort from tracker slots.
    REQUIRED_LEAD_FIELDS = ("email", "phone")

    def __init__(self, bot: Text, name: Text):
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch the bot's CRMClientDetails record. Raises if the bot was never
        onboarded to ERPNext CRM at all -- callers must check is_crm_enabled()
        and onboarding_status separately, since those are recoverable/expected
        states (not configuration errors) that should skip publishing quietly
        rather than raise.
        """
        doc = CRMClientDetails.objects(bot=self.bot).first()
        if not doc:
            raise ValueError(f"No CRM configuration found for bot '{self.bot}'")
        return doc

    @staticmethod
    def _extract_lead_fields(tracker: Tracker) -> Dict[str, Any]:
        return {
            "name": tracker.get_slot("name") or tracker.get_slot("full_name") or "",
            "first_name": tracker.get_slot("first_name") or "",
            "last_name": tracker.get_slot("last_name") or "",
            "email": (tracker.get_slot("email") or "").strip(),
            "phone": tracker.get_slot("phone") or tracker.get_slot("mobile_no") or "",
            "company": tracker.get_slot("company") or tracker.get_slot("organization") or "",
        }

    @staticmethod
    def _build_target_url(base_url: Text, site_name: Text) -> Text:
        """Routes to the correct ERPNext tenant the same way ERPNextClient does
        (Host-derived from the URL itself), by substituting the site's hostname
        into the shared bench base_url."""
        parsed = urlparse(base_url)
        netloc = f"{site_name}:{parsed.port}" if parsed.port else site_name
        return urlunparse((parsed.scheme, netloc, "/api/method/kairon_connector.api.v1.webhook.receive_event", "", "", ""))

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any], **kwargs):
        action_call = kwargs.get('action_call', {})
        status = STATUSES.SUCCESS.value
        exception = None
        bot_response = "Thanks! I've passed your details on to our sales team."
        result_payload: Dict[str, Any] = {}
        skip_reason = None

        try:
            # 1. CRM-disabled gate -- must be checked before anything else touches
            #    CRM config or resolves a target: a disabled bot must never emit this.
            if not MongoProcessor.is_crm_enabled(self.bot):
                skip_reason = "crm_disabled"
            # 2. Idempotency -- only fire once per conversation.
            elif tracker.get_slot(self.ALREADY_QUALIFIED_SLOT):
                skip_reason = "already_qualified"
            else:
                doc = self.retrieve_config()
                if doc.onboarding_status != CRMOnboardingStatus.COMPLETED.value:
                    skip_reason = f"provisioning_incomplete:{doc.onboarding_status}"
                else:
                    lead_fields = self._extract_lead_fields(tracker)
                    if not any(lead_fields.get(f) for f in self.REQUIRED_LEAD_FIELDS):
                        skip_reason = f"missing_required_fields:{'|'.join(self.REQUIRED_LEAD_FIELDS)}"
                    else:
                        _, transcript = ActionUtility.prepare_message_trail_as_str(tracker.events)
                        event = KaironEvent(
                            event_type="lead.qualified",
                            payload={
                                "bot_id": self.bot,
                                "conversation_id": tracker.sender_id,
                                "summary": f"Qualified lead from Kairon chatbot conversation ({tracker.sender_id}).",
                                "transcript": transcript,
                                "lead_data": lead_fields,
                                "qualification_score": tracker.get_slot("qualification_score") or 100,
                                "intent": tracker.get_intent_of_latest_message(skip_fallback_intent=False) or "",
                                "budget": tracker.get_slot("budget") or "",
                                "industry": tracker.get_slot("industry") or "",
                            }
                        )

                        crm_config = Utility.environment.get("crm", {})
                        base_url = crm_config.get("bench", {}).get("base_url", "http://localhost:8080")
                        target_url = self._build_target_url(base_url, doc.site_name)
                        secret = CRMProcessor.get_lead_webhook_secret(self.bot)

                        publish_result = KaironEventPublisher.publish_webhook(target_url, secret, event)
                        result_payload = {
                            "event_id": event.event_id,
                            "correlation_id": event.correlation_id,
                            "target_url": target_url,
                            "status_code": publish_result.get("status_code"),
                            "success": publish_result.get("success"),
                        }
                        if not publish_result.get("success"):
                            status = STATUSES.FAIL.value
                            exception = f"ERPNext webhook rejected event: HTTP {publish_result.get('status_code')} {publish_result.get('response_text')}"

            if skip_reason:
                result_payload = {"skipped_reason": skip_reason}
                if skip_reason == "crm_disabled":
                    bot_response = None
                logger.debug(f"[ActionERPNextCRMLeadQualified] Skipped publish for bot '{self.bot}', conversation '{tracker.sender_id}': {skip_reason}")

        except Exception as e:
            logger.exception(e)
            status = STATUSES.FAIL.value
            exception = str(e)
            bot_response = "I've noted your details, but there was an issue notifying our sales team -- someone will still follow up."
        finally:
            trigger_info_data = action_call.get('trigger_info') or {}
            trigger_info_obj = TriggerInfo(**trigger_info_data)
            ActionServerLogs(
                type="erpnext_crm_lead_qualified_action",
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot=self.bot,
                exception=exception,
                bot_response=bot_response,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                messages=result_payload,
                trigger_info=trigger_info_obj,
                request_id=get_request_id()
            ).save()

        if bot_response:
            dispatcher.utter_message(bot_response)

        slots_to_set = {KaironSystemSlots.kairon_action_response.value: bot_response}
        if result_payload.get("success") or skip_reason == "already_qualified":
            slots_to_set[self.ALREADY_QUALIFIED_SLOT] = True
        return slots_to_set
