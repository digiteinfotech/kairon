---
created: "2026-10-26T12:44:00Z"
last_edited: "2026-10-26T14:00:00Z"
---

# Cavekit: Config and Deploy

## Scope
Configuration of the new server, Mongo data representation, secret handling, dependency hygiene, concurrency posture and the docker-compose swap that makes the port a drop-in replacement for the existing Python action server.

See context/refs/research-brief-java-action-server-port.md for evidence.

## Requirements

### R1: Config mapping
**Description:** Every config key the Python action server reads has an equivalent in the port with the same env var name and default.
**Acceptance Criteria:**
- [ ] [GAP] `DATABASE_URL` sets the Mongo connection; when the URL names no database, `kairon` is used
- [ ] [GAP] `ACTION_SERVER_REQUEST_TIMEOUT` sets the outbound timeout (default 60)
- [ ] [GAP] The pyscript URL, evaluator URL, events server URL, async callback base URL, live agent URL/token/enabled, simple-agent URL, voice-call URL, web-search URL, support mail address, CORS origins, Fernet key (`FERNET_KEY`), JWT secret (`SECRET_KEY`) and algorithm, async-callback AES key and IV (`ASYNC_CALLBACK_AES_KEY`, `ASYNC_CALLBACK_AES_IV`, used by the callback token in cavekit-core-actions.md R7) and unmasked char count are each configurable
- [ ] [GAP] Each of those keys uses the same env var name as the Python `system.yaml` and the same default
- [ ] [GAP] A table mapping every Python key to its port key is documented and has no unmapped Python key used by in-scope actions
**Dependencies:** none

### R2: No shipped secrets
**Description:** Secrets have no defaults.
**Acceptance Criteria:**
- [ ] The packaged config contains no value for the Fernet key, JWT secret, AES key or AES IV
- [ ] [GAP] Startup without the Fernet key fails with an error naming the missing key
- [ ] [GAP] Startup without the JWT secret fails with an error naming the missing key
- [ ] [GAP] Startup without the AES key fails with an error naming the missing key
- [ ] [GAP] Startup without the AES IV fails with an error naming the missing key
- [ ] None of the default secret values in the Python `system.yaml` appear anywhere in the port's repository
**Dependencies:** none

### R3: Mongo representation
**Description:** Documents written by the port are indistinguishable from those Python writes.
**Acceptance Criteria:**
- [ ] [GAP] UUIDs are written as binary subtype 3 (Python legacy) and read without error
- [ ] Dates are written as BSON dates truncated to millisecond precision
- [ ] Collection names match Python defaults: `actions`, `action_server_logs`, `http_action_config`, `key_vault`, `bot_settings`, `slots` and each per-type config collection named in the action kits
- [ ] [UNVERIFIED] A document written by the port is read by the Python server without error
**Dependencies:** none

### R4: Compose swap
**Description:** The port replaces the Python service in docker-compose with no other file changes.
**Acceptance Criteria:**
- [ ] [GAP] Only the `kairon-action-server` service's image, command and environment block change in `docker/docker-compose.yml`; no other service changes
- [ ] The service listens on port 5055
- [ ] [UNVERIFIED] Consumers reaching `http://kairon-action-server:5055/webhook` work unchanged
- [ ] [GAP] The service starts with the existing `DATABASE_URL` plus explicit `FERNET_KEY`, `SECRET_KEY`, `ASYNC_CALLBACK_AES_KEY` and `ASYNC_CALLBACK_AES_IV` entries in its environment block (the Python service inherits these from `system.yaml` defaults, which R2 forbids)
- [ ] [UNVERIFIED] The compose file carries no secret value inline; each secret entry references a host environment variable or an env file (needs human review)
**Dependencies:** R1, R2

### R5: Dependency hygiene
**Description:** The outbound HTTP stack is not affected by GHSA-q6gh-6v2r-hjv3.
**Acceptance Criteria:**
- [ ] [GAP] No dependency version in the build is listed as affected by GHSA-q6gh-6v2r-hjv3
- [ ] [UNVERIFIED] A redirect to another origin does not carry `Authorization`, `Cookie` or `Proxy-Authorization` (behavioural contract in cavekit-outbound-clients.md R3)
**Dependencies:** none

### R6: Blocking execution
**Description:** Blocking work never runs on the request event loop, and the pool fits parallel fan-out.
**Acceptance Criteria:**
- [ ] [GAP] Mongo, SMTP and outbound HTTP calls do not execute on request event-loop threads
- [ ] [UNVERIFIED] `/healthcheck` answers within 1 second while 50 webhook requests are blocked on a slow upstream
- [ ] [UNVERIFIED] Pool sizing supports cavekit-orchestration-actions.md R1 fan-out (needs human review)
**Dependencies:** none

## Out of Scope
- Native image builds
- Kubernetes manifests
- Lambda transport config keys (pyscript, web search trigger_task)
- LLM and vector config keys (prompt_action, database_action deferred); LLM rephrase

## Cross-References
- See also: cavekit-integration-actions.md
- See also: cavekit-webhook-contract.md
- See also: cavekit-dispatch-and-logging.md
- See also: cavekit-templating-and-secrets.md
- See also: cavekit-outbound-clients.md
- See also: cavekit-core-actions.md
- See also: cavekit-orchestration-actions.md
- See also: cavekit-parity-harness.md

## Source Traceability
- R1: system.yaml (incl. :96 action.request_timeout); kairon/shared/utils.py:267-275 (ConfigLoader), 1084-1101 (mongoengine_connection)
- R2: system.yaml (security.fernet_key, security.secret_key, async_callback_action.short_secret)
- R3: kairon/shared/actions/data_objects.py (mongoengine defaults); kairon/shared/utils.py:1084-1101
- R4: docker/docker-compose.yml:40, 77-95
- R5: advisory GHSA-q6gh-6v2r-hjv3
- R6: kairon/actions/definitions/custom_parallel_actions.py:145-171

## Gap Summary
Brownfield verification against the existing port (2026-10-26): 5 met, 14 gaps, 6 unverified by code reading.
Criteria prefixed `[GAP]` are not satisfied by the current code; `[UNVERIFIED]` need runtime, fixture, or human confirmation.

| Req | Gap | Evidence |
|---|---|---|
| R1 | A table mapping every Python key to its port key is documented and has no unmapped Python  | action-server/ (no mapping doc found) — The port repo has no Python-key-to-port-key mapping table; the only mentions are in context/kits and context/refs. |
| R1 | Each of those keys uses the same env var name as the Python `system.yaml` and the same def | action-server/src/main/resources/application.yml:24-47 — All env vars are KAIRON_* or MONGODB_URI, not the system.yaml names (e.g. FERNET_KEY, SECRET_KEY, PYSCRIPT_EVALUATOR_ENDPOINT, EVENT_SERVER_ENDPOINT, SECRET_UNMASKED_CHAR_COUNT). |
| R1 | The pyscript URL, evaluator URL, events server URL, async callback base URL, live agent UR | action-server/src/main/resources/application.yml:9-11,22-44; ActionSettings.java:10-32 — Most URLs and keys are settable, but there is no AES key, AES IV or support mail setting, and CORS origins are hardcoded to *. |
| R1 | `ACTION_SERVER_REQUEST_TIMEOUT` sets the outbound timeout (default 60) | action-server/src/main/resources/application.yml:26; ActionSettings.java:12 — The timeout env var is KAIRON_ACTION_TIMEOUT with default 5, not ACTION_SERVER_REQUEST_TIMEOUT with default 60. |
| R1 | `DATABASE_URL` sets the Mongo connection; when the URL names no database, `kairon` is used | action-server/src/main/resources/application.yml:47; catalog/MongoFactory.java:107-114 — The Mongo URI is read from MONGODB_URI, not DATABASE_URL, and falls back to database conversations instead of kairon. |
| R2 | Startup without the AES IV fails with an error naming the missing key | action-server/src/main/java/com/kairon/action/ActionSettings.java:10-32 — There is no AES IV setting at all, so startup cannot validate it. |
| R2 | Startup without the AES key fails with an error naming the missing key | action-server/src/main/java/com/kairon/action/ActionSettings.java:10-32 — There is no AES key setting at all, so startup cannot validate it. |
| R2 | Startup without the Fernet key fails with an error naming the missing key | action-server/src/main/java/com/kairon/action/ActionSettings.java:28; support/Tokens.java:fernetKey() — There is no startup validation; a missing Fernet key only fails at first use with an ActionFailure. |
| R2 | Startup without the JWT secret fails with an error naming the missing key | action-server/src/main/java/com/kairon/action/ActionSettings.java:29; Application.java:8 — There is no startup validation for jwt-secret; it defaults to an empty string. |
| R3 | UUIDs are written as binary subtype 3 (Python legacy) and read without error | action-server/src/main/java/com/kairon/action/catalog/MongoFactory.java:108 — MongoClients.create(uri) sets no uuidRepresentation and the default URI has none, so the driver default (UNSPECIFIED) applies and subtype-3 UUIDs are neither written nor decoded. |
| R4 | Only the `kairon-action-server` service's image, command and environment block change in ` | docker/docker-compose.yml:77-97 — Compose is unchanged (no git diff); kairon-action-server still runs image kairon with the Python uvicorn command. |
| R4 | The service starts with the existing `DATABASE_URL` plus explicit `FERNET_KEY`, `SECRET_KE | docker/docker-compose.yml:96-97 — The environment block holds only DATABASE_URL; FERNET_KEY, SECRET_KEY, ASYNC_CALLBACK_AES_KEY and ASYNC_CALLBACK_AES_IV are missing, and the port would read MONGODB_URI anyway. |
| R5 | No dependency version in the build is listed as affected by GHSA-q6gh-6v2r-hjv3 | action-server/build.gradle:38 — The Micronaut version is 4.10.22, which is below the fixed 4.10.24 and therefore in the affected range. |
| R6 | Mongo, SMTP and outbound HTTP calls do not execute on request event-loop threads | action-server/src/main/java/com/kairon/action/server/WebhookController.java:21-56; resources/application.yml:1-17 — There is no @ExecuteOn(TaskExecutors.BLOCKING) and no micronaut.server.thread-selection, so the blocking webhook (Mongo, HTTP, mail) runs on Netty event-loop threads. |

## Changelog
- 2026-10-26: Initial draft from approved design.
- 2026-10-26: Review iteration 1 fixes (dependency cycles, compose secrets, scheduling endpoint contract, failure-mail paths, missing sender_id, dependency graph).
- 2026-10-26: Review iteration 2 fixes (scheduling rejection semantics, callback token derivation, AES IV, cross-references, tiering).
- 2026-10-26: Brownfield gap pass against existing port: 14 [GAP], 6 [UNVERIFIED] markers added.
