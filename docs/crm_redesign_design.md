# CRM redesign: audit, design and deployment

Branch `crm_integration`. Companion to `docs/crm_architecture_audit.md` (ownership boundaries, Metering handoff).
Everything under "Findings" was read from source in the five local repositories, not assumed from the brief.

## 1. Findings (Phase 1 audit)

### 1.1 The brief differs from the code in four places

| Brief says | Code says | Consequence |
|---|---|---|
| Metering executes Bench commands | `kairon/crm/services/bench_executor.py` and `provisioners/*` run `docker exec <container> bench ...` **from the Kairon process**. Metering has only a signed, read-mostly CRM *metadata mirror* (`kairon-metering/com/kairon/crm`, `routers/crm_admin_router.py`, `crm_router.py`); it contains no Bench/Docker code. | There is no Metering execution boundary to "preserve". The privileged boundary today is Kairon -> local Docker socket. See 1.7: this cannot work on ECS Fargate. |
| "PyScript callback" | Three different mechanisms exist (1.4). The one that matches "scheduled every ~5 minutes, runs analytics" is the **Analytics Pipeline**: event server -> `KScheduler` (APScheduler + Mongo job store) -> `analytics_pipeline` event -> `AnalyticsRunner` executing a restricted PyScript. | We reuse the *scheduler and event server*, but run system code (not user PyScript) for lead analysis. |
| Admin creates the ERPNext admin from an email | Provisioning creates the ERPNext user for the **Kairon staff member who clicked onboard** (`current_user.email`, `processing._phase_create_user`). | Changed: the user is now `crm_admin_email`. |
| Kairon team authenticates to Kairon | Admin signs in to Kairon **per bot** with that bot's credentials (`crmApi.js` `kaironLogin`); Kairon authorizes bot membership (`ADMIN_ACCESS`). Staff-to-Kairon auth is an open team decision (see audit doc). | We add an optional fail-closed staff allowlist (`crm.staff_allowlist`); we do not invent a bridge. |

### 1.2 Current architecture and data flow

```
Admin UI (Next.js) --per-bot Kairon JWT--> Kairon API /api/bot/{bot}/crm/*
   PUT /settings enable_crm -> MongoProcessor.edit_bot_settings -> CRMMeteringSync (signed HTTP) -> Metering (mirror only)
   POST /crm/onboard (synchronous, up to 15 min) -> CRMProcessor.onboard_company
        -> atomic Mongo lock -> ProvisioningService state machine
             BenchExecutor (docker exec bench new-site ...)   <-- local Docker socket
             ERPNextClient (REST via Host header, Administrator login then integration-user API keys)
   Kairon -> ERPNext tenant: KaironEventPublisher (HMAC) -> kairon_connector.api.v1.webhook.receive_event
        -> core/router -> handlers/lead_handler.py  (CRM Lead create/update, idempotent on custom_kairon_conversation_id)
   Chat runtime: ActionERPNextCRMLeadQualified (flow step) -> lead_dispatch.resolve_lead_target -> same webhook
```

### 1.3 Provisioning sequence (existing)
`PENDING -> PROJECT_CREATED -> BENCH_RUNNING -> SITE_CREATED -> SITE_HEALTHY -> COMPANY_CREATED -> USER_CREATED -> COMPLETED`, with `FAILED_*` states that resume from the failed phase (`ProvisioningService.RETRYABLE_STATES`). Lock = `CRMClientDetails.lock` with 2 h stale recovery. Tenant URL from `CRMProcessor.get_tenant_url`. Reused as is.

### 1.4 Callback / async mechanisms found (and which one the brief most likely means)

| Mechanism | Where | What it is |
|---|---|---|
| **PyScript callbacks** | `kairon/async_callback/*`, `actions/definitions/callback_action.py`, `pyscript.py`, `shared/pyscript/*` | Bot-author Python (RestrictedPython) run by a separate callback service on a URL token; triggered by chat actions or the scheduler. |
| **Analytics Pipeline** | `events/definitions/analytic_pipeline_handler.py`, `shared/analytics/analytics_pipeline_processor.py`, `shared/concurrency/actors/analytics_runner.py`, `kairon/cli/analytics_pipeline.py` | Cron-scheduled PyScript with helpers `get_data_analytics`, `process_instruction` (LLM), etc. **This is the "PyScript analytics on a schedule" the manager most plausibly means.** Not a callback in the HTTP sense. |
| Event server + KScheduler | `events/server.py`, `events/scheduler/kscheduler.py` | FastAPI service; APScheduler `BackgroundScheduler` with Mongo job store; executors: standalone / dramatiq / AWS Lambda / callback. |
| Webhooks | `crm/routes.py` `/webhook/invitation-accepted`, connector `receive_event` | HMAC-signed HTTP. |
| asyncio | `async def` in actions and `MailUtility` | In-process concurrency; unrelated to scheduling. |

Constraint discovered: `SchedulerConfiguration` (`shared/actions/data_objects.py:1184`) enforces `events.scheduler.min_trigger_interval` = **86340 s (~24 h)**, so a 5-minute analytics pipeline **cannot be created through the user-facing pipeline API**. The event server API itself has no such limit.

Constraint discovered: `KScheduler` runs one `BackgroundScheduler` per event-server process over a shared Mongo job store. APScheduler does not coordinate several schedulers on one store; two replicas can fire the same job. Therefore the new job must be **idempotent and lease-protected in the application**, not rely on the scheduler.

### 1.5 Users, bots and conversations
- Tracker store `KMongoTrackerStore` writes per turn: raw events in collection `<bot>` and one **flattened** doc in `flattened_conversations` `{type:"flattened", bot, sender_id, conversation_id, timestamp (user-event epoch s), data:{user_input, bot_response:[{text}], intent}, tag}`.
- Existing index `(bot, type, timestamp desc)` and `(bot, type, sender_id, timestamp desc)` make windowed queries by bot cheap. No new tracker index is required.
- `HistoryProcessor.fetch_chat_users` is date-granular and unbounded (`distinct`), so the new pipeline queries `flattened_conversations` directly with `$gt watermark` and a limit.
- `sender_id` is the channel user id and is what the existing action sends as `conversation_id`; the connector dedupes Leads on it.

### 1.6 Lead qualification today
`ActionERPNextCRMLeadQualified` fires when a flow reaches it; "qualified" means "flow got here"; it needs email/phone slots; it builds a transcript from the tracker and publishes `lead.qualified`. It has no criteria, no LLM, no scheduling, no retry.

Replaced by: the scheduled `kairon/crm/analytics` pipeline. Retained: `lead_dispatch.resolve_lead_target`, `KaironEvent` / `KaironEventPublisher`, `CRMProcessor.get_lead_webhook_secret`, connector `lead_handler` (idempotent on `conversation_id`, so both paths cannot create two Leads for one user). The action itself is **deprecated, not deleted**: removing it touches `actions/definitions/factory.py`, `shared/actions` enums, slot provisioning in `edit_bot_settings` and bots that already have the action configured. It does not conflict at runtime, so deletion is left as an explicit team decision (files listed in section 9).

### 1.7 ECS findings (blockers)
1. **`docker exec` provisioning cannot run on ECS Fargate** (no Docker socket) and is a privilege-escalation risk on EC2. Production needs a Bench execution service (an ECS task that owns the Bench container, or an SSM/ECS-Exec/RunTask wrapper) behind an authenticated HTTP API. Metering was named in the brief but contains none of this. **Not built here; needs a decision** (section 8).
2. `BenchExecutor` and `/crm/onboard` are synchronous (long HTTP request). Fine locally, fragile behind an ALB (default idle timeout 60 s).
3. `localhost` defaults exist for `BENCH_BASE_URL`, `CRM_METERING_URL`, event server / LLM URLs; all must be set per environment.

### 1.8 Users in ERPNext/connector today
Kairon -> ERPNext REST as the integration user (`ERPNextClient.get_users/invite_user/get_invitation_status`), native `User Invitation`, `CRMInvitation` audit docs, webhook `invitation-accepted`. `/crm/create-user` shells out via `docker exec` (flagged, unchanged). The connector has **no user-management API**; it has SSO (`api/v1/sso.py`, 60 s single-use link, blocked for `Administrator`/`Guest`).

## 2. Design

### 2.1 Provisioning + administrator invitation (Kairon)
- `CRMOnboardRequest` gains `crm_admin_email` (required, validated). Stored on `CRMClientDetails.crm_admin_email`. The ERPNext owner user becomes this email.
- Public status vocabulary mapped from existing states (no data migration): Pending / Provisioning / Configuring / Verifying / Ready / Failed (`CRMProcessor.public_provisioning_status`). Returned by `GET /crm/status`.
- Invitation is a separate persisted sub-state (`invitation_status`: `NOT_SENT | PENDING | SENDING | SENT | FAILED`) with attempts, timestamps, error class (never the token). It is created **only** when provisioning reaches `COMPLETED`. Delivery failure never changes `onboarding_status`.
- Secure access: the email carries the tenant URL and a **Frappe password-setup link** (`/update-password?key=...`) that the connector generates on demand (`reset_password(send_email=False)`). It is single-use and expires per Frappe's `reset_password_link_expiry_duration`; no password or long-lived token is stored or logged; the key is held in memory only while the email is built. The 60 s SSO link is not suitable for email and is left untouched. Referrer leakage: the link lands on the tenant's own page and the key is consumed on submit.
- Duplicates: atomic claim (`PENDING|FAILED -> SENDING`), cooldown and max-attempts on explicit resend, deterministic per-provisioning idempotency (`provisioning_id`).
- Retry: `retry_pending_invitations()` runs inside the 5-minute scheduled job (no second scheduler); also `POST /crm/admin-invitation/resend`.
- Provider: existing `MailUtility.trigger_smtp` (system `email` settings). If email is not enabled the state is `FAILED` with `email_not_configured`; nothing claims delivery.

### 2.2 User management (connector + Kairon + Admin)
- Connector: new `kairon_connector/api/v1/users.py` using the same HMAC scheme as events (timestamp-bound, tenant secret, replay window, event-id cache). Operations: `list`, `get`, `invite` (create-or-reuse + role allowlist + setup link), `resend`, `set_enabled`. Role allowlist is code-defined and excludes `System Manager`, `Administrator`, `Guest`, `All`; `Administrator` and the integration user are never listable or modifiable.
- Kairon: `CRMUserManagement` calls the connector with the tenant's webhook secret, requires `COMPLETED`, audits each action in `CRMInvitation`, and the routes keep `ADMIN_ACCESS` plus the optional staff allowlist.
- Admin: `/bot/[botId]/crm-users` page; guarded by ready status.

### 2.3 Lead analytics pipeline
```
event server cron "*/5 * * * *" (job id crm_lead_analysis, bot=system) --> CRMLeadAnalysisEvent (EventClass.crm_lead_analysis)
   (or `python -m kairon crm_lead_analysis run` from an ECS scheduled task; same code)
 -> per bot with enable_crm & COMPLETED & prompt enabled   [failures isolated per bot]
      lease (Mongo atomic, TTL)  -> skip if another worker holds it
      scan flattened_conversations: bot, type, timestamp in (watermark - lookback, now - idle], group by sender_id, max ts, limit N
      per sender: skip if record.last_analysed_ts >= max ts, or already dispatched
                  fetch bounded history -> LLM(prompt v) -> strict JSON validation -> policy
                  qualified -> KaironEvent lead.qualified (conversation_id = sender_id) -> connector (idempotent)
                  record result; retry with backoff; permanent failure -> FAILED_PERMANENT (queryable dead-letter)
      advance watermark only to the last fully handled sender timestamp
 -> retry pending admin invitations
```
Qualification policy: strict schema; `qualifies_as_lead` must be literal `true`; `confidence >= min_confidence` (default 0.7); at least one contact channel that is **verifiably present in the user's own messages** (an email/phone the model invented is dropped). Unknown fields stay `null`. Transcript is untrusted: fixed system prompt, transcript inside delimiters with an explicit "data only" instruction, escaped delimiters, length caps; output is parsed, never executed.

### 2.4 Persistence (new, all Mongo, additive; no migration of existing documents)
`CRMLeadQualificationConfig`, `CRMLeadPromptRevision`, `CRMLeadAnalysisState`, `CRMLeadAnalysisRecord`; new optional fields on `CRMClientDetails` (`strict: False` already). Indexes are declared in the models and created on first use by mongoengine.

## 3. API contracts (Kairon, all under `/api/bot/{bot}/crm`, bearer token, `ADMIN_ACCESS`, plus the optional staff allowlist)

Errors follow Kairon's envelope: HTTP 200 with `{"success": false, "message": "...", "error_code": ...}`; validation failures are 422.

### 3.1 `POST /onboard` (changed) and `POST /validate` (changed)
```json
{ "company_name": "Acme Jewellers", "abbr": "ACM", "default_currency": "INR", "country": "India",
  "crm_admin_email": "owner@acme.com", "selected_modules": ["CRM"] }
```
Backend rules: company name `[A-Za-z0-9_ ]{1,100}`; abbr `[A-Za-z0-9]{1,10}`; currency ISO-4217 shape `^[A-Z]{3}$`; country a name of 2-60 letters/punctuation; email RFC-pragmatic, <=254, lower-cased. **ERPNext itself does not enforce country/currency compatibility** (it only requires that both exist as Link values), so compatibility is not checked here; an unknown country or currency fails at `create_company` and is retried from `FAILED_COMPANY`. Site name is `<company_name_slug>.localhost`; a clash with another bot's tenant is refused with an error before anything is created (the record stays `PENDING` with `last_error` set).
Response (unchanged shape): `{ "status": "COMPLETED", "accepted": true, "provisioned": true, "failed": false, "site_name": "...", "site_url": "...", "erpnext_user": "owner@acme.com" }`. `temporary_password` is **no longer returned** (none is issued).
Re-onboarding a COMPLETED tenant with the same company is idempotent (no new tenant, no new email). A different `crm_admin_email` on a COMPLETED tenant is refused ("use user management").

### 3.2 `GET /status` (extended, backward compatible)
```json
{ "onboarding_status": "COMPLETED", "status": "Ready", "ready": true, "failed": false, "company_name": "Acme Jewellers",
  "crm_admin_email": "owner@acme.com", "tenant_url": "https://acme_jewellers.example", "attempt_number": 1,
  "invitation": { "status": "SENT", "attempts": 1, "sent_at": "2026-10-15T12:00:00", "next_attempt_at": null, "last_error": null } }
```
`status` is one of Pending / Provisioning / Configuring / Verifying / Ready / Failed (grouping of the 8 stored states). `ready` is true only for COMPLETED. `GET /details` additionally exposes `crm_admin_email` and the invitation fields.

### 3.3 `POST /admin-invitation/resend`
`{ "attempted": true, "invitation_status": "SENT", "attempts": 2 }`; `attempted:false` = cooldown (60 s), concurrent attempt or tenant not ready.

### 3.4 User management (tenant must be COMPLETED)
| Method + path | Body | Result |
|---|---|---|
| `GET /managed-users` | - | `[ {email, first_name, last_name, enabled, status: Active|Invited|Not signed in|Disabled, roles, created, last_login} ]` |
| `GET /users/assignable-roles` | - | `{ "roles": ["Sales User", ...] }` |
| `POST /users/invite` | `{email, roles[], first_name?}` | `{email, roles, status:"invited", email_delivery:"sent"|"failed"}`; 4xx-style errors: role not permitted, user already exists |
| `GET /users/{email}` | - | one user |
| `POST /users/{email}/resend-invitation` | - | `{email, email_delivery}`; 60 s cooldown |
| `PUT /users/{email}/enabled` | `{enabled: bool}` | updated user; the CRM administrator cannot be disabled here; connector also refuses the last System Manager |

The older `GET /users`, `POST /invite-user` (native ERPNext User Invitation) and `POST /create-user` are unchanged. `/create-user` shells out through `docker exec` and should be retired with the Bench boundary decision.

### 3.5 Lead qualification
| Method + path | Notes |
|---|---|
| `GET /lead-qualification/prompt` | `{prompt, version, enabled, min_confidence, updated_by, updated_at}` or `null` |
| `PUT /lead-qualification/prompt` | `{prompt (1-4000 chars), enabled, min_confidence 0-1}`; bumps `version` only when the text changes; scoped to the caller's bot |
| `GET /lead-qualification/prompt/revisions` | immutable history |
| `POST /lead-qualification/prompt/test` | `{prompt?, conversation:[{user, bot}]}` (<=30 turns) -> `{qualifies_as_lead, confidence, reason, lead_fields, dispatched:false}`; never stores or sends |
| `GET /lead-qualification/status` | `{last_run_at, last_run_stats, last_error, watermark, counts:{UNQUALIFIED, NEEDS_CONTACT, QUALIFIED, DISPATCHED, ANALYSIS_FAILED, FAILED_PERMANENT}}` |
| `GET /lead-qualification/failed` / `POST /lead-qualification/retry-failed` | the dead-letter set: `{sender_id, attempts, last_error, prompt_version}`; retry requeues it for the next run |

### 3.6 Kairon -> connector (tenant) contracts
Event: `lead.qualified` to `/api/method/kairon_connector.api.v1.webhook.receive_event` (unchanged; HMAC `X-Kairon-Signature`, `X-Kairon-Timestamp`, `X-Kairon-Event-ID`; 202 = queued, 200 `duplicate_ignored`). Payload additions: none; `event_id` is now deterministic per user and `conversation_id` = `sender_id`.
User management: `POST /api/method/kairon_connector.api.v1.users.<list_users|get_user|invite_user|resend_invitation|set_user_enabled|assignable_roles>`, JSON body always contains `"site"` (must equal the tenant's site), signed with the same scheme; response `{"message": ...}` or `{"error": ...}`. 401 bad/stale signature, 409 replayed request id, 403 wrong site, 400 rule violation, 404 unknown user.

## 4. Lifecycles

**Provisioning + invitation.** `PUT /settings {enable_crm:true}` -> staff `POST /onboard` (validated twice) -> lock -> Bench/ERPNext phases (existing state machine) -> CRM administrator user created with *no* ERPNext welcome mail and an in-memory verification password -> integration-user/API keys, webhook secrets, module isolation -> verification logs in as the administrator -> password rotated to a value nobody holds -> `COMPLETED` -> `mark_pending` (once per run, only with an admin email) -> background `send`: atomic claim, connector issues Frappe reset key, Kairon emails tenant URL + setup link -> `SENT`. Failure of any email step leaves `COMPLETED` untouched, sets `FAILED` + backoff (60 s doubling, cap 1 h, 5 attempts) and the 5-minute job retries; the Admin UI resend endpoint is the manual path.

**Lead analysis (every 5 minutes).** See 2.3. Per-sender record states: `UNQUALIFIED` / `NEEDS_CONTACT` re-analysed only when newer messages exist; `QUALIFIED` retried (delivery only, no second LLM call) with backoff; `DISPATCHED` final; `ANALYSIS_FAILED` retried; `FAILED_PERMANENT` after 5 attempts or a 4xx other than 408/409/425/429 (dead letter, visible and requeueable via API). "DISPATCHED" means the connector accepted the event (202 queued); the connector's own handler is idempotent on `conversation_id`.

## 5. Callback / PyScript findings and the chosen mechanism
See 1.4. Chosen: **event server cron (existing KScheduler) -> existing dramatiq/Mongo queue -> existing `kairon-worker`**, running a *system* event (`CRMLeadAnalysisEvent`), not user PyScript. Reasons: the job needs privileged access (all tenants' conversations, tenant secrets), must not be editable by bot authors, and PyScript's restricted sandbox and 24 h minimum interval are the wrong fit. The PyScript Analytics Pipeline remains available for bot-author analytics and is untouched. Nothing is polled from the chat server.

## 6. ECS design (smallest reliable set)
Services that must exist (names are examples; no real identifiers are invented here):
1. `kairon-api` (existing). Hosts CRM routes. No scheduler in it.
2. `kairon-event-server` (existing, **exactly one task** or accept duplicate firing, which the lease tolerates). Owns the 5-minute schedule via APScheduler + Mongo job store (`kscheduler` collection), so the schedule survives restarts and deployments (`misfire_grace_time` 2 h, `coalesce`).
3. `kairon-worker` (existing dramatiq worker; any number of tasks). Executes the job. Its task definition needs the env vars in section 7 (LLM URL, tracker Mongo, e-mail, bench base URL), which the API task already has.
4. LLM server, history/tracker Mongo, Mongo: existing.
5. **Bench/ERPNext**: separate (see blocker 8.1).

One-time operation after deploy: `python -m kairon crm_lead_analysis schedule` (idempotent; or a `PUT/POST /api/events/execute/crm_lead_analysis?is_scheduled=true` with `cron_exp "*/5 * * * *"`). **Nothing registers it automatically**: deploying the image does not start the analytics until this is run once per environment.

Alternative if the single event-server task is unacceptable: an EventBridge Scheduler rule (rate 5 minutes) running an ECS task with command `python -m kairon crm_lead_analysis run` using the worker task definition. The same code runs; no other change. Do not enable both without need (the lease makes it safe, but it wastes LLM-free scans).

Duplicate-execution protection: Mongo lease per bot (10 min TTL, atomic upsert on a unique index) + per-sender records + deterministic event id + connector idempotency. Crash recovery: an expired lease is taken over; the watermark only advances after a clean pass. Graceful shutdown: a run is bounded (50 analyses/bot) and every state transition is persisted per sender; SIGTERM mid-run loses at most the in-flight sender, which is retried next cycle. Health: `kairon-event-server /healthcheck` (existing); job health is `GET /lead-qualification/status` (`last_run_at` older than ~15 min = alert).
Callbacks/webhooks: Kairon -> tenant uses the tenant's secret (generated at provisioning, stored encrypted); tenant -> Kairon `invitation-accepted` is HMAC-verified (existing). Tenant addressing is Host-header based through `BENCH_BASE_URL`; in ECS this must be an internal service URL (ALB/Cloud Map), not `localhost`.

## 7. Configuration (names only; supply values through Secrets Manager / task definition)
Existing and required: `DATABASE_URL`, `TRACKER_URL` (tracker Mongo), `EVENT_SERVER_ENDPOINT`, `EVENTS_QUEUE_URL`, `EVENTS_EXECUTOR_TYPE=dramatiq`, `LLM_SERVER_URL`, `BENCH_BASE_URL`, `BENCH_TENANT_URL_SCHEME=https`, `BENCH_TENANT_URL_PORT` (only if non-default), `BENCH_DB_PASSWORD`, `CRM_METERING_URL` / `CRM_METERING_EVENT_SECRET` (optional), `SECRET_KEY` (encrypts tenant secrets).
Email (the provider is Kairon's existing SMTP sender; there is no new provider): `EMAIL_ENABLE=true`, `EMAIL_SENDER_EMAIL`, `EMAIL_SENDER_SERVICE`, `EMAIL_SENDER_PORT`, `EMAIL_SENDER_USERID`, `EMAIL_SENDER_PASSWORD`, `EMAIL_SENDER_TLS`. With `EMAIL_ENABLE=false` invitations stay `FAILED` with "Email delivery is not enabled" and nothing is claimed as sent.
New: `CRM_STAFF_ALLOWLIST` (optional, comma separated emails / `@domain`), `CRM_LEAD_LLM_TYPE` (default `openai`), `CRM_LEAD_LLM_MODEL` (default `gpt-4o-mini`), `CRM_LEAD_LLM_TIMEOUT` (60), `CRM_LEAD_BATCH_SIZE` (50), `CRM_LEAD_IDLE_SECONDS` (120), `CRM_LEAD_LOOKBACK_SECONDS` (900), `CRM_LEAD_MAX_ATTEMPTS` (5), `CRM_LEAD_MAX_TRANSCRIPT_CHARS` (6000). The LLM key lives in the LLM server / `LLMSecret`, never in these.
Admin: `NEXT_PUBLIC_KAIRON_API_URL` (existing).

Database: new collections `crm_lead_qualification_config`, `crm_lead_prompt_revision`, `crm_lead_analysis_state`, `crm_lead_analysis_record` (indexes are declared on the models and created on first use) and new optional fields on `crm_client_details` (`strict: False`; absent = defaults). **No data migration is required.** Existing tenants have no `crm_admin_email`: they are never emailed, and re-onboarding with a new email is refused.

Deployment order: (1) connector app update on the bench (`bench --site <site> migrate` is not required: no DocType change; restart workers to load `api/v1/users.py`) for every tenant, **before** step 2, otherwise user management and invitations fail with a connector 404; (2) Kairon API, event server, worker; (3) run `crm_lead_analysis schedule`; (4) Admin. Rollback: reverse order; the new collections and fields are ignored by older code; unschedule with `DELETE /api/events/crm_lead_analysis` on the event server.

## 8. Blockers, decisions and risks (nothing below is claimed as done)
1. **Bench execution on ECS.** `BenchExecutor` uses `docker exec`. This cannot run on Fargate and the brief's Metering-executes-Bench premise is not what the code does. Needs a decision: an authenticated Bench-runner service (HTTP) owned by infra, with `BenchExecutor` calling it. Until then, provisioning works only where Kairon can reach the Docker socket (local/EC2).
2. **Synchronous onboarding.** Still one long request; ALB idle timeout (60 s default) will cut it while the server continues and the status endpoint stays accurate. Making it asynchronous needs the Bench runner from (1) so the work does not live in an API task.
3. **Staff identity.** Admin signs in to Kairon per bot; `CRM_STAFF_ALLOWLIST` narrows who may provision/manage but is not a staff-to-Kairon auth bridge (existing open decision).
4. **Setup-link lifetime.** Frappe's default reset-link lifetime is 20 min (verified on the installed Frappe); the connector raises it to 72 h on the first invitation in a tenant, which also applies to that tenant's ordinary "forgot password" links (still single use).
5. **Old lead action** is deprecated, not removed (1.6).
6. **First-run backfill**: a bot's first analysis starts one hour back (`initial_backfill_seconds`), not from the beginning of history.
7. **LLM cost/privacy**: only the last 40 turns (<= 6000 chars) of an *idle*, *changed* conversation are sent, once per change; the transcript is also sent to that company's own ERPNext on qualification. Kairon stores no transcript for this feature (only fields, confidence, reason, status).
8. APScheduler in more than one event-server task can double-fire; harmless by design, wasteful.

## 9. Files changed
Kairon: `kairon/crm/{models,schemas,processor,routes,constants}.py`, `kairon/crm/services/{provisioning,erpnext_client,admin_invitation,connector_client,user_management}.py`, `kairon/crm/analytics/{models,qualifier,source,pipeline,processor}.py`, `kairon/events/{publisher.py,models.py,definitions/crm_lead_analysis.py,definitions/factory.py}`, `kairon/shared/constants.py`, `kairon/cli/crm_lead_analysis.py`, `kairon/__init__.py`, `kairon/actions/definitions/erpnext_crm_lead.py` (deprecation note), `system.yaml`, tests `tests/unit_test/crm_redesign_test.py` (new), `tests/unit_test/crm_test.py`, `tests/integration_test/test_crm_e2e.py`.
Remove when the old action is retired: `kairon/actions/definitions/erpnext_crm_lead.py`, its entries in `actions/definitions/factory.py` and the `ActionType` enum in `shared/actions`, the `kairon_lead_qualified_sent` slot block in `MongoProcessor.edit_bot_settings`, and `tests/unit_test/action/erpnext_crm_lead_action_test.py`.
Admin: `src/components/crm/{CrmSettingsCard,crmValidation}.js`, `crmUsersLogic.js(+test)`, `CrmUsersPanel.js`, `src/redux/api/crmApi.js`, `src/app/bot/[botId]/layout.js`, `src/app/bot/[botId]/crm-users/page.js`, `package.json` (`test:crm`).
Bench / connector: `kairon_connector/api/v1/users.py`, `core/{user_roles,signed_request}.py`, `tests/test_user_management.py`, `streamlit_apps/crm/{services/crm.py,views/2_CRM_Onboarding.py}`.
Metering: **no change required**: the mirror events carry no administrator email or invitation data, and its strict schema would reject new fields.
Kairon UI: untouched.

## 10. End-to-end verification (local, 2026-10-15)
Real local stack: Kairon API, event server (`standalone` executor), Metering (local-only launcher, see below), Admin dev server, local bench (`frappe-backend-1`, Postgres), Mailpit as the SMTP sink (STARTTLS + auth accepted), a mock LLM server. Test data only (bots `crm_final_bot*`, tenants `zeta_final_co`, `beta_final_co`, `*.example.test` mailboxes).
Verified in the browser and against the live tenant: validation, provisioning to Ready, invitation email (tenant URL, single-use setup link, expires 72 h, reuse rejected, token absent from logs and Mongo), user management (invite/resend/disable/enable, privileged roles refused, administrator protected, tenant isolation), prompt save/update/versioning/test, the 5-minute schedule firing at 22:40/22:45/22:50/22:55/23:00 local, and a real CRM Lead in the tenant's Leads list (fields from the source conversation only; invented phone dropped; no Leads for unqualified, ambiguous, malformed or timed-out conversations; replay of the same event left exactly one Lead).
Defects found and fixed during this run: (1) a failed `bench new-site` left a half-built site that blocked every retry (rollback added, `_rollback_partial_site`); (2) header badge showed `Failed` while a retry was running (`resolveCrmView` now reports in-progress while a request is in flight); (3) mock/test artifacts excluded. Added the Admin Lead Qualification page (`/bot/{id}/lead-qualification`).
Deployment facts learned: the connector must be present in the tenant image/volume (`api/v1/users.py`, `core/user_roles.py`, `core/signed_request.py`) before invitations work (HTTP 417 otherwise); Kairon API and event server must be restarted to load new code; the Bench host Postgres must be reachable as `db` from the Bench container.
Known limits: Sales User accounts see no leads they do not own (Frappe CRM permission model); an unauthenticated API call returns HTTP 200 with `error_code: 401` (platform-wide convention the Admin client relies on, not changed); `run_cycle` reports `bots` including bots skipped for having no ready tenant; Metering needs a local launcher on this FastAPI version because of an unrelated route (`Path(default=...)`); `test_get_executor_logs` is flaky on pristine `HEAD` too (1 failure in 6 runs: two log rows with near-identical timestamps are returned in unstable order).

## 11. Reuse of the Analytics Pipeline LLM and the PyScript callback (supersedes 2.3, 5 and 6 where they conflict)

### 11.1 What the existing Analytics Pipeline does (read from source, then verified live)
- **Definition:** `AnalyticsPipelineConfig` (`pipeline_name`, `callback_name`, `scheduler_config`) points at a `CallbackConfig` whose `pyscript_code` is the PyScript. Created through `POST /api/bot/{bot}/analytics/events` (`routers/bot/analytics.py`) or `AnalyticsPipelineEvent.enqueue(add_schedule)`.
- **Trigger:** `AnalyticsPipelineEvent._add_schedule` -> `Utility.request_event_server(analytics_pipeline, is_scheduled=True, cron_exp=...)` -> event server `KScheduler` (APScheduler, Mongo job store) -> `ExecutorFactory` executor -> `AnalyticsPipelineEvent.execute`.
- **Execution:** `AnalyticsRunner.execute` validates the script with `compile_restricted`, then runs it in a **subprocess** (`python -m kairon.shared.pyscript.analytics_worker`, 600 s `communicate` timeout) with an allowlist of helpers. The helper list exists twice (`analytics_runner.py` for validation, `analytics_worker.py` for execution); a helper must be in both.
- **LLM:** the pipeline's only LLM entry point is `CallbackScriptUtility.process_instruction(..., operation_type="completion", model_id, llm_type="openrouter", bot, user)`: it requires the platform `LLMSecret` for `openrouter`, then POSTs `{llm.url}/{bot}/completion/{llm_type}` (`formatted_response` is the answer). No key is sent from Kairon; the LLM server holds provider access.
- **Results and errors:** the script's `bot_response` and any exception are written to `AnalyticsPipelineLogs` (`Completed` / `Fail` with `exception`); optional e-mail triggers exist. A cron pipeline is kept after a failure and fires again.
- **Schedule limit (verified):** `SchedulerConfiguration` (stored) and `AnalyticsSchedulerConfig` (API request) both reject cron intervals below `events.scheduler.min_trigger_interval` = **86340 s** (env `MIN_SCHDULER_TRIGGER_INTERVAL`). It is configuration, not a hard-coded rule, but it is shared with message broadcasts, so lowering it globally would change broadcasts too.

### 11.2 What CRM now does
- **LLM:** `qualifier.invoke_llm` calls `CallbackScriptUtility.process_instruction` (completion, provider `openrouter`, the bot id as tenant context). CRM has no client, provider, endpoint or key of its own; the former `crm.lead_analysis.llm_type` setting and CRM-owned HTTP call were removed. Only the **model id** is CRM-configurable (`CRM_LEAD_LLM_MODEL`, default `openai/gpt-4o-mini`, a model id the pipeline already uses in its tests; it must be allowed on the platform LLM). `process_instruction` gained two optional, backward-compatible arguments: `system_prompt` (so the fixed instruction is a real system message and the untrusted transcript stays in the user message) and `timeout` (the original call had none).
- **PyScript:** each CRM-enabled bot gets an ordinary Analytics Pipeline `crm_lead_qualification`: callback `crm_lead_qualification` with the one-line script `bot_response = analyse_crm_leads()`, cron `*/5 * * * *`. `analyse_crm_leads` is a new helper in both allowlists, bound by the runner to the pipeline's own bot, so a script cannot analyse another bot. It runs `LeadAnalysisPipeline.run_bot(bot)` (lease, watermark, per-user records, validation, dispatch; unchanged).
- **Lifecycle:** saving a lead-qualification prompt with `enabled` creates the callback and the schedule (idempotent); disabling removes the schedule (`CRMLeadPipelineManager`). The prompt is saved even if scheduling fails, and the response says so (`pipeline.scheduled=false`, `pipeline.error`).
- **Interval:** `events.scheduler.analytics_min_trigger_interval` (env `ANALYTICS_MIN_TRIGGER_INTERVAL`) overrides the minimum for **analytics pipelines only**. Unset = identical to before (so a 5-minute pipeline is refused). The CRM deployment sets **300**. Broadcasts keep their limit.
- **Platform job:** `crm_lead_analysis` (event server) no longer analyses leads; it only retries pending administrator invitations.

### 11.3 Runtime limits that apply
Subprocess hard limit 600 s per run (the runner does not kill the child on timeout, so a run must finish by itself: the analysis stops starting new analyses after a time budget, default 420 s, and resumes next tick from the persisted state); per-call LLM timeout 60 s (`CRM_LEAD_LLM_TIMEOUT`); one bot per pipeline run; concurrent runs for one bot are prevented by the Mongo lease; imports/network are the sandbox's (`requests` is in the allowlist but CRM does not use it). A run uses the event server's configured executor: `standalone` (event-server process), `dramatiq` (Mongo broker -> `kairon-worker`) or `aws_lambda` (task definition `ANALYTICS_PIPELINE_TASK_DEFINITION`, running `python -m kairon analytics_pipeline <bot> <user> <event_id>`), so in ECS the code runs wherever that executor places it; the task needs `DATABASE_URL`, `TRACKER_URL`, `LLM_SERVER_URL`, the bench URL and tenant secrets, and the platform `openrouter` `LLMSecret` must exist in the same database.

### 11.4 Evidence (local, 2026-10-16)
Live path exercised: prompt saved from the Admin API -> pipeline + callback created -> event-server cron fired at 18:55 and 19:00 (exactly five minutes apart) -> `AnalyticsPipelineEvent.execute` -> `AnalyticsRunner` subprocess -> PyScript -> `analyse_crm_leads` -> `process_instruction` -> HTTP to the LLM server -> validation -> signed webhook -> real CRM Lead `CRM-LEAD-2026-00002` in `zeta_final_co`. **The LLM server was a local stand-in** (`mock_llm.py`): no real provider was called, so the real model's behaviour (and the real `openrouter` key) is untested. Second tick: only the two failed conversations were retried; Lead count stayed 2.

## 12. Bench execution on ECS Fargate: status, integration and contract
**Status: Kairon side integrated and tested against a stand-in; the runner service does not exist, so ECS provisioning is NOT complete.**

**What changed (backward compatible).** `crm.bench.execution_mode` (env `BENCH_EXECUTION_MODE`) is `docker` by default and in every existing test: behaviour is byte-for-byte the previous `docker exec` path (verified by the unchanged provisioning suites and a test that asserts the exact command). Any other value than `docker`/`runner` is an explicit error. In `runner` mode `BaseProvisioner` gets `self.runner` (`get_bench_runner()`), and each Bench action maps one-to-one to a contract operation:

| Docker-mode action | Runner operation | Notes |
|---|---|---|
| pre-flight: `bench --version`, `test -d sites/<s>`, `test -d apps/<a>` | `health`, `site_exists`, `list_apps` | read-only, never replayed from cache |
| `bench new-site ... --install-app` | `new_site` | `params`: `db_name`, `apps`; `secrets`: `admin_password`; DB root credentials stay with the runner; failure triggers `drop_site` |
| rollback of a half-built site | `drop_site` | |
| `bench install-app` (apps, `kairon_connector`) | `install_app` | |
| `bench set-config encryption_key` | `set_encryption_key` | generated and kept by the runner |
| `set-default desktop:home_page` | `set_homepage` | |
| logs dir, `bench migrate`, frontend asset sync, Administrator/user/Company/Fiscal-Year script | `prepare_tenant` | implemented server-side; `params`: admin email, company, abbr, currency, country |
| setup-wizard bypass, clear-cache | `finalize_tenant` | |
| gunicorn reload | `reload_workers` | global |
| `BenchExecutor.set_admin_password` | `set_admin_password` | `secrets`: `admin_password` |

Call sites **not** ported (refused or skipped in runner mode, never run via docker): Tier 1 -> Tier 2 upgrade (`AppUpgradeProvisioner`: explicit error), `/crm/create-user` (`BenchExecutor.create_crm_user`: explicit error, use invitations), `BenchExecutor._database_exists` (not on the provisioning path), and the four `ERPNextClient` "container fallback" helpers (key generation, workspace visibility, clear-cache, default workspace), which are already fallbacks behind HTTP paths and now short-circuit to the HTTP path when there is no container. Pre-flight, provisioning and `set_admin_password` do not need a container name or the docker binary in runner mode (`resolve_container_name` returns `""` without calling `docker ps`).

**Configuration** (fail closed): `BENCH_EXECUTION_MODE=runner` requires `BENCH_RUNNER_URL` (https; `BENCH_RUNNER_ALLOW_INSECURE_HTTP=true` is for local development only) and `BENCH_RUNNER_SECRET` (secret store), optional `BENCH_RUNNER_JOB_TIMEOUT` (default 1200 s). `python -m kairon crm_lead_analysis check` reports these problems before a deployment.

**Contract the runner must implement** (client: `kairon/crm/services/bench_runner.py`):
- `POST /v1/operations` `{operation, site, params, secrets, idempotency_key}` -> `202 {job_id}`; `GET /v1/jobs/{job_id}` -> `{state: queued|running|succeeded|failed, result, error}`. Jobs and polling because `new_site` can take minutes.
- Signature: `X-Kairon-Signature: sha256=HMAC-SHA256(secret, "<X-Kairon-Timestamp>." + raw body)`; headers `X-Kairon-Timestamp` (epoch seconds) and `X-Kairon-Request-Id` (single-use). The client builds exactly this (tested by recomputing it).
- **Runner-side obligations (Kairon cannot enforce them):** constant-time signature check; reject timestamps outside +-300 s; remember request ids >= 10 min and reject repeats (replay protection); allowlist the operations and validate each operation's params; accept only tenant site names `^[a-z0-9][a-z0-9_]{0,59}\.localhost$`; treat `secrets` as write-only (never log, persist, echo, or place in results or errors); honour `idempotency_key` per operation (same key, same job, no second site); hold the database root credentials; TLS inside the VPC only; return short, secret-free `error` text.
- **Client behaviour:** retries only transport errors and 408/425/429/5xx (3 attempts, backoff 1 s, 2 s, 4 s); never retries 401/403 or other 4xx; polls every 3 s up to the job timeout then fails; refuses credential-like keys in `params`; refuses unknown operations and malformed site names or job ids before any request. Idempotency keys are `<provisioning id>:<operation>:<site>` for mutations (a retry of the same run reuses the job, a new onboarding attempt starts fresh) and random for read-only operations.
- **Known coupling:** `prepare_tenant` and `new_site` replace shell and Python snippets that today live in `base_provisioner.py`; the runner owner must reproduce their behaviour (see the table). Until a runner exists, only the stand-in used by the tests implements this contract.

**Still required for ECS:** build and deploy the runner (ECS service owning the Bench volume, or an equivalent), implement the operations above, then run live provisioning against it; port the upgrade path if Tier 1 -> 2 upgrades are needed.

## 13. Deployment checklist (verified locally; ECS values are placeholders to be supplied by infra)
| Item | Requirement | Verified |
|---|---|---|
| `ANALYTICS_MIN_TRIGGER_INTERVAL=300` | Set on the **Kairon API** (validates pipeline creation via `AnalyticsSchedulerConfig` / `SchedulerConfiguration`) and on any process that saves `AnalyticsPipelineConfig`; the event server and executor do not validate the interval but should carry the same value for consistency. Missing/empty => 86340 (a 5-minute pipeline is refused); non-integer or < 60 => ignored with a warning (strict limit kept). Broadcasts always use `MIN_SCHDULER_TRIGGER_INTERVAL`. | Local API and event-server processes both loaded 300; fallback cases unit-tested |
| Platform `LLMSecret` `openrouter` | Must exist in the database the pipeline subprocess connects to, with `CRM_LEAD_LLM_MODEL` (default `openai/gpt-4o-mini`) in its `models` list; otherwise each analysis fails with a recorded, readable reason and the lead is retried. | Local record is a **fake key**; no real provider call made |
| Pipeline creation | Automatic when a lead prompt is saved enabled (`CRMLeadPipelineManager`); the response states `pipeline.scheduled` and `pipeline.error`. No manual per-bot step. The platform job `crm_lead_analysis` (invitation retries) is registered once with `python -m kairon crm_lead_analysis schedule`. | Live |
| Order | 1 connector update in every tenant; 2 Kairon API + event server + executor/worker (same image and env); 3 register `crm_lead_analysis`; 4 Admin. | Learned from the HTTP 417 seen without the connector files |
| Executor | `events.executor.type` decides where the PyScript subprocess runs (`standalone`, `dramatiq` worker, or `aws_lambda` with `ANALYTICS_PIPELINE_TASK_DEFINITION`); that environment needs `DATABASE_URL`, `TRACKER_URL`, `LLM_SERVER_URL`, bench base URL and the tenant secrets. | Standalone only |
| Provisioning | Kairon side ready for `BENCH_EXECUTION_MODE=runner`; blocked on the runner service itself (section 12). `python -m kairon crm_lead_analysis check` reports the configuration problems read-only (exit 1 if a required check fails). | Check run against the local environment |
