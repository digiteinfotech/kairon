---
created: "2026-10-26T12:44:00Z"
last_edited: "2026-10-26T14:00:00Z"
---

# Cavekit: Parity Harness

## Scope
Proving the port matches the existing Python action server. A recorder on the Python test-suite side captures golden fixtures from the existing 434 action-server test nodes without editing them. A replay capability on the port side runs every fixture against the new server and checks the response, outbound calls and Mongo writes. Also covers coverage reporting and the CI regression gate.

See context/refs/research-brief-java-action-server-port.md for evidence.

## Requirements

### R1: Fixture recorder (Python side)
**Description:** Running the existing Python action-server tests produces one JSON fixture per passing test node, with no edits to existing test files.
**Acceptance Criteria:**
- [ ] [GAP] Enabling the recorder changes no existing test file (diff of test files is empty)
- [ ] [GAP] Each passing test node produces exactly one fixture file named from its node id
- [ ] [GAP] Failing test nodes produce no fixture
- [ ] [GAP] Each fixture contains: Mongo seed documents, the inbound webhook request, every mocked upstream request with its canned response, the webhook response, and the Mongo documents written during the test
- [ ] [GAP] Timestamps, ObjectIds, UUIDs and JWTs are replaced by documented placeholders
- [ ] [GAP] Recording the same suite twice yields byte-identical fixtures
**Dependencies:** none

### R2: Fixture format
**Description:** Fixtures follow a documented, versioned schema.
**Acceptance Criteria:**
- [ ] [GAP] Every fixture carries a schema version field
- [ ] [GAP] A schema document describes every fixture field and placeholder
- [ ] [GAP] BSON types are encoded as canonical extended JSON
- [ ] [GAP] Every recorded fixture validates against the schema
**Dependencies:** R1

### R3: Replay (port side)
**Description:** Each fixture runs as an independently reported test case against the new server.
**Acceptance Criteria:**
- [ ] [GAP] Each fixture produces exactly one reported pass/fail result named by its node id
- [ ] [GAP] Replay seeds the action catalog from the fixture's Mongo seed documents
- [ ] [GAP] Replay serves each recorded upstream response for its recorded request
- [ ] [GAP] Replay POSTs the recorded request to `/webhook`
- [ ] [GAP] The response must equal the recorded response, ignoring placeholder-normalized fields
- [ ] [GAP] Every recorded outbound call must be made with the recorded method, URL, headers of interest and body
- [ ] [GAP] No outbound call beyond the recorded ones is made
- [ ] [GAP] Written `action_server_logs` and other written documents must equal the recorded ones, ignoring `_id` and timestamps
**Dependencies:** R2, cavekit-webhook-contract.md R2, cavekit-dispatch-and-logging.md R4

### R4: Two storage backends
**Description:** The same replay runs against an in-memory catalog and a real MongoDB instance.
**Acceptance Criteria:**
- [ ] [GAP] The full fixture set runs against the in-memory catalog
- [ ] [GAP] The full fixture set runs against a real MongoDB instance
- [ ] [GAP] A fixture's result is the same on both backends
**Dependencies:** R3, cavekit-config-and-deploy.md R3

### R5: Coverage report
**Description:** Parity progress is reported against the 434-node list.
**Acceptance Criteria:**
- [ ] [GAP] The report states the percentage of the 434 nodes with a passing replay
- [ ] [GAP] The report breaks the percentage down by action type
- [ ] [GAP] The report lists every untranslatable node (one that patches Python internals) with a reason
- [ ] [UNVERIFIED] Triage of untranslatable nodes is agreed (needs human review)
**Dependencies:** R3

### R6: Regression gate
**Description:** CI blocks regressions.
**Acceptance Criteria:**
- [ ] [GAP] CI fails when any fixture that passed on the base branch fails on the change
- [ ] [GAP] CI passes when previously passing fixtures still pass and new ones fail
**Dependencies:** R3, R5

## Out of Scope
- Shadow traffic or live request mirroring
- Recording real (non-mocked) upstream traffic
- Fixtures for prompt_action and database_action (deferred)
- Lambda transports, LLM rephrase, native image
- Parity of the events-server endpoint (cavekit-events-schedule-api.md has its own tests)

## Cross-References
- See also: cavekit-events-schedule-api.md
- See also: cavekit-webhook-contract.md
- See also: cavekit-dispatch-and-logging.md
- See also: cavekit-core-actions.md
- See also: cavekit-integration-actions.md
- See also: cavekit-orchestration-actions.md
- See also: cavekit-config-and-deploy.md

## Source Traceability
- R1: tests/integration_test/action_service_test.py (real Mongo, `responses`/`aioresponses` mocks); tests/unit_test/action/{action_test,test_agent_action,test_store_page_action,test_voice_call_action,kremote_action_test}.py; recorder installed as a pytest conftest.py autouse hook
- R2: bson.json_util CANONICAL_JSON_OPTIONS
- R3-R4: action-server/src/test/resources/python-action-nodes.txt (434 pytest node ids)
- R5: action-server/src/test/resources/python-action-nodes.txt
- R6: CI pipeline configuration

## Gap Summary
Brownfield verification against the existing port (2026-10-26): 0 met, 26 gaps, 1 unverified by code reading.
Criteria prefixed `[GAP]` are not satisfied by the current code; `[UNVERIFIED]` need runtime, fixture, or human confirmation.

| Req | Gap | Evidence |
|---|---|---|
| R1 | Each fixture contains: Mongo seed documents, the inbound webhook request, every mocked ups | tests/conftest.py:1-14 — No fixture capture of seeds, requests, mocked upstream calls, responses or written docs. |
| R1 | Each passing test node produces exactly one fixture file named from its node id | tests/conftest.py:1-14 — No fixture files are produced by any hook. |
| R1 | Enabling the recorder changes no existing test file (diff of test files is empty) | tests/conftest.py:1-14 — No recorder exists; conftest only has sessionfinish actor cleanup and a LOG_LEVEL fixture (the non-edit property is untested because nothing is enabled). |
| R1 | Failing test nodes produce no fixture | tests/conftest.py:1-14 — No recorder, so no pass/fail-conditional fixture writing. |
| R1 | Recording the same suite twice yields byte-identical fixtures | tests/conftest.py:1-14 — No recorder, so determinism cannot hold. |
| R1 | Timestamps, ObjectIds, UUIDs and JWTs are replaced by documented placeholders | tests/conftest.py:1-14 — No placeholder normalization logic exists. |
| R2 | A schema document describes every fixture field and placeholder | context/ — No fixture schema document exists. |
| R2 | BSON types are encoded as canonical extended JSON | tests/conftest.py:1-14 — No bson.json_util canonical encoding of fixtures anywhere in the test harness. |
| R2 | Every fixture carries a schema version field | context/ — No fixture format or schema version exists. |
| R2 | Every recorded fixture validates against the schema | context/ — No fixtures and no schema to validate against. |
| R3 | Each fixture produces exactly one reported pass/fail result named by its node id | action-server/src/test/java/com/kairon/action/ParityKit.java:37 — ParityKit is unused by any test class; WebhookTest has 23 hand-written @Test methods, no per-fixture dynamic tests named by node id. |
| R3 | Every recorded outbound call must be made with the recorded method, URL, headers of intere | action-server/src/test/java/com/kairon/action/ParityKit.java:341-346 — HITS captures method/path/query/auth/body/timestamp but nothing compares them to recorded outbound calls; arbitrary headers and full URL host are not captured. |
| R3 | No outbound call beyond the recorded ones is made | action-server/src/test/java/com/kairon/action/ParityKit.java:43 — HITS list could support a no-extra-calls check, but no such assertion against a recorded set exists. |
| R3 | Replay POSTs the recorded request to `/webhook` | action-server/src/test/java/com/kairon/action/ParityKit.java:262 — send() can POST arbitrary JSON to /webhook but no code reads recorded requests from fixtures. |
| R3 | Replay seeds the action catalog from the fixture's Mongo seed documents | action-server/src/test/java/com/kairon/action/ParityKit.java:175-179 — Catalog seeding is via hand-coded register()/put() into MemoryActionCatalog, not from fixture seed documents. |
| R3 | Replay serves each recorded upstream response for its recorded request | action-server/src/test/java/com/kairon/action/ParityKit.java:361-369 — Stub server serves hand-set path bodies/default bodies (pathBody/resolveBody), not recorded responses keyed by recorded request. |
| R3 | The response must equal the recorded response, ignoring placeholder-normalized fields | action-server/src/test/java/com/kairon/action/ParityKit.java:226 — Response checks are hand-written assertions (ok()/assertEquals), no recorded-response comparison with placeholder ignoring. |
| R3 | Written `action_server_logs` and other written documents must equal the recorded ones, ign | action-server/src/test/java/com/kairon/action/ParityKit.java:299 — logs() reads action_server_logs from the memory catalog for hand assertions; no comparison to recorded documents ignoring _id/timestamps. |
| R4 | A fixture's result is the same on both backends | action-server/build.gradle — Only one backend is run, so no cross-backend comparison exists. |
| R4 | The full fixture set runs against a real MongoDB instance | action-server/build.gradle — No Testcontainers/Mongo test dependency or test-resources; MongoActionCatalog is never exercised in tests. |
| R4 | The full fixture set runs against the in-memory catalog | action-server/src/test/resources/application-test.yml:7 — Tests run with catalog: memory only, and no fixture set exists. |
| R5 | The report breaks the percentage down by action type | action-server/src/test/resources/python-action-nodes.txt — Node list has no action-type mapping and no report breakdown exists. |
| R5 | The report lists every untranslatable node (one that patches Python internals) with a reas | action-server/src/test/resources/python-action-nodes.txt — No untranslatable-node list or reasons recorded. |
| R5 | The report states the percentage of the 434 nodes with a passing replay | action-server/src/test/resources/python-action-nodes.txt — 434-node list exists but nothing in action-server/ reads it; no coverage report is produced. |
| R6 | CI fails when any fixture that passed on the base branch fails on the change | .github/workflows/cicd.yml — No workflow builds or tests action-server/gradle; scan_image.yml only pulls the pre-existing digite/kairon-action-server image. |
| R6 | CI passes when previously passing fixtures still pass and new ones fail | .github/workflows/cicd.yml — No CI job runs fixtures or compares against a base-branch baseline. |

## Changelog
- 2026-10-26: Initial draft from approved design.
- 2026-10-26: Brownfield gap pass against existing port: 26 [GAP], 1 [UNVERIFIED] markers added.
