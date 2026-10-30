---
created: "2026-10-30"
last_edited: "2026-10-30"
---
# Implementation Tracking: llm-vector-clients + prompt-database-actions

Build site: context/plans/build-site-llm-prompt-db.md

| Task | Status | Notes |
|------|--------|-------|
| T-100 | DONE | config keys llm.url/request_timeout, vector.db/key; legacy llmUrl/vectorUrl kept until T-126. T-107 must move/remove legacy yml lines before editing CONFIG.md rows (placeholderDefault matches first). |
| T-101 | DONE | catalog lookups (llm secret, model, cognition schema/data). Live-Mongo contract run gated on KAIRON_TEST_MONGO_URI, not yet run (12 skipped). |
| T-102 | DONE | jtokkit 1.1.0 pinned; checkAdvisories does not scan jtokkit (vetted via OSV lookup only). |
| T-103 | DONE | dynamic nulls kept; triggers T-112 (http fail_reason, bot_response raw_gpt_response updated). |
| T-104 | DONE | FaqGate: missing bot_settings/llm_settings/enable_faq = FAQ disabled (Python defaults). |
| T-105 | DONE | PromptParams extracted; num_bot_responses default 5; ContextSource hook for crud/action (T-113/T-114). |
| T-106 | DONE | DbPayload extracted; scalar payload_search accepted, Python str() concat and TypeError text. |
| T-107 | DONE | CONFIG.md rows; legacy llm-url/vector-url yml lines moved below new keys (T-126 deletes them + getters). |
| T-108 | DONE | LlmHttp (headers, llm timeout, 1 attempt, status phrases). Kit conflict: LLM R3 c4 says 404 -> 'Not Found' but Python's RetryClient(raise_for_status) path may yield 'Internal Server Error' for any non-2xx (outbound-clients R1 GAP). Reconcile kits before T-116. |
| T-109 | DONE | LlmSecrets; cross-language Fernet test passes. API: secret, checkModel, embeddingSecret, usesDefaultEmbeddingSecret. |
| T-110 | DONE | QdrantClient.search (5s, api-key only when set, urljoin drops base path). Rendering/concurrency left to T-119. Non-2xx/non-JSON texts approximated. |
| T-111 | DONE | prompt never dispatches buttons. |
| T-112 | DONE | form_validation no user_msg; callback metadata []; schedule data {}; prompt extras order + media_ids after config load (T-123: keep after model check). |
| T-113 | DONE | CrudSource (16 tests); ActionSupport.pythonJsonError made public. Bad Fernet token text differs (accepted divergence). |
| T-114 | DONE | NestedActionSource; ActionContext.succeeded/isSuccess/response + one `context.succeeded(...)` line in Http/GoogleSearch/LiveAgent/Agent/ParallelAction. Not replicated: Python AttributeError when nested type has no is_success (set_slot, email, pyscript...): Java appends nothing - review. |
| T-115 | DONE | CognitionSchemas (find/forEmbedding/forAction/resolveProvider). T-122/T-123: call secrets.secret(bot,llmType) BEFORE the openrouter swap to keep Python failure order; T-122 replaces DatabaseAction.trainingNeeded with forAction(). |
| T-116 | DONE | LlmClient.complete + url() helper for T-117 embed. |
| T-117 | DONE | LlmClient.embed/embedAll (LlmClientEmbeddingTest 10); 3-arg @Inject ctor (LlmHttp, ActionSettings, CognitionSchemas); 2-arg ctor completion-only. |
| T-118 | DONE | LlmClient.answer(AnswerParams[, logs]) -> Answer(content, callId); AnswerParams splits endpointLlmType (URL, openrouter after swap) vs llmType (perplexity); rephrase log survives main failure; T-121 passes its own log list. |
| T-119 | DONE | SimilarityContext.attach/render (7 tests; latch proves concurrency); StubServer.startConcurrent added; virtual thread per search (like ParallelAction); first failure in config order raised (Python: first in time). |
| T-120 | DONE | QdrantClient.query(bot, collection, payload, llmType, embeddingSecret, user); 3-arg @Inject ctor; no api-key; c8 error text is 'Failed to execute the url: Got non-200 status code: ...' - kit c8 should say 'contains'. |
| T-121 | DONE | LlmProcessor.predict(AnswerParams, collection, similarityPrompts, embeddingSecret, logs) -> Prediction(response, elapsedSeconds); caller owns logs list -> llm_logs; failure log: completions appended then one error entry; non-list embedding response passes null vector (divergence). |
| T-122 | DONE | DatabaseAction rewritten: llm_type is always 'openai' (Python Qdrant.__init__ LLMProcessor(bot, DEFAULT_LLM)); order FAQ->config->db_type->openai embedding secret->schema->swap(databaseSwapsToOpenrouter inline)->payload->query. Old vector-url POST removed. Open (corrected by gate): a missing `dispatch`/`failure_response` is NOT a KeyError in Python - to_mongo() fills mongoengine defaults (dispatch True, failure text 'I have failed to process your request.'); Java throws IllegalArgumentException('dispatch') (T-124 must default instead; HttpAction:64 has the same issue); expression composer lacks `[0]` indexing (outside scope). T-126 deletes vector-url key/setter and ParityKit /vector default. |
| T-123 | DONE | PromptAction rewritten on real services. Step order: FAQ -> config -> user_msg -> llm_type (null=openai) -> params -> llm+embedding secret -> schema (non-default collection) + inline openrouter swap -> model check (original llm_type) -> media_ids -> predict. resolveProvider not used (secrets must load before schema). LlmProcessor P3s fixed (catch Exception+StackOverflowError, null query fails at embedding stage, LOG.error). Left: ActionSettings.llmUrl + ParityKit /llm stub (T-126); log/output polish (T-125). Known P3: non-list media_ids -> null; null hyperparameters text. |
| T-124 | DONE | DatabaseAction.responseConfig defaults (dispatch true, evaluation_type expression, dispatch_type text; null failure_response -> 'I have failed to process your request.'); log order config,payload,response,user_msg; failure mail on every error incl FAQ-disabled; falsy bot_response omitted. Open: logged config is raw stored doc (Python to_mongo adds defaults); `headers` not written (matches recorded fixtures; kit R7 c3 names it - reconcile); HttpAction:64 same missing-dispatch problem (follow-up). |
| T-125 | DONE | PromptAction output/log parity; ConfigViews (new, package-private, shared) builds the to_mongo() view for both actions (no _id, mongoengine defaults, declared order); null hyperparameters take defaults from l_l_m_metadata (openai) via catalog.all - without that doc the action fails at config load ('Could not find any hyperparameters for openai LLM.') like Python; null db_type -> qdrant. Gate item 3 (schema_metadata missing => error) was WRONG: Python schema_metadata has default=SchemaMetadata so defaults load; test proves parity. Kit ticks done incl. new R7 to_mongo criterion. Note: .venv310 no longer exists, so to_mongo shape derived from mongoengine 0.29 semantics, not run. |
| T-126 | DONE | adapter leftovers removed (ActionSettings llmUrl/vectorUrl, legacy yml keys, ParityKit /llm /vector stubs -> real LLM-server/Qdrant path stubs, CognitionSchemas.resolveProvider + Provider record, LlmSecrets dep). No compose/deployment files reference the old keys. Kit R7 c7 ticked; R7 c8 still to tick at final verification (T-100 tests prove config keys). |
| T-127 | TODO | tier 9 |

## Tier 0 gate (inspector, 2026-10-30): PROCEED (0 P0/P1)
Codex gate failed to run (invocation error); inspector used. Inputs for T-112 / follow-ups:
- P2 form_validation: Python never passes user_msg; Java save() always adds it (ActionSupport.java:89, FormValidationAction.java:92).
- P2 CallbackAction.java:49 metadataLog init null; Python [] -> init empty list.
- P2 ScheduleAction.java:62 dataLog init null; Python {} -> init empty map.
- P3 PromptAction.java:125 extras order: llm_call_id belongs after time_elapsed.
- P3 PromptAction.java:44 media_ids read before FAQ gate; Python null until config loaded.
- P3 DbPayload list += str extends char-wise in Python (edge; deliberate divergence or port).
- P3 findLlmSecret/findLlmModel .first() vs Python .get() MultipleObjectsReturned (accept/document).

## Tier 1 gate (inspector, 2026-10-30): BLOCK -> fixed (cycle 1)
- P1 fixed: LlmHttp maps any real >=400 response to 'Internal Server Error' (Python RetryClient raise_for_status before status_code set); transport failures keep 503/408/500. LlmHttpTest updated; kit llm-vector-clients R3 c4 reworded (outbound-clients R1 c4 was right).
- P3 fixed: form_validation no longer logs exception (Python never passes it).
- Open P3: QdrantClient non-2xx/non-JSON error text should match aiohttp 3.9.5 ClientResponseError str (`<status>, message='<phrase>', url=URL('<url>')`); LlmSecrets bad-Fernet-token text differs (Python '' ) - accept or map; T-123 keep media_ids read after secret lookup + model check.
- Never log LlmSecrets.secret() map (holds plaintext api_key).

## Tier 2 gate (inspector, 2026-10-30): BLOCK -> fixed (cycle 1)
- P1 fixed (user decision: replicate Python): nested action of a type without Python is_success (17 types incl. database) runs then fails the prompt with "'<PyClass>' object has no attribute 'is_success'". Kit R4 c4 corrected; T-114 DONE stands.
- P2 fixed: missing cognition schema text now "'NoneType' object has no attribute 'schema_metadata'" (CognitionSchemas.NOT_FOUND, DatabaseAction); database swap rule split (databaseSwapsToOpenrouter: whenever training_needed false); resolveProvider resolves original llm + embedding secret before the openrouter swap.
- Accepted risk (user decision: match Python): crud slot-mode Mongo operator injection; documented in kit 'Known risks'; decrypted secure data lands in llm_logs.
- Open P3: CrudSource result_limit null => unlimited / non-int fails; null crud_config/collections error texts; prompt nesting itself recurses to StackOverflowError (add depth guard or catch Error); LlmClient mediaIds typed List<?> (Python forwards any truthy value). T-122 must use databaseSwapsToOpenrouter and forAction().

## Tier 3+4 gate (inspector, 2026-10-30): PROCEED (0 P0/P1/P2, 6 P3)
Kit R5 c7/c8 wording fixed. Open P3: SimilarityContext.join should unwrap Error causes; LlmClient joinInstructions/perplexity accept invalid inputs Python rejects (T-121 must pass lists); StubServer.startConcurrent executor never shut down (shutdownNow in close()); 2-arg LlmClient/QdrantClient ctors could be package-private.

## Tier 5 gate (inspector, 2026-10-30): PROCEED (0 P0/P1, 2 P2, 6 P3)
- P2 for T-124: DatabaseAction missing dispatch/failure_response -> mongoengine defaults (dispatch true, 'I have failed to process your request.'); HttpAction:64 same issue (separate follow-up).
- P2 for T-124: database log dynamic order must be config, payload, response, user_msg (re-put user_msg in extras after response, add order assertion).
- P3 for T-123 (owns LlmProcessor edits): catch Exception (+StackOverflowError) in predict; null query fails at embedding stage ('NoneType' object is not iterable) instead of text "None"; LOG.error with the exception (no secrets in messages).
- P3 T-126: delete vector-url leftovers (ActionSettings:41,105; application.yml:53; ParityKit:154,440; ReplayEndpoints:48; application-test.yml:23). Tick kit R8 c1-c6 and prompt-db R6 c4/c5 with test names at the end.

## Tier 6 gate (inspector, 2026-10-30): PROCEED (0 P0/P1, 1 P2, 8 P3)
Folded into T-125 (to_mongo view of logged config for BOTH actions):
- P2 DatabaseAction.java:108 logged config includes _id (Python pops it); kit R1 '[x] _id absent' was only verified for prompt_action.
- P3 null/missing hyperparameters: Python mongoengine default (Utility.get_default_llm_hyperparameters, data_objects.py:951) -> action succeeds; Java fails with NoneType text. (Earlier impl note describing this as 'null hyperparameters text' was wrong.)
- P3 null db_type -> Python default 'qdrant'.
- P3 logged config should be to_mongo() view with defaults (response sub-doc, failure_response, llm_type, hyperparameters).
- P3 schema_metadata missing -> Python AttributeError "'NoneType' object has no attribute 'training_needed'" (forAction).
For T-126: delete CognitionSchemas.resolveProvider (+tests) if unused, ActionSettings llmUrl/vectorUrl getters/setters.
Accepted P3: non-string query repr in LlmProcessor; non-list media_ids -> [] (Python forwards raw).
Proposed kit R7 criterion: logged prompt/database configs are the to_mongo() view (no _id, defaults applied).
