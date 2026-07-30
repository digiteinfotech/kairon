import re
import requests
import subprocess
from typing import Dict, Any, List, Set
from helpers.poll_utility import poll_until, TimeoutError


class MailboxReader:
    def __init__(self, mailpit_api_url: str = "http://localhost:8025"):
        self.mailpit_api_url: str = mailpit_api_url.rstrip("/")

    def get_baseline_message_ids(self) -> Set[str]:
        return self.get_all_message_ids()


    def get_all_message_ids(self) -> Set[str]:
        try:
            res = requests.get(f"{self.mailpit_api_url}/api/v1/messages", timeout=5)
            if res.status_code == 200:
                messages = res.json().get("messages", [])
                return {m["ID"] for m in messages}
        except Exception:
            pass
        return set()

    def flush_erpnext_email_queue(self, site_name: str):
        """Flushes ERPNext email queue so queued invitation emails are sent to Mailpit immediately."""
        try:
            subprocess.run([
                "docker", "exec", "frappe-backend-1",
                "bench", "--site", site_name, "execute", "frappe.email.queue.flush"
            ], capture_output=True, timeout=10)
        except Exception:
            pass

    def poll_for_new_invitation_email(
        self,
        recipient_email: str,
        baseline_ids: Set[str],
        site_name: str,
        timeout: float = 15.0
    ) -> Dict[str, Any]:
        """
        Polls Mailpit until a new email arrives for `recipient_email`.
        Asserts that EXACTLY 1 new email was delivered.
        Verifies headers, Message-ID, timestamp, and extracts the invitation setup URL.
        """
        def check_mailbox():
            self.flush_erpnext_email_queue(site_name)
            res = requests.get(f"{self.mailpit_api_url}/api/v1/messages", timeout=5)
            if res.status_code != 200:
                return None
            
            messages = res.json().get("messages", [])
            new_messages = [m for m in messages if m["ID"] not in baseline_ids]
            
            target_messages = [
                m for m in new_messages 
                if any(r.get("Address", "").lower() == recipient_email.lower() for r in m.get("To", []))
            ]
            
            if target_messages:
                return target_messages
            return None

        new_target_messages = poll_until(
            check_mailbox,
            timeout=timeout,
            initial_delay=0.3,
            error_message=f"No invitation email delivered to '{recipient_email}' in Mailpit"
        )

        if len(new_target_messages) != 1:
            raise AssertionError(f"Expected EXACTLY 1 new invitation email for '{recipient_email}', but found {len(new_target_messages)}")

        msg_summary = new_target_messages[0]
        msg_id = msg_summary["ID"]

        # Fetch full message payload from Mailpit
        detail_res = requests.get(f"{self.mailpit_api_url}/api/v1/message/{msg_id}", timeout=5)
        if detail_res.status_code != 200:
            raise RuntimeError(f"Failed to fetch message details for ID {msg_id}")

        full_msg = detail_res.json()
        
        # Verify Headers
        sender = full_msg.get("From", {}).get("Address", "")
        subject = full_msg.get("Subject", "")
        message_id_header = full_msg.get("MessageID", "")
        created_at = full_msg.get("Date") or full_msg.get("Created", "")


        if not message_id_header:
            raise AssertionError("Invitation email is missing Message-ID header.")
        if not created_at:
            raise AssertionError("Invitation email is missing Created timestamp.")


        html_body = full_msg.get("HTML", "") or full_msg.get("Text", "")
        
        # Extract invitation URL specifically matching accept_invitation or update-password key links
        url_match = re.search(r'href=["\'](https?://[^"\']*(?:accept_invitation|update-password|\?key=)[^"\']+)["\']', html_body)
        if not url_match:
            url_match = re.search(r'https?://[^\s"\'<>]+(?:accept_invitation|update-password|\?key=)[^\s"\'<>]*', html_body)

        invitation_url = url_match.group(1) if url_match and len(url_match.groups()) > 0 else (url_match.group(0) if url_match else "")

        
        if not invitation_url:
            raise AssertionError(f"Could not extract invitation URL from email body. Body preview: {html_body[:300]}")

        return {
            "mailpit_id": msg_id,
            "sender": sender,
            "recipient": recipient_email,
            "subject": subject,
            "message_id": message_id_header,
            "created_at": created_at,
            "invitation_url": invitation_url,
            "html_body": html_body
        }

    def clear_messages_for_recipient(self, recipient_email: str):
        """Deletes messages sent to `recipient_email` from Mailpit."""
        try:
            res = requests.get(f"{self.mailpit_api_url}/api/v1/messages", timeout=5)
            if res.status_code == 200:
                messages = res.json().get("messages", [])
                for m in messages:
                    if any(r.get("Address", "").lower() == recipient_email.lower() for r in m.get("To", [])):
                        requests.delete(f"{self.mailpit_api_url}/api/v1/message/{m['ID']}", timeout=5)
        except Exception:
            pass
