# Java Action Server Gap Execution Plan

Generated: 2026-10-28 · Rechecked: 2026-10-30
Sources: `context/impl/gap-python-vs-java.md` (Python-vs-Java gaps), `GAP_VALIDATION_REPORT.md`, 3 read-only recheck passes.

## Recheck result (2026-10-30)

- Full `./gradlew test`: **BUILD SUCCESSFUL, 0 failures** (includes uncommitted PromptAction/DatabaseAction edits).
- The 140 `[GAP]` items in `GAP_CHECKLIST.md` are **stale tracking**: kit criteria are covered by passing suites. Action: clear the `[GAP]` markers in the kits (task G0).
- The real backlog is the Python-vs-Java list below. Status was agent-verified by reading code (file:line); **nothing was run**, so confirm each item with a failing test before fixing.
- Java paths are under `action-server/src/main/java/com/kairon/action/`.

## Closed since 2026-10-27 (drop from backlog)

| Gap | Evidence |
|---|---|
| #5 F-003 non-2xx handling | `support/HttpCaller.java:139-167`; `HttpCallerExchangeTest`, `ActionLogEventsTest` |
| #3 action registration (prompt/database) | `actions/ActionFactory.java:16-22` (uncommitted) |
| #19 parallel recursion guard | Python has none either |
| `model.agent.url` | Python agent_action uses `simple_agent.url`; Java `SIMPLE_AGENT_URL` is correct |
| #17 keyless google_search, #18 rephrase | Deliberate fail-closed / non-port, tested in `ActionGapParityTest` |
| F-005, F-008 | Resolved (T-049, failure-mail shape); `impl-review-findings.md` still lists them |

## P1 — parity-visible, fix first

A1–A4 done 2026-10-30 (uncommitted, tests added). A1 write side only: not yet loaded through mongoengine. Kit `cavekit-dispatch-and-logging.md` R3 log-intent line stays `[GAP]`: it says the catch-all does not skip `nlu_fallback`, but Python processor.py:30,44 does (Java matches Python); fix the kit text.

| Pkt | Gap | Java | Work |
|---|---|---|---|
| ~~A1~~ DONE | #1 callback_data `timestamp` is BSON Date; missing `state`, `execution_mode` (Python `FloatField`) | `CallbackAction.java:~79-90`, `catalog/MongoActionCatalog.java:81-82` | Write float epoch, `state:0`, `execution_mode` async value. Verify by loading doc via mongoengine (.venv310). |
| ~~A2~~ DONE | #2 `${a.b}` missing key yields "None" | `support/ActionSupport.java:~876-891` | `walk()` throws ActionFailure on absent key / bad index. |
| ~~A3~~ DONE | #4 intent() skip `nlu_fallback` (context intent only; log intent stays ranking[0]) | `runtime/TrackerState.java:78-87` | Add skip variant; null on empty ranking. |
| ~~A4~~ DONE | #5 F-001 mask from the right | `support/ActionSupport.java:333-339` | Mask from right. |
| A5 | #3 prompt_action residue: `crud` and `action` prompt sources, CognitionSchema lookup, openrouter/embedding size | `actions/PromptAction.java` | Port or record as deliberate divergence (product call). |
| A6 | #3 database_action: vector/LLM delegated to service; URLs default empty | `actions/DatabaseAction.java` | Document required config in `CONFIG.md`; fail-fast at startup if action used. |

## prompt_action / database_action parity (2026-10-30)

Read-only comparison of `kairon/actions/definitions/{prompt,database}.py` vs Java `PromptAction`/`DatabaseAction` (uncommitted). Nothing was run beyond the Java suite.

**Fixed (uncommitted, tests in `ActionGapParityTest`):** database `db_type` != qdrant fails with "Database not yet implemented!"; schema lookup now precedes payload build (failure log has empty messages/payload as in Python); database payload/response logged with Python repr; prompt slot source renders null as `None`.

**Open:**
| Sev | Gap |
|---|---|
| P1 | prompt `crud` and `action` prompt sources not ported (fall through as static text) — A5 |
| P1 | LLM/vector request+response contract with remote service undefined (only test stubs `/llm`, `/vector`); `VECTOR_DB` is Qdrant URL in Python but an unspecified adapter in Java; `CONFIG.md` still says "deferred" |
| P1 | model-exists check, CognitionSchema/embedding size, openrouter secret swap exist only if the remote service does them |
| P2 | prompt dispatches buttons from remote `recommendations`; Python never does (test encodes this) |
| P2 | database `payload_search` edge cases: scalar JSON rejected, null concat gives "x null" (Python TypeError) |
| P3 | database log key order (Python: config, payload, response, user_msg; Java user_msg first); missing-schema error text; missing `bot_settings` treated as disabled (Python default `enable_faq` unverified) |

**Decision needed:** call real services (Qdrant + LLM server) like Python, or keep the adapter and write its contract spec. This sets the scope of every P1 above.

## P2 — contract and behavior

| Pkt | Gap | Java | Work |
|---|---|---|---|
| B1 | #8 404/405 → 200 `{success:false,error_code}` | `server/WebhookController.java` | Global `@Error` handlers. |
| B2 | #9 catch-all Mongo/JWT/AppException → 200 `error_code:422` (Java: 500 text/plain) | `WebhookController.java:104-108`, `ActionProcessor.java:84-100` | Map exceptions. |
| B3 | #10 dispatch uses `String.valueOf`; JSON list/scalar sent as text | `ActionSupport.java:~653-665` | `PyRepr.str`; send list/scalar as custom payload. |
| B4 | #6 schedule `runAt` dateutil formats | `actions/ScheduleAction.java:166-190` | Add formats or record divergence. |
| B5 | #11 form_validation "Expression evaluation log" message | `actions/FormValidationAction.java:56-59` | Return log from `evaluateScript`; add message before result. |
| B6 | #12 two_stage_fallback takes first, not newest example | `TwoStageFallbackAction.java:~106-117`, `MongoActionCatalog.java:54` | Sort `-timestamp`. |
| B7 | #13 razorpay missing `short_url`/non-dict stays Success; `api_response` null | `actions/RazorpayAction.java:73,89` | Fail+mail; log `"None"`. |
| B8 | #14 hubspot/agent api_response `String.valueOf`, `""` not None | `HubspotAction.java:67`, `AgentAction.java:81` | `PyRepr.str` + falsy→null. |
| B9 | #15 jira: GET project/issuetype ids | `actions/JiraAction.java:44-55` | Add lookups, send ids. |
| B10 | #16 pipedrive domain rewrite | `actions/PipedriveAction.java:97-112` | Use raw domain + `v1/`. |
| B11 | #19 parallel child budget 60s vs 300s | `ParallelAction.java:~165` | 300s deadline for child call. |
| B12 | #7 pyscript/web_search lambda path | `ActionSupport.java:~452-466`, `WebSearchAction.java:~72` | **Kit-excluded** — product decision. |
| B13 | #12/#20 keys: `voice.exotel.subdomain`, `events.scheduler.min_trigger_interval`; others (`app.server_url`, `storage.assets.*`, `notifications.*`, `lock_store.url`, `model.retention`, `apm.enable`) | `VoiceCallAction.java:29`, `ScheduleAction` | Add only the first two; rest only if a ported feature needs them. |

## P3 — logged text / small deltas (batch into one PR per file group)

- **Use `PyRepr.str`:** `SlotSetAction.java:40` (True/None), `WebSearchAction.java:83`, `PipedriveAction.java:92` (also match `utils.py:1020-1070`), `AgentAction.java:67`, `FormValidationAction.java:59` (`True`), `RazorpayAction.java:51,76` ("Got None.").
- **HttpAction** (`:88-115`): fail on non-dict `dynamic_params`; log None for falsy `bot_response`; falsy `media_ids` handling.
- **EmailAction** `:58-59`: check `to_email` before `from_email`.
- **LiveAgentAction** `:57`: quote key like KeyError text.
- **VoiceCallAction** `:82-90`: add `errors: []` to ChannelLogs.
- **GoogleSearch** (`ActionSupport.java:729`, `GoogleSearchAction.java:113-115`): fail on missing title/snippet/link.
- **Pyscript:** build context before setting `dispatch` (`PyscriptAction.java:50-51`); no-timeout (`runPyscript`); fail on non-dict body (`ActionSupport.java:~463`); strip `_id` from logged config (`:73`).
- **Callback:** default `expire_in`→0, `shorten_token`→false (`ActionSupport.java:829`); null `dynamic_url_slot_name` (`CallbackAction.java:~84`) — emit or record divergence.
- **Shared:** `attach_response` must throw on missing `data` (`ActionSupport.java:~864-866`).
- **Multiple matches:** raise multi-match error (two_stage, form_validation) — form_validation site not rechecked.
- **Zendesk** `tags:null` (`ZendeskAction.java:48`): confirm against Python first.
- **Schedule** error text prefix / unknown `schedule_action_type` exception: compare with `schedule.py:117-133,219`; unverified.
- **Server infra:** per-request log line + request-id MDC; startup Mongo ping + `load_system_properties`; Dockerfile `HEALTHCHECK /healthcheck`; deflate/br no-compress test (unverified); OTel/APM (out of scope unless requested).
- **F-002 media source:** diff `ActionSupport.java:776-812` against `utils.py:185-231` (not compared).

## Housekeeping

- **G0:** clear stale `[GAP]` markers in `context/kits/cavekit-*.md`; refresh `GAP_CHECKLIST.md`; remove F-005/F-008 from `impl-review-findings.md`.
- No test exists for #13–#16; `ActionGapParityTest` covers only prompt/database, bot_response, two_stage, google, voice. Add a failing test per packet before fixing.

## Rollout

1. G0 + A1–A4 (data-integrity and parity-visible).
2. B1–B3 (server contract), then B5–B11 per-action, one PR per packet with tests.
3. P3 batches.
4. Product decisions needed: A5, B4, B12, kit-excluded items (lambda, keyless google, rephrase, OTel).
