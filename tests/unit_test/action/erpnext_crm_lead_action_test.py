import os

os.environ["system_file"] = "./tests/testing_data/system.yaml"

import uuid

import pytest
from mongoengine import connect
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from unittest import mock

from kairon.shared.utils import Utility
Utility.load_system_metadata()

from kairon.actions.definitions.erpnext_crm_lead import ActionERPNextCRMLeadQualified
from kairon.actions.definitions.factory import ActionFactory
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.data_objects import ActionServerLogs, Actions
from kairon.shared.data.data_objects import BotSettings
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.processor import CRMProcessor


class TestERPNextCRMLeadAction:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @staticmethod
    def _make_tracker(sender_id, slots=None, intent="request_demo", text="I want a demo"):
        slots = slots or {}
        events = [
            {"event": "user", "text": text},
            {"event": "bot", "text": "Sure, let me get your details."},
        ]
        latest_message = {"text": text, "intent": {"name": intent}, "intent_ranking": [{"name": intent}]}
        return Tracker(sender_id=sender_id, slots=slots, events=events, paused=False,
                        latest_message=latest_message, followup_action=None, active_loop=None,
                        latest_action_name=None)

    @staticmethod
    def _provision_bot(bot, enable_crm=True, onboarding_status=CRMOnboardingStatus.COMPLETED.value,
                        site_name="kairon-test-tenant.localhost", secret="test_secret_for_unit_tests"):
        BotSettings(bot=bot, user="tester", enable_crm=enable_crm).save()
        CRMClientDetails(
            bot=bot, company_name=f"Test Co {bot}", abbr="TC", default_currency="USD", country="US",
            user="tester", onboarding_status=onboarding_status, site_name=site_name,
            lead_webhook_secret=Utility.encrypt_message(secret),
        ).save()
        return secret

    @pytest.mark.asyncio
    async def test_skips_publish_when_crm_disabled(self):
        bot = f"bot_{uuid.uuid4().hex[:8]}"
        self._provision_bot(bot, enable_crm=False)

        tracker = self._make_tracker(sender_id=f"conv_{uuid.uuid4().hex[:8]}", slots={"email": "lead@example.com"})
        dispatcher = CollectingDispatcher()
        action = ActionERPNextCRMLeadQualified(bot, "erpnext_crm_lead_qualified")

        with mock.patch("kairon.actions.definitions.erpnext_crm_lead.KaironEventPublisher.publish_webhook") as mock_publish:
            result = await action.execute(dispatcher, tracker, {})

        mock_publish.assert_not_called()
        assert action.ALREADY_QUALIFIED_SLOT not in result

        log = ActionServerLogs.objects(bot=bot, sender=tracker.sender_id).order_by("-timestamp").first()
        assert log.messages.get("skipped_reason") == "crm_disabled"

    @pytest.mark.asyncio
    async def test_skips_publish_when_required_lead_fields_missing(self):
        bot = f"bot_{uuid.uuid4().hex[:8]}"
        self._provision_bot(bot)

        # No email AND no phone slot set -- nothing actionable to hand to sales.
        tracker = self._make_tracker(sender_id=f"conv_{uuid.uuid4().hex[:8]}", slots={"name": "Someone"})
        dispatcher = CollectingDispatcher()
        action = ActionERPNextCRMLeadQualified(bot, "erpnext_crm_lead_qualified")

        with mock.patch("kairon.actions.definitions.erpnext_crm_lead.KaironEventPublisher.publish_webhook") as mock_publish:
            result = await action.execute(dispatcher, tracker, {})

        mock_publish.assert_not_called()
        log = ActionServerLogs.objects(bot=bot, sender=tracker.sender_id).order_by("-timestamp").first()
        assert log.messages.get("skipped_reason", "").startswith("missing_required_fields")

    @pytest.mark.asyncio
    async def test_publishes_once_then_idempotently_skips_duplicate_within_same_conversation(self):
        bot = f"bot_{uuid.uuid4().hex[:8]}"
        self._provision_bot(bot)
        sender_id = f"conv_{uuid.uuid4().hex[:8]}"
        dispatcher = CollectingDispatcher()
        action = ActionERPNextCRMLeadQualified(bot, "erpnext_crm_lead_qualified")

        tracker_first = self._make_tracker(sender_id=sender_id, slots={"email": "dup@example.com"})
        with mock.patch("kairon.actions.definitions.erpnext_crm_lead.KaironEventPublisher.publish_webhook",
                         return_value={"status_code": 202, "success": True, "response_text": "{}"}) as mock_publish:
            first_result = await action.execute(dispatcher, tracker_first, {})

        assert mock_publish.call_count == 1
        assert first_result[action.ALREADY_QUALIFIED_SLOT] is True

        # Second turn in the SAME conversation: slot is now set on the tracker, as Rasa would replay it.
        tracker_second = self._make_tracker(sender_id=sender_id,
                                             slots={"email": "dup@example.com", action.ALREADY_QUALIFIED_SLOT: True})
        with mock.patch("kairon.actions.definitions.erpnext_crm_lead.KaironEventPublisher.publish_webhook") as mock_publish_2:
            await action.execute(dispatcher, tracker_second, {})

        mock_publish_2.assert_not_called()
        log = ActionServerLogs.objects(bot=bot, sender=sender_id).order_by("-timestamp").first()
        assert log.messages.get("skipped_reason") == "already_qualified"

    @pytest.mark.asyncio
    async def test_publishes_lead_qualified_event_with_correct_payload_and_email_field(self):
        bot = f"bot_{uuid.uuid4().hex[:8]}"
        secret = self._provision_bot(bot, site_name="kairon_uat_demo.localhost")

        tracker = self._make_tracker(
            sender_id=f"conv_{uuid.uuid4().hex[:8]}",
            intent="request_demo",
            slots={"email": "prospect@example.com", "name": "Prospect Name", "company": "Prospect Co",
                   "budget": "50k", "phone": "+15551234567"},
        )
        dispatcher = CollectingDispatcher()
        action = ActionERPNextCRMLeadQualified(bot, "erpnext_crm_lead_qualified")

        with mock.patch("kairon.actions.definitions.erpnext_crm_lead.KaironEventPublisher.publish_webhook",
                         return_value={"status_code": 202, "success": True, "response_text": "{}"}) as mock_publish:
            result = await action.execute(dispatcher, tracker, {})

        assert mock_publish.call_count == 1
        call_args = mock_publish.call_args
        target_url, used_secret, event = call_args[0][0], call_args[0][1], call_args[0][2]

        assert target_url == "http://kairon_uat_demo.localhost:8080/api/method/kairon_connector.api.v1.webhook.receive_event"
        assert used_secret == secret
        assert event.event_type == "lead.qualified"
        assert event.payload["bot_id"] == bot
        assert event.payload["conversation_id"] == tracker.sender_id
        assert event.payload["intent"] == "request_demo"
        # Regression: must be "email", never "email_id" -- see kairon_connector's field_mapper.py fix.
        assert event.payload["lead_data"]["email"] == "prospect@example.com"
        assert "email_id" not in event.payload["lead_data"]
        assert event.payload["lead_data"]["phone"] == "+15551234567"
        assert result[action.ALREADY_QUALIFIED_SLOT] is True

    @pytest.mark.asyncio
    async def test_marks_failed_status_when_erpnext_rejects_event(self):
        bot = f"bot_{uuid.uuid4().hex[:8]}"
        self._provision_bot(bot)
        tracker = self._make_tracker(sender_id=f"conv_{uuid.uuid4().hex[:8]}", slots={"email": "fail@example.com"})
        dispatcher = CollectingDispatcher()
        action = ActionERPNextCRMLeadQualified(bot, "erpnext_crm_lead_qualified")

        with mock.patch("kairon.actions.definitions.erpnext_crm_lead.KaironEventPublisher.publish_webhook",
                         return_value={"status_code": 401, "success": False, "response_text": '{"code":"KRN001"}'}):
            result = await action.execute(dispatcher, tracker, {})

        # A rejected delivery must not be treated as "qualified and sent".
        assert action.ALREADY_QUALIFIED_SLOT not in result
        log = ActionServerLogs.objects(bot=bot, sender=tracker.sender_id).order_by("-timestamp").first()
        assert log.status == "Failed"
        assert "401" in (log.exception or "")

    def test_action_factory_resolves_registered_type_to_real_class(self):
        """
        Production-reachability proof: a bot's flow references this action purely by
        name (as it would from a story/rule step), exactly like Pipedrive/Hubspot --
        ActionFactory must resolve that name, via the Actions registry, to the real
        ActionERPNextCRMLeadQualified class, not a mock or a dead reference.
        """
        bot = f"bot_{uuid.uuid4().hex[:8]}"
        action_name = "erpnext_crm_lead_qualified"
        Actions(name=action_name, type=ActionType.erpnext_crm_lead_qualified_action.value,
                bot=bot, user="tester").save()

        instance = ActionFactory.get_instance(bot, action_name)
        assert isinstance(instance, ActionERPNextCRMLeadQualified)

    def test_get_lead_webhook_secret_matches_provisioned_secret(self):
        bot = f"bot_{uuid.uuid4().hex[:8]}"
        secret = self._provision_bot(bot)
        assert CRMProcessor.get_lead_webhook_secret(bot) == secret
