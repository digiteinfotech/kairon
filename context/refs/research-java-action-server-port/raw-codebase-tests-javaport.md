## Agent: codebase-tests-javaport

### Java port inventory
All 24 Python ActionType values have a Java class (~4.8k LOC main, ~1k LOC tests). No TODO/FIXME/UnsupportedOperationException stubs found; only intentional unsupported-type failure at `actions/ActionFactory.java:31`.

| Class | LOC | Type string | Judgement |
|---|---|---|---|
| HttpAction | 115 | http_action | Complete; tested (`httpActionTemplatesCity`) |
| SlotSetAction | 49 | slot_set_action | Complete; tested incl. null-timestamp |
| FormValidationAction | 101 | form_validation_action | Looks complete; untested |
| EmailAction | 110 | email_action | Looks complete; untested |
| GoogleSearchAction | 106 | google_search_action | Looks complete |
| JiraAction | 75 | jira_action | Looks complete, small |
| ZendeskAction | 67 | zendesk_action | Looks complete, small |
| PipedriveAction | 117 | pipedrive_leads_action | Looks complete |
| HubspotAction | 73 | hubspot_forms_action | Looks complete |
| TwoStageFallbackAction | 147 | two_stage_fallback | Complete; 2 tests |
| BotResponseAction | 70 | kairon_bot_response | Complete; tested via `utter_` |
| RazorpayAction | 112 | razorpay_action | Looks complete |
| PromptAction | 132 | prompt_action | Looks complete; uses llm-url/vector-url |
| PyscriptAction | 71 | pyscript_action | Complete; calls external pyscript-url |
| DatabaseAction | 155 | database_action | Looks complete |
| WebSearchAction | 105 | web_search_action | Looks complete |
| LiveAgentAction | 144 | live_agent_action | Complete; 2 tests |
| CallbackAction | 125 | callback_action | Complete; 1 test |
| ScheduleAction | 169 | schedule_action | Complete; 1 test |
| ParallelAction | 169 | parallel_action | Complete; 1 test |
| VoiceCallAction | 106 | voice_call_action | Complete; 1 test |
| VoiceDisconnectAction | 40 | kairon_voice_disconnect | Complete; 1 test |
| StorePageAction | 102 | store_page_action | Complete; 2 tests |
| AgentAction | 86 | agent_action | Looks complete; uses simple-agent-url |

Other: `ActionFactory.java:21-47` maps type->action (`kairon_voice_disconnect` by name, `utter_*` -> bot response, else `catalog.findActive` by bot+name; unknown type throws "X type action is not supported with action server"). Catalog: `ActionCatalog` interface, `MongoActionCatalog` (83 LOC, `@Requires(kairon.action.catalog=mongo)`, findActive/findBotSettings/findByBot/insert adding `_id`+`timestamp`), `MemoryActionCatalog` (155, tests), `MongoFactory`. Runtime: Dispatcher(52), TrackerState(114), ActionContext(31), KaironAction(10), ActionFailure(12), RequestIds(24). Server: WebhookController(80), SecurityFilter(35), ActionProcessor(90). Support: ActionSupport(666), HttpCaller(266, test-only `https-stub-base` rewrite line 212), Tokens(261, Fernet+JWT), Jsons, Maps.

Implication: feature-complete on paper; risk is behavioural fidelity. Confidence: high structure, medium per-action.

### Parity harness
- `ParityKit.java` (482 LOC): in-JVM `com.sun.net.httpserver.HttpServer` stub on 127.0.0.1:18780 (lines 81-98), records every request as `Hit` in `HITS`. Canned responses via `PATH_BODIES`, `PATH_STATUS`, `SCRIPT_BODIES`, `forcedStatus`, `bodyOverride`, `defaultBody` (line 416). Uses `MemoryActionCatalog` (no real Mongo). Helpers: register, put, slots, latest, logs/log (reads `Kairon.LOGS`), event, slotValue, responses, text, hit.
- `WebhookTest.java` (496 LOC): ~22 hand-written tests asserting Python behaviour (unsupportedTypeStays200, missingTrackerIs422, emptyBodyIs422, blankNextActionIsJsonNull, slotSetKeepsNullTimestamp, emptyStorePageIdentifierLogsTwice, nullIntentRankingEscapes, fernetAndJwt).
- `application-test.yml`: catalog memory, port -1, all external URLs -> stub :18780, Fernet key + JWT secret.
- `python-action-nodes.txt`: 434 pytest node IDs (210 action_test.py, 164 action_service_test.py, 20 test_voice_call_action.py, 19 test_agent_action.py, 16 test_store_page_action.py, 5 kremote_action_test.py). NOT read by any code; it is a checklist of Python tests to port.
- No recorded fixtures, no automated record-and-compare. Harness CAN assert responses + logs + outbound hits. Coverage ~22/434.

### Python test assets
- `tests/integration_test/action_service_test.py`: 16,560 lines, 165 tests. FastAPI TestClient against `kairon.actions.server:action`. Real Mongo via mongoengine `connect(...)` line 70 (no mongomock). Outbound HTTP mocked with `responses` (55 uses) + `aioresponses`; also `unittest.mock.patch`, `AsyncMock`, `deepdiff`. Tests seed Mongo docs (HttpActionConfig, Actions, SlotSetAction, BotSettings...) then POST webhook.
- `tests/unit_test/action/action_test.py`: 5,484 lines, 211 tests (ActionUtility, http exec, URL prep) + test_agent_action.py, test_store_page_action.py, test_voice_call_action.py, kremote_action_test.py.
- Mineable as golden fixtures: each integration test = (seed docs, request, mocked upstream, expected JSON). Manual work: tests don't emit fixtures; seeds via mongoengine need BSON dump; some tests patch internals with no Java equivalent. Alternative: run Python suite with recording hook around responses/TestClient/Mongo.

### Coverage gap
`kairon/shared/actions/models.py:32-56` (24 enum members) vs Java type strings: 1:1, no missing either way. Behavioural gaps: PyscriptAction, PromptAction, AgentAction, WebSearchAction, VoiceCallAction, LiveAgentAction delegate to external services via config URLs; Python may run some in-process (needs check).

### Config, build, docker
- `application.yml`: port 5055, CORS GET/POST/OPTIONS any origin. Keys under `kairon.action`: catalog (KAIRON_ACTION_CATALOG, default mongo), rasa-sdk-version "3.6.21", request-timeout, callback-base-url, events-server-url, web-search-url, evaluator-url, pyscript-url, live-agent-url, live-agent-token, live-agent-enabled, vector-url, llm-url, simple-agent-url, voice-call-url, frontend-url, fernet-key, jwt-secret, jwt-algorithm, token-expire, unmasked-char-count; each with KAIRON_* env. `mongodb.uri` from MONGODB_URI default `mongodb://localhost:27017/conversations`. Python uses DATABASE_URL `mongodb://mongo:27017/kairon` → env var name AND default DB differ.
- `build.gradle`: Micronaut plugin 4.5.4, version 4.10.22, netty, JUnit5, Java 21, mongodb-driver-sync 5.5.1, serde-jackson. No explicit GraalVM/nativeCompile config, no reflection config files; `build/native` exists (attempted).
- `docker/docker-compose.yml:77-95`: kairon-action-server = Python image `uvicorn kairon.actions.server:action --port 5055`, publishes 5055, sets DATABASE_URL. Line 40 `ACTION_SERVER_URL: http://kairon-action-server:5055/webhook`. No Java Dockerfile/service.

### Open questions
- Parity bar response-only or also logs + outbound? (harness supports all three)
- Auto-convert 434 nodes into fixtures or port by hand?
- Should Java honour Python DATABASE_URL env var?
- Do Python pyscript/llm/vector actions run in-process vs Java HTTP delegation?
- Is native image a hard requirement? No config yet; Mongo driver + Jackson reflection untested.
