import time
import subprocess
from typing import Dict, Any
from helpers.mailbox_reader import MailboxReader


class TestCleanup:
    @staticmethod
    def execute_teardown(
        test_run_id: str,
        test_user_email: str,
        site_name: str,
        bot_id: str
    ) -> Dict[str, Any]:
        """
        Executes robust teardown cleanup of all resources tagged with `test_run_id` or `test_user_email`.
        Guaranteed to run in `finally` blocks.
        Returns cleanup metrics.
        """
        start_time = time.time()
        deleted_summary = {
            "erpnext_user": False,
            "user_permissions": 0,
            "user_invitations": 0,
            "crm_invitations": 0,
            "mailpit_messages": 0
        }
        leftovers = []

        if site_name and test_user_email:
            # 1. Delete ERPNext User Permission
            try:
                script_perm = f"import frappe; frappe.init(site='{site_name}'); frappe.connect(); count = frappe.db.delete('User Permission', {{'user': '{test_user_email}'}}); frappe.db.commit(); print('DELETED_PERMS:', count)"
                res_perm = subprocess.run(["docker", "exec", "frappe-backend-1", "./env/bin/python", "-c", script_perm], capture_output=True, text=True, timeout=10)
                if "DELETED_PERMS:" in res_perm.stdout:
                    deleted_summary["user_permissions"] = int(res_perm.stdout.split("DELETED_PERMS:")[1].strip())
            except Exception as e:
                leftovers.append(f"User Permission for '{test_user_email}': {e}")

            # 2. Delete ERPNext User Invitation
            try:
                script_inv = f"import frappe; frappe.init(site='{site_name}'); frappe.connect(); count = frappe.db.delete('User Invitation', {{'email': '{test_user_email}'}}); frappe.db.commit(); print('DELETED_INVS:', count)"
                res_inv = subprocess.run(["docker", "exec", "frappe-backend-1", "./env/bin/python", "-c", script_inv], capture_output=True, text=True, timeout=10)
                if "DELETED_INVS:" in res_inv.stdout:
                    deleted_summary["user_invitations"] = int(res_inv.stdout.split("DELETED_INVS:")[1].strip())
            except Exception as e:
                leftovers.append(f"User Invitation for '{test_user_email}': {e}")

            # 3. Delete ERPNext User document
            try:
                script_user = f"import frappe; frappe.init(site='{site_name}'); frappe.connect(); count = frappe.db.delete('User', {{'name': '{test_user_email}'}}); frappe.db.commit(); print('DELETED_USER:', count)"
                res_user = subprocess.run(["docker", "exec", "frappe-backend-1", "./env/bin/python", "-c", script_user], capture_output=True, text=True, timeout=10)
                if "DELETED_USER:" in res_user.stdout and int(res_user.stdout.split("DELETED_USER:")[1].strip()) > 0:
                    deleted_summary["erpnext_user"] = True
            except Exception as e:
                leftovers.append(f"ERPNext User '{test_user_email}': {e}")

        # 4. Delete MongoDB CRMInvitation record
        if test_user_email and bot_id:
            try:
                from kairon.crm.models import CRMInvitation
                deleted_count = CRMInvitation.objects(bot=bot_id, email=test_user_email).delete()
                deleted_summary["crm_invitations"] = deleted_count
            except Exception as e:
                leftovers.append(f"MongoDB CRMInvitation for '{test_user_email}': {e}")

        # 5. Clear Mailpit messages for test user
        if test_user_email:
            try:
                mailbox = MailboxReader()
                mailbox.clear_messages_for_recipient(test_user_email)
                deleted_summary["mailpit_messages"] = 1
            except Exception as e:
                leftovers.append(f"Mailpit messages for '{test_user_email}': {e}")

        cleanup_duration = round(time.time() - start_time, 3)

        return {
            "cleanup_duration_seconds": cleanup_duration,
            "deleted_summary": deleted_summary,
            "leftover_resources": leftovers,
            "success": len(leftovers) == 0
        }
