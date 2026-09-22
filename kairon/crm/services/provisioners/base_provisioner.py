import json
import subprocess
from abc import ABC, abstractmethod
from typing import Dict, Any
from loguru import logger
from cryptography.fernet import Fernet
from kairon.exceptions import AppException
from kairon.crm.models import CRMClientDetails
from kairon.crm.services.docker_utils import resolve_container_name
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
        self.container_name = resolve_container_name(bench_config, self.__class__.__name__)

    @staticmethod
    def _clean_site_name(company_name: str) -> tuple:
        """Derives a docker/bench-safe site slug from a company name."""
        clean_name = "".join(c if c.isalnum() else "_" for c in company_name.lower())
        return clean_name, f"{clean_name}.localhost"

    @staticmethod
    def _load_client_doc(company_name: str) -> CRMClientDetails:
        doc = CRMClientDetails.objects(company_name__iexact=company_name.strip()).first()
        if not doc:
            raise AppException(f"CRMClientDetails record not found for company: {company_name}")
        return doc

    def _bench_new_site(self, site_name: str, db_name: str, admin_password: str, install_app: str, label: str):
        """Runs `bench new-site` installing the given app. Raises AppException on failure."""
        cmd = [
            "docker", "exec", self.container_name,
            "bench", "new-site", site_name,
            "--db-name", db_name,
            "--db-host", self.bench_config.get("db_host", "db"),
            "--db-port", str(self.bench_config.get("db_port", 5432)),
            "--db-type", "postgres",
            "--db-root-username", self.bench_config.get("db_user", "postgres"),
            "--db-root-password", self.bench_config.get("db_password", ""),
            "--admin-password", admin_password,
            "--install-app", install_app,
            "--force"
        ]
        logger.info(f"[{label}] Running command: docker exec {self.container_name} bench new-site {site_name} --install-app {install_app}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise AppException(f"[{label}] Bench new-site failed: {res.stderr or res.stdout}")

    def _install_kairon_connector(self, site_name: str, label: str):
        """Installs the kairon_connector app used for webhook/lead-sync integration. Raises AppException on failure."""
        connector_cmd = [
            "docker", "exec", self.container_name,
            "bench", "--site", site_name, "install-app", "kairon_connector"
        ]
        logger.info(f"[{label}] Installing kairon_connector on {site_name}")
        c_res = subprocess.run(connector_cmd, capture_output=True, text=True)
        if c_res.returncode != 0:
            raise AppException(f"[{label}] kairon_connector install failed: {c_res.stderr or c_res.stdout}")

    def _bypass_setup_wizard(self, site_name: str, app_names: list, label: str):
        """Marks the given apps + System Settings as setup-complete, clears cache, and switches bench context to the site."""
        try:
            for app_name in app_names:
                subprocess.run([
                    "docker", "exec", self.container_name,
                    "bench", "--site", site_name, "execute", "frappe.db.set_value",
                    "--args", f"['Installed Application', {{'app_name': '{app_name}'}}, 'is_setup_complete', 1]"
                ], capture_output=True)
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "execute", "frappe.db.set_single_value",
                "--args", "['System Settings', 'setup_complete', 1]"
            ], capture_output=True)
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "--site", site_name, "clear-cache"
            ], capture_output=True)
            subprocess.run([
                "docker", "exec", self.container_name,
                "bench", "use", site_name
            ], capture_output=True)
        except Exception as e:
            logger.warning(f"[{label}] Setup wizard bypass warning: {e}")

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
                "--args", json.dumps(["desktop:home_page", home_page])
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

            # Ensure CRM frontend assets exist in Nginx frontend container.
            # Piped directly between two subprocesses (no shell=True) to avoid
            # invoking a shell to interpret a command string. Uses the resolved
            # backend container name (self.container_name) instead of a hardcoded
            # "frappe-backend-1" -- a deployment using a different Compose project
            # name would otherwise silently fail this sync (swallowed below into a
            # warning) and leave the tenant's CRM frontend broken.
            frontend_container = self.bench_config.get("frontend_container_name", "frappe-frontend-1")
            try:
                tar_out = subprocess.Popen(
                    ["docker", "exec", self.container_name, "tar", "-cf", "-", "-C", "/home/frappe/frappe-bench/apps", "crm"],
                    stdout=subprocess.PIPE
                )
                tar_in = subprocess.Popen(
                    ["docker", "exec", "-i", frontend_container, "tar", "-xf", "-", "-C", "/home/frappe/frappe-bench/apps"],
                    stdin=tar_out.stdout, stdout=subprocess.PIPE
                )
                tar_out.stdout.close()
                tar_in.communicate(timeout=15)
                subprocess.run([
                    "docker", "exec", frontend_container, "ln", "-sfn",
                    "/home/frappe/frappe-bench/apps/crm/crm/public", "/home/frappe/frappe-bench/assets/crm"
                ], capture_output=True, timeout=15)
            except Exception as fe_err:
                logger.warning(f"[BaseProvisioner] Frontend asset sync warning: {fe_err}")

            # 3. Create admin user, assign roles, create company & fiscal year, and finalize setup flags
            c_name = (company_name or "").strip()
            c_abbr = (abbr or (c_name[:3].upper() if c_name else "COMP")).strip()
            c_currency = (default_currency or "INR").strip()
            c_country = (country or "India").strip()

            py_script = f"""
import frappe

frappe.init(site='{site_name}', sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()

admin_doc = frappe.get_doc('User', 'Administrator')
for role in ['Sales Manager', 'Sales User', 'System Manager']:
    if not any(r.role == role for r in admin_doc.roles):
        admin_doc.append('roles', {{'role': role}})
admin_doc.save(ignore_permissions=True)

# User creation & credential issuance (welcome email vs. temporary password) is owned
# exclusively by ProvisioningService.execute_onboarding_workflow ->
# ERPNextClient.create_erpnext_user(), which runs right after this bench step and
# knows whether to send a welcome-email set-password link or a temporary password.
# Creating the user here (as this used to) and setting its password to the ephemeral,
# never-returned Administrator admin_password would race that decision and leave the
# tenant owner with a password nobody is ever told -- so this only touches the user
# if create_erpnext_user already ran in a prior resumed attempt and the user exists.
user_email = {json.dumps(admin_email.strip())}
if user_email and user_email.lower() != 'administrator' and frappe.db.exists('User', user_email):
    u = frappe.get_doc('User', user_email)
    for role in ['System Manager', 'Sales Manager', 'Sales User', 'Desk User']:
        if not any(r.role == role for r in u.roles):
            u.append('roles', {{'role': role}})
    u.save(ignore_permissions=True)

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

comp_title = {json.dumps(c_name)}
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
                'abbr': {json.dumps(c_abbr)},
                'default_currency': {json.dumps(c_currency)},
                'country': {json.dumps(c_country)}
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
