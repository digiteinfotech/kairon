import subprocess
import secrets
import string
import time
import json
import re
from loguru import logger
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.services.preflight_validator import PreFlightValidator
from kairon.crm.services.provisioners.factory import ProvisionerFactory


class BenchExecutor:

    def generate_database_name(self, company_name: str) -> str:
        """
        Generates a valid, readable PostgreSQL database name from the company name.
        """
        # 1. Lowercase
        name = company_name.lower()
        # 2. Replace non-alphanumeric with underscore
        name = re.sub(r'[^a-z0-9]', '_', name)
        # 3. Collapse multiple underscores
        name = re.sub(r'_+', '_', name)
        # 4. Strip leading/trailing underscores
        name = name.strip('_')
        # 5. Prefix with erpnext_
        name = f"erpnext_{name}"
        # 6. Ensure maximum length of 63 characters
        if len(name) > 63:
            name = name[:63].rstrip('_')
        return name

    def _database_exists(self, db_name: str, bench_config: dict, container_name: str) -> bool:
        """
        Checks if a database exists in the PostgreSQL container.
        """
        db_host = bench_config.get("db_host", "db")
        db_port = str(bench_config.get("db_port", 5432))
        db_user = bench_config.get("db_user", "postgres")
        db_password = bench_config.get("db_password", "")
        
        safe_password = db_password.replace("'", "\\'")
        
        script = f"""
import psycopg2
try:
    conn = psycopg2.connect(
        host='{db_host}',
        port={db_port},
        user='{db_user}',
        password='{safe_password}',
        database='postgres'
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM pg_database WHERE datname='{db_name}'")
    exists = cursor.fetchone() is not None
    conn.close()
    print("EXISTS" if exists else "NOT_EXISTS")
except Exception as e:
    print(f"ERROR: {{e}}")
"""
        cmd = [
            "docker", "exec", container_name,
            "./env/bin/python", "-c", script
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            out = res.stdout.strip()
            if out == "EXISTS":
                return True
        return False

    def _resolve_container_name(self, bench_config: dict) -> str:
        """
        Resolves the backend container name dynamically from configuration,
        falling back to docker ps resolution if empty.
        """
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
                logger.info(f"[BenchExecutor] Dynamically resolved container name: {container_name}")
            else:
                container_name = "frappe-backend-1"
                logger.warning(f"[BenchExecutor] Failed to resolve container name. Using fallback: {container_name}")
        return container_name

    def provision_site(
        self, company_name: str, abbr: str, default_currency: str, country: str, admin_password: str, bot: str = None, selected_features: list = None
    ):
        logger.info(
            f"BenchExecutor.provision_site: company_name={company_name}, abbr={abbr}, "
            f"default_currency={default_currency}, country={country}, features={selected_features}"
        )

        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})

        # Phase 0: Pre-flight Configuration Validation
        plan = PreFlightValidator.validate_configuration(selected_features or ["crm"])

        # Instantiate strategy via ProvisionerFactory
        provisioner = ProvisionerFactory.create(plan, bench_config)

        # Execute provisioning strategy
        return provisioner.provision(
            company_name=company_name,
            abbr=abbr,
            default_currency=default_currency,
            country=country,
            admin_password=admin_password,
            bot=bot or company_name
        )

    def set_admin_password(self, site_name: str, admin_password: str):
        """
        Securely rotates/sets the Administrator password of an existing site
        without storing it persistently.
        """
        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})
        container_name = self._resolve_container_name(bench_config)

        cmd = [
            "docker", "exec", container_name,
            "bench", "--site", site_name, "set-admin-password", admin_password
        ]
        logger.info(f"Running command: docker exec {container_name} bench --site {site_name} set-admin-password ********")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise AppException(f"Failed to set admin password on retry: {result.stderr or result.stdout}")

    def create_crm_user(self, bot: str, email: str, role: str):
        logger.info(
            f"BenchExecutor.create_crm_user: bot={bot}, email={email}, role={role}"
        )

        doc = CRMClientDetails.objects(bot=bot).first()
        if not doc:
            raise AppException("CRM configuration details not found for this bot.")

        site_name = doc.site_name
        if not site_name:
            raise AppException("CRM site has not been created yet.")

        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})
        container_name = self._resolve_container_name(bench_config)

        script = f"""
import frappe
from frappe.utils.password import update_password
frappe.init(site='{site_name}')
frappe.connect()
email = '{email}'
role = '{role}'
if not frappe.db.exists('User', email):
    user = frappe.get_doc({{
        'doctype': 'User',
        'email': email,
        'first_name': email.split('@')[0],
        'enabled': 1,
        'send_welcome_email': 0
    }})
    user.insert(ignore_permissions=True)
    update_password(email, 'Password@123')
user = frappe.get_doc('User', email)
user.add_roles(role)
frappe.db.commit()
"""
        cmd = [
            "docker", "exec", "-i", container_name,
            "./env/bin/python", "-c", script
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise AppException(f"Failed to create user inside container: {result.stderr or result.stdout}")

        return {
            "status": "success",
            "message": "User created successfully inside bench site.",
            "email": email,
            "role": role,
        }

    def get_db_tables(self, site_name: str) -> list:
        """
        Retrieves all table names from the PostgreSQL database of a given bench site.
        """
        import ast
        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})
        container_name = self._resolve_container_name(bench_config)

        cmd = [
            "docker", "exec", container_name,
            "bench", "--site", site_name, "execute", "frappe.db.get_tables"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            try:
                tables = ast.literal_eval(res.stdout.strip())
                if isinstance(tables, (list, tuple)):
                    return sorted([str(t) for t in tables])
            except Exception as e:
                logger.error(f"Failed to parse database tables: {e}")
        return []

    def get_table_content(self, site_name: str, table_name: str, limit: int = 50) -> list:
        """
        Retrieves rows from a given PostgreSQL database table of a bench site.
        """
        if not re.match(r'^[A-Za-z0-9_]+$', table_name):
            raise AppException("Invalid table name format.")

        crm_config = Utility.environment.get("crm", {})
        bench_config = crm_config.get("bench", {})
        container_name = self._resolve_container_name(bench_config)

        script = f"""
import frappe
import json
frappe.init(site='{site_name}')
frappe.connect()
try:
    rows = frappe.db.sql('SELECT * FROM "{table_name}" LIMIT {limit}', as_dict=True)
    print(json.dumps(rows, default=str))
except Exception as e:
    print(json.dumps([]))
"""
        cmd = [
            "docker", "exec", "-w", "/home/frappe/frappe-bench/sites", "-i", container_name,
            "/home/frappe/frappe-bench/env/bin/python", "-c", script
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            try:
                output_str = res.stdout.strip()
                if "[" in output_str and "]" in output_str:
                    json_part = output_str[output_str.find("["):output_str.rfind("]")+1]
                    return json.loads(json_part)
                return json.loads(output_str)
            except Exception as e:
                logger.error(f"Failed to parse table content: {e}")
        return []

    def reload_gunicorn_workers(self, container_name: str):
        """
        Sends SIGHUP to Gunicorn master (PID 1) inside container to gracefully reload all worker processes.
        This ensures preloaded Gunicorn workers reload newly created site configs and encryption keys.
        """
        try:
            cmd = [
                "docker", "exec", container_name,
                "/home/frappe/frappe-bench/env/bin/python", "-c",
                "import os, signal; os.kill(1, signal.SIGHUP)"
            ]
            subprocess.run(cmd, capture_output=True, timeout=10)
            import time
            time.sleep(2)
            logger.info(f"Triggered Gunicorn worker reload (SIGHUP) in {container_name}")
        except Exception as e:
            logger.warning(f"Failed to reload Gunicorn workers: {e}")

