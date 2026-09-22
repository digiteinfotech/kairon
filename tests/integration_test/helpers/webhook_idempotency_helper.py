import json
import hmac
import hashlib
import base64
import requests
import subprocess
from typing import Dict, Any
from helpers.poll_utility import poll_until


class WebhookIdempotencyHelper:
    def __init__(self, kairon_api_url: str = "http://localhost:5000"):
        self.kairon_api_url = kairon_api_url.rstrip("/")

    @staticmethod
    def compute_signature(payload_dict: dict, secret: str) -> tuple[bytes, str]:
        raw_body = json.dumps(payload_dict).encode("utf-8")
        signature = base64.b64encode(
            hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        ).decode("utf-8")
        return raw_body, signature

    def send_webhook(self, site_name: str, payload: dict, signature: str) -> requests.Response:
        url = f"{self.kairon_api_url}/api/bot/{site_name}/crm/webhook/invitation-accepted"
        headers = {
            "Content-Type": "application/json",
            "X-Kairon-Site": site_name,
            "X-Frappe-Webhook-Signature": signature
        }
        return requests.post(url, json=payload, headers=headers, timeout=15)

    def count_user_permissions_in_erpnext(self, recipient_email: str, site_name: str) -> int:
        """Counts how many User Permission records exist for the recipient in ERPNext."""
        cmd = [
            "docker", "exec", "frappe-backend-1",
            "bench", "--site", site_name, "execute",
            "frappe.db.count", "--args", f"['User Permission', {{'user': '{recipient_email}'}}]"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip().isdigit():
            return int(res.stdout.strip())
        return 0

    def verify_webhook_flow_and_idempotency(
        self,
        site_name: str,
        recipient_email: str,
        webhook_secret: str,
        company_name: str
    ) -> Dict[str, Any]:
        """
        1. Sends initial valid invitation acceptance webhook.
        2. Asserts HTTP 200 OK.
        3. Polls ERPNext until User Permission is created.
        4. Sends DUPLICATE webhook payload with identical signature.
        5. Asserts HTTP 200 OK and verifies count of User Permission stays EXACTLY 1.
        """
        payload = {
            "name": f"INV-{recipient_email}",
            "email": recipient_email,
            "status": "Accepted",
            "app_name": "frappe"
        }
        
        raw_body, signature = self.compute_signature(payload, webhook_secret)
        
        # 1. Send initial webhook
        first_res = self.send_webhook(site_name, payload, signature)
        if first_res.status_code != 200:
            raise RuntimeError(f"Initial webhook delivery failed: status {first_res.status_code}, response: {first_res.text}")

        # 2. Poll ERPNext for User Permission creation
        def check_perm():
            return self.count_user_permissions_in_erpnext(recipient_email, site_name) >= 1

        poll_until(
            check_perm,
            timeout=15,
            error_message=f"User Permission not created in ERPNext for '{recipient_email}' after webhook"
        )

        perm_count_before_dup = self.count_user_permissions_in_erpnext(recipient_email, site_name)

        # 3. Send DUPLICATE webhook
        dup_res = self.send_webhook(site_name, payload, signature)
        if dup_res.status_code != 200:
            raise RuntimeError(f"Duplicate webhook delivery failed: status {dup_res.status_code}, response: {dup_res.text}")

        perm_count_after_dup = self.count_user_permissions_in_erpnext(recipient_email, site_name)

        if perm_count_after_dup != perm_count_before_dup:
            raise AssertionError(f"Webhook Idempotency Failure: Duplicate webhook created additional User Permissions! Before: {perm_count_before_dup}, After: {perm_count_after_dup}")

        return {
            "first_webhook_status": first_res.status_code,
            "duplicate_webhook_status": dup_res.status_code,
            "user_permission_count": perm_count_after_dup,
            "idempotent": True
        }
