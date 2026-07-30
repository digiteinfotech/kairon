import requests
from typing import Dict, Any, Set
from helpers.mailbox_reader import MailboxReader


class InviteIdempotencyHelper:
    def __init__(self, kairon_api_url: str = "http://localhost:5000"):
        self.kairon_api_url = kairon_api_url.rstrip("/")

    def verify_reinvite_idempotency(
        self,
        bot_id: str,
        auth_token: str,
        recipient_email: str,
        site_name: str,
        baseline_mailpit_ids: Set[str]
    ) -> Dict[str, Any]:
        """
        Invites an already accepted user email again via POST /api/bot/{bot}/crm/invite-user.
        Asserts:
        - Response status is 200 OK with 'already_accepted' status.
        - Zero extra emails generated in Mailpit.
        """
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "email": recipient_email,
            "roles": ["CRM User"]
        }

        mailbox = MailboxReader()
        pre_reinvite_ids = mailbox.get_all_message_ids()

        url = f"{self.kairon_api_url}/api/bot/{bot_id}/crm/invite-user"
        res = requests.post(url, json=payload, headers=headers, timeout=15)

        if res.status_code != 200:
            raise RuntimeError(f"Re-invite request failed with status {res.status_code}: {res.text}")

        data = res.json().get("data", {})
        status = data.get("status")
        if status != "already_accepted":
            raise AssertionError(f"Expected status 'already_accepted' on re-invitation, but got '{status}'")

        # Verify no extra email was sent in Mailpit
        current_ids = mailbox.get_all_message_ids()
        new_ids = current_ids - pre_reinvite_ids

        
        if len(new_ids) > 0:
            raise AssertionError(f"Re-invite Idempotency Failure: Extra email was dispatched to Mailpit on re-invitation!")

        return {
            "status": status,
            "extra_emails_sent": 0,
            "idempotent": True
        }
