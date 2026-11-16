# CRM deployment guide

What an operator must configure to run the CRM integration (ERPNext / Frappe CRM tenants provisioned per bot). Every
setting below is read from `system.yaml` (`crm:` block, `events:` block) and was checked against the code that uses it. Nothing
here is a recommended value unless it says so; values such as domains, ARNs and URLs are yours to supply.

Read-only readiness report at any time:

```
python -m kairon crm_lead_analysis check      # exit status 1 when a required check fails; never prints a secret
```

## A. Tenant addressing

A tenant has one name that is used twice: it is the Frappe **site name** (the directory on the Bench and the `Host` header the
Bench routes on) and the hostname in every link a user opens. It is `<company-slug>.<tenant domain>`, for example
`acme-jewellers.<your domain>`.

| Setting | Default | Meaning |
|---|---|---|
| `BENCH_TENANT_DOMAIN` | `localhost` | Domain appended to the company slug. **Set a real domain you control in production.** The default only works on a single machine. |
| `BENCH_TENANT_URL_SCHEME` | `http` | Use `https` in production. One-click login and invitation links are refused over `http` unless `BENCH_SSO_ALLOW_INSECURE_HTTP=true` (local development only). |
| `BENCH_TENANT_URL_PORT` | unset | Optional port added to tenant links (for a local stack on a non-default port). |
| `BENCH_BASE_URL` | `http://localhost:8080` | Where **Kairon** reaches the Bench frontend. All server-to-tenant calls (REST, lead events, user management) go to this URL with the tenant in the `Host` header, so tenant names never need to resolve from the Kairon or action-server hosts. |

Rules the code applies:
- Slugs are lower-case, hyphenated, at most 55 characters; longer names are shortened with a deterministic hash suffix so two
  long names with the same start stay distinct. Underscores are not used (they are not valid in DNS names).
- A tenant that already has a `site_name` keeps it. Changing `BENCH_TENANT_DOMAIN` affects new tenants only; it does not rename
  existing ones.
- The tenant's database name is derived from a hash of the site name, so it never depends on the company name's length.
- The public URL shown to users is `<scheme>://<site_name>[:port]`. The site name, the DNS record and the TLS certificate must
  all match. A wildcard record and certificate for `*.<BENCH_TENANT_DOMAIN>` is the usual way to provide this; that infrastructure
  is outside this repository.
- **External Bench runner:** site names sent to the runner look like `acme-jewellers.<domain>`, not `*.localhost`. A runner that
  only accepts `^[a-z0-9][a-z0-9_]{0,59}\.localhost$` will reject every operation. Kairon's own check now accepts
  `^[a-z0-9][a-z0-9_-]{0,59}\.<dns name>$`; the runner service (not in this repository) must be updated to match.

## B. Bench execution mode

| Setting | Default | Meaning |
|---|---|---|
| `BENCH_EXECUTION_MODE` | `docker` | `docker`: Kairon runs `docker exec` against the Bench container. `runner`: Kairon calls an external HTTP Bench runner. Any other value is a configuration error. |
| `BENCH_RUNNER_URL` | unset | Required in `runner` mode. Must be `https://` (see below). |
| `BENCH_RUNNER_SECRET` | unset | Required in `runner` mode. Signs every request (HMAC-SHA256, timestamped). |
| `BENCH_RUNNER_JOB_TIMEOUT` | `1200` | Seconds Kairon waits for one runner operation. |
| `BENCH_RUNNER_ALLOW_INSECURE_HTTP` | `false` | Allows an `http://` runner URL. Local development only. |
| `BENCH_DB_PASSWORD` | unset | Database root password. **Required in `docker` mode only.** In `runner` mode the runner holds database credentials itself and Kairon does not need this value. |
| `BENCH_CONTAINER_NAME`, `BENCH_FRONTEND_CONTAINER_NAME`, `BENCH_DB_HOST`, `BENCH_DB_PORT`, `BENCH_DB_USER` | see `system.yaml` | Docker mode only. The container name must match `[A-Za-z0-9][A-Za-z0-9_.-]*`; anything else is rejected. |

Behaviour that matters in production:
- `docker` mode needs the Docker socket in the Kairon API container, which is root-equivalent access to the host, and it puts
  the database and administrator passwords on `docker exec` command lines. It cannot run on AWS Fargate at all. Treat it as a
  local / development mode. **Enforcing runner-only in production is not done by the code and is a pending manager decision;** the
  default has not been changed.
- `python -m kairon crm_lead_analysis check` reports the mode and warns when it is `docker` (`bench_runner_for_ecs`).
- The runner's own obligations (signature verification, replay protection, schema checks, TLS inside the VPC, idempotency) are
  listed in the docstring of `kairon/crm/services/bench_runner.py`. Kairon cannot enforce them.

## C. Outgoing email

There are two different mail paths:

1. **Invitation and setup-link emails sent by Kairon** (the CRM administrator's invitation, managed-user invitations, resends).
   These use Kairon's own mail configuration. They require `EMAIL_ENABLE=true` and a working Kairon mail setup. Without it
   the invitation is recorded as `FAILED` with the reason and retried by the scheduled job (up to 5 attempts, backing off up to an
   hour); provisioning itself is never failed by mail. `crm_lead_analysis check` reports `email_enabled`.
2. **Mail sent by ERPNext itself** (password resets, ERPNext-native notifications). These use the tenant's default outgoing
   Email Account, which Kairon creates at provisioning time **only** from these settings:

| Setting | Default | Meaning |
|---|---|---|
| `BENCH_SMTP_SERVER` | unset | SMTP host. **Without it no Email Account is created** and ERPNext-native mail cannot be sent. |
| `BENCH_SMTP_EMAIL_ID` | unset | Sender address. Also required; both must be set. |
| `BENCH_SMTP_PORT` | unset | Defaults to 587 with TLS, otherwise 25. |
| `BENCH_SMTP_USE_TLS` | `false` | `true`, `1` or `yes` enables STARTTLS. |

The account is created without SMTP authentication (`no_smtp_authentication`), so the relay must accept connections from the
Bench without credentials (for example an internal relay). There is no setting for SMTP username/password. For a local stack
you can point `BENCH_SMTP_SERVER` at your own test mail catcher. SMTP is optional for provisioning to succeed.

`BENCH_SMTP_ENABLED` appears in `system.yaml` but is only passed along and not used to decide anything.

## D. CRM platform job (lead analysis, invitation retries, reconciliation)

One platform-wide event, `crm_lead_analysis`, runs every five minutes and does three independent things. A failure in one is
logged and does not stop the others:

| Step | What it does |
|---|---|
| Lead analysis | For every CRM-enabled bot with an enabled prompt and a `COMPLETED` tenant: finds conversations idle for `CRM_LEAD_IDLE_SECONDS`, asks the platform LLM (`openrouter` `LLMSecret`) to judge them against that bot's prompt, and sends qualified leads to that bot's tenant as signed events. Each bot is protected by its own lease, so overlapping runs and several workers skip a bot already being processed. A watermark and per-conversation records prevent repeated analysis and duplicate leads. |
| Invitation retries | Delivers pending or failed administrator invitations (bounded per run). |
| Reconciliation | Checks pending ERPNext user invitations and assigns company permission for any whose acceptance webhook was missed. |

A prompt change or enable/disable takes effect on the next run; saving a prompt does not schedule anything.

Setup:

| Setting | Meaning |
|---|---|
| `EVENTS_EXECUTOR_TYPE` | Existing Kairon setting. With the default `standalone` executor no task definition is needed. |
| `CRM_LEAD_ANALYSIS_TASK_DEFINITION` | The task definition (Lambda function name or ECS task definition) that the Lambda / ECS executor starts for the `crm_lead_analysis` event, exactly like the other `events.task_definition` entries. **Required for every non-standalone executor;** the readiness check fails without it. The task must run the same Kairon image and execute the event. |
| `python -m kairon crm_lead_analysis schedule` | One-time registration of the five-minute schedule on the event server. **Idempotent:** it updates the existing job (fixed id `crm_lead_analysis`) or creates it, so running it again does not create a second schedule. Options: `--cron`, `--timezone` (default UTC). |
| `python -m kairon crm_lead_analysis run` | Runs one pass now in the current process; safe to overlap with scheduled runs. |
| `python -m kairon crm_lead_analysis check` | Readiness report (see below). |

Lead-analysis tuning, all optional: `CRM_LEAD_LLM_MODEL` (must be enabled on the platform `openrouter` secret),
`CRM_LEAD_LLM_TIMEOUT`, `CRM_LEAD_BATCH_SIZE`, `CRM_LEAD_IDLE_SECONDS`, `CRM_LEAD_LOOKBACK_SECONDS`, `CRM_LEAD_MAX_ATTEMPTS`,
`CRM_LEAD_MAX_TRANSCRIPT_CHARS`. Conversation text is sent to the LLM server after redaction of common secrets, so the LLM URL
should be remote-capable and `https://` (the check warns otherwise).

Troubleshooting:
- A bot's last error is on its analysis state (`last_error`, visible through `GET .../crm/lead-qualification/status`); dead-lettered
  conversations are listed by `.../lead-qualification/failed` and requeued by `.../retry-failed`.
- Nothing runs if the job is not registered: `crm_lead_analysis check` shows `platform_job_registered`.
- Failed invitation emails show their reason in `GET .../crm/status` (`invitation.last_error`).

## E. Staff access and Metering

| Setting | Default | Meaning |
|---|---|---|
| `CRM_STAFF_ALLOWLIST` | unset | Comma-separated emails or `@domain` suffixes. **When set, it gates every CRM route for every caller** (Kairon login or staff token); anyone not listed is refused. When unset, the normal per-bot admin rule applies. |
| `CRM_STAFF_JWT_SECRET` | unset | Same value as Metering's `METERING_JWT_SECRET`. When set, a Metering staff token (HS256, audience `kairon-metering`, `type` claim `metering-staff`) is accepted on `/crm/...` routes as an admin of the requested bot, **and only if the staff email is allow-listed** (an empty allowlist rejects every staff token). Unset disables staff tokens. Use a long random value (the check requires at least 32 characters) and keep it out of logs and source control. Anyone holding this secret can mint such tokens; share it with as few services as possible. |
| `CRM_METERING_URL`, `CRM_METERING_EVENT_SECRET` | unset | Where tenant provisioning results are sent to Metering. Both unset skips the handoff silently; a failed handoff never blocks CRM and can be retried through `POST .../crm/metering-sync`. Use `https://` and a long random event secret. |

All of these secrets must come from your secret store, never from the repository.

## F. Unique tenant site names

A tenant's site name is its identity, so a unique index protects against two bots claiming one name at the same moment. It is not
created automatically (an automatic unique index would break every CRM query on a database that already contains duplicates).

```
python -m kairon crm_lead_analysis ensure-indexes
```

- Checks for duplicate site names first. If any exist it changes nothing, lists them, and exits with status 1; resolve them by
  hand (records are never deleted or rewritten automatically), then run it again.
- Idempotent. Records without a site name are ignored (sparse index).
- `crm_lead_analysis check` reports `site_name_unique` (required) and `site_name_index` (advice).

## G. Go-live checklist

- [ ] `BENCH_TENANT_DOMAIN` is a domain you control; a wildcard DNS record and certificate exist for `*.<domain>`.
- [ ] `BENCH_TENANT_URL_SCHEME=https`; `BENCH_SSO_ALLOW_INSECURE_HTTP` is not set.
- [ ] `BENCH_BASE_URL` points at the Bench frontend reachable from Kairon and the action server.
- [ ] Production uses `BENCH_EXECUTION_MODE=runner` (the Docker socket is not mounted into the API container); the runner is
      deployed, reachable over `https://`, and accepts DNS-style site names.
- [ ] `BENCH_RUNNER_URL` and `BENCH_RUNNER_SECRET` are set from the secret store.
- [ ] `EMAIL_ENABLE=true` with a working Kairon mail setup (administrator and user invitations).
- [ ] `BENCH_SMTP_SERVER` and `BENCH_SMTP_EMAIL_ID` are set if ERPNext-native mail is needed.
- [ ] Platform `openrouter` `LLMSecret` exists and `CRM_LEAD_LLM_MODEL` is enabled on it; the LLM server URL is `https://`.
- [ ] `CRM_LEAD_ANALYSIS_TASK_DEFINITION` is set (Lambda / ECS executors).
- [ ] `python -m kairon crm_lead_analysis ensure-indexes` completed (no duplicates).
- [ ] `python -m kairon crm_lead_analysis schedule` was run once.
- [ ] `python -m kairon crm_lead_analysis check` exits 0 (read every warning, including the optional ones).
- [ ] `CRM_STAFF_ALLOWLIST` is set if only staff may operate CRM; `CRM_STAFF_JWT_SECRET` is set only if Metering staff tokens are used.
- [ ] Logs are watched for `[CRMLeadAnalysis]` (job results), `[LeadAnalysis]` (per-bot failures) and `[BenchRunner]` (runner failures).

## H. Known limitations

- `POST .../crm/onboard` returns `202` and provisions in an in-process background task. If the API worker restarts during a run,
  the run stops; the tenant stays locked until the two-hour stale-lock window passes, after which `/onboard` resumes it safely.
  Poll `GET .../crm/status` for the outcome.
- Catalog modules without an entry in `metadata/provisioning_matrix.yml` (Assets, Buying, Maintenance, Manufacturing, Payroll,
  Projects, Quality, Support) are rejected at validation until an entry is added.
- `BENCH_RECONCILE_INTERVAL` and `BENCH_SMTP_ENABLED` are present in `system.yaml` but do not change behaviour: reconciliation
  runs on the platform job's five-minute schedule.
