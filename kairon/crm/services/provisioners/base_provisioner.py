import json
import subprocess
import signal
from abc import ABC, abstractmethod
from typing import Dict, Any
from loguru import logger
from cryptography.fernet import Fernet
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.services.provisioning_models import ProvisioningPlan


class BaseProvisioner(ABC):
    """
    Abstract Base Strategy for Bench site provisioning operations.
    Encapsulates site creation, encryption key pre-locking, setup wizard bypass,
    Gunicorn worker reloads, and operational metadata persistence.
    """

    def __init__(self, plan: ProvisioningPlan, bench_config: dict):
        self.plan = plan
        self.bench_config = bench_config
        self.container_name = self._resolve_container_name(bench_config)

    def _resolve_container_name(self, bench_config: dict) -> str:
        container_name = bench_config.get("container_name")
        if not container_name:
            cmd = [
                "docker", "ps",
                "--filter", "label=com.docker.compose.service=backend",
                "--filter", "label=com.docker.compose.project=frappe",
                "--format", "{{.Names}}"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                container_name = res.stdout.strip()
            else:
                container_name = "frappe-backend-1"
        return container_name

    def reload_gunicorn_workers(self):
        """
        Reloads backend workers gracefully using configurable strategy.
        Supports sighup_pid1, supervisorctl, or fallback.
        """
        reload_strategy = self.bench_config.get("reload_strategy", "sighup_pid1")
        logger.info(f"[BaseProvisioner] Reloading workers via strategy '{reload_strategy}'...")

        try:
            if reload_strategy == "supervisorctl":
                cmd = ["docker", "exec", self.container_name, "supervisorctl", "restart", "frappe-gunicorn"]
                subprocess.run(cmd, capture_output=True, timeout=15)
            else:
                # Default: SIGHUP to PID 1
                cmd = [
                    "docker", "exec", self.container_name,
                    "/home/frappe/frappe-bench/env/bin/python", "-c",
                    "import os, signal; os.kill(1, signal.SIGHUP)"
                ]
                subprocess.run(cmd, capture_output=True, timeout=10)
            logger.info("[BaseProvisioner] Worker reload signal sent successfully.")
        except Exception as e:
            logger.warning(f"[BaseProvisioner] Failed to reload workers: {e}")

    def prelock_encryption_key(self, site_name: str):
        """Generates and sets encryption_key in site_config.json before any DB operations."""
        try:
            new_enc_key = Fernet.generate_key().decode()
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "set-config", "encryption_key", new_enc_key
            ], capture_output=True)
            logger.info(f"[BaseProvisioner] Explicitly set encryption_key for {site_name}")
        except Exception as e:
            logger.warning(f"[BaseProvisioner] Failed to pre-set encryption_key for {site_name}: {e}")

    def set_homepage(self, site_name: str, home_page: str):
        """Configures default home page / workspace route for the site."""
        try:
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "execute", "frappe.db.set_default",
                "--args", f"['desktop:home_page', '{home_page}']"
            ], capture_output=True)
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "execute", "frappe.db.commit"
            ], capture_output=True)
            logger.info(f"[BaseProvisioner] Set homepage to '{home_page}' for {site_name}")
        except Exception as e:
            logger.warning(f"[BaseProvisioner] Failed to set home page: {e}")

    def setup_user_and_migrate(
        self, site_name: str, admin_email: str, admin_password: str, company_name: str = None,
        abbr: str = None, default_currency: str = "INR", country: str = "India"
    ):
        """Creates logs directory, runs bench migrate, initializes Company, Fiscal Year, User with email/roles, and sets setup_complete."""
        try:
            # 1. Ensure logs directory exists for site
            subprocess.run(["docker", "exec", self.container_name, "mkdir", "-p", f"sites/{site_name}/logs"], capture_output=True)

            # 2. Run bench migrate to sync app fixtures & doctypes
            logger.info(f"[BaseProvisioner] Running bench migrate on site '{site_name}'...")
            subprocess.run(["docker", "exec", self.container_name, "bench", "--site", site_name, "migrate"], capture_output=True)

            # Ensure CRM frontend assets exist in Nginx frontend container
            try:
                cmd_sync = "docker exec frappe-backend-1 tar -cf - -C /home/frappe/frappe-bench/apps crm | docker exec -i frappe-frontend-1 tar -xf - -C /home/frappe/frappe-bench/apps && docker exec frappe-frontend-1 ln -sfn /home/frappe/frappe-bench/apps/crm/crm/public /home/frappe/frappe-bench/assets/crm"
                subprocess.run(cmd_sync, shell=True, capture_output=True, timeout=15)
            except Exception as fe_err:
                logger.warning(f"[BaseProvisioner] Frontend asset sync warning: {fe_err}")

            # 3. Create admin user, assign roles, create company & fiscal year, and finalize setup flags
            c_name = (company_name or "").strip()
            c_abbr = (abbr or (c_name[:3].upper() if c_name else "COMP")).strip()
            c_currency = (default_currency or "INR").strip()
            c_country = (country or "India").strip()

            py_script = f"""
import frappe
from frappe.utils.password import update_password

frappe.init(site='{site_name}', sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()

admin_doc = frappe.get_doc('User', 'Administrator')
for role in ['Sales Manager', 'Sales User', 'System Manager']:
    if not any(r.role == role for r in admin_doc.roles):
        admin_doc.append('roles', {{'role': role}})
admin_doc.save(ignore_permissions=True)

user_email = '{admin_email.strip()}'
if user_email and user_email.lower() != 'administrator':
    if not frappe.db.exists('User', user_email):
        u = frappe.get_doc({{
            'doctype': 'User',
            'email': user_email,
            'first_name': user_email.split('@')[0].title(),
            'enabled': 1,
            'send_welcome_email': 0,
            'user_type': 'System User',
            'roles': [{{'role': r}} for r in ['System Manager', 'Sales Manager', 'Sales User', 'Desk User']]
        }})
        u.insert(ignore_permissions=True)
    else:
        u = frappe.get_doc('User', user_email)
        for role in ['System Manager', 'Sales Manager', 'Sales User', 'Desk User']:
            if not any(r.role == role for r in u.roles):
                u.append('roles', {{'role': role}})

    u.new_password = '{admin_password}'
    u.save(ignore_permissions=True)
    try:
        update_password(user_email, '{admin_password}')
    except Exception:
        pass

    if not frappe.db.exists('Notification Settings', user_email):
        try:
            ns = frappe.get_doc({{
                'doctype': 'Notification Settings',
                'name': user_email,
                'user': user_email,
                'enable_notification': 1
            }})
            ns.insert(ignore_permissions=True)
        except Exception:
            pass

comp_title = '{c_name}'
if comp_title:
    if frappe.db.exists('DocType', 'CRM Organization'):
        if not frappe.db.exists('CRM Organization', {{'organization_name': comp_title}}):
            frappe.get_doc({{
                'doctype': 'CRM Organization',
                'organization_name': comp_title
            }}).insert(ignore_permissions=True)

    if frappe.db.exists('DocType', 'Company'):
        for wt in ['Transit', 'Manufacturing', 'Stores']:
            if frappe.db.exists('DocType', 'Warehouse Type') and not frappe.db.exists('Warehouse Type', wt):
                frappe.get_doc({{'doctype': 'Warehouse Type', 'name': wt}}).insert(ignore_permissions=True)

        if not frappe.db.exists('Company', comp_title):
            c = frappe.get_doc({{
                'doctype': 'Company',
                'company_name': comp_title,
                'abbr': '{c_abbr}',
                'default_currency': '{c_currency}',
                'country': '{c_country}'
            }})
            c.insert(ignore_permissions=True)

        frappe.db.set_single_value('Global Defaults', 'default_company', comp_title)
        if user_email:
            frappe.defaults.set_user_default('company', comp_title, user_email)
            frappe.defaults.set_user_default('Company', comp_title, user_email)

        # Ensure active Fiscal Year exists
        import datetime
        now_year = datetime.date.today().year
        fy_name = f"{{now_year}}-{{now_year+1}}"
        if not frappe.db.exists('Fiscal Year', fy_name):
            fy = frappe.get_doc({{
                'doctype': 'Fiscal Year',
                'year': fy_name,
                'year_start_date': f"{{now_year}}-01-01",
                'year_end_date': f"{{now_year}}-12-31"
            }})
            fy.insert(ignore_permissions=True)

frappe.db.set_single_value('System Settings', 'setup_complete', 1)
frappe.db.set_value('Installed Application', {{'app_name': 'frappe'}}, 'is_setup_complete', 1)
try:
    frappe.db.set_value('Installed Application', {{'app_name': 'crm'}}, 'is_setup_complete', 1)
except Exception:
    pass
try:
    frappe.db.set_value('Installed Application', {{'app_name': 'erpnext'}}, 'is_setup_complete', 1)
except Exception:
    pass
frappe.db.sql("UPDATE \\\"tabDefaultValue\\\" SET defvalue='1' WHERE defkey='setup_complete'")
frappe.db.commit()
frappe.clear_cache()
"""
            subprocess.run([
                "docker", "exec", "-w", "/home/frappe/frappe-bench/sites", self.container_name,
                "/home/frappe/frappe-bench/env/bin/python", "-c", py_script
            ], capture_output=True)
            logger.info(f"[BaseProvisioner] Configured user '{admin_email}' and company '{c_name}' on '{site_name}'.")
        except Exception as e:
            logger.warning(f"[BaseProvisioner] Failed user setup or migrate: {e}")


    @abstractmethod
    def provision(self, company_name: str, abbr: str, default_currency: str, country: str, admin_password: str, bot: str) -> Dict[str, Any]:
        """Executes the provisioning strategy."""
        pass
