# Kairon ERPNext CRM Integration — Operational & Architecture Manual

## 1. Executive Overview

This manual documents the operational prerequisites, architecture design, security model, troubleshooting guides, recovery procedures, and version compatibility assumptions for Kairon's automated ERPNext CRM provisioning subsystem.

---

## 2. Operational Architecture & Security Decisions

### A. Integration User Roles & System Permissions
During site provisioning, Kairon provisions a dedicated system integration user (`kairon-crm@<site_domain>`). This user is granted two primary Frappe roles:
1. **System Manager**: Grants REST API access to create and manage DocTypes, users, company records, webhooks, and site configurations.
2. **Workspace Manager**: Required in Frappe v15+ to permit modifying the `is_hidden` attribute on standard `Workspace` documents via HTTP `PUT` requests (`/api/resource/Workspace/<name>`). Without `Workspace Manager`, Frappe returns `403 Forbidden` on workspace visibility operations.

### B. Immediate Cryptographic Key Pre-Locking
- **Problem**: Standard `bench new-site` creates `site_config.json` without an `encryption_key`. Frappe's runtime `get_encryption_key()` generates a key dynamically on the first cryptographic write (e.g., generating API secrets). In multi-worker pre-forked Gunicorn environments (`--preload`), concurrent worker threads generate different keys, leading to decryption failures (`frappe.AuthenticationError: 401`).
- **Operational Requirement**: `BenchExecutor.provision_site()` explicitly generates a 32-byte Fernet key (`Fernet.generate_key().decode()`) and writes it into `site_config.json` immediately after `bench new-site` finishes.

### C. Worker Process Synchronization (Gunicorn `SIGHUP`)
- **Mechanism**: Gunicorn master process (PID 1 inside `frappe-backend-1`) pre-forks worker threads with code and site configuration loaded in memory.
- **Operational Requirement**: After writing site configuration or modifying site settings, `os.kill(1, signal.SIGHUP)` is executed inside the backend container followed by a 2-second buffer. This forces the master process to gracefully terminate existing workers and spawn fresh workers that read the updated `site_config.json` keys from disk.

### D. Multi-Layered Access Control: Module Profiles vs. Workspace Hiding
Kairon implements a **two-layered defense**:
1. **Layer 1 (UI Hiding via Workspace `is_hidden`)**: Hides navigation cards and sidebar links in Frappe Desk UI for unselected modules (e.g., `Stock`, `Selling`, `Manufacturing`). This provides a clean UX and prevents redirection loops.
2. **Layer 2 (Backend Security via Roles, Role Permissions & User Permissions)**: Assigns roles and configures `Role Permissions` for DocType access. `User Permissions` restrict records within allowed DocTypes. `Module Profiles` control module and UI visibility only; they do not block direct API or URL access to the underlying DocTypes.

### E. UI-Only Visibility vs. Server Security Model
> **IMPORTANT SECURITY NOTE**: Workspace hiding (`is_hidden = 1`) and Module Profiles are strictly **UI layout / visibility directives**. Neither enforces backend data security or blocks direct API/URL access to a DocType. True tenant security and permission enforcement are guaranteed by **Roles**, **Role Permissions**, and **User Permissions** (e.g., Company permission filters).

---

## 3. Deployment Prerequisites

Before deploying the ERPNext CRM Provisioning subsystem to production, verify:
1. **Infrastructure Containers**:
   - `frappe-backend-1` container must be active and accessible via Docker socket or CLI exec.
   - Dedicated PostgreSQL database container (`db:5432`) running with administrative user credentials (`postgres`).
2. **Kairon Environment Variables (`system.yaml`)**:
   - `crm.enabled: true`
   - `crm.bench.container_name: "frappe-backend-1"`
   - `crm.bench.sites_path: "/home/frappe/frappe-bench/sites"`
   - `crm.bench.db_host: "db"`
   - `crm.bench.db_port: 5432`
3. **Network & Webhook Access**:
   - Mailpit or outbound SMTP server active for user invitation delivery.
   - Public or internal network routing configured for Kairon webhook callback endpoint (`/api/bot/{bot}/crm/webhook/invitation-accepted`).

---

## 4. Troubleshooting & Recovery Procedures

### Troubleshooting Matrix

| Symptom / Log Error | Likely Cause | Recommended Fix / Action |
| :--- | :--- | :--- |
| `frappe.exceptions.AuthenticationError` (401) | Gunicorn worker holding stale `encryption_key` in pre-forked memory. | Trigger manual worker reload: `docker exec frappe-backend-1 kill -HUP 1`. |
| `MandatoryError: [Workspace, Welcome Workspace]: type` | Virtual workspace missing mandatory field validation in Frappe v15. | Retrying via `reconcile-modules` automatically uses the container DB fallback (`frappe.db.set_value`). |
| Desk UI flickering or loading blank screen | Default workspace set to `setup-wizard` or hidden module. | Call `/api/bot/{bot}/crm/reconcile-modules` to reset `desktop:home_page` to `workspace/CRM`. |
| `AppException: Provisioning workflow is already in progress` | Atomic lock was acquired by a concurrent or previous request. | Check `CRMClientDetails.lock` state in MongoDB; lock auto-clears on completion or error. |

### Recovery Procedure for Failed Provisioning
If a provisioning run fails (`FAILED_BENCH`, `FAILED_COMPANY`, or `FAILED_USER`):
1. **Inspect Log Errors**: Query `/api/bot/{bot}/crm/details` to view `last_error` and `onboarding_status`.
2. **Re-trigger Provisioning**: The workflow is fully idempotent. Call `POST /api/bot/{bot}/crm/onboard` with the same parameters.
   - If the site was created, `BenchExecutor` uses idempotent updates without destroying database tables.
   - `ERPNextClient` detects existing users, profiles, and companies, skipping duplicate creation steps.
3. **Force Drift Repair**: Call `POST /api/bot/{bot}/crm/reconcile-modules` to repair any partially applied workspace visibilities or user roles.

---

## 5. Rollback Procedure

In the event of a critical deployment rollback:
1. **Disable CRM Integration**: Update `system.yaml` setting `crm.enabled: false`.
2. **Revert Backend Microservice**: Redeploy the previous Kairon API docker image.
3. **Database Metadata Preservation**: `CRMClientDetails` records in MongoDB do not modify existing non-CRM Kairon bot settings and can remain safely in place.
4. **Restore or Remove Already-Provisioned/Upgraded Sites**: Disabling the API and rolling back its image does NOT undo work already done inside a tenant's Frappe site (e.g. `bench install-app erpnext` from an in-place upgrade). For any site provisioned or upgraded before the rollback, either:
   - **Restore from backup**: `AppUpgradeProvisioner` takes a `bench backup` immediately before `install-app erpnext` and records the path in `CRMClientDetails.latest_backup_path`. Restore it with `bench --site <site_name> restore <backup_path> --force`, then run `bench --site <site_name> migrate` to reconcile schema state.
   - **Accept forward-compatibility**: if the upgrade completed successfully before rollback, leave the site as-is (it is now Tier 2/ERPNext-installed) and update `CRMClientDetails.tier`/`installed_apps` to match, so future reads of that record aren't inconsistent with the site's real state.
   Do not just delete the site without one of the above -- that discards tenant data with no recovery path.
5. **ERPNext Site Isolation**: Dedicated tenant databases created during testing (`erpnext_<company>`) are isolated and can be removed via `bench drop-site <site_name> --force`.

---

## 6. Known Limitations

1. **ERPNext Single-Bench Scope**: Currently validated for single-bench container setups where all tenant sites reside within one Frappe bench instance.
2. **Workspace UI Level Hiding**: Hiding a workspace via `is_hidden = 1` removes the workspace from the Frappe Desk sidebar but does not replace DocType role-based permission checks.
3. **Email Gateway Dependent**: Invited user workflows rely on an active SMTP relay or Mailpit container for invitation link delivery.

---

## 7. Version Compatibility Assumptions

- **Validated Framework**: Frappe Framework `v15.x` (Python 3.10+, PostgreSQL backend).
- **Validated ERPNext App**: ERPNext `v15.x`.
- **Future Upgrade Guidelines**: When upgrading to Frappe v16+, review:
  - `Workspace` DocType schema for new mandatory fields.
  - `Module Profile` document structure.
  - Compatibility of `PUT /api/resource/Workspace/{name}` endpoints.
