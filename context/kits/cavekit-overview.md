---
created: "2026-10-26T12:44:00Z"
last_edited: "2026-10-26T14:00:00Z"
---

# Cavekit Overview

## Project
Kairon Action Server Port: a drop-in replacement for the existing Python Rasa-style action server (`POST /webhook` on port 5055). Parity bar: same webhook responses, same `action_server_logs` records and same outbound side effects (HTTP, SMTP, callbacks, Mongo writes) for 22 action types. prompt_action and database_action are deferred; Lambda transports, LLM rephrase and native image are out of scope. Evidence: context/refs/research-brief-java-action-server-port.md; approved design: context/refs/approved-design-java-action-server-port.md.

Coverage: 10 domain kits, 68 requirements, 401 acceptance criteria.

## Domain Index
| Domain | Cavekit File | Requirements | Status | Description |
|---|---|---|---|---|
| Webhook Contract | cavekit-webhook-contract.md | 6 | DRAFT | Request parsing, response envelope, error contract, headers, health endpoints |
| Dispatch and Logging | cavekit-dispatch-and-logging.md | 7 | DRAFT | Type resolution, catch-all failure, `action_server_logs` contract, failure mail |
| Templating and Secrets | cavekit-templating-and-secrets.md | 8 | DRAFT | Placeholder/response templates, parameter resolution, Python repr/json, Fernet, HS256 JWT |
| Outbound Clients | cavekit-outbound-clients.md | 8 | DRAFT | Swallowing/raising HTTP, redirects, wire format, pyscript/evaluator, SMTP, media multipart |
| Core Actions | cavekit-core-actions.md | 7 | DRAFT | slot_set, form_validation, two_stage_fallback, bot_response, voice_disconnect, store_page, callback |
| Integration Actions | cavekit-integration-actions.md | 13 | DRAFT | http, email, google, web_search, jira, zendesk, pipedrive, hubspot, razorpay, live_agent, agent, voice_call, pyscript |
| Orchestration Actions | cavekit-orchestration-actions.md | 2 | DRAFT | parallel_action loopback fan-out, schedule_action via events server |
| Events Schedule API | cavekit-events-schedule-api.md | 5 | DRAFT | New JSON scheduling endpoint on the Python events server (single job writer) |
| Parity Harness | cavekit-parity-harness.md | 6 | DRAFT | Python-side fixture recorder, port-side replay, coverage report, CI gate |
| Config and Deploy | cavekit-config-and-deploy.md | 6 | DRAFT | Config mapping, no shipped secrets, Mongo representation, compose swap, CVE hygiene, blocking execution |

## Cross-Reference Map
| Domain A | Interacts With | Interaction Type |
|---|---|---|
| webhook-contract | dispatch-and-logging | Hands parsed request to dispatch; renders its result/empty envelope |
| webhook-contract | core / integration / orchestration actions | Renders action slots and utterances into the envelope |
| webhook-contract | config-and-deploy | Reads CORS origins; body-size ceiling |
| dispatch-and-logging | templating-and-secrets | Uses Python repr for log fields |
| dispatch-and-logging | outbound-clients | Sends failure mail via SMTP |
| dispatch-and-logging | core / integration / orchestration actions | Resolves and runs actions; defines base and per-type log fields |
| templating-and-secrets | outbound-clients | Supplies evaluation context and resolved params |
| templating-and-secrets | config-and-deploy | Reads Fernet key, JWT secret, unmasked char count |
| outbound-clients | core / integration / orchestration actions | Provides HTTP, evaluator, pyscript, SMTP primitives |
| outbound-clients | config-and-deploy | Timeout and service URLs; CVE-free redirect handling |
| orchestration-actions | events-schedule-api | schedule_action submits jobs to the new endpoint |
| orchestration-actions | webhook-contract | parallel_action POSTs to the server's own `/webhook` |
| parity-harness | webhook-contract, dispatch-and-logging, all action kits | Replays recorded fixtures against responses, outbound calls, Mongo writes |
| parity-harness | config-and-deploy | Runs replay against in-memory and real MongoDB backends |
| core-actions | config-and-deploy | Collection names, callback base URL |

## Dependency Graph
Derived from requirement-level dependencies in each kit (no cycles):

1. **Tier 0, no dependencies:** cavekit-config-and-deploy.md, cavekit-events-schedule-api.md
2. **Tier 1:** cavekit-webhook-contract.md (config-and-deploy R1), cavekit-templating-and-secrets.md (config-and-deploy R1, R2)
3. **Tier 2:** cavekit-outbound-clients.md (templating-and-secrets R3, R4; config-and-deploy R1, R5)
4. **Tier 3:** cavekit-dispatch-and-logging.md (webhook-contract R1, R3, R4; templating-and-secrets R7; outbound-clients R7; config-and-deploy R1, R3)
5. **Tier 4, parallel:** cavekit-orchestration-actions.md (webhook-contract R1; dispatch-and-logging R4; templating-and-secrets R3; outbound-clients R1, R2; config-and-deploy R6; events-schedule-api R1, R3), cavekit-core-actions.md (dispatch-and-logging R1, R3, R4; templating-and-secrets R1, R5-R7; outbound-clients R6; config-and-deploy R1, R2, R3), cavekit-integration-actions.md (dispatch-and-logging R5; templating-and-secrets R1-R4, R6; outbound-clients R1, R2, R5-R8; config-and-deploy R1, R3), cavekit-parity-harness.md (webhook-contract R2; dispatch-and-logging R4; config-and-deploy R3)

Replay in cavekit-parity-harness.md R3-R6 exercises the outputs of tiers 1-4 but can be built as soon as tier 3 lands.

## Gap Summary

Brownfield verification of every acceptance criterion against the existing port (`action-server/`) and the Python events server, 2026-10-26. `[GAP]` = not satisfied by current code; `[UNVERIFIED]` = needs runtime, fixture or human confirmation. Per-kit tables with evidence are in each kit's Gap Summary section.

| Kit | Met | Gap | Unverified | Total |
|---|---|---|---|---|
| cavekit-config-and-deploy.md | 5 | 14 | 6 | 25 |
| cavekit-core-actions.md | 50 | 7 | 2 | 59 |
| cavekit-dispatch-and-logging.md | 24 | 20 | 0 | 44 |
| cavekit-events-schedule-api.md | 1 | 16 | 1 | 18 |
| cavekit-integration-actions.md | 73 | 10 | 2 | 85 |
| cavekit-orchestration-actions.md | 13 | 7 | 3 | 23 |
| cavekit-outbound-clients.md | 24 | 12 | 3 | 39 |
| cavekit-parity-harness.md | 0 | 26 | 1 | 27 |
| cavekit-templating-and-secrets.md | 25 | 10 | 7 | 42 |
| cavekit-webhook-contract.md | 20 | 16 | 3 | 39 |
| **Total** | **235** | **138** | **28** | **401** |

**Where the gaps concentrate:**
- Entire capabilities missing: SMTP (email action and failure mail), the fixture recorder and replay harness, the events-server scheduling endpoint, startup secret validation, blocking-executor configuration.
- Contract deviations: 422 status codes where Python returns 200 or 500, missing request-id generation and secure headers, catch-all response leaking prior utterances, missing `trigger_info` on catch-all logs.
- Log-shape deviations: no `events[]`/`time_elapsed` on http_action, Java `Map.toString` instead of Python repr for `bot_response`, missing `messages[]` on several types, field order.
- Config drift: `MONGODB_URI`/`KAIRON_*` names instead of `DATABASE_URL`/`ACTION_SERVER_REQUEST_TIMEOUT`, no `uuidRepresentation`, HTTP client version inside the GHSA-q6gh-6v2r-hjv3 range.
- Behaviour deviations: schedule_action writes the job store directly, parallel_action runs children in-process, callback short-token path unimplemented, form encoding and redirect limits differ, media multipart differs.
- Over-built relative to scope: prompt_action and database_action are registered, and LLM rephrase is implemented.

**Kit corrections made during the pass** (code already matched Python, kit was wrong): form_validation slot-value rule and no-match status, bot_response exception path, callback config lookup by `name` and URL separator, http expression mode is a local template fill, google/web_search dispatch flag, razorpay `username` key and integer truncation, agent_action response derivation, store-page and agent JWT structure (encrypted `sub`, `version` 2.0, no `exp` on integration tokens).

## Changelog
- 2026-10-26: Initial draft from approved design.
- 2026-10-26: Review iteration 1 fixes (dependency cycles, compose secrets, scheduling endpoint contract, failure-mail paths, missing sender_id, dependency graph).
- 2026-10-26: Review iteration 2 fixes (scheduling rejection semantics, callback token derivation, AES IV, cross-references, tiering).
- 2026-10-26: Brownfield gap pass: 138 [GAP] and 28 [UNVERIFIED] markers across kits; 14 kit criteria corrected where the code already matched Python.
