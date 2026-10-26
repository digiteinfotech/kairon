# Action server configuration

The Java port reads the same environment variables, with the same defaults, as the Python action
server's `system.yaml` (repo root). Bindings live in `src/main/resources/application.yml`; the bound
properties are fields of `com.kairon.action.ActionSettings` (prefix `kairon.action`) and `mongodb.uri`.

`ConfigMappingTest` parses the table below and checks each row against `system.yaml` and
`application.yml`, so keep the table format (backticked cells) when editing it.

Default column conventions:
- `` `value` ``: same default in Python and the port.
- `none`: Python declares no default (`${NAME}`); the port defaults to empty.
- `secret`: Python ships a default value; the port deliberately ships none (cavekit-config-and-deploy.md R2).
- `deviation: value`: port default intentionally differs; reason in Notes.

## Python key to port key

| Python key | Env var | Port property | Default | Notes |
|---|---|---|---|---|
| `database.url` | `DATABASE_URL` | `mongodb.uri` | `mongodb://localhost:27017/conversations` | URL without a database name uses `kairon`. UUIDs use `pythonLegacy` (subtype 3) unless the URL sets `uuidRepresentation`. |
| `action.request_timeout` | `ACTION_SERVER_REQUEST_TIMEOUT` | `kairon.action.request-timeout` | `60` | Outbound HTTP timeout, seconds. |
| `action.url` | `ACTION_SERVER_URL` | `kairon.action.action-server-url` | `http://localhost:5055/webhook` | Own webhook URL (parallel_action loopback). |
| `async_callback_action.url` | `ASYNC_CALLBACK_ACTION_SERVER_URL` | `kairon.action.callback-base-url` | `http://localhost:5059/callback` | Async callback base URL. |
| `async_callback_action.short_secret.aes_key` | `ASYNC_CALLBACK_AES_KEY` | `kairon.action.async-callback-aes-key` | secret | Callback short token key. |
| `async_callback_action.short_secret.aes_iv` | `ASYNC_CALLBACK_AES_IV` | `kairon.action.async-callback-aes-iv` | secret | Callback short token IV. |
| `async_callback_action.pyscript.url` | `TRIGGER_MAIN_PYSCRIPT_URL` | `kairon.action.pyscript-url` | `http://localhost:5059/main_pyscript/execute-python` | Pyscript evaluation endpoint (`ActionUtility.run_pyscript`). |
| `evaluator.url` | `EXPRESSION_EVALUATOR_ENDPOINT` | `kairon.action.evaluator-url` | `http://192.168.100.109:8085/evaluate` | Expression evaluator. |
| `events.server_url` | `EVENT_SERVER_ENDPOINT` | `kairon.action.events-server-url` | `http://localhost:5056` | Events server. |
| `web_search.url` | `WEB_SEARCH_URL` | `kairon.action.web-search-url` | none | Web search endpoint. |
| `live_agent.url` | `LIVE_AGENT_SERVER_URL` | `kairon.action.live-agent-url` | `http://localhost:8000/api/v1` | Live agent server. |
| `live_agent.auth_token` | `LIVE_AGENT_AUTH_TOKEN` | `kairon.action.live-agent-token` | secret | Live agent bearer token. |
| `live_agent.enable` | - | `kairon.action.live-agent-enabled` | `true` | Literal in Python (no env var). |
| `simple_agent.url` | `SIMPLE_AGENT_URL` | `kairon.action.simple-agent-url` | none | Simple agent server. |
| `support_mail` | `KAIRON_SUPPORT_MAIL` | `kairon.action.support-mail` | `kairon@digite.com` | Failure mail recipient. |
| `cors.origin` | `ALLOWED_ORIGIN` | `kairon.action.cors-origin` | `["*"]` | JSON list (as Python json-decodes it) or comma-separated; parsed by `ActionSettings.corsOrigins()`. Wiring into the CORS filter is T-035. |
| `security.fernet_key` | `FERNET_KEY` | `kairon.action.fernet-key` | secret | Fernet key. |
| `security.secret_key` | `SECRET_KEY` | `kairon.action.jwt-secret` | secret | JWT secret. |
| `security.algorithm` | - | `kairon.action.jwt-algorithm` | `HS256` | Literal in Python (no env var). |
| `security.unmasked_char_count` | `SECRET_UNMASKED_CHAR_COUNT` | `kairon.action.unmasked-char-count` | `2` | Secret masking. |
| `security.unmasked_char_strategy` | `SECRET_UNMASKED_CHAR_STRATEGY` | `kairon.action.unmasked-char-strategy` | `from_right` | Secret masking. |
| `app.frontend_url` | `FRONTEND_URL` | `kairon.action.frontend-url` | `http://localhost:3000` | `BASE_URL` in email templates. |
| `llm.url` | `LLM_SERVER_URL` | `kairon.action.llm-url` | deviation: empty (Python `http://localhost`) | Only read by prompt_action and LLM rephrase, both deferred; an empty value keeps them off. |
| `vector.db` | `VECTOR_DB` | `kairon.action.vector-url` | deviation: empty (Python `http://localhost:6333`) | Only read by database_action, deferred; an empty value keeps it off. |

## Python keys not mapped (out of scope)

| Python key | Reason |
|---|---|
| `web_search.trigger_task`, `evaluator.pyscript.trigger_task`, `async_callback_action.pyscript.trigger_task`, `events.task_definition.*`, `events.executor.*` | Lambda transports are out of scope; the port always uses the HTTP endpoints above. |
| `events.queue.*`, `events.scheduler.collection` | schedule_action calls the events server instead of writing jobs to Mongo (cavekit-events-schedule-api.md). |
| `events.scheduler.min_trigger_interval` | Validated when the action config is saved, not by the action server. |
| `security.token_expire` | Login-token lifetime; the action server's store-page/agent tokens use the code constant 15 minutes (`kairon/shared/auth.py`), mapped to `kairon.action.token-expire` (fixed 15). |

## Port-only settings

| Port property | Env var | Default | Notes |
|---|---|---|---|
| `kairon.action.catalog` | `KAIRON_ACTION_CATALOG` | `mongo` | `memory` for tests. |
| `kairon.action.voice-call-url` | `KAIRON_VOICE_CALL_URL` | empty | Python calls the telephony provider SDK directly; no system.yaml key exists. |
| `kairon.action.https-stub-base` | - | empty | Test-only https redirect to a stub server. |
| `micronaut.server.max-request-size`, `micronaut.server.max-request-buffer-size` | `MICRONAUT_SERVER_MAX_REQUEST_SIZE`, `MICRONAUT_SERVER_MAX_REQUEST_BUFFER_SIZE` | `64MB` | See below. |

## Request body-size ceiling (needs human sign-off)

The Python server (uvicorn, `docker/docker-compose.yml`) applies no body-size limit. Micronaut's
default of 10 MB would reject a 20 MB tracker with 413, so the port sets
`micronaut.server.max-request-size` and `micronaut.server.max-request-buffer-size` (Micronaut >= 4.5 buffers `@Body String` under the second limit, also 10 MB by default) to `64MB` (cavekit-webhook-contract.md R6). `RequestSizeTest`
proves a 20 MB tracker is processed. The 64 MB ceiling is a proposal: it bounds memory per request
while staying well above observed trackers. It must be agreed by a human before rollout and can be
overridden with `MICRONAUT_SERVER_MAX_REQUEST_SIZE` and `MICRONAUT_SERVER_MAX_REQUEST_BUFFER_SIZE` (set both).

## Dependency hygiene

GHSA-q6gh-6v2r-hjv3 affects `io.micronaut:micronaut-http-client` 4.x below 4.10.24. The port uses
`java.net.http` for outbound calls and does not ship `micronaut-http-client`. `build.gradle` pins a
floor of 4.10.24 for every `io.micronaut:micronaut-http*` artifact that does get resolved, and the
`checkAdvisories` task (run by `check`) fails the build if any resolved Micronaut core/http artifact
is below 4.10.24.
