# Findings Board: java-action-server-port

Generated: 2026-10-26

## Research Questions
- Q1 (codebase-architecture): dispatch chain + request/response contract — ANSWERED (raw-codebase-architecture-dependencies.md F1-F3)
- Q2 (codebase-patterns): per-action side effects — ANSWERED (raw-codebase-patterns.md, 24-row table + 7 cross-cutting behaviors)
- Q3 (codebase-tests): Java port state + parity harness — ANSWERED (raw-codebase-tests-javaport.md)
- Q4 (codebase-dependencies): external services/collections/secrets — ANSWERED (F4-F7, F9-F11)
- Q5 (web-library-landscape): Micronaut + native + Mongo — PARTIAL (raw-library-landscape.md; thin sources)
- Q6 (web-existing-art): parity testing patterns — PARTIAL (raw-existing-art.md; snippets only)

## Wave 1 Findings (key)
1. Java port has all 24 action classes, ~4.8k LOC, no stubs; ~22 hand-written parity tests vs 434 Python test nodes listed in python-action-nodes.txt (unwired checklist). ParityKit stub server can assert responses + in-memory logs + outbound hits.
2. Python contract: POST /webhook {next_action, tracker, domain, version, trigger_info}; response {events:[slot events only, timestamp:null], responses:[rasa_sdk message dicts]}. Actions return dict of slots; processor emits SlotSet for every key incl None.
3. Error contract: processor catch-all -> 200 {"events":[],"responses":[]} + Failed log record (no type) + failure mail. Global handlers -> HTTP 200 {success:false,error_code,message}. Missing tracker -> 500. Blank next_action -> 200 null.
4. Logs: action_server_logs DynamicDocument; per-type fields differ widely (see table); status Success|Failed; trigger_info default always present; request_id from X-Kairon-Request-ID or uuid4; parallel_action pre-creates empty log and children reference it.
5. Templating is hand-rolled: $SENDER_ID/$INTENT/$USER_MESSAGE, $$keyvault, $slot in that order; ${RESPONSE}, ${a.b.0} dotted paths. No jinja. Character-exact port required.
6. Pyscript/expression evaluation is NEVER in-process: run_pyscript -> HTTP (async_callback_action.pyscript.url) or Lambda; evaluate_script -> evaluator.url. Java HTTP delegation matches Python for the HTTP transport.
7. Outbound HTTP: execute_request_async swallows transport exceptions (status None, continues); retry effectively disabled; timeout action.request_timeout 60s. Sync paths (hubspot, razorpay, evaluate_script) raise on non-2xx.
8. Side effects beyond HTTP: SMTP (email_action + failure mail to support_mail), Mongo writes (CallbackData, ChannelLogs, events job-store), JWT minting (store_page, agent), Fernet (keyvault, params, sender_id), nested in-process action execution (prompt_action), self-loopback (parallel_action).
9. Config drift: Java reads MONGODB_URI (default conversations DB); Python reads DATABASE_URL (default kairon DB). Python pyscript URL key is async_callback_action.pyscript.url, not evaluator.pyscript.url.
10. No auth on /webhook; secure headers + CORS + GZip + request-id middleware; GET / and /healthcheck.
11. Web: hand-rolled interpolator recommended; keep tracker as Map/Document to avoid reflection; low-level Micronaut HttpClient for dynamic URLs; micronaut-email-javamail for SMTP; delegate pyscript (never GraalPy). WireMock journals + JsonUnit for side-effect diffing; Diffy-style multicast is blind to side effects.

## Wave 2 Findings (key)
12. Scheduler: schedule_action writes a pickled APScheduler Job (func ref + DateTrigger + tz objects) into the events job-store; only stock APScheduler MongoDBJobStore reads it; no Kairon unpickling code. /api/events/dispatch/{id} only wakes the scheduler. Existing JSON endpoint POST /api/events/execute/{event_type}?is_scheduled=true is restricted to message_broadcast and analytics_pipeline. No generic callback/flow scheduling endpoint exists. Hand-crafting the pickle from Java is unsafe and unmaintainable (web consensus). Commit 8032de5c did not change who writes jobs.
13. rasa_sdk message dict ALWAYS has 8 keys {text, buttons:[], elements:[], custom:{}, template, response, image, attachment}; utter_message(None) still appends with text:null; kwargs merge top-level.
14. next_action NOT lowercased on lookup; Actions.clean lowercases on write only; UTTER_PREFIX check case-sensitive.
15. Collection names are mongoengine defaults: actions, action_server_logs, http_action_config, key_vault, bot_settings, slots (no meta overrides).
16. Test expectations confirmed: missing action -> 200 {"events":[],"responses":[]} + log exception "No action found for given bot and name"; missing next_action -> 200 null; validation error -> HTTP 200 {success:false, error_code:422, message:[...], data:null}.
17. Fixture mining: conftest autouse recorder wrapping responses/aioresponses + Mongo before/after snapshots + TestClient wrap -> fixtures/<nodeid>.json; Java @TestFactory replays with WireMock + JsonUnit ignoring _id/timestamp. Freeze time for determinism.
18. Fernet: hand-roll (~40 lines javax.crypto) or fernet-java8 (default 60s TTL conflicts with Python no-TTL decrypt). Verify with fernet/spec vectors + cross-language round trip.
19. Python repr parity: several log fields use str(dict) (single quotes, True/None). Java needs a PyRepr helper tested against captured Python strings. json.dumps separators/ensure_ascii/float formatting differ from Jackson.
20. SECURITY: Micronaut http-client < 4.10.24 forwards Authorization across redirect domains and has no hop cap (GHSA-q6gh-6v2r-hjv3). Port is on 4.10.22. Bump. Replicate aiohttp redirect rules (10 hops, 301/302/303 POST->GET, 307/308 keep) and ClientTimeout(total=) wall-clock cap explicitly.
21. Mongo: set uuidRepresentation=pythonLegacy to match mongoengine (verify subtype 3 on real docs); truncate Instant to millis; use BSON date codecs not ISO strings; Document preserves insertion order.
22. uuid7: RFC 9562; store as 32-char lowercase hex to match Python .hex.
23. Micronaut/Netty: blocking work on @ExecuteOn(BLOCKING) with virtual threads; loopback fan-out needs pool >= fan-out; verify max-request-size (10MB default vs uvicorn unlimited), client read-timeout 10s default vs action timeout 60s.
24. Native: JCA (AES/CBC, HmacSHA256) fine with literal algorithm names; hand-rolled HS256 JWT safest; Jakarta Mail needs resource/reflection hints (micronaut-email-javamail ships them); avoid mongodb+srv or smoke-test SRV.
25. HTTP wire parity: requests form-encodes nested dict lossy (a=b), drops None; query spaces `+`; Content-Type `application/json` no charset; UA differs. Pin explicitly where downstream could care.

## Contradictions
- Codebase-tests agent lists server.py webhook at ~277-295; patterns agent at 315-333. Line drift only; same function.
- Codebase-tests agent guessed Python "may run pyscript/llm in-process"; patterns agent confirms pyscript is always remote. LLM (prompt_action) IS in-process via LLMProcessor.predict + litellm.

## Open Questions (for wave 2 + clarifying questions)
A. schedule_action pickles an APScheduler job into Mongo — Java cannot produce Python pickle. RESOLVED in research: must not write pickle from Java; needs a new JSON scheduling endpoint on the Python events server (or a Python shim). Decision: in scope for v1 or defer schedule_action?
B. prompt_action / database_action depend on in-process LLMProcessor, Qdrant, CognitionSchema — large separate scope. In v1?
C. Preserve 200-with-empty-events failure contract?
D. Failure mail: port it or log-only?
E. Native image: hard requirement?
F. Fixture strategy: auto-mine 434 Python tests vs hand-port.
G. RESOLVED: utter_message(None) -> 8-key dict with text:null; next_action case-sensitive; collection names are mongoengine defaults.
H. Honour DATABASE_URL env var in Java?
