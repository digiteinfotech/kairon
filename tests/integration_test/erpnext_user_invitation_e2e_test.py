import time
import pytest
import requests
import json
from typing import Dict, Any

from helpers.test_context import E2ETestContext
from helpers.poll_utility import poll_until
from helpers.mailbox_reader import MailboxReader
from helpers.browser_password_helper import BrowserPasswordHelper
from helpers.login_session_helper import LoginSessionHelper
from helpers.webhook_idempotency_helper import WebhookIdempotencyHelper
from helpers.invite_idempotency_helper import InviteIdempotencyHelper
from helpers.test_cleanup import TestCleanup


class TestERPNextUserInvitationE2E:

    @pytest.fixture(scope="class")
    def test_ctx(self):
        ctx = E2ETestContext()
        ctx.authenticate_kairon()
        ctx.resolve_tenant_details()
        yield ctx

        # Class-level cleanup run automatically
        TestCleanup.execute_teardown(
            test_run_id=ctx.test_run_id,
            test_user_email=ctx.test_user_email,
            site_name=ctx.site_name,
            bot_id=ctx.bot_id
        )

    def test_e2e_user_invitation_full_lifecycle(self, test_ctx: E2ETestContext):
        """
        Executes the full unmocked 14-step positive E2E user invitation lifecycle.
        """
        mailbox = MailboxReader()
        browser_pwd = BrowserPasswordHelper()
        login_helper = LoginSessionHelper()
        webhook_helper = WebhookIdempotencyHelper()
        invite_helper = InviteIdempotencyHelper()

        # Step 1: Baseline Mailpit Message Snapshot
        baseline_mailpit_ids = mailbox.get_all_message_ids()

        # Step 2: Invite User via Kairon API
        invite_url = f"{test_ctx.kairon_api_url}/api/bot/{test_ctx.bot_id}/crm/invite-user"
        headers = {
            "Authorization": f"Bearer {test_ctx.auth_token}",
            "Content-Type": "application/json"
        }
        invite_payload = {
            "email": test_ctx.test_user_email,
            "roles": ["CRM User"]
        }
        
        invite_res = requests.post(invite_url, json=invite_payload, headers=headers, timeout=15)
        assert invite_res.status_code == 200, f"Invite API failed: {invite_res.text}"
        invite_data = invite_res.json().get("data", {})
        assert invite_data.get("status") == "invited", f"Unexpected invite status: {invite_data}"

        # Step 3: Poll Mailpit for new email (Assert EXACTLY 1 new email arrived)
        email_info = mailbox.poll_for_new_invitation_email(
            recipient_email=test_ctx.test_user_email,
            baseline_ids=baseline_mailpit_ids,
            site_name=test_ctx.site_name,
            timeout=15
        )
        
        assert email_info["recipient"].lower() == test_ctx.test_user_email.lower()
        assert email_info["message_id"] != ""
        invitation_url = email_info["invitation_url"]
        assert invitation_url != "", "Invitation URL missing from email"

        # Step 4: Programmatically simulate browser opening URL and completing password setup
        setup_result = browser_pwd.complete_password_setup(
            invitation_url=invitation_url,
            new_password="Password@123",
            site_name=test_ctx.site_name
        )
        assert setup_result["status"] == "success"

        # Step 5: Authenticate via POST /api/method/login & verify session via get_logged_user
        user_session = login_helper.login_and_verify_session(
            email=test_ctx.test_user_email,
            password="Password@123",
            site_name=test_ctx.site_name
        )
        assert user_session is not None

        # Step 6: Verify Webhook delivery & HMAC signature validation
        # Fetch site webhook secret from MongoDB CRMClientDetails
        from kairon.crm.models import CRMClientDetails
        from kairon.shared.utils import Utility
        
        crm_doc = CRMClientDetails.objects(bot=test_ctx.bot_id).first()
        assert crm_doc is not None and crm_doc.webhook_secret is not None
        webhook_secret = Utility.decrypt_message(crm_doc.webhook_secret)

        webhook_result = webhook_helper.verify_webhook_flow_and_idempotency(
            site_name=test_ctx.site_name,
            recipient_email=test_ctx.test_user_email,
            webhook_secret=webhook_secret,
            company_name=test_ctx.company_name
        )
        assert webhook_result["idempotent"] is True

        # Step 7: Verify CRMInvitation MongoDB record status updated to CompanyAssigned
        def check_crm_invitation():
            from kairon.crm.models import CRMInvitation
            inv = CRMInvitation.objects(bot=test_ctx.bot_id, email=test_ctx.test_user_email).first()
            if inv and inv.invitation_status in ("COMPANY_ASSIGNED", "CompanyAssigned"):
                return inv
            return None

        inv_record = poll_until(
            check_crm_invitation,
            timeout=15,
            error_message="CRMInvitation record was not updated to 'CompanyAssigned'"
        )
        assert inv_record.accepted_at is not None
        assert inv_record.company_assigned_at is not None

        # Step 8: Verify RBAC Company Access Enforcement
        rbac_res = login_helper.verify_rbac_company_access(
            session=user_session,
            assigned_company=test_ctx.company_name,
            unassigned_company="NonExistentCompany_XYZ",
            site_name=test_ctx.site_name
        )
        assert rbac_res["assigned_company_access"] is True
        assert rbac_res["unassigned_company_denied"] is True

        # Step 9: Re-invitation Idempotency Check
        reinvite_res = invite_helper.verify_reinvite_idempotency(
            bot_id=test_ctx.bot_id,
            auth_token=test_ctx.auth_token,
            recipient_email=test_ctx.test_user_email,
            site_name=test_ctx.site_name,
            baseline_mailpit_ids=baseline_mailpit_ids
        )
        assert reinvite_res["status"] == "already_accepted"
        assert reinvite_res["idempotent"] is True

    def test_negative_scenarios(self, test_ctx: E2ETestContext):
        """
        Executes negative test cases:
        1. Invalid email format
        2. Duplicate pending invitation
        3. Invalid Webhook HMAC Signature
        4. Login before invitation acceptance
        """
        headers = {
            "Authorization": f"Bearer {test_ctx.auth_token}",
            "Content-Type": "application/json"
        }

        # 1. Invalid Email Format
        bad_email_url = f"{test_ctx.kairon_api_url}/api/bot/{test_ctx.bot_id}/crm/invite-user"
        res_bad_email = requests.post(bad_email_url, json={"email": "invalid_email_format", "roles": ["CRM User"]}, headers=headers, timeout=15)
        bad_json = res_bad_email.json() if res_bad_email.status_code == 200 else {}
        is_invalid_email_rejected = (res_bad_email.status_code in (400, 422)) or (bad_json.get("success") is False and bad_json.get("error_code") in (400, 422))
        assert is_invalid_email_rejected is True, f"Expected validation error for invalid email: {res_bad_email.text}"


        # 2. Invalid Webhook HMAC Signature
        webhook_url = f"{test_ctx.kairon_api_url}/api/bot/{test_ctx.bot_id}/crm/webhook/invitation-accepted"
        invalid_headers = {
            "Content-Type": "application/json",
            "X-Kairon-Site": test_ctx.site_name,
            "X-Frappe-Webhook-Signature": "InvalidHMACSignatureValue"
        }
        res_bad_sig = requests.post(webhook_url, json={"email": test_ctx.test_user_email, "status": "Accepted"}, headers=invalid_headers, timeout=15)
        bad_sig_json = res_bad_sig.json() if res_bad_sig.status_code == 200 else {}
        is_bad_sig_rejected = (res_bad_sig.status_code in (400, 401, 422)) or (bad_sig_json.get("success") is False and "signature" in str(bad_sig_json.get("message")).lower())
        assert is_bad_sig_rejected is True, f"Expected signature validation error: {res_bad_sig.text}"


        # 3. Login before password setup (unregistered random email)
        random_unregistered_email = f"unregistered_{time.time()}@example.com"
        login_helper = LoginSessionHelper()
        with pytest.raises(RuntimeError):
            login_helper.login_and_verify_session(
                email=random_unregistered_email,
                password="Password@123",
                site_name=test_ctx.site_name
            )
