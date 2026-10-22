# CRM integration: ownership boundaries

Branch `crm_integration`. This replaces an earlier draft that proposed moving lead/event code to Metering; the team has since confirmed the boundaries below. Nothing has been moved or deleted. The Kairon to Metering handoff below was added afterwards.

## Confirmed ownership

| Area | Owner | Notes |
|---|---|---|
| CRM REST APIs (`/api/bot/{bot}/crm/*`), `PUT /settings` (`enable_crm`), auth/roles | **Kairon** | `enable_crm` is authoritative only through `MongoProcessor.edit_bot_settings` (it also provisions the `kairon_lead_qualified_sent` slot) |
| CRM tenant metadata (`CRMClientDetails`), validation, provisioning state machine | **Kairon** | Authoritative source |
| Lead runtime: `ActionERPNextCRMLeadQualified`, its factory/enum entries, slot provisioning, `KaironEvent`/`KaironEventPublisher`, `CRMProcessor.get_lead_webhook_secret` | **Kairon** | `lead.qualified` goes directly from Kairon to the tenant's ERPNext. Not moved |
| CRM configuration UI (Bot Settings CRM card) | **Kairon Admin** | Calls Kairon APIs with a per-bot Kairon sign-in |
| Streamlit CRM & ERPNext demo/ops app | **ERPNext/bench repo** | `apps/kairon_connector/streamlit_apps/crm/`; HTTP-only client of Kairon, no Kairon imports (enforced by a test) |
| ERPNext-side receiver (`kairon_connector`, HMAC, idempotency, handlers) | **Frappe bench repo** | Separate repo, untouched |
| `bench new-site` / `docker exec` provisioning (`BenchExecutor`, `services/provisioners/*`) | **Kairon today; infra/Terraform later** | Stays until a destination repo and a replacement exist |
| CRM metadata/events consumer | **Metering** | Implemented as a signed HTTP API (see "Kairon to Metering handoff"). Kairon remains authoritative; Metering only records what Kairon reports |

## Facts established by the three-repo audit
- Metering (`kairon-metering`) is an analytics/admin service over Kairon's MongoDB. Before the handoff work it had no CRM, event bus, or Terraform code (it now has only the signed CRM metadata API below). Its `master` has no user authentication on its routes; its login lives on the unmerged branch `origin/admin_authentication` (own JWT, staff-only `valid_users`).
- A Metering/Admin token is not accepted for per-bot Kairon CRM APIs: Kairon authorizes bot membership (`fetch_role_for_user`). Do not assume a bridge; see pending decisions.
- Metering's `/api/features/bot_features/{bot}/update` writes `bot_settings` directly in MongoDB, bypassing `edit_bot_settings`. `enable_crm` must therefore stay on Kairon's `PUT /settings`. Fixed in Metering (`BotFeatures.KAIRON_OWNED_SETTINGS`): the generic API now hides and rejects `enable_crm`. Its other routes remain unauthenticated on `master`.
- `KaironEventPublisher` is **not** on master; it was added on this branch (commit `0291f70f`) and is used only by the lead action.
- There is no "Data Factory" code in Kairon.
- Kairon had no CRM lifecycle/metadata event before the handoff; it now emits the four events below. `lead.qualified` remains the only event sent to ERPNext.

## Deferred (documented, not changed)
- Streamlit CRM app: **moved** to the ERPNext/bench repo (`apps/kairon_connector/streamlit_apps/crm/`), where it runs as a thin client of Kairon's REST API. Removed from Kairon together with its `.gitignore` allow-rule. `tests/integration_test/test_crm_e2e.py` no longer imports it (it calls Kairon's own provisioning classes directly); the health/logs/tenant-helper tests moved with the re-homed services.
- `/crm/tables*` (raw tenant DB rows to bot admins) and `/crm/create-user` (shells out via docker): not used by Admin. The migrated Streamlit app has client wrappers for them in `services/crm.py` but no page calls them; candidates for removal/infra.
- `POST /crm/onboard` returns `erpnext_user` and `temporary_password`; Streamlit and the E2E suite read them.
- `bench new-site` passes the DB root and Administrator passwords as command-line arguments.
- `crm/manager.py`, `crm/services/crm_client.py`, `base_frappe_client.py`: no production caller.
- `CRMProcessor.reconcile_invitations` is documented as scheduled but nothing schedules it.
- `/crm/onboard` is synchronous (long runs can hit proxy timeouts); status is available at `GET /crm/status`.

## Pending team decisions
1. Admin (staff console) to Kairon authentication for acting on a customer's bot. Per-bot Kairon sign-in stays until decided.
2. Metering's own user authentication (its JWT login is on the unmerged `admin_authentication` branch). The CRM API does not depend on it: it is service-to-service HMAC.
3. Whether `/onboard` should stop returning the temporary password.
4. Destination and interface for provisioning (infra/Terraform).

## Kairon to Metering handoff
Transport: authenticated HTTP, reusing Kairon's `KaironEvent` envelope and `KaironEventPublisher` HMAC scheme (`X-Kairon-Signature: sha256=HMAC(secret, "<timestamp>." + body)`, `X-Kairon-Timestamp`, +-300 s). No broker.

Config. Kairon: `CRM_METERING_URL`, `CRM_METERING_EVENT_SECRET` (both unset => handoff skipped, never blocks CRM). Metering: `CRM_EVENT_SECRET` (unset => ingestion returns 503, fails closed). Use the same value on both sides.

| Event | Sent when | Payload (metadata only) |
|---|---|---|
| `crm.enabled` / `crm.disabled` | `enable_crm` changes through `PUT /settings` (`MongoProcessor.edit_bot_settings`) | `bot`, `user` |
| `crm.tenant.provisioned` | end of `onboard_company`, status `COMPLETED` | `bot`, `user`, `company_name`, `company_abbr`, `country`, `currency`, `tenant_name`, `tenant_url`, `provisioning_status`, `tier` |
| `crm.tenant.provision_failed` | end of `onboard_company`, status `FAILED_*` | same without `tenant_*`; no error text |

- Metering: `POST /api/crm/events` (ingest, idempotent on `event_id`; stale events logged, not applied), `GET /api/crm/bots/{bot}`, `GET /api/crm/bots/{bot}/events`. All require the signature. Unknown payload fields (e.g. passwords) are rejected with 422. Storage: `crm_bot_metadata`, `crm_tenant_metadata`, `crm_events`.
- Failure handling: a Metering outage or rejection is logged and never fails onboarding or settings. Retry with `POST /api/bot/{bot}/crm/metering-sync` (rebuilds from Kairon's record; deterministic event id `evt_<provisioning_id>_<type>`, so repeats are ignored). Delivery state is stored on `CRMClientDetails.metering_synced*` and is not returned by `/crm/details`.
- Limitation: delivery happens inline at the end of the synchronous `/crm/onboard`, up to 5 s extra when Metering is down; there is no background retry queue.
- `enable_crm` is Kairon-only: Metering's generic features API no longer shows or writes it (422).

## Redesign (administrator invitation, user management, scheduled lead analytics)
See `docs/crm_redesign_design.md`. It supersedes the "Deferred" notes on `/crm/create-user`, `reconcile_invitations` scheduling and `temporary_password` where they conflict.
