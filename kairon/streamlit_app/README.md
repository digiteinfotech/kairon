# Kairon Platform — Tier 1: CRM & ERPNext Demo

A clean, tier-based Streamlit demo/orchestration UI for the Kairon ↔ Frappe CRM/ERPNext
integration. This app is a **thin consumer of existing Kairon backend APIs** — it does not
implement authentication, provisioning, or invitation logic itself.

## Architecture

```
app.py                      Entry point: login gate + st.navigation shell
components/
  auth.py                   Login form + session-state helpers (calls services/crm.py)
  ui.py                     CSS injection, sidebar (user/bot context), status badges
views/
  1_Tier_Selection.py       Landing dashboard — CRM tier available, others "Coming Soon"
  2_CRM_Onboarding.py       is_crm check -> tenant form -> provisioning -> Tenant Ready
  3_Invite_User.py          Native ERPNext user invitation
services/
  api.py                    Generic authenticated HTTP client (token in session_state)
  crm.py                    Typed wrappers for every Kairon CRM REST endpoint used here
config.py                  API_BASE_URL / TIMEOUT (env-overridable)
```

`services/tenant_service.py`, `provisioning_service.py`, `health_service.py`,
`logs_service.py` are **legacy files kept on disk only** because
`tests/integration_test/test_crm_e2e.py` still imports them. They query MongoDB
and `docker exec` the backend directly, bypassing the Kairon API — the new Tier 1 app
does **not** import or use them.

## Responsibilities

- **Streamlit**: renders UI, calls Kairon REST APIs, never touches Mongo/Postgres/docker directly.
- **Kairon backend** (`kairon/crm/*`, `kairon/api/app/routers/*`): authentication, `enable_crm`
  enforcement, tenant provisioning state machine, ERPNext user invitation, secrets storage.
- **ERPNext**: the actual CRM workspace, Administrator setup, native `UserInvitation` flow.

## Backend API contract used

| Purpose | Endpoint | Auth |
|---|---|---|
| Login | `POST /api/auth/login` | none (issues JWT) |
| User + bots | `GET /api/user/details` | Bearer |
| Bot settings (`enable_crm`) | `GET/PUT /api/bot/{bot}/settings` | Bearer, PUT needs admin scope |
| Provision tenant | `POST /api/bot/{bot}/crm/onboard` | Bearer, admin scope |
| Provisioning status | `GET /api/bot/{bot}/crm/status` | Bearer, admin scope |
| Tenant details / site URL | `GET /api/bot/{bot}/crm/details` | Bearer, admin scope |
| Invite user (native ERPNext) | `POST /api/bot/{bot}/crm/invite-user` | Bearer, admin scope |

Tenant ownership and `enable_crm` are enforced **server-side** (`current_user.get_bot()` from
the JWT, `MongoProcessor.is_crm_enabled` check in `CRMProcessor.onboard_company`) — the UI only
reflects this, it does not gate access on its own.

## Running

```bash
# 1. Kairon API (from kairon repo root)
python3 -m uvicorn kairon.api.app.main:app --host 0.0.0.0 --port 8082

# 2. Streamlit app (from kairon repo root)
PYTHONPATH=. streamlit run kairon/streamlit_app/app.py --server.port 8501
```

Open `http://localhost:8501`. Requires MongoDB (`conversations` DB), the `frappe-backend-1` /
`frappe-db-1` docker stack, and (optionally) Mailpit for invitation emails, all running.

Log in with any Kairon account. CRM is off by default: enable it from the app itself, or via
`PUT /api/bot/{bot}/settings` with `{"enable_crm": true}`.

## Tests

```bash
# Unit tests (hermetic, no Docker needed)
python3 -m pytest tests/unit_test/crm_test.py tests/unit_test/hybrid_provisioning_test.py -q

# Real end-to-end suite (live Kairon API + ERPNext bench + Mailpit + MongoDB; uses disposable e2e_* tenants)
KAIRON_RUN_LIVE_E2E_TESTS=1 KAIRON_E2E_USER=... KAIRON_E2E_PASSWORD=... BENCH_DB_PASSWORD=... python3 -m pytest tests/integration_test/test_crm_e2e.py -q
```

## Known environment limitation

This sandbox's Traefik reverse proxy (`frappe-proxy-1`, ports 80/443) force-redirects all
plain-HTTP traffic to HTTPS, but has no TLS route for freshly provisioned tenant subdomains,
so `http://<site>.localhost` (the URL the backend returns, and what `link_button` opens) 404s
through Traefik in this environment. The site itself is fully live and reachable directly via
`http://<site>.localhost:8080` (the `frappe-frontend-1` container's exposed port). This is a
pre-existing local reverse-proxy configuration gap, not a Kairon/Streamlit code defect — the
backend's `site_url` value is correct and portable to any environment where the proxy isn't
forcing HTTPS on unregistered hosts.
