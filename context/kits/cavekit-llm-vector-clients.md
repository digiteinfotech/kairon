---
created: "2026-10-30T00:00:00Z"
last_edited: "2026-10-30"
---

# Cavekit: LLM and Vector Clients

## Scope
The outbound clients prompt_action and database_action need to reach the real services directly, as the Python action server does (no intermediate adapter): the LLM server's embedding and completion endpoints, Qdrant similarity search and Qdrant point query, LLM secret and model resolution, cognition-schema handling, and the LLM log/result shape returned to the actions. Which action calls which client, and how results are logged and dispatched, is defined in cavekit-prompt-database-actions.md.

Approved design 2026-10-30: call the real services; Qdrant `api-key` header sent on similarity search but not on database-action point query (Python quirk kept).

## Requirements

### R1: Embedding client
**Description:** Texts are embedded by the LLM server's embedding endpoint, exactly as Python sends them.
**Acceptance Criteria:**
- [x] The request is a POST to `{llm.url}/{url-quoted bot}/aembedding/{llm_type}` (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook, PromptDatabaseE2ETest#databaseActionEmbeddingAndPayloadSearchThroughWebhook, ActionGapParityTest#databaseActionDispatchesResponse)
- [x] The body is `{"text": [<texts>], "user": <sender_id>, "kwargs": {...}}`; a single-string input is sent as a one-element `text` list (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook)
- [x] `kwargs.invocation` is `prompt_action` for prompt similarity/query embedding and `db_action_qdrant` for database-action embedding (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook, PromptDatabaseE2ETest#databaseActionEmbeddingAndPayloadSearchThroughWebhook)
- [x] When the collection's cognition schema has `training_needed` false, `kwargs` carries `collection` and `model` = the schema's `model_id`; otherwise neither key is present (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook (no keys), ActionGapParityTest#promptActionSwapsToOpenrouterForUntrainedCollection (collection + model))
- [ ] [GAP] `kwargs.truncated_texts` holds each text cut to its first 8191 `cl100k_base` tokens (a 9000-token input yields an 8191-token string; a short input is unchanged)
- [x] `kwargs.api_key` is the embedding secret's `api_key` (R6) (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook, PromptDatabaseE2ETest#databaseActionEmbeddingAndPayloadSearchThroughWebhook)
- [ ] [GAP] For a single-string input whose response is a list, the first element is returned as the vector; for list input the full response is returned
- [ ] [GAP] Any status outside 200-204 fails per R3
**Dependencies:** R3, R6, R7, cavekit-config-and-deploy.md R1

### R2: Completion client
**Description:** Chat completions go to the LLM server's completion endpoint with Python's message layout.
**Acceptance Criteria:**
- [x] The request is a POST to `{llm.url}/{url-quoted bot}/completion/{llm_type}` (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook)
- [x] The body has keys `messages`, `hyperparameters`, `user`, `invocation`, `media_ids` (`[]` when none), `should_process_media` (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook)
- [ ] [GAP] For a JSON-object response, the answer content is its `formatted_response` and the raw completion is its `response`; for a non-object response both are the body as-is
- [ ] [GAP] The call id is the raw completion's `litellm_call_id`, else its `openrouter_call_id`, when the raw completion is an object; otherwise null
- [x] When the query prompt is enabled and non-empty, a rephrase completion is sent first with invocation `{invocation}_rephrase`, messages `[system, user "{query_prompt}\n\n Q: {query}\n A:"]`, `media_ids` `[]` and `should_process_media` false; its content replaces the query (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook)
- [ ] [GAP] The main messages are `[{"role":"system", system prompt}, <history messages...>, {"role":"user", ...}]`, with history omitted when empty
- [ ] [GAP] The main user content is `"{context} \n{instructions} \nQ: {query} \nA:"` when instructions are present (instructions joined with `\n`), else `"{context} \nQ: {query} \nA:"`
- [ ] [GAP] When `llm_type` is perplexity and hyperparameters carry `search_domain_filter` `[d1, d2]`, the query sent is suffixed with ` inurl:d1|d2`
- [ ] [GAP] Any status outside 200-204 fails per R3
**Dependencies:** R3, R6, cavekit-config-and-deploy.md R1

### R3: LLM transport rules
**Description:** LLM calls share Python's header, timeout, retry and error semantics.
**Acceptance Criteria:**
- [ ] [GAP] Requests carry `X-Kairon-Request-ID` (when a request id exists) and the request-timestamp header, and no `Authorization` header
- [ ] [GAP] The timeout is `llm.request_timeout` seconds, default 30 when unset
- [ ] [GAP] Exactly one request is sent per call, including for 5xx responses (no retry)
- [ ] [GAP] Any response with status >= 400 (4xx or 5xx) fails with `Internal Server Error`, because the Python client raises on status before the status code is recorded and the wrapper reports 500; a 2xx/3xx outside 200-204 (e.g. 206) fails with its HTTP status phrase
- [ ] [GAP] A connection failure fails with `Service Unavailable`, a timeout with `Request Timeout`, any other transport error with `Internal Server Error`
- [ ] [GAP] A 2xx non-JSON body is kept as raw text
**Dependencies:** cavekit-outbound-clients.md R1

### R4: Similarity search
**Description:** Each enabled similarity source is searched in Qdrant and rendered into the prompt context.
**Acceptance Criteria:**
- [x] The request is a POST to `{vector.db}/collections/{name}/points/search` with body `{"vector", "limit", "with_payload": true, "score_threshold"}` (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook)
- [x] `limit` is the source's `top_results` (default 10) and `score_threshold` its `similarity_threshold` (default 0.70) (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook)
- [x] The collection name is `{bot}_faq_embd` when the source collection is `default`, else `{bot}_{collection}_faq_embd` (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook)
- [x] An `api-key` header equal to `vector.key` is sent when `vector.key` is set, and omitted otherwise (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook (sent), PromptDatabaseE2ETest#promptActionCompletionServerErrorFailsWithoutMail (omitted))
- [ ] [GAP] The timeout is 5 seconds and exactly one request is sent per search
- [x] With two similarity sources, both searches are in flight concurrently and their context blocks appear in config order (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook (barrier: both searches in flight before either replies))
- [x] Each hit contributes `payload.content` when present, else the payload without `collection_name` (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook)
- [ ] [GAP] With at least one hit value, the context gains `"Instructions on how to use {name}:\n{Python list repr of values}\n{instructions}\n"`; with none it gains nothing
- [ ] [GAP] A search response without a `result` key fails the prediction
**Dependencies:** R1, cavekit-templating-and-secrets.md R7, cavekit-config-and-deploy.md R1

### R5: Vector point query (database action)
**Description:** database_action queries Qdrant directly.
**Acceptance Criteria:**
- [x] The request is a POST to `{vector.db}/collections/{bot}_{collection}_faq_embd/points/query` (verified: PromptDatabaseE2ETest#databaseActionEmbeddingAndPayloadSearchThroughWebhook)
- [ ] [GAP] When `embedding_search` is a non-empty string, body `query` is its embedding (R1, invocation `db_action_qdrant`); otherwise no `query` key
- [x] A `payload_search` object is merged into the body at top level (verified: PromptDatabaseE2ETest#databaseActionEmbeddingAndPayloadSearchThroughWebhook)
- [x] The body has `with_payload: true` and `limit` (default 10) whenever it has other content (verified: PromptDatabaseE2ETest#databaseActionEmbeddingAndPayloadSearchThroughWebhook (explicit limit kept), ActionGapParityTest#databaseActionDispatchesResponse (default 10))
- [ ] [GAP] A payload yielding no query and no payload_search fails with `No Operation to perform`
- [x] No `api-key` header is sent, even when `vector.key` is set (verified: PromptDatabaseE2ETest#databaseActionEmbeddingAndPayloadSearchThroughWebhook)
- [ ] [GAP] The timeout is `action.request_timeout` seconds, default 60 (the deployed default; the Python code's own fallback when the key is absent is 1)
- [ ] [GAP] A status outside 200/201/202/204 fails with a message containing `Got non-200 status code: {code} {body text}` (the action wraps it as `Failed to execute the url: Got non-200 status code: ...`)
- [ ] [GAP] Any other request error fails with a message starting `Failed to execute the url:`
- [ ] [GAP] On success the full Qdrant JSON (or text for non-JSON) is returned unmodified
- [x] A `db_type` other than `qdrant` fails with `Database not yet implemented!` (verified: ActionGapParityTest#databaseActionRejectsUnknownDbTypeBeforeBuildingPayload)
**Dependencies:** R1, R7, cavekit-config-and-deploy.md R1

### R6: LLM secrets and model check
**Description:** Credentials and model availability resolve as in Python.
**Acceptance Criteria:**
- [ ] [GAP] The LLM secret is read by `{bot, llm_type}` and, when absent, by `llm_type` with no bot (global)
- [ ] [GAP] The resolved secret exposes `api_key` (decrypted) and `api_version`, `api_base_url` only when non-empty
- [ ] [GAP] No bot or global secret fails with `LLM secret for '{llm_type}' is not configured!`
- [ ] [GAP] The model check matches `{bot, llm_type, models contains model}`, falling back to global; a miss fails with `The model '{model}' is not available for '{llm_type}'.`
- [ ] [GAP] The embedding secret is the `openai` secret when `llm_type` is neither `openai` nor an excluded type; otherwise it is the LLM secret
- [ ] [GAP] The excluded LLM types are exactly `openrouter` (an `openrouter` LLM uses its own secret for embeddings)
**Dependencies:** cavekit-templating-and-secrets.md R5

### R7: Cognition schema handling
**Description:** The collection's cognition schema decides model and provider.
**Acceptance Criteria:**
- [ ] [GAP] The schema is looked up by `{bot, collection_name}` with the collection name verbatim
- [ ] [GAP] A schema with no metadata values reads as `training_needed` true, size 3072, `model_id` `text-embedding-3-large`
- [ ] [GAP] In the embedding client a missing schema is treated as `training_needed` true
- [x] In prompt_action and database_action a missing schema fails the action with `'NoneType' object has no attribute 'schema_metadata'` (verified: CognitionSchemasTest, forActionFailsOnMissingSchema)
- [ ] [GAP] In prompt and database actions a missing schema fails the action
- [ ] [GAP] prompt_action: when the collection is not `default` and `training_needed` is false, `llm_type` becomes `openrouter` and both LLM and embedding secrets become the openrouter secret; database_action swaps whenever `training_needed` is false, whatever the collection (verified helper: CognitionSchemasTest#databaseSwapsWheneverTrainingNotNeededEvenForDefaultCollection)
- [ ] [GAP] Before the swap the original `llm_type` secret and its embedding secret are resolved first, so a missing original secret fails first as in Python
**Dependencies:** R6

### R8: Prediction result and LLM log capture
**Description:** A prediction (embedding, search, completion) returns Python's result shape and logs.
**Acceptance Criteria:**
- [x] Each completion appends `{messages, raw_completion_response, type, hyperparameters}` to the LLM logs, `type` `rephrase_query` or `answer_query`, in call order (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook)
- [ ] [GAP] A failure before the embedding returns appends `{"error": "Creating a new embedding for the provided query. <exc>"}`
- [x] A failure after the embedding returns appends `{"error": "Retrieving chat completion for the provided query. <exc>"}` (verified: PromptDatabaseE2ETest#promptActionCompletionServerErrorFailsWithoutMail)
- [x] A failure result is `{"is_failure": true, "exception": <exc>, "content": null}` (verified: PromptDatabaseE2ETest#promptActionCompletionServerErrorFailsWithoutMail)
- [x] A success result is `{"content", "similarity_context", "litellm_call_id"}` (verified: PromptDatabaseE2ETest#promptActionFullPipelineThroughWebhook)
- [ ] [GAP] The elapsed time is the wall-clock seconds of the whole prediction (embedding, search and completion)
**Dependencies:** R1, R2, R4

## Out of Scope
- Model training, collection creation and point upsert
- Use of the schema embedding size for collection creation
- Sparse and rerank embeddings
- LLMLogs persistence (written by the LLM server)
- Adding retries or an `Authorization` header to LLM calls
- Sending `api-key` on the database-action point query

## Cross-References
- See also: cavekit-prompt-database-actions.md
- See also: cavekit-outbound-clients.md
- See also: cavekit-templating-and-secrets.md
- See also: cavekit-config-and-deploy.md
- See also: cavekit-dispatch-and-logging.md
- See also: cavekit-core-actions.md
- See also: cavekit-integration-actions.md

## Source Traceability
- R1: kairon/shared/llm/processor.py:147-197 (truncate_text, get_embedding)
- R2: kairon/shared/llm/processor.py:210-296 (__get_completion, __get_answer, __rephrase_query), 579-594 (modify_user_message_for_perplexity)
- R3: kairon/shared/actions/utils.py:45-87 (execute_request_async); kairon/shared/rest_client.py
- R4: kairon/shared/llm/processor.py:372-381, 440-493 (similarity search and context attach)
- R5: kairon/shared/vector_embeddings/db/qdrant.py:34-57; kairon/shared/vector_embeddings/db/factory.py
- R6: kairon/shared/admin/processor.py:39-79; kairon/shared/llm/processor.py:49-53; kairon/shared/data/constant.py:259 (DEFAULT_LLM `openai`), 263-264 (ExcludedLLMTypes: `openrouter` only)
- R7: kairon/actions/definitions/prompt.py:83-97; kairon/actions/definitions/database.py:88-93; kairon/shared/cognition/data_objects.py:35-38
- R8: kairon/shared/llm/processor.py:110-145, 241-279

## Changelog
- 2026-10-30: Initial draft from approved design (real services, no adapter; Qdrant api-key parity quirk).
- 2026-10-30: R6 lists the excluded LLM types explicitly (`openrouter`); See also lines for dispatch-and-logging, core-actions, integration-actions (bidirectional).
- 2026-10-30: R7 missing-schema text, per-action swap rule and secret-failure order specified from tier 2 gate.
