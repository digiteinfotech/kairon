package com.kairon.action;

import com.kairon.action.actions.ActionFactory;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.TrackerState;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Jsons;
import com.kairon.action.support.Tokens;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Packet T-028..T-031: unsupported types and no rephrase (dispatch-and-logging R1 c6, core-actions R4 c4),
 * two-stage text search (core-actions R3 c2), google CSE request (integration-actions R3 c3),
 * voice provider initiate-call (integration-actions R12 c2).
 */
@MicronautTest
class ActionGapParityTest {

    @Inject
    EmbeddedServer server;
    @Inject
    MemoryActionCatalog catalog;
    @Inject
    Tokens tokens;
    @Inject
    ActionSupport support;
    @Inject
    ActionFactory factory;
    @Inject
    HttpCaller http;
    @Inject
    ActionSettings settings;

    ParityKit kit;

    @BeforeAll
    static void servers() throws Exception {
        ParityKit.startServers();
    }

    @AfterAll
    static void stop() {
        ParityKit.stopServers();
    }

    @BeforeEach
    void reset() {
        kit = new ParityKit(server, catalog, tokens, support, factory, http, settings);
        kit.restore();
        kit.resetState();
    }

    // ---- T-028: unsupported types ----

    @Test
    void unknownTypeIsUnsupported() {
        String type = "unknown_action";
        String name = "act_" + type;
        kit.register(name, type);
        ActionFailure failure = kit.failureOf(() -> factory.get(kit.bot, name));
        assertEquals(type + " type action is not supported with action server", failure.getMessage());

        Map<String, Object> body = kit.ok(name);
        assertEquals(List.of(), body.get("events"));
        assertEquals(List.of(), body.get("responses"));
        Document log = kit.log(name);
        assertNull(log.get("type"));
        assertEquals(type + " type action is not supported with action server", log.get("exception"));
        assertEquals(Kairon.FAIL, log.get("status"));
    }

    // ---- T-123: prompt_action against the LLM server + Qdrant ----

    private static final String COMPLETION_REPLY =
            "{\"formatted_response\":\"llm-answer\",\"response\":{\"litellm_call_id\":\"call-77\"}}";

    private String completionPath(String llmType) {
        return "/" + kit.bot + "/completion/" + llmType;
    }

    private String searchPath(String collection) {
        return "/collections/" + kit.bot + "_" + collection + "_faq_embd/points/search";
    }

    private void llmSecretWithModels(String llmType, String apiKey, List<String> models) {
        kit.put(com.kairon.action.catalog.ActionCatalog.LLM_SECRET, kit.doc("bot", kit.bot, "llm_type", llmType,
                "api_key", tokens.encrypt(apiKey), "models", models));
    }

    /** prompt_action: system + bot_content(kb_docs) + nested http action + query prompt. */
    private void registerPrompt(String name) {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true,
                "llm_settings", kit.doc("enable_faq", true)));
        kit.register(name, "prompt_action");
        kit.register("kb_http", "http_action");
        kit.put("http_action_config", kit.doc("bot", kit.bot, "action_name", "kb_http", "status", true,
                "http_url", ParityKit.STUB + "/mock", "request_method", "GET", "content_type", "json",
                "response", kit.doc("dispatch", false, "dispatch_type", "text",
                        "value", "${data.data}", "evaluation_type", "expression")));
        kit.put("prompt_action", kit.doc(
                "bot", kit.bot,
                "name", name,
                "status", true,
                "llm_type", "openai",
                "process_media", true,
                "num_bot_responses", 3,
                "instructions", List.of("be concise"),
                "user_question", kit.doc("type", "from_user_message", "value", "ignored"),
                "llm_prompts", List.of(
                        kit.doc("type", "system", "name", "sys", "data", "You are helpful", "is_enabled", true),
                        kit.doc("type", "user", "name", "kb", "source", "bot_content", "data", "kb_docs", "instructions", "cite", "is_enabled", true,
                                "hyperparameters", kit.doc("top_results", 5, "similarity_threshold", 0.8)),
                        kit.doc("type", "user", "name", "Http", "source", "action", "data", "kb_http", "is_enabled", true),
                        kit.doc("type", "query", "name", "q", "data", "Answer using KB", "instructions", "strict", "is_enabled", true)
                ),
                "hyperparameters", kit.doc("model", "gpt-4o-mini", "temperature", 0.0),
                "set_slots", List.of(kit.doc("name", "answer", "value", "${data}", "evaluation_type", "expression")),
                "dispatch_response", true,
                "failure_message", "fallback"
        ));
    }

    private void llmServerOk() {
        kit.pathBody(embedPath("openai"), "[[0.1,0.2]]");
        kit.pathBody(searchPath("kb_docs"), "{\"result\":[{\"payload\":{\"content\":\"kanban is a board\"}}]}");
        kit.pathBody(completionPath("openai"), COMPLETION_REPLY);
    }

    private List<ParityKit.Hit> hitsUnder(String prefix) {
        return ParityKit.HITS.stream().filter(hit -> hit.path().startsWith(prefix)).toList();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        return (Map<String, Object>) value;
    }

    /** T-123: embedding -> Qdrant search -> rephrase + answer completions on the real LLM server paths. */
    @Test
    void promptActionDispatchesResponse() {
        registerPrompt("ask_llm");
        cognitionSchema("kb_docs", true);
        llmSecretWithModels("openai", "sk-openai", List.of("gpt-4o-mini"));
        llmServerOk();

        Map<String, Object> body = kit.ok("ask_llm", kit.slots("media_ids", List.of("m1")), kit.latest("what is kanban"));
        assertEquals("llm-answer", kit.text(body));
        // T-111: Python never sends recommendation buttons
        assertEquals(1, kit.responses(body).size());
        assertEquals(List.of(), kit.responses(body).get(0).get("buttons"));
        assertEquals("llm-answer", kit.event(body, Kairon.ACTION_RESPONSE).get("value"));
        assertEquals("call-77", kit.event(body, Kairon.LLM_CALL_ID).get("value"));
        assertEquals("llm-answer", kit.event(body, "answer").get("value"));
        assertTrue(ParityKit.HITS.stream().noneMatch(hit -> hit.path().startsWith("/llm")), "no adapter POST");

        // embedding: first similarity collection, invocation prompt_action, openai embedding secret
        Map<String, Object> embedBody = Jsons.readMap(kit.hitPath(embedPath("openai")).body());
        assertEquals(List.of("what is kanban"), embedBody.get("text"));
        Map<String, Object> embedKwargs = asMap(embedBody.get("kwargs"));
        assertEquals("prompt_action", embedKwargs.get("invocation"));
        assertFalse(embedKwargs.containsKey("collection"), "training_needed true pops collection");
        assertEquals("sk-openai", embedKwargs.get("api_key"));
        // Qdrant search with the query vector and the source's limits
        Map<String, Object> search = Jsons.readMap(kit.hitPath(searchPath("kb_docs")).body());
        assertEquals(List.of(0.1, 0.2), search.get("vector"));
        assertEquals(5, ((Number) search.get("limit")).intValue());
        assertEquals(0.8, ((Number) search.get("score_threshold")).doubleValue(), 1e-9);

        // rephrase then answer completions
        List<ParityKit.Hit> completions = hitsUnder(completionPath("openai"));
        assertEquals(2, completions.size());
        Map<String, Object> rephrase = Jsons.readMap(completions.get(0).body());
        assertEquals("prompt_action_rephrase", rephrase.get("invocation"));
        assertEquals(List.of(), rephrase.get("media_ids"));
        assertEquals(false, rephrase.get("should_process_media"));
        Map<String, Object> main = Jsons.readMap(completions.get(1).body());
        assertEquals(List.of("messages", "hyperparameters", "user", "invocation", "media_ids", "should_process_media"),
                new java.util.ArrayList<>(main.keySet()));
        assertEquals("prompt_action", main.get("invocation"));
        assertEquals(List.of("m1"), main.get("media_ids"));
        assertEquals(true, main.get("should_process_media"));
        assertEquals("default", main.get("user"));
        assertEquals(Map.of("model", "gpt-4o-mini", "temperature", 0.0), main.get("hyperparameters"));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> messages = (List<Map<String, Object>>) main.get("messages");
        assertEquals(Map.of("role", "system", "content", "You are helpful\n"), messages.get(0));
        String userContent = String.valueOf(messages.get(messages.size() - 1).get("content"));
        // nested http action (R4 c1) and similarity context reach the prompt; instructions joined
        assertTrue(userContent.contains("Http:\ntest_data\n"), userContent);
        assertTrue(userContent.contains("Instructions on how to use kb:\n['kanban is a board']\ncite\n"), userContent);
        assertTrue(userContent.endsWith(" \nbe concise \nQ: llm-answer \nA:"), userContent);

        Document log = kit.log("ask_llm");
        assertEquals("prompt_action", log.get("type"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
        assertNull(log.get("exception"));
        assertEquals("call-77", log.get("llm_call_id"));
        assertEquals(List.of("m1"), log.get("media_ids"));
        assertTrue(((Number) log.get("time_elapsed")).doubleValue() > 0);
        Map<String, Object> llmResponse = asMap(log.get("llm_response"));
        assertEquals(List.of("content", "similarity_context", "litellm_call_id"),
                new java.util.ArrayList<>(llmResponse.keySet()));
        assertEquals("llm-answer", llmResponse.get("content"));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> llmLogs = (List<Map<String, Object>>) log.get("llm_logs");
        assertEquals(List.of("rephrase_query", "answer_query"), llmLogs.stream().map(entry -> entry.get("type")).toList());
        // T-112: Python ActionServerLogs(...) keyword order puts llm_call_id after time_elapsed
        List<String> keys = new java.util.ArrayList<>(log.keySet());
        keys.remove("_id");
        assertEquals(List.of("events", "recommendations", "llm_response", "kairon_faq_action_config", "llm_logs",
                "user_msg", "media_ids", "time_elapsed", "llm_call_id"), keys.subList(keys.size() - 9, keys.size()));
        Map<String, Object> loggedConfig = asMap(log.get("kairon_faq_action_config"));
        assertFalse(loggedConfig.containsKey("_id"));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> events = (List<Map<String, Object>>) log.get("events");
        assertEquals(2, events.size());
        assertEquals("llm_response", events.get(0).get("type"));
        assertEquals("llm-answer", events.get(0).get("response"));
        assertEquals("slots_to_fill", events.get(1).get("type"));
        assertEquals(Map.of("answer", "llm-answer"), events.get(1).get("data"));
    }

    private void assertFailedBeforeLlm(String name, String exception) {
        Map<String, Object> body = kit.ok(name, kit.slots("media_ids", List.of("m1")), kit.latest("what is kanban"));
        assertEquals("fallback", kit.text(body));
        Document log = kit.log(name);
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals(exception, log.get("exception"));
        assertNull(log.get("media_ids"), "media_ids read only after the model check");
        assertEquals(List.of(), log.get("llm_logs"), "processor built: empty llm_logs");
        // only the nested http action (params build) ran; nothing reached the LLM server or Qdrant
        assertTrue(ParityKit.HITS.stream().allMatch(hit -> hit.path().startsWith("/mock")),
                "no LLM/Qdrant hit: " + ParityKit.HITS);
        assertTrue(hitsUnder("/" + kit.bot).isEmpty());
        assertTrue(hitsUnder("/collections").isEmpty());
    }

    /** T-123: a non-default first collection without a CognitionSchema fails before any LLM call. */
    @Test
    void promptActionMissingSchemaFailsBeforeLlm() {
        registerPrompt("no_schema_prompt");
        llmSecretWithModels("openai", "sk-openai", List.of("gpt-4o-mini"));
        llmServerOk();
        assertFailedBeforeLlm("no_schema_prompt", com.kairon.action.support.llm.CognitionSchemas.NOT_FOUND);
    }

    /** T-123: the model check on hyperparameters.model (original llm_type) fails before any LLM call. */
    @Test
    void promptActionUnknownModelFailsBeforeLlm() {
        registerPrompt("bad_model_prompt");
        cognitionSchema("kb_docs", true);
        llmSecretWithModels("openai", "sk-openai", List.of("gpt-4o"));
        llmServerOk();
        assertFailedBeforeLlm("bad_model_prompt", "The model 'gpt-4o-mini' is not available for 'openai'.");
    }

    /** T-123: LLMProcessor(bot, llm_type) loads the secret before the schema lookup (Python failure order). */
    @Test
    void promptActionMissingSecretFailsBeforeSchemaLookup() {
        registerPrompt("no_secret_prompt");
        llmServerOk();
        Map<String, Object> body = kit.ok("no_secret_prompt", kit.slots(), kit.latest("q"));
        assertEquals("fallback", kit.text(body));
        Document log = kit.log("no_secret_prompt");
        assertEquals("LLM secret for 'openai' is not configured!", log.get("exception"));
        assertNull(log.get("llm_logs"), "processor never built");
        assertTrue(hitsUnder("/" + kit.bot).isEmpty());
    }

    /** T-123: is_failure from predict -> status Failed, exception from the result, content None. */
    @Test
    void promptActionPredictionFailureSetsFailed() {
        registerPrompt("fail_prompt");
        cognitionSchema("kb_docs", true);
        llmSecretWithModels("openai", "sk-openai", List.of("gpt-4o-mini"));
        llmServerOk();
        kit.pathStatus(completionPath("openai"), 500);

        Map<String, Object> body = kit.ok("fail_prompt", kit.slots("media_ids", List.of("m1")), kit.latest("q"));
        assertNull(kit.event(body, Kairon.ACTION_RESPONSE).get("value"));
        assertNull(kit.event(body, Kairon.LLM_CALL_ID).get("value"));
        Document log = kit.log("fail_prompt");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("Internal Server Error", log.get("exception"));
        assertEquals(List.of("m1"), log.get("media_ids"));
        Map<String, Object> llmResponse = asMap(log.get("llm_response"));
        assertEquals(List.of("is_failure", "exception", "content"), new java.util.ArrayList<>(llmResponse.keySet()));
        assertEquals(true, llmResponse.get("is_failure"));
        assertEquals(List.of(Map.of("error", "Retrieving chat completion for the provided query. Internal Server Error")),
                log.get("llm_logs"));
        assertEquals(1, hitsUnder(embedPath("openai")).size());
    }

    /** T-123: non-default collection with training_needed false swaps endpoints/secrets to openrouter. */
    @Test
    void promptActionSwapsToOpenrouterForUntrainedCollection() {
        registerPrompt("or_prompt");
        cognitionSchema("kb_docs", false);
        llmSecretWithModels("openai", "sk-openai", List.of("gpt-4o-mini"));
        llmSecret("openrouter", "sk-or");
        kit.pathBody(embedPath("openrouter"), "[[0.3]]");
        kit.pathBody(searchPath("kb_docs"), "{\"result\":[]}");
        kit.pathBody(completionPath("openrouter"), COMPLETION_REPLY);

        kit.ok("or_prompt", kit.slots(), kit.latest("q"));
        assertEquals(Kairon.SUCCESS, kit.log("or_prompt").get("status"));
        Map<String, Object> kwargs = asMap(Jsons.readMap(kit.hitPath(embedPath("openrouter")).body()).get("kwargs"));
        assertEquals("kb_docs", kwargs.get("collection"));
        assertEquals("or-embed-model", kwargs.get("model"));
        assertEquals("sk-or", kwargs.get("api_key"));
        assertEquals(2, hitsUnder(completionPath("openrouter")).size());
        assertTrue(hitsUnder(completionPath("openai")).isEmpty());
        assertTrue(hitsUnder(embedPath("openai")).isEmpty());
    }

    private static final String DB_POINTS = "{\"result\":{\"points\":[{\"id\":1,\"payload\":{\"answer\":\"kanban board\"}}]},\"status\":\"ok\"}";

    private String dbQueryPath(String collection) {
        return "/collections/" + kit.bot + "_" + collection + "_faq_embd/points/query";
    }

    private String embedPath(String llmType) {
        return "/" + kit.bot + "/aembedding/" + llmType;
    }

    private void llmSecret(String llmType, String apiKey) {
        kit.put(com.kairon.action.catalog.ActionCatalog.LLM_SECRET, kit.doc("bot", kit.bot, "llm_type", llmType,
                "api_key", tokens.encrypt(apiKey)));
    }

    private void cognitionSchema(String collection, boolean trainingNeeded) {
        kit.put("cognition_schema", kit.doc("bot", kit.bot, "collection_name", collection,
                "schema_metadata", kit.doc("training_needed", trainingNeeded, "model_id", "or-embed-model")));
    }

    /** T-122: embedding via LLM server (openai, embedding secret), then Qdrant points/query without api-key. */
    @Test
    void databaseActionDispatchesResponse() {
        settings.setVectorKey("vec-key");
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true,
                "llm_settings", kit.doc("enable_faq", true, "provider", "anthropic")));
        cognitionSchema("faq", true);
        llmSecret("openai", "sk-openai");
        kit.pathBody(embedPath("openai"), "[[0.1,0.2]]");
        kit.pathBody(dbQueryPath("faq"), DB_POINTS);
        kit.register("faq_lookup", "database_action");
        kit.put("database_action", kit.doc(
                "bot", kit.bot,
                "name", "faq_lookup",
                "status", true,
                "db_type", "qdrant",
                "collection", "faq",
                "payload", List.of(kit.doc("type", "from_value", "value", "kanban", "query_type", "embedding_search")),
                "response", kit.doc("dispatch", true, "dispatch_type", "text",
                        "value", "found: ${data.status}", "evaluation_type", "expression"),
                "set_slots", List.of(kit.doc("name", "answer", "value", "${data.status}", "evaluation_type", "expression")),
                "failure_response", "db failed"
        ));

        Map<String, Object> body = kit.ok("faq_lookup", kit.slots(), kit.latest("what is kanban"));
        assertEquals("found: ok", kit.text(body));
        assertEquals("found: ok", kit.event(body, Kairon.ACTION_RESPONSE).get("value"));
        assertEquals("ok", kit.event(body, "answer").get("value"));

        ParityKit.Hit embed = kit.hitPath(embedPath("openai"));
        assertEquals("POST", embed.method());
        Map<String, Object> embedBody = Jsons.readMap(embed.body());
        assertEquals(List.of("kanban"), embedBody.get("text"));
        assertEquals("default", embedBody.get("user"));
        @SuppressWarnings("unchecked")
        Map<String, Object> kwargs = (Map<String, Object>) embedBody.get("kwargs");
        assertEquals("db_action_qdrant", kwargs.get("invocation"));
        assertFalse(kwargs.containsKey("collection"), "training_needed true: no collection/model kwargs");
        assertEquals("sk-openai", kwargs.get("api_key"));

        ParityKit.Hit query = kit.hitPath(dbQueryPath("faq"));
        assertEquals("POST", query.method());
        assertEquals("{\"query\": [0.1, 0.2], \"with_payload\": true, \"limit\": 10}",
                Jsons.pythonDumps(Jsons.readAny(query.body())));
        assertTrue(ParityKit.API_KEY_PATHS.isEmpty(), "no api-key header: " + ParityKit.API_KEY_PATHS);
        assertTrue(ParityKit.HITS.stream().noneMatch(hit -> hit.path().startsWith("/vector")), "no adapter POST");

        Document log = kit.log("faq_lookup");
        assertEquals("database_action", log.get("type"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
        @SuppressWarnings("unchecked")
        List<Object> messages = (List<Object>) log.get("messages");
        assertEquals(Map.of("embedding_search", "kanban"), messages.get(0));
        @SuppressWarnings("unchecked")
        List<String> composeLog = (List<String>) messages.get(1);
        assertEquals("evaluation_type: expression", composeLog.get(0));
        assertEquals("initiating slot evaluation", messages.get(2));
        assertEquals("{'embedding_search': 'kanban'}", log.get("payload"));
        assertEquals("{'result': {'points': [{'id': 1, 'payload': {'answer': 'kanban board'}}]}, 'status': 'ok'}",
                log.get("response"));
    }

    /** T-122: training_needed false swaps embedding to openrouter (its secret, schema model) after loading openai. */
    @Test
    void databaseActionSwapsToOpenrouterWhenTrainingNotNeeded() {
        registerDatabase("or_db", "qdrant");
        cognitionSchema("faq", false);
        llmSecret("openai", "sk-openai");
        llmSecret("openrouter", "sk-or");
        kit.pathBody(embedPath("openrouter"), "[[0.5]]");
        kit.pathBody(dbQueryPath("faq"), DB_POINTS);

        kit.ok("or_db", kit.slots(), kit.latest("q"));
        assertEquals(Kairon.SUCCESS, kit.log("or_db").get("status"));
        Map<String, Object> embedBody = Jsons.readMap(kit.hitPath(embedPath("openrouter")).body());
        @SuppressWarnings("unchecked")
        Map<String, Object> kwargs = (Map<String, Object>) embedBody.get("kwargs");
        assertEquals("faq", kwargs.get("collection"));
        assertEquals("or-embed-model", kwargs.get("model"));
        assertEquals("sk-or", kwargs.get("api_key"));
        assertTrue(ParityKit.HITS.stream().noneMatch(hit -> hit.path().endsWith("/aembedding/openai")));
    }

    /** T-122: Qdrant ctor loads the openai secret before the schema lookup (Python failure order). */
    @Test
    void databaseActionMissingOpenaiSecretFailsBeforeSchemaLookup() {
        registerDatabase("no_secret", "qdrant");
        kit.ok("no_secret", kit.slots(), kit.latest("q"));
        Document log = kit.log("no_secret");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("LLM secret for 'openai' is not configured!", log.get("exception"));
        assertEquals(List.of(), log.get("messages"));
    }

    /** T-122: missing openrouter secret fails after the schema lookup, before the payload. */
    @Test
    void databaseActionMissingOpenrouterSecretFailsBeforePayload() {
        registerDatabase("no_or", "qdrant");
        cognitionSchema("faq", false);
        llmSecret("openai", "sk-openai");
        kit.ok("no_or", kit.slots(), kit.latest("q"));
        Document log = kit.log("no_or");
        assertEquals("LLM secret for 'openrouter' is not configured!", log.get("exception"));
        assertEquals(List.of(), log.get("messages"));
        assertNull(log.get("payload"));
    }

    /** T-122: Qdrant failure surfaces as the action exception with the failure response dispatched. */
    @Test
    void databaseActionQdrantErrorFails() {
        registerDatabase("q_err", "qdrant");
        cognitionSchema("faq", true);
        llmSecret("openai", "sk-openai");
        kit.pathBody(embedPath("openai"), "[[0.1]]");
        kit.pathBody(dbQueryPath("faq"), "{\"status\":{\"error\":\"boom\"}}");
        kit.pathStatus(dbQueryPath("faq"), 500);
        Map<String, Object> body = kit.ok("q_err", kit.slots(), kit.latest("q"));
        assertEquals("db failed", kit.text(body));
        Document log = kit.log("q_err");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertTrue(String.valueOf(log.get("exception")).startsWith("Failed to execute the url"), String.valueOf(log.get("exception")));
        assertEquals(List.of(Map.of("embedding_search", "kanban")), log.get("messages"));
    }

    private void registerDatabase(String name, String dbType) {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true,
                "llm_settings", kit.doc("enable_faq", true)));
        kit.register(name, "database_action");
        kit.put("database_action", kit.doc("bot", kit.bot, "name", name, "status", true,
                "db_type", dbType, "collection", "faq",
                "payload", List.of(kit.doc("type", "from_value", "value", "kanban", "query_type", "embedding_search")),
                "response", kit.doc("dispatch", true, "dispatch_type", "text", "value", "done", "evaluation_type", "expression"),
                "set_slots", List.of(), "failure_response", "db failed"));
    }

    @Test
    void databaseActionRejectsUnknownDbTypeBeforeBuildingPayload() {
        registerDatabase("bad_db", "mongo");
        kit.ok("bad_db", kit.slots(), kit.latest("q"));
        Document log = kit.log("bad_db");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("Database not yet implemented!", log.get("exception"));
        assertEquals(List.of(), log.get("messages"));
    }

    @Test
    void databaseActionMissingSchemaFailsBeforePayloadIsLogged() {
        registerDatabase("no_schema", "qdrant");
        llmSecret("openai", "sk-openai");
        kit.ok("no_schema", kit.slots(), kit.latest("q"));
        Document log = kit.log("no_schema");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals(com.kairon.action.support.llm.CognitionSchemas.NOT_FOUND, log.get("exception"));
        assertEquals(List.of(), log.get("messages"));
        assertNull(log.get("payload"));
    }

    private static List<String> logKeys(Document log) {
        return log.keySet().stream().filter(key -> !"_id".equals(key)).toList();
    }

    /** T-124: success log = non-null declared fields in R4 order, then config, payload, response, user_msg. */
    @Test
    void databaseActionSuccessLogKeyOrder() {
        registerDatabase("ok_order", "qdrant");
        cognitionSchema("faq", true);
        llmSecret("openai", "sk-openai");
        kit.pathBody(embedPath("openai"), "[[0.1]]");
        kit.pathBody(dbQueryPath("faq"), DB_POINTS);
        Map<String, Object> body = kit.ok("ok_order", kit.slots(), kit.latest("what is kanban"));
        assertEquals("done", kit.text(body));
        Document log = kit.log("ok_order");
        assertEquals(List.of("type", "intent", "action", "sender", "bot_response", "messages", "bot", "timestamp",
                "status", "trigger_info", "request_id", "config", "payload", "response", "user_msg"), logKeys(log));
        assertEquals("done", log.get("bot_response"));
        assertEquals("what is kanban", log.get("user_msg"));
        assertFalse(log.containsKey("exception"), "declared null exception omitted");
    }

    /**
     * T-124: falsy bot_response (failure_response "") is omitted (declared); payload/response stay null (dynamic);
     * dispatch still utters the failure text.
     */
    @Test
    void databaseActionFailureLogOmitsFalsyBotResponseKeepsDynamicNulls() {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true,
                "llm_settings", kit.doc("enable_faq", true)));
        kit.register("empty_fail", "database_action");
        kit.put("database_action", kit.doc("bot", kit.bot, "name", "empty_fail", "status", true,
                "db_type", "mongo", "collection", "faq",
                "payload", List.of(kit.doc("type", "from_value", "value", "kanban", "query_type", "embedding_search")),
                "response", kit.doc("dispatch", true, "dispatch_type", "text", "value", "done", "evaluation_type", "expression"),
                "set_slots", List.of(), "failure_response", ""));
        RecordingFailureMail.CALLS.clear();
        Map<String, Object> body = kit.ok("empty_fail", kit.slots(), kit.latest("q"));
        assertEquals("", kit.text(body));
        assertEquals("", kit.event(body, Kairon.ACTION_RESPONSE).get("value"));
        Document log = kit.log("empty_fail");
        assertEquals(List.of("type", "intent", "action", "sender", "exception", "messages", "bot", "timestamp",
                "status", "trigger_info", "request_id", "config", "payload", "response", "user_msg"), logKeys(log));
        assertTrue(log.containsKey("payload") && log.get("payload") == null);
        assertTrue(log.containsKey("response") && log.get("response") == null);
        assertEquals(1, RecordingFailureMail.CALLS.size());
    }

    /** T-124: missing response / failure_response take mongoengine defaults (dispatch true, default failure text). */
    @Test
    void databaseActionMissingResponseConfigUsesDefaults() {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true,
                "llm_settings", kit.doc("enable_faq", true)));
        kit.register("no_resp", "database_action");
        kit.put("database_action", kit.doc("bot", kit.bot, "name", "no_resp", "status", true,
                "db_type", "mongo", "collection", "faq",
                "payload", List.of(kit.doc("type", "from_value", "value", "kanban", "query_type", "embedding_search"))));
        Map<String, Object> body = kit.ok("no_resp", kit.slots(), kit.latest("q"));
        assertEquals(Kairon.FAILED_DOT, kit.text(body));
        Document log = kit.log("no_resp");
        assertEquals("Database not yet implemented!", log.get("exception"));
        assertEquals(Kairon.FAILED_DOT, log.get("bot_response"));
    }

    /** T-124: response without dispatch / failure_response null -> dispatch true, default failure text. */
    @Test
    void databaseActionResponseWithoutDispatchDispatchesByDefault() {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true,
                "llm_settings", kit.doc("enable_faq", true)));
        kit.register("no_disp", "database_action");
        Document config = kit.doc("bot", kit.bot, "name", "no_disp", "status", true,
                "db_type", "mongo", "collection", "faq",
                "payload", List.of(kit.doc("type", "from_value", "value", "kanban", "query_type", "embedding_search")),
                "response", kit.doc("value", "done"));
        config.put("failure_response", null);
        kit.put("database_action", config);
        Map<String, Object> body = kit.ok("no_disp", kit.slots(), kit.latest("q"));
        assertEquals(Kairon.FAILED_DOT, kit.text(body));
        assertEquals(Kairon.FAILED_DOT, kit.log("no_disp").get("bot_response"));
    }

    /** T-124: dispatch false -> nothing uttered on failure. */
    @Test
    void databaseActionDispatchFalseUttersNothing() {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true,
                "llm_settings", kit.doc("enable_faq", true)));
        kit.register("silent", "database_action");
        kit.put("database_action", kit.doc("bot", kit.bot, "name", "silent", "status", true,
                "db_type", "mongo", "collection", "faq",
                "payload", List.of(kit.doc("type", "from_value", "value", "kanban", "query_type", "embedding_search")),
                "response", kit.doc("dispatch", false, "value", "done"), "failure_response", "db failed"));
        Map<String, Object> body = kit.ok("silent", kit.slots(), kit.latest("q"));
        assertTrue(kit.responses(body).isEmpty(), String.valueOf(body));
        assertEquals("db failed", kit.event(body, Kairon.ACTION_RESPONSE).get("value"));
    }

    /** T-124: FAQ disabled fails before config load: default failure text, not dispatched, failure mail sent. */
    @Test
    void databaseActionFaqDisabledSendsFailureMail() {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true,
                "llm_settings", kit.doc("enable_faq", false)));
        kit.register("faq_off", "database_action");
        RecordingFailureMail.CALLS.clear();
        Map<String, Object> body = kit.ok("faq_off", kit.slots(), kit.latest("q"));
        assertTrue(kit.responses(body).isEmpty(), String.valueOf(body));
        assertEquals(Kairon.FAILED_DOT, kit.event(body, Kairon.ACTION_RESPONSE).get("value"));
        Document log = kit.log("faq_off");
        assertEquals(Kairon.FAQ_DISABLED, log.get("exception"));
        assertEquals(Kairon.FAILED_DOT, log.get("bot_response"));
        assertTrue(log.containsKey("config") && log.get("config") == null);
        assertEquals(List.of("type", "intent", "action", "sender", "bot_response", "exception", "messages", "bot",
                "timestamp", "status", "trigger_info", "request_id", "config", "payload", "response", "user_msg"),
                logKeys(log));
        assertEquals(1, RecordingFailureMail.CALLS.size());
        assertEquals("faq_off", RecordingFailureMail.CALLS.get(0).action());
    }

    // ---- T-028: kairon_bot_response never rephrases ----

    @Test
    void botResponseIgnoresRephraseFlag() {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true, "rephrase_response", true));
        Map<String, Object> domain = Map.of("responses", Map.of("utter_greet", List.of(Map.of("text", "Hello"))));
        Map<String, Object> body = kit.ok("utter_greet", kit.slots(), kit.latest("hi"), List.of(), domain, "default", "utter_greet", null, null);
        assertEquals("utter_greet", kit.responses(body).get(0).get("response"));
        assertEquals(Map.of("response", "utter_greet"), kit.event(body, Kairon.ACTION_RESPONSE).get("value"));
        assertTrue(ParityKit.HITS.stream().noneMatch(hit -> hit.path().contains("/llm")), "no LLM call");
        Document log = kit.log("utter_greet");
        assertEquals("kairon_bot_response", log.get("type"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
        assertEquals(true, log.get("enable_rephrasing"));
        assertEquals(false, log.get("is_rephrased"));
        assertTrue(log.containsKey("raw_gpt_response"), "dynamic raw_gpt_response=None is stored as null");
        assertNull(log.get("raw_gpt_response"));
    }

    @Test
    void botResponseRephraseDisabledDefaults() {
        Map<String, Object> domain = Map.of("responses", Map.of("utter_bye", List.of(Map.of("text", "Bye"))));
        kit.ok("utter_bye", kit.slots(), kit.latest("bye"), List.of(), domain, "default", "utter_bye", null, null);
        Document log = kit.log("utter_bye");
        assertEquals(false, log.get("enable_rephrasing"));
        assertEquals(false, log.get("is_rephrased"));
        assertNull(log.get("raw_gpt_response"));
    }

    @Test
    void botResponseWithoutTemplatesFailsButStillUtters() {
        Map<String, Object> body = kit.ok("utter_missing", kit.slots(), kit.latest("hi"), List.of(),
                Map.of("responses", Map.of()), "default", "utter_missing", null, null);
        assertEquals("utter_missing", kit.responses(body).get(0).get("response"));
        Document log = kit.log("utter_missing");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("Cannot choose from an empty sequence", log.get("exception"));
    }

    // ---- T-029: two-stage text search ----

    private void fallback(int count) {
        kit.register("fallback", "two_stage_fallback");
        kit.put("kairon_two_stage_fallback_action", kit.doc(
                "bot", kit.bot, "name", "fallback", "status", true, "fallback_message", "Try these",
                "text_recommendations", new Document("count", count).append("use_intent_ranking", false)));
        kit.put("training_examples", kit.doc("bot", kit.bot, "text", "flight status please", "status", true, "intent", "status"));
        kit.put("training_examples", kit.doc("bot", kit.bot, "text", "book a flight", "status", true, "intent", "book"));
        kit.put("training_examples", kit.doc("bot", kit.bot, "text", "hotel booking", "status", true, "intent", "hotel"));
        kit.put("training_examples", kit.doc("bot", kit.bot, "text", "cancel flight", "status", false, "intent", "cancel"));
        kit.put("training_examples", kit.doc("bot", "other-bot", "text", "flight", "status", true, "intent", "x"));
    }

    @SuppressWarnings("unchecked")
    private List<String> buttonTexts(Map<String, Object> body) {
        List<Map<String, Object>> buttons = (List<Map<String, Object>>) kit.responses(body).get(0).get("buttons");
        return buttons.stream().map(button -> {
            assertEquals(button.get("text"), button.get("payload"));
            return String.valueOf(button.get("text"));
        }).toList();
    }

    @Test
    void twoStageTextSearchOrderedByScoreAndLimited() {
        fallback(1);
        Map<String, Object> body = kit.ok("fallback", kit.slots(), kit.latest("flights"));
        assertEquals(List.of("book a flight"), buttonTexts(body));
        Document log = kit.log("fallback");
        assertEquals("two_stage_fallback", log.get("type"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
    }

    @Test
    void twoStageTextSearchReturnsAllMatchesUpToCount() {
        fallback(5);
        Map<String, Object> body = kit.ok("fallback", kit.slots(), kit.latest("flight"));
        assertEquals(List.of("book a flight", "flight status please"), buttonTexts(body));
    }

    @Test
    void twoStageTextSearchIsWordBasedNotSubstring() {
        fallback(5);
        Map<String, Object> body = kit.ok("fallback", kit.slots(), kit.latest("fli"));
        assertEquals(Kairon.UTTER_DEFAULT, kit.responses(body).get(0).get("response"));
    }

    @Test
    void memoryTextSearchFiltersAndScores() {
        fallback(5);
        List<Document> found = catalog.searchText("training_examples", kit.bot, "the hotel", 5);
        assertEquals(1, found.size());
        assertEquals("hotel booking", found.get(0).get("text"));
        assertTrue(found.get(0).get("_text_score") instanceof Double);
        assertEquals(List.of(), catalog.searchText("training_examples", kit.bot, "flight -book", 5).stream()
                .map(doc -> doc.get("text")).filter("book a flight"::equals).toList());
        assertEquals(List.of(), catalog.searchText("training_examples", kit.bot, "flight", 0));
    }

    // ---- T-030: google CSE request ----

    private void google(String apiKey, Object website) {
        kit.register("google", "google_search_action");
        kit.put("google_search_action", kit.doc("bot", kit.bot, "name", "google", "status", true,
                "api_key", kit.param("api_key", "value", apiKey), "search_engine_id", "asdfg::567890",
                "num_results", 1, "website", website, "failure_response", "I have failed to process your request",
                "dispatch_response", true));
    }

    private static Map<String, String> query(String raw) {
        Map<String, String> out = new LinkedHashMap<>();
        for (String pair : raw.split("&")) {
            String[] parts = pair.split("=", 2);
            out.put(URLDecoder.decode(parts[0], StandardCharsets.UTF_8),
                    parts.length > 1 ? URLDecoder.decode(parts[1], StandardCharsets.UTF_8) : "");
        }
        return out;
    }

    @Test
    void googleCseQueryMatchesPython() {
        google("KEY-1234", "https://nimblework.com");
        Map<String, Object> body = kit.ok("google", kit.slots(), kit.latest("what is kanban"));
        ParityKit.Hit hit = kit.hitPath("/customsearch/v1");
        assertEquals("GET", hit.method());
        Map<String, String> query = query(hit.query());
        assertEquals(List.of("q", "cx", "num", "key", "alt"), List.copyOf(query.keySet()));
        assertEquals("what is kanban", query.get("q"));
        assertEquals("asdfg::567890", query.get("cx"));
        assertEquals("1", query.get("num"));
        assertEquals("KEY-1234", query.get("key"));
        assertEquals("json", query.get("alt"));
        assertFalse(query.containsKey("siteSearch"), "Python pops website before the CSE call");
        assertTrue(kit.text(body).startsWith("S\nTo know more"));
        assertEquals(Kairon.SUCCESS, kit.log("google").get("status"));
    }

    @Test
    void googleKeylessPathBuildsSiteTermAndFailsClosed() {
        google("", "https://nimblework.com");
        Map<String, Object> body = kit.ok("google", kit.slots(), kit.latest("what is kanban?"));
        assertTrue(ParityKit.HITS.stream().noneMatch(hit -> hit.path().contains("/customsearch")));
        assertEquals("I have failed to process your request", kit.text(body));
        Document log = kit.log("google");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertTrue(String.valueOf(log.get("exception")).contains("'what is kanban? site: https://nimblework.com'"),
                String.valueOf(log.get("exception")));
    }

    // ---- T-031: voice provider initiate-call ----

    private void voiceAction() {
        kit.register("call_me", "voice_call_action");
        kit.put("voice_call_action", kit.doc("bot", kit.bot, "name", "call_me", "status", true,
                "to_phone_number", kit.doc("parameter_type", "slot", "value", "phone")));
    }

    private void voiceChannel(String provider, boolean withToken) {
        Document config = kit.doc("telephony_provider", provider, "account_sid", tokens.encrypt("AC123"),
                "phone_number", "+15550000000", "call_url", "https://kairon.test/voice/call",
                "status_url", "https://kairon.test/voice/status");
        if (withToken) {
            config.put("auth_token", "twilio".equals(provider) ? tokens.encrypt("tok-secret") : "tok-secret");
        }
        kit.put("channels", kit.doc("bot", kit.bot, "connector_type", "voice", "config", config));
    }

    @Test
    void twilioInitiateCallRequestAndChannelLog() {
        voiceAction();
        voiceChannel("twilio", true);
        kit.pathBody("/Calls.json", "{\"sid\":\"CA999\",\"status\":\"queued\"}");
        Map<String, Object> body = kit.ok("call_me", kit.slots("phone", "+919999999999"), kit.latest("call me"));

        ParityKit.Hit hit = kit.hitPath("/Calls.json");
        assertEquals("POST", hit.method());
        assertEquals("/2010-04-01/Accounts/AC123/Calls.json", hit.path());
        assertEquals(HttpCaller.basic("AC123", "tok-secret"), hit.auth());
        Map<String, String> form = query(hit.body());
        assertEquals("+919999999999", form.get("To"));
        assertEquals("+15550000000", form.get("From"));
        assertEquals("https://kairon.test/voice/call", form.get("Url"));
        assertEquals("https://kairon.test/voice/status", form.get("StatusCallback"));
        assertEquals("POST", form.get("StatusCallbackMethod"));
        assertTrue(ParityKit.HITS.stream().noneMatch(h -> h.path().equals("/voice")), "generic voiceCallUrl not used");

        List<Document> channelLogs = catalog.all("channel_logs");
        assertEquals(1, channelLogs.size());
        Document log = channelLogs.get(0);
        assertEquals("voice", log.get("type"));
        assertEquals("initiated", log.get("status"));
        assertEquals(Map.of("to", "+919999999999", "call_sid", "CA999"), Map.copyOf((Map<String, Object>) log.get("data")));
        assertEquals("CA999", log.get("message_id"));
        assertEquals(kit.bot, log.get("bot"));
        assertEquals("system", log.get("user"));
        assertEquals("bot", log.get("initiator"));

        assertEquals("I'm placing a call to you now.", kit.text(body));
        assertEquals(Kairon.SUCCESS, kit.log("call_me").get("status"));
        assertEquals("voice_call_action", kit.log("call_me").get("type"));
    }

    @Test
    void twilioErrorFailsTheCall() {
        voiceAction();
        voiceChannel("twilio", true);
        kit.pathStatus("/Calls.json", 401);
        kit.pathBody("/Calls.json", "{\"code\":20003,\"message\":\"Authenticate\",\"status\":401}");
        Map<String, Object> body = kit.ok("call_me", kit.slots("phone", "+919999999999"), kit.latest("call me"));
        assertEquals(Kairon.CALL_FAIL, kit.text(body));
        Document log = kit.log("call_me");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("HTTP 401 error: Unable to create record: Authenticate", log.get("exception"));
        assertTrue(catalog.all("channel_logs").isEmpty());
    }

    @Test
    void missingAuthTokenIsKeyError() {
        voiceAction();
        voiceChannel("twilio", false);
        kit.ok("call_me", kit.slots("phone", "+919999999999"), kit.latest("call me"));
        assertEquals("'auth_token'", kit.log("call_me").get("exception"));
        assertTrue(ParityKit.HITS.isEmpty());
    }

    @Test
    void missingChannelFails() {
        voiceAction();
        kit.ok("call_me", kit.slots("phone", "+919999999999"), kit.latest("call me"));
        assertEquals("Channels matching query does not exist.", kit.log("call_me").get("exception"));
    }

    @Test
    void exotelInitiateCallRequest() {
        voiceAction();
        voiceChannel("exotel", true);
        kit.pathBody("/Calls/connect.json", "{\"Call\":{\"Sid\":\"EX42\"}}");
        kit.ok("call_me", kit.slots("phone", "+919999999999"), kit.latest("call me"));
        ParityKit.Hit hit = kit.hitPath("/Calls/connect.json");
        assertEquals("/v1/Accounts/AC123/Calls/connect.json", hit.path());
        assertEquals(HttpCaller.basic("AC123", "tok-secret"), hit.auth());
        Map<String, String> form = query(hit.body());
        assertEquals("+919999999999", form.get("From"));
        assertEquals("+15550000000", form.get("CallerId"));
        assertEquals("https://kairon.test/voice/call", form.get("Url"));
        assertEquals("https://kairon.test/voice/status", form.get("StatusCallback"));
        assertEquals("EX42", catalog.all("channel_logs").get(0).get("message_id"));
    }

    @Test
    void maskFollowsPythonStrategyFromRight() {
        assertEquals("", support.mask(""));
        assertEquals("****", support.mask("abcd"));
        assertEquals("*****fg", support.mask("abcdefg"));
        String strategy = settings.getUnmaskedCharStrategy();
        try {
            settings.setUnmaskedCharStrategy("from_left");
            assertEquals("ab*****", support.mask("abcdefg"));
        } finally {
            settings.setUnmaskedCharStrategy(strategy);
        }
    }

    private static TrackerState trackerWith(Map<String, Object> latest) {
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("sender_id", "u");
        raw.put("slots", Map.of());
        raw.put("latest_message", latest);
        raw.put("events", List.of());
        return TrackerState.from(raw);
    }

    @Test
    void intentSkipsNluFallbackOnlyWhenAskedAndIsNullWithoutRanking() {
        Map<String, Object> latest = new LinkedHashMap<>();
        latest.put("intent", Map.of("name", "nlu_fallback"));
        latest.put("intent_ranking", List.of(Map.of("name", "nlu_fallback"), Map.of("name", "greet")));
        TrackerState tracker = trackerWith(latest);
        assertEquals("nlu_fallback", tracker.intent());
        assertEquals("greet", tracker.intent(true));
        assertNull(trackerWith(Map.of("intent", Map.of("name", "greet"))).intent(true));
        latest.put("intent_ranking", List.of(Map.of("name", "nlu_fallback")));
        assertNull(trackerWith(latest).intent(true));
    }

    @Test
    void placeholderWithMissingKeyFailsLikePython() {
        Map<String, Object> response = Map.of("a", Map.of("b", 1));
        assertEquals("1", support.prepareResponse("${a.b}", response));
        ActionFailure failure = org.junit.jupiter.api.Assertions.assertThrows(ActionFailure.class,
                () -> support.prepareResponse("${a.missing}", response));
        assertTrue(failure.getMessage().startsWith("Unable to retrieve value for key from HTTP response"));
    }

    // ---- agent_action parity with master 4f0a2fd5 (chat history in payload, max_iterations 5) ----

    private void registerAgent(String name, boolean dispatch) {
        kit.register(name, "agent_action");
        kit.put("agent_action_config", kit.doc("bot", kit.bot, "name", name, "status", true,
                "agent_id", "agent-1", "dispatch_bot_response", dispatch));
    }

    private static Map<String, Object> turn(String event, String text) {
        Map<String, Object> turn = new LinkedHashMap<>();
        turn.put("event", event);
        turn.put("text", text);
        return turn;
    }

    @Test
    void agentActionPrefixesChatHistoryAndSendsFiveIterations() {
        registerAgent("ask_agent", true);
        List<Object> events = List.of(turn("user", "u1"), turn("bot", "b1"), turn("user", "current"));
        Map<String, Object> body = kit.ok("ask_agent", kit.slots(), kit.latest("current"), events, Map.of(),
                "default", "ask_agent", null, null);
        assertEquals("agent-out", kit.text(body));
        String sent = kit.hitPath("/agent").body();
        Map<String, Object> request = Jsons.readMap(sent);
        assertEquals("Conversation history:\nuser: u1\nassistant: b1\n\nCurrent message: current", request.get("message"));
        assertEquals(5, ((Number) request.get("max_iterations")).intValue());
        assertNull(request.get("session_id"));
        assertEquals(Map.of(), request.get("metadata"));
    }

    @Test
    void agentActionKeepsOnlyLastFiveHistoryMessages() {
        registerAgent("ask_agent", true);
        List<Object> events = new java.util.ArrayList<>();
        for (int i = 0; i < 6; i++) {
            events.add(turn("user", "u" + i));
            events.add(turn("bot", "b" + i));
        }
        events.add(turn("user", "current"));
        kit.ok("ask_agent", kit.slots(), kit.latest("current"), events, Map.of(), "default", "ask_agent", null, null);
        String message = (String) Jsons.readMap(kit.hitPath("/agent").body()).get("message");
        assertTrue(message.startsWith("Conversation history:\nassistant: b3\n"), message);
        assertTrue(message.endsWith("assistant: b5\n\nCurrent message: current"), message);
        assertEquals(5, message.lines().filter(line -> line.startsWith("user: ") || line.startsWith("assistant: ")).count());
    }

    @Test
    void agentActionWithoutHistorySendsPlainMessage() {
        registerAgent("ask_agent", true);
        kit.ok("ask_agent", kit.slots(), kit.latest("hi"), List.of(turn("user", "hi")), Map.of(), "default", "ask_agent", null, null);
        assertEquals("hi", Jsons.readMap(kit.hitPath("/agent").body()).get("message"));
    }

    @Test
    void agentActionLogsApiResponseAsPythonRepr() {
        registerAgent("ask_agent", true);
        kit.ok("ask_agent");
        assertEquals("{'output': 'agent-out'}", kit.log("ask_agent").get("api_response"));
    }

    @Test
    void agentActionDispatchFalseUttersNothing() {
        registerAgent("quiet_agent", false);
        Map<String, Object> body = kit.ok("quiet_agent");
        assertEquals(List.of(), kit.responses(body));
        assertEquals("agent-out", kit.event(body, Kairon.ACTION_RESPONSE).get("value"));
    }

    @Test
    void agentActionStripsEveryTrailingSlashFromBaseUrl() {
        registerAgent("ask_agent", true);
        String original = settings.getSimpleAgentUrl();
        try {
            settings.setSimpleAgentUrl(original + "///");
            kit.ok("ask_agent");
            assertTrue(kit.hitPath("/agent").path().startsWith("/agent/agents/"), kit.hitPath("/agent").path());
        } finally {
            settings.setSimpleAgentUrl(original);
        }
    }
}
