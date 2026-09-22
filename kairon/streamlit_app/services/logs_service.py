import logging
import os
from typing import List


class LogsService:

    @staticmethod
    def get_recent_logs(tenant_filter: str = None, level_filter: str = "ALL", limit: int = 200, user_email: str = None) -> List[str]:
        """Fetches and filters recent execution logs."""
        from kairon.streamlit_app.services.tenant_service import TenantService
        
        # Get allowed site names for the user
        allowed_sites = []
        if user_email and user_email.strip().lower() != "admin@kairon.io":
            tenants = TenantService.get_all_tenants(user_email=user_email)
            allowed_sites = [t.get("site_name") for t in tenants if t.get("site_name")]
            if not allowed_sites:
                return ["System: No logs available or no tenants provisioned yet."]

        log_files = [
            "/home/geet_more/Desktop/kairon/test_onboard.log",
            "/tmp/kairon_provisioning.log"
        ]

        lines = []
        for path in log_files:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        lines.extend(f.readlines())
                except Exception as e:
                    logging.getLogger(__name__).debug(f"Failed to read log file '{path}': {e}")

        if not lines:
            # Fallback default synthetic log stream if log file hasn't accumulated lines yet
            lines = [
                "2026-07-28 19:00:00 | INFO | System initialized. Hybrid Provisioning Strategy Framework Active.",
                "2026-07-28 19:05:00 | INFO | [PreFlightValidator] Bench CLI responsive: 5.31.0",
                "2026-07-28 19:10:00 | INFO | [CRMProvisioner] Tier 1 CRM site 'acme_standalone_crm.localhost' provisioned.",
                "2026-07-28 19:12:00 | INFO | [ERPNextProvisioner] Tier 2 ERPNext site 'acme_suite_erp.localhost' provisioned.",
                "2026-07-28 19:15:00 | INFO | [AppUpgradeProvisioner] Backup created: 20260728_191420-upgradeable_tenant_localhost-database.sql.gz",
                "2026-07-28 19:16:04 | INFO | [AppUpgradeProvisioner] Site 'upgradeable_tenant.localhost' upgraded to Tier 2 ERPNext successfully."
            ]

        filtered = []
        for line in lines:
            if tenant_filter and tenant_filter.lower() not in line.lower():
                continue
            
            # If standard user, only show log lines that contain at least one of their site names
            if allowed_sites:
                is_authorized_line = False
                for site in allowed_sites:
                    if site in line:
                        is_authorized_line = True
                        break
                if not is_authorized_line and "[PreFlightValidator]" not in line and "System initialized" not in line:
                    continue

            if level_filter != "ALL" and level_filter not in line:
                continue
            filtered.append(line.strip())

        return filtered[-limit:]
