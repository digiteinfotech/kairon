## Agent: codebase-architecture-dependencies
Paths relative to kairon/ unless noted. rasa_sdk = .venv/lib/python3.12/site-packages/rasa_sdk (S/).

### F1 Dispatch chain (Confidence: high)
POST /webhook -> ActionHandler.process_actions -> ActionProcessor.process_action -> ActionFactory.get_instance -> ActionX.execute.
- Route actions/server.py:~277-295: `webhook(request_json: dict)`; `check_version_compatibility` only warns; `if result:` wraps 200 JSONResponse; None -> `null` 200.
- Handler actions/handlers/action.py:11-35: blank `next_action` -> warn, return None. Missing `tracker` -> KeyError -> 500 (no handler). `domain = get("domain", {})`. rasa_sdk CollectingDispatcher; `validate_events`; `_create_api_response(events, dispatcher.messages)`.
- Processor actions/handlers/processor.py:19-47: `bot_id = tracker.get_slot("bot")`; empty bot/action -> ActionFailure("Bot id and action name not found in slot"). `slots = await instance.execute(...)`; returns `[SlotSet(k,v) for k,v in slots.items()]`. Actions return dict of slots only, never events.
- Factory actions/definitions/factory.py:30-58,68-73: static dict ActionType string -> class (24 types, shared/actions/models.py:32-56). Unknown -> ActionFailure("<type> type action is not supported with action server").
- Type resolution shared/actions/utils.py:507-520: `kairon_voice_disconnect` by name; `UTTER_PREFIX` -> kairon_bot_response; else `Actions.objects(bot=,name=,status=True).get().type`; DoesNotExist -> ActionFailure("No action found for given bot and name") (:523-532).
- Base actions/definitions/base.py: `retrieve_config()`, `async execute(dispatcher, tracker, domain, **kwargs)`.

### F2 Request contract (Confidence: high)
`{next_action, tracker, domain, version, ...}`; extra keys ignored except `trigger_info` (read by HTTP action). Tracker.from_dict (S/interfaces.py:24-36): sender_id (required), slots {}, latest_message {} (text, intent.name, entities), events [], paused false, followup_action None, active_loop (fallback active_form, {}), latest_action_name None, stack []. `bot` slot mandatory.
`build_context` shared/actions/utils.py:360-384 -> keys: sender_id, user_message, slot (current_slot_values), intent, chat_log, key_vault (all decrypted secrets when extract_keyvault), latest_message, KAIRON_USER_MSG_ENTITY (first entity value), session_started (iat). Same dict is evaluator/pyscript context. `domain` unused by HTTP action.

### F3 Response contract (Confidence: high)
`{"events":[...], "responses":[...]}` (S/executor.py:378-381). Events: only slot events `{"event":"slot","timestamp":null,"name":k,"value":v}` (S/events.py:44-47); all returned slots emitted incl. system slots kairon_action_response, http_status_code, llm_call_id. `validate_events` drops dicts lacking `event`. No BotUttered events. Responses: CollectingDispatcher.utter_message appends `{text, buttons:[], elements:[], custom:{}, template, response, image, attachment, **kwargs}` (S/executor.py:54-66); json_message -> custom; text = str(response).
HTTP-action dispatch shared/actions/utils.py:678-716: list response -> one message per item (dict -> custom, else text); dispatch_type=json: json.loads string, on decode error fall back to text + log "Failed to convert http response to json: ...". Dispatch only when dispatch_bot_response true AND bot_response truthy.
Implication: field order, explicit null timestamp, always-present image/attachment nulls matter.

### F4 Config sources (Mongo) (Confidence: high core, med other collection names)
- Connection: lifespan server.py:~97-103 `connect(**Utility.mongoengine_connection(environment["database"]["url"]))` + `AccountProcessor.load_system_properties()`. URL parsing shared/utils.py:1084-1101 (replicaset, authsource, authmechanism). env==test -> mongomock.
- Collections: mongoengine default snake_case of class, no overrides found. `actions` (data_objects.py:287: name, type, bot, user, timestamp, status; name lowercased on save). Per-type config classes in shared/actions/data_objects.py: HttpActionConfig(:151), SlotSetAction, FormValidationAction, EmailActionConfig, PyscriptActionConfig, DatabaseAction, GoogleSearchAction, WebSearchAction, JiraAction, ZendeskAction, PipedriveLeadsAction, HubspotFormsAction, KaironTwoStageFallbackAction, PromptAction, RazorpayAction, LiveAgentActionConfig, CallbackActionConfig, ScheduleAction, ParallelActionConfig, VoiceCallAction, StorePageAction, AgentActionConfig.
- HttpActionConfig: action_name, http_url, request_method, content_type(json|data), params_list[], dynamic_params(str), headers[], response{dispatch, dispatch_type, value, evaluation_type}, set_slots[], bot, user, timestamp, status; queried bot=,action_name=,status=True.
- Other: `key_vault` (shared/data/data_objects.py:1006), `slots` (name,bot,status=True), `bot_settings` (missing -> defaults), `bot`. HttpActionRequestBody: key, value, parameter_type (value|slot|sender_id|user_message|intent|chat_log|key_vault|latest_message), encrypt.
- Auditlog base publishes audit logs on save (shared/data/audit/processor.py).

### F5 Secrets/encryption (Confidence: high)
- Fernet with `security.fernet_key` (shared/utils.py:1391-1407); InvalidToken on bad token.
- KeyVault.value Fernet-encrypted pre_save (data_objects.py:1015-1018); decrypted in get_secret_from_key_vault (utils.py:387-404), get_all_secrets_from_keyvault (:407-424).
- get_parameter_value (utils.py:~254-289): encrypt && parameter_type==value -> decrypt; log value masked via Utility.get_masked_value; key_vault param -> get_secret_from_key_vault(raise_err=False) -> None if missing.
- Utility.decrypt_action_parameter (shared/utils.py:1991); process_sender_id decrypts sender id when valid token. ActionUtility.encrypt_secrets body not read.
- system.yaml also has AES key/IV under async_callback_action.short_secret and JWT security.secret_key (callback action). FLAG: system.yaml ships hard-coded default secrets; Java port must not copy them.
- Java needs Fernet (AES-128-CBC + HMAC-SHA256, versioned token); test cross-language interop.

### F6 system.yaml / env config (Confidence: high)
Utility.load_environment() shared/utils.py:267-275 -> ConfigLoader(os.getenv("system_file","./system.yaml")); `${ENV_VAR:default}` interpolation. Keys used: database.url, cors.origin, security.fernet_key, action.request_timeout (60), evaluator.url, evaluator.pyscript.{trigger_task,url}, async_callback_action.pyscript.{trigger_task,url}, web_search.{trigger_task,url}, llm.{key,url,request_timeout}, vector.{db,key}, events.*, app.*, env, support_mail, email config.

### F7 External services (Confidence: high for evaluator/pyscript/HTTP)
- Expression evaluator utils.py:1086-1097: POST evaluator.url `{"script","data"}` -> `{success,data}`; success=false -> ActionFailure("Expression evaluation failed: ...").
- Pyscript run_pyscript utils.py:759-785: body `{"source_code","predefined_objects": context}`; if evaluator.pyscript.trigger_task -> AWS Lambda via CloudUtility.trigger_lambda(EventClass.pyscript_evaluator); else POST async_callback_action.pyscript.url; non-200 statusCode -> ActionFailure; result resp['body']. evaluate_pyscript: result.slots (bot slot filtered), bot_response or body.
- Outbound HTTP: ActionUtility.execute_request_async via AioRestClient (utils.py:45-95): default timeout action.request_timeout; adds REQUEST_TIMESTAMP_HEADER; GET/PUT/POST/DELETE; content_type json|data; returns (body, status, elapsed, headers); media_ids -> multipart via UserMedia.get_media_bytes_from_media_id.
- Prompt action: LLM via llm.url, litellm_call_id slot (actions/definitions/prompt.py:66-166); Qdrant vector.db. Others not read.
- No Redis in actions/.

### F8 HTTP action flow (Confidence: high) actions/definitions/http.py:54-181
1 load config; 2 build_context(tracker, True) + bot; 3 headers via prepare_request; 4 body from dynamic_params (pyscript) or params_list; 5 prepare_url; 6 execute; 7 compose_response (evaluation_type expression|script via evaluator); 8 fill_slots_from_response. On any exception: bot_response "I have failed to process your request", status FAIL, trigger_action_failure_mail. finally: dispatch response, save ActionServerLogs. Slots always include kairon_action_response, http_status_code. Failing action still returns 200 with fallback utterance.

### F9 ActionServerLogs (Confidence: high)
Collection `action_server_logs`, DynamicDocument (data_objects.py:263-282). Declared: type, intent, action, sender, headers, url, request_method, request_params, api_response, bot_response, exception, messages, bot, timestamp (utcnow), status (SUCCESS|FAIL default SUCCESS), trigger_info{trigger_name:"",trigger_type:"implicit",trigger_id:""}, request_id. HTTP action adds: events (list of {type: slots|response|api_call|filled_slots|...}), fail_reason, user_msg, time_elapsed, http_status_code. Indexes bot, (bot,-timestamp). request_id from X-Kairon-Request-ID header or uuid4 (shared/middleware.py), echoed on response.

### F10 Error-handling contract (Confidence: high)
- Processor catch-all processor.py:36-47: log, save ActionServerLogs(intent, action, sender, exception=str(e), bot, status=FAIL, request_id), trigger_action_failure_mail (asyncio task, best-effort, support_mail), no re-raise, returns None -> webhook returns HTTP 200 `{"events":[],"responses":[]}`. Applies to ActionFailure and any action exception.
- ActionExecutionRejection/ActionNotFoundException server.py:~285-295: 400 `{"error","action_name"}` (rasa_sdk; kairon doesn't raise).
- Global handlers server.py:~160-262: `{success:false, error_code:int, message:str}` with HTTP 200 always: StarletteHTTPException (error_code=status), AssertionError, RequestValidationError (message=exc.errors()), DoesNotExist, PyMongoError, mongoengine errors, PyJWTError, AppException (422). Non-object body -> 200 `{success:false,error_code:422,message:[...]}`.

### F11 Auth/security (Confidence: high)
No auth on /webhook. log_requests parses Authorization only to log `rid=` (server.py:~143-158). Middlewares: CORS (cors.origin, credentials, all methods/headers), GZip, request-id, OTel, add_secure_headers (HSTS, CSP, no-referrer, permissions policy, Cache-Control must-revalidate, X-Content-Type-Options, Server: Secure, COEP require-corp, COOP same-origin, CORP same-origin; ACAO = request Origin else allowed_origins[0]). GET / -> {"message":"Kairon Action Server Up and Running"}; GET /healthcheck -> {"message":"health check ok"}.

### Open questions
1. encrypt_secrets and prepare_url exact semantics (log masking, URL templating).
2. compose_response / fill_slots_from_response semantics (utils.py:648-760, 788+).
3. Failure mail: port it or log only?
4. What load_system_properties loads; does action server depend on it?
5. v1 action scope.
6. Confirm per-type collection names against live DB.
7. Preserve 200-with-empty-events failure contract?
8. Pyscript endpoint config inconsistency (async_callback_action.pyscript.* vs evaluator.pyscript.*).
9. Fernet cross-language interop test.
