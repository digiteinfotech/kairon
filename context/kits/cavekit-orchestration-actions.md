---
created: "2026-10-26T12:44:00Z"
last_edited: "2026-10-30"
---

# Cavekit: Orchestration Actions

## Scope
Actions that coordinate other work: parallel_action (fans out to the server's own webhook) and schedule_action (submits a job to the events server). Each must match the existing Python action server on webhook response, `action_server_logs` records and outbound side effects, except that schedule_action submits its job through the new events-server endpoint (cavekit-events-schedule-api.md) instead of writing the job store directly.

See context/refs/research-brief-java-action-server-port.md for evidence.

## Requirements

### R1: parallel_action
**Description:** Runs several actions concurrently through the server's own webhook and merges their slots.
**Acceptance Criteria:**
- [ ] Config is read from `parallel_action_config` by `bot`, `name`, `status: true`
- [x] A pre-record is saved to `action_server_logs` before any child request holding only `request_id`, `timestamp` (creation time), `status: "Success"` and the default `trigger_info`; its `_id` is the `trigger_id`, and the later fill keeps that `timestamp` (verified: ParallelActionTest#childrenPostToOwnWebhookAndSlotsMergeInChildOrder)
- [x] One POST per configured child action goes to the server's own webhook URL (default `http://localhost:5055/webhook`) (verified: ParallelActionTest#childrenPostToOwnWebhookAndSlotsMergeInChildOrder)
- [ ] Each child body equals the original request with `next_action` = the child name and `trigger_info` = `{"trigger_name": <parent name>, "trigger_type": "parallel_action", "trigger_id": <parent log id>}`
- [x] Each child request carries the parent's request id header (verified: ParallelActionTest#childrenPostToOwnWebhookAndSlotsMergeInChildOrder)
- [ ] Child utterances are discarded; only child events with `event` = `slot` are merged, last write wins in child order
- [ ] A failing or erroring child does not fail the parent; the parent log `status` is `Success`
- [ ] When `dispatch_response_text` is true, `response_text` is uttered and `kairon_action_response` is set; otherwise neither
- [ ] The pre-created record is later updated with `type: "parallel_action"`, `action`, `sender`, `bot_response`, `exception`, `status`, `user_msg`, `trigger_info`, `request_id`
- [ ] Every child log has `trigger_info.trigger_id` equal to the parent record id
- [ ] [UNVERIFIED] No dedicated failure utterance exists; on exception responses and log match the recorded Python fixture (needs human review)
- [ ] [UNVERIFIED] A fan-out of 10 children under 10 concurrent parent requests completes without deadlock or request timeout
- [ ] [UNVERIFIED] Executor pool sizing for fan-out is agreed (needs human review)
**Dependencies:** cavekit-webhook-contract.md R1, cavekit-dispatch-and-logging.md R4, cavekit-outbound-clients.md R1, cavekit-config-and-deploy.md R6

### R2: schedule_action
**Description:** Schedules a pyscript or flow for later execution via the events server.
**Acceptance Criteria:**
- [ ] Config is read from `schedule_action` by `bot`, `name`, `status: true`; callback config from `callback_config`
- [ ] `schedule_time` resolves via parameter resolution; `timezone` and `params_list` resolve as configured
- [x] The port generates the job id as a 32-character lowercase hex UUIDv7 and submits exactly one `POST {events server URL}/api/events/schedule/action` with the body defined in cavekit-events-schedule-api.md R1 (`job_id`, `run_at`, `timezone`, `schedule_action_type`, `schedule_action`, `bot`, `user`, `data`) (verified: ScheduleActionTest#pyscriptPostsTheReferenceRequestThenDispatchesOnce)
- [x] The submission is treated as failed when the HTTP status is not 200 OR the response envelope's `success` is not `true` (the events server returns rejections as HTTP 200 with `success: false`); a failed submission fails the action (Failed log, failure utterance) and no dispatch GET is sent (verified: ScheduleActionTest#envelopeSuccessFalseIsAFailedSubmissionWithoutDispatch, ScheduleActionTest#non200StatusIsAFailedSubmissionWithoutDispatch)
- [x] The port writes no document to the events job-store collection (verified: ScheduleActionTest#pyscriptPostsTheReferenceRequestThenDispatchesOnce)
- [ ] After submission, one GET goes to `{events server URL}/api/events/dispatch/{job id}`
- [ ] When `dispatch_bot_response` is true, `response_text` is uttered as text
- [ ] Returned slots are `{}`
- [ ] Failure utterance: `Sorry, I am unable to process your request at the moment.`
- [x] Log: `type: "schedule_action"`, `schedule_action`, `schedule_time`, `timezone`, `execution_info`, `data`, `bot_response`, `messages`, `exception` (verified: ScheduleActionTest#pyscriptPostsTheReferenceRequestThenDispatchesOnce)
**Dependencies:** cavekit-events-schedule-api.md R1, cavekit-events-schedule-api.md R3, cavekit-templating-and-secrets.md R3, cavekit-outbound-clients.md R2, cavekit-config-and-deploy.md R1

## Out of Scope
- Writing the scheduler job store from the port (pickled jobs are never produced)
- prompt_action nesting of actions and database_action (cavekit-prompt-database-actions.md R4)
- Lambda transports, LLM rephrase in kairon_bot_response, native image

## Cross-References
- See also: cavekit-core-actions.md
- See also: cavekit-webhook-contract.md
- See also: cavekit-dispatch-and-logging.md
- See also: cavekit-templating-and-secrets.md
- See also: cavekit-outbound-clients.md
- See also: cavekit-events-schedule-api.md
- See also: cavekit-parity-harness.md
- See also: cavekit-config-and-deploy.md

## Source Traceability
- R1: kairon/actions/definitions/custom_parallel_actions.py:76-78, 145-193; kairon/shared/actions/data_objects.py:1134
- R2: kairon/actions/definitions/schedule.py:192-236 (job build + direct insert being replaced), 212-216 (dispatch GET); kairon/shared/actions/data_objects.py:1105

## Gap Summary
Brownfield verification against the existing port (2026-10-26): 13 met, 7 gaps, 3 unverified by code reading.
Criteria prefixed `[GAP]` are not satisfied by the current code; `[UNVERIFIED]` need runtime, fixture, or human confirmation.

| Req | Gap | Evidence |
|---|---|---|
| R1 | A pre-record is saved to `action_server_logs` before any child request holding only `reque | action-server/src/main/java/com/kairon/action/actions/ParallelAction.java:66,109-113 — Stub holds request_id and timestamp but not the default status and trigger_info Python's model adds. |
| R1 | Each child request carries the parent's request id header | action-server/src/main/java/com/kairon/action/actions/ParallelAction.java:116,136 — There is no HTTP request, so no header is sent; the parent request id is only carried in-process through the RequestIds thread-local. |
| R1 | One POST per configured child action goes to the server's own webhook URL (default `http:/ | action-server/src/main/java/com/kairon/action/actions/ParallelAction.java:26-28,145 — Children run in-process through ActionProcessor.handle on virtual threads, so no HTTP POST goes to the own webhook URL and no webhook URL is configurable. |
| R2 | Log: `type: "schedule_action"`, `schedule_action`, `schedule_time`, `timezone`, `execution | action-server/src/main/java/com/kairon/action/actions/ScheduleAction.java:119-125 — The log has type, schedule_action, schedule_time, timezone, execution_info, data, bot_response and exception, but no messages field. |
| R2 | The port generates the job id as a 32-character lowercase hex UUIDv7 and submits exactly o | action-server/src/main/java/com/kairon/action/actions/ScheduleAction.java:73,96-107 — It generates a uuid7 hex id but sends no POST to /api/events/schedule/action; it builds a job document and inserts it into scheduler_jobs instead. |
| R2 | The port writes no document to the events job-store collection | action-server/src/main/java/com/kairon/action/actions/ScheduleAction.java:107 — It writes a JSON job document directly to the scheduler_jobs collection (not pickled), which the kit forbids. |
| R2 | The submission is treated as failed when the HTTP status is not 200 OR the response envelo | action-server/src/main/java/com/kairon/action/actions/ScheduleAction.java:138-141 — There is no submission step; only the dispatch GET is checked, and only for status != 200, with no check of the success field in the envelope. |

## Changelog
- 2026-10-26: Initial draft from approved design.
- 2026-10-26: Review iteration 1 fixes (dependency cycles, compose secrets, scheduling endpoint contract, failure-mail paths, missing sender_id, dependency graph).
- 2026-10-26: Review iteration 2 fixes (scheduling rejection semantics, callback token derivation, AES IV, cross-references, tiering).
- 2026-10-26: Brownfield gap pass against existing port: 7 [GAP], 3 [UNVERIFIED] markers added.
- 2026-10-26: Build wave 2: R1 c2 corrected to Python (pre-record = request_id + model defaults, custom_parallel_actions.py:76-77).
- 2026-10-30: [GAP] markers re-verified against tests
- 2026-10-30: Stale deferred prompt/database Out of Scope lines now point to cavekit-prompt-database-actions.md.
