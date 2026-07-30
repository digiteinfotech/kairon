import re
import urllib.parse
import requests
from typing import Dict, Any


class BrowserPasswordHelper:
    def __init__(self, erpnext_base_url: str = "http://localhost:8080"):
        self.base_url = erpnext_base_url.rstrip("/")

    def complete_password_setup(self, invitation_url: str, new_password: str = "Password@123", site_name: str = None) -> Dict[str, Any]:
        """
        Simulates the end-user browser flow:
        1. Issues GET request to `invitation_url`, following HTTP redirects while preserving host/port.
        2. Extracts the reset `key` parameter from the redirect Location header.
        3. Submits password setup through the web form flow (POST /api/method/frappe.core.doctype.user.user.update_password).
        4. Verifies ERPNext completes setup successfully.
        """
        session = requests.Session()
        session.verify = False

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) E2E-Test-Browser",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        session.headers.update(headers)
        if site_name:
            session.headers["Host"] = site_name

        # Normalize invitation URL scheme and host:port to self.base_url
        if invitation_url.startswith("http"):
            parsed_inv = urllib.parse.urlparse(invitation_url)
            parsed_base = urllib.parse.urlparse(self.base_url)
            invitation_url = urllib.parse.urlunparse((
                parsed_base.scheme,
                parsed_base.netloc,
                parsed_inv.path,
                parsed_inv.params,
                parsed_inv.query,
                parsed_inv.fragment
            ))

        # Step 1: Open invitation link (manual redirect following to preserve host:port)
        res = session.get(invitation_url, allow_redirects=False, timeout=15)
        
        current_url = invitation_url
        location_history = []
        key = None

        for _ in range(5):
            parsed_curr = urllib.parse.urlparse(current_url)
            q_params = urllib.parse.parse_qs(parsed_curr.query)
            if "key" in q_params:
                key = q_params["key"][0]

            if res.status_code in (301, 302, 303, 307, 308):
                loc = res.headers.get("Location", "")
                location_history.append(loc)
                if loc:
                    parsed_loc = urllib.parse.urlparse(loc)
                    parsed_base = urllib.parse.urlparse(self.base_url)
                    current_url = urllib.parse.urlunparse((
                        parsed_base.scheme,
                        parsed_base.netloc,
                        parsed_loc.path,
                        parsed_loc.params,
                        parsed_loc.query,
                        parsed_loc.fragment
                    ))
                    res = session.get(current_url, allow_redirects=False, timeout=15)
                else:
                    break
            else:
                break

        if not key:
            key_match = re.search(r'key=([a-zA-Z0-9_-]+)', " ".join(location_history) + " " + current_url)
            if key_match:
                key = key_match.group(1)

        if not key:
            raise AssertionError(f"Could not extract password setup 'key' from invitation GET response. Final URL: {current_url}")

        # Step 3: Submit new password via form POST action
        post_url = f"{self.base_url}/api/method/frappe.core.doctype.user.user.update_password"
        post_data = {
            "key": key,
            "old_password": "",
            "new_password": new_password,
            "logout_all_sessions": "1"
        }
        
        post_headers = {"Accept": "application/json"}
        res_post = session.post(post_url, data=post_data, headers=post_headers, timeout=15)
        
        if res_post.status_code != 200:
            raise RuntimeError(f"Password setup POST submission failed with status {res_post.status_code}: {res_post.text}")

        res_json = res_post.json() if res_post.headers.get("content-type", "").startswith("application/json") else {}
        
        return {
            "status": "success",
            "key": key,
            "response": res_json,
            "final_url": current_url
        }
