package com.kairon.action;

import com.kairon.action.actions.ActionFactory;
import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.catalog.MemoryActionCatalog;
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

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * T-127: end-to-end prompt_action / database_action scenarios through {@code POST /webhook} against stubbed LLM server
 * ({@code /{bot}/aembedding/{type}}, {@code /{bot}/completion/{type}}) and Qdrant
 * ({@code /collections/{name}/points/search}, {@code /points/query}) endpoints. The LLM server is the sequential
 * parity stub; Qdrant is the thread-pooled stub so concurrent similarity searches can be proven with a barrier.
 */
@MicronautTest
class PromptDatabaseE2ETest {

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
        // Qdrant on the concurrent stub (same handler / HITS), LLM server on the sequential stub
        settings.setVectorDb(ParityKit.concurrentStubUrl);
        settings.setVectorKey("vec-key");
        RecordingFailureMail.CALLS.clear();
    }

    // ---------------------------------------------------------------- fixtures

    private static final String SENDER = "user-42";
    private static final String QUESTION = "what is kanban";
    private static final String REPHRASED = "Explain kanban boards";
    private static final String ANSWER = "Kanban is a visual board.";
    private static final String REPHRASE_REPLY =
            "{\"formatted_response\":\"" + REPHRASED + "\",\"response\":{\"litellm_call_id\":\"rephrase-1\"}}";
    private static final String ANSWER_REPLY =
            "{\"formatted_response\":\"" + ANSWER + "\",\"response\":{\"litellm_call_id\":\"call-99\"}}";
    private static final Map<String, Object> HYPERPARAMETERS = orderedMap("model", "gpt-4o-mini", "temperature", 0.0,
            "top_p", 0.9);

    private static final String SYSTEM = "You are helpful\n";
    private static final String QUERY_PROMPT = "q:\nAnswer using KB\nInstructions on how to use q:\nstrict\n\n";
    private static final String SLOT_SECTION = "Plan:\nGold\n";
    private static final String CRUD_SECTION = "Collection data for orders:\n[{'id': 1, 'item': 'board'}]\n"
            + "Instructions on how to use collection orders:\nuse orders\n\n";
    private static final String HTTP_SECTION = "Http:\ntest_data\n";
    private static final String KB_BLOCK = "Instructions on how to use kb:\n['kanban is a board']\ncite\n";
    private static final String POLICY_BLOCK = "Instructions on how to use policies:\n[{'rule': 'wip limits'}]\nfollow policy\n";
    private static final String SIMILARITY_CONTEXT =
            SLOT_SECTION + CRUD_SECTION + HTTP_SECTION + "\n" + KB_BLOCK + "\n" + POLICY_BLOCK;

    private static Map<String, Object> orderedMap(Object... pairs) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i + 1 < pairs.length; i += 2) {
            map.put(String.valueOf(pairs[i]), pairs[i + 1]);
        }
        return map;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        return (Map<String, Object>) value;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> asMaps(Object value) {
        return (List<Map<String, Object>>) value;
    }

    private static List<String> keys(Object map) {
        return new ArrayList<>(asMap(map).keySet());
    }

    private String embedPath(String llmType) {
        return "/" + kit.bot + "/aembedding/" + llmType;
    }

    private String completionPath(String llmType) {
        return "/" + kit.bot + "/completion/" + llmType;
    }

    private String searchPath(String collectionPart) {
        return "/collections/" + kit.bot + collectionPart + "_faq_embd/points/search";
    }

    private String queryPath(String collection) {
        return "/collections/" + kit.bot + "_" + collection + "_faq_embd/points/query";
    }

    private List<ParityKit.Hit> hits(String path) {
        return ParityKit.HITS.stream().filter(hit -> hit.path().equals(path)).toList();
    }

    private int indexOf(ParityKit.Hit hit) {
        return ParityKit.HITS.indexOf(hit);
    }

    private void faq(boolean enabled) {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true,
                "llm_settings", kit.doc("enable_faq", enabled)));
    }

    private void openaiSecret(List<String> models) {
        kit.put(ActionCatalog.LLM_SECRET, kit.doc("bot", kit.bot, "llm_type", "openai",
                "api_key", tokens.encrypt("sk-openai"), "models", models));
    }

    private void cognitionSchema(String collection, boolean trainingNeeded) {
        kit.put("cognition_schema", kit.doc("bot", kit.bot, "collection_name", collection,
                "schema_metadata", kit.doc("training_needed", trainingNeeded, "model_id", "or-embed-model")));
    }

    private void crudData() {
        kit.put(ActionCatalog.COGNITION_DATA, kit.doc("bot", kit.bot, "collection_name", "orders",
                "is_secure", List.of(), "data", kit.doc("id", 1, "item", "board"),
                "filterable_attrs", List.of(kit.doc("k", "status", "v", "open"))));
        kit.put(ActionCatalog.COGNITION_DATA, kit.doc("bot", kit.bot, "collection_name", "orders",
                "is_secure", List.of(), "data", kit.doc("id", 2, "item", "card"),
                "filterable_attrs", List.of(kit.doc("k", "status", "v", "closed"))));
    }

    /**
     * prompt_action with system + history + two bot_content sources (kb_docs, default) + slot + crud + nested http
     * action + query prompt, plus one disabled prompt that must not reach the LLM.
     */
    private void registerFullPrompt(String name) {
        kit.register(name, "prompt_action");
        kit.register("kb_http", "http_action");
        kit.put("http_action_config", kit.doc("bot", kit.bot, "action_name", "kb_http", "status", true,
                "http_url", ParityKit.STUB + "/mock", "request_method", "GET", "content_type", "json",
                "response", kit.doc("dispatch", false, "dispatch_type", "text",
                        "value", "${data.data}", "evaluation_type", "expression")));
        crudData();
        kit.put("prompt_action", kit.doc(
                "bot", kit.bot,
                "name", name,
                "status", true,
                "llm_type", "openai",
                "process_media", true,
                "num_bot_responses", 2,
                "instructions", List.of("be concise"),
                "user_question", kit.doc("type", "from_user_message"),
                "llm_prompts", List.of(
                        kit.doc("type", "system", "name", "sys", "data", "You are helpful", "source", "static", "is_enabled", true),
                        kit.doc("type", "user", "name", "History", "source", "history", "data", "", "is_enabled", true),
                        kit.doc("type", "user", "name", "kb", "source", "bot_content", "data", "kb_docs",
                                "instructions", "cite", "is_enabled", true,
                                "hyperparameters", kit.doc("top_results", 5, "similarity_threshold", 0.8)),
                        kit.doc("type", "user", "name", "policies", "source", "bot_content", "data", "default",
                                "instructions", "follow policy", "is_enabled", true),
                        kit.doc("type", "user", "name", "Plan", "source", "slot", "data", "plan", "is_enabled", true),
                        kit.doc("type", "user", "name", "orders", "source", "crud", "is_enabled", true,
                                "instructions", "use orders",
                                "crud_config", kit.doc("collections", List.of("orders"),
                                        "query", kit.doc("status", "open"), "result_limit", 2)),
                        kit.doc("type", "user", "name", "Http", "source", "action", "data", "kb_http", "is_enabled", true),
                        kit.doc("type", "user", "name", "off", "source", "static", "data", "never sent", "is_enabled", false),
                        kit.doc("type", "query", "name", "q", "source", "static", "data", "Answer using KB",
                                "instructions", "strict", "is_enabled", true)),
                "hyperparameters", kit.doc("model", "gpt-4o-mini", "temperature", 0.0, "top_p", 0.9),
                "set_slots", List.of(kit.doc("name", "answer", "value", "${data}", "evaluation_type", "expression")),
                "dispatch_response", true,
                "failure_message", "prompt fallback"));
    }

    private void llmAndQdrantOk() {
        kit.pathBody(embedPath("openai"), "[[0.1,0.2,0.3]]");
        kit.pathSequence(completionPath("openai"), REPHRASE_REPLY, ANSWER_REPLY);
        kit.pathBody(searchPath("_kb_docs"),
                "{\"result\":[{\"id\":1,\"score\":0.9,\"payload\":{\"content\":\"kanban is a board\",\"collection_name\":\"kb_docs\"}}]}");
        kit.pathBody(searchPath(""),
                "{\"result\":[{\"id\":7,\"score\":0.8,\"payload\":{\"rule\":\"wip limits\",\"collection_name\":\"default\"}}]}");
    }

    private List<Map<String, Object>> conversation() {
        return List.of(
                orderedMap("event", "session_started"),
                orderedMap("event", "user", "text", "hi"),
                orderedMap("event", "bot", "text", "Hello! Ask me anything."),
                orderedMap("event", "user", "text", QUESTION));
    }

    private Map<String, Object> postPrompt(String name) {
        return kit.ok(name, kit.slots("plan", "Gold", "media_ids", List.of("m1", "m2")), kit.latest(QUESTION),
                conversation(), Map.of(), SENDER, name, null, null);
    }

    // ---------------------------------------------------------------- (1) prompt_action happy path

    @Test
    void promptActionFullPipelineThroughWebhook() {
        faq(true);
        registerFullPrompt("kb_answer");
        cognitionSchema("kb_docs", true);
        openaiSecret(List.of("gpt-4o-mini"));
        llmAndQdrantOk();
        ParityKit.barrier = ParityKit.Barrier.of("/points/search", 2);

        Map<String, Object> body = postPrompt("kb_answer");

        // ---- webhook envelope: one text message, no buttons; slot events for set_slots + system slots
        assertEquals(List.of("events", "responses"), keys(body));
        List<Map<String, Object>> responses = kit.responses(body);
        assertEquals(1, responses.size(), String.valueOf(responses));
        assertEquals(ANSWER, responses.get(0).get("text"));
        assertEquals(List.of(), responses.get(0).get("buttons"));
        assertEquals(ANSWER, kit.slotValue(body, "answer"));
        assertEquals(ANSWER, kit.slotValue(body, Kairon.ACTION_RESPONSE));
        assertEquals("call-99", kit.slotValue(body, Kairon.LLM_CALL_ID));
        List<Map<String, Object>> slotEvents = asMaps(body.get("events"));
        assertEquals(List.of("answer", Kairon.ACTION_RESPONSE, Kairon.LLM_CALL_ID),
                slotEvents.stream().map(event -> event.get("name")).toList());
        assertTrue(slotEvents.stream().allMatch(event -> "slot".equals(event.get("event"))), String.valueOf(slotEvents));

        // ---- call order: nested http, ONE embedding, two searches, rephrase completion, answer completion
        List<ParityKit.Hit> embeds = hits(embedPath("openai"));
        assertEquals(1, embeds.size(), "exactly one embedding request");
        List<ParityKit.Hit> kbSearch = hits(searchPath("_kb_docs"));
        List<ParityKit.Hit> defaultSearch = hits(searchPath(""));
        assertEquals(1, kbSearch.size());
        assertEquals(1, defaultSearch.size());
        assertEquals(2, ParityKit.HITS.stream().filter(hit -> hit.path().startsWith("/collections")).count(),
                "only the two named collections are searched: " + ParityKit.HITS);
        List<ParityKit.Hit> completions = hits(completionPath("openai"));
        assertEquals(2, completions.size());
        int embedAt = indexOf(embeds.get(0));
        assertTrue(indexOf(hits("/mock").get(0)) < embedAt, "nested action runs while params are built");
        assertTrue(embedAt < indexOf(kbSearch.get(0)) && embedAt < indexOf(defaultSearch.get(0)));
        assertTrue(Math.max(indexOf(kbSearch.get(0)), indexOf(defaultSearch.get(0))) < indexOf(completions.get(0)));
        assertTrue(ParityKit.HITS.stream().filter(hit -> !hit.path().equals("/mock"))
                .allMatch(hit -> "POST".equals(hit.method())), "LLM server and Qdrant calls are POSTs");
        // both searches were in flight at the same time (barrier released only when both arrived)
        assertEquals(0, ParityKit.barrier.timeouts().get(), "similarity searches did not overlap");

        // ---- embedding body: original user question, sender, kwargs (training_needed true: no collection/model)
        Map<String, Object> embedBody = Jsons.readMap(embeds.get(0).body());
        assertEquals(List.of("text", "user", "kwargs"), keys(embedBody));
        assertEquals(List.of(QUESTION), embedBody.get("text"));
        assertEquals(SENDER, embedBody.get("user"));
        Map<String, Object> kwargs = asMap(embedBody.get("kwargs"));
        assertEquals(List.of("invocation", "truncated_texts", "api_key"), keys(kwargs));
        assertEquals("prompt_action", kwargs.get("invocation"));
        assertEquals(List.of(QUESTION), kwargs.get("truncated_texts"));
        assertEquals("sk-openai", kwargs.get("api_key"));

        // ---- searches: same vector, per-source limit/threshold, api-key header (vector.key set)
        Map<String, Object> kbBody = Jsons.readMap(kbSearch.get(0).body());
        assertEquals(List.of("vector", "limit", "with_payload", "score_threshold"), keys(kbBody));
        assertEquals(List.of(0.1, 0.2, 0.3), kbBody.get("vector"));
        assertEquals(5, ((Number) kbBody.get("limit")).intValue());
        assertEquals(true, kbBody.get("with_payload"));
        assertEquals(0.8, ((Number) kbBody.get("score_threshold")).doubleValue(), 1e-9);
        Map<String, Object> defaultBody = Jsons.readMap(defaultSearch.get(0).body());
        assertEquals(List.of(0.1, 0.2, 0.3), defaultBody.get("vector"));
        assertEquals(10, ((Number) defaultBody.get("limit")).intValue());
        assertEquals(0.7, ((Number) defaultBody.get("score_threshold")).doubleValue(), 1e-9);
        assertTrue(ParityKit.API_KEY_PATHS.containsAll(List.of(searchPath("_kb_docs"), searchPath(""))),
                String.valueOf(ParityKit.API_KEY_PATHS));

        // ---- rephrase completion
        List<Map<String, Object>> rephraseMessages = List.of(
                orderedMap("role", "system", "content", SYSTEM),
                orderedMap("role", "user", "content", QUERY_PROMPT + "\n\n Q: " + QUESTION + "\n A:"));
        Map<String, Object> rephrase = Jsons.readMap(completions.get(0).body());
        assertEquals(List.of("messages", "hyperparameters", "user", "invocation", "media_ids", "should_process_media"),
                keys(rephrase));
        assertEquals(rephraseMessages, rephrase.get("messages"));
        assertEquals(HYPERPARAMETERS, rephrase.get("hyperparameters"));
        assertEquals(List.of("model", "temperature", "top_p"), keys(rephrase.get("hyperparameters")));
        assertEquals(SENDER, rephrase.get("user"));
        assertEquals("prompt_action_rephrase", rephrase.get("invocation"));
        assertEquals(List.of(), rephrase.get("media_ids"));
        assertEquals(false, rephrase.get("should_process_media"));

        // ---- answer completion: system, history (last 2 bot turns window), user block with every source
        String userBlock = SIMILARITY_CONTEXT + " \nbe concise \nQ: " + REPHRASED + " \nA:";
        List<Map<String, Object>> answerMessages = List.of(
                orderedMap("role", "system", "content", SYSTEM),
                orderedMap("role", "user", "content", "hi"),
                orderedMap("role", "assistant", "content", "Hello! Ask me anything."),
                orderedMap("role", "user", "content", QUESTION),
                orderedMap("role", "user", "content", userBlock));
        Map<String, Object> main = Jsons.readMap(completions.get(1).body());
        assertEquals(List.of("messages", "hyperparameters", "user", "invocation", "media_ids", "should_process_media"),
                keys(main));
        assertEquals(answerMessages, main.get("messages"));
        assertFalse(String.valueOf(main.get("messages")).contains("never sent"), "disabled prompt excluded");
        assertEquals(HYPERPARAMETERS, main.get("hyperparameters"));
        assertEquals(SENDER, main.get("user"));
        assertEquals("prompt_action", main.get("invocation"));
        assertEquals(List.of("m1", "m2"), main.get("media_ids"));
        assertEquals(true, main.get("should_process_media"));

        // ---- action_server_logs record
        Document log = kit.log("kb_answer");
        assertEquals(List.of("type", "intent", "action", "sender", "bot_response", "bot", "timestamp", "status",
                        "trigger_info", "request_id", "events", "recommendations", "llm_response",
                        "kairon_faq_action_config", "llm_logs", "user_msg", "media_ids", "time_elapsed", "llm_call_id"),
                log.keySet().stream().filter(key -> !"_id".equals(key)).toList());
        assertEquals("prompt_action", log.get("type"));
        assertEquals("greet", log.get("intent"));
        assertEquals(SENDER, log.get("sender"));
        assertEquals(ANSWER, log.get("bot_response"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
        assertFalse(log.containsKey("exception"));
        assertNull(log.get("recommendations"));
        assertEquals(QUESTION, log.get("user_msg"));
        assertEquals(List.of("m1", "m2"), log.get("media_ids"));
        assertEquals("call-99", log.get("llm_call_id"));

        Map<String, Object> llmResponse = asMap(log.get("llm_response"));
        assertEquals(List.of("content", "similarity_context", "litellm_call_id"), keys(llmResponse));
        assertEquals(ANSWER, llmResponse.get("content"));
        assertEquals(SIMILARITY_CONTEXT, llmResponse.get("similarity_context"));
        assertEquals("call-99", llmResponse.get("litellm_call_id"));

        List<Map<String, Object>> llmLogs = asMaps(log.get("llm_logs"));
        assertEquals(List.of("rephrase_query", "answer_query"), llmLogs.stream().map(entry -> entry.get("type")).toList());
        for (Map<String, Object> entry : llmLogs) {
            assertEquals(List.of("messages", "raw_completion_response", "type", "hyperparameters"), keys(entry));
            assertEquals(HYPERPARAMETERS, entry.get("hyperparameters"));
        }
        assertEquals(rephraseMessages, llmLogs.get(0).get("messages"));
        assertEquals(Map.of("litellm_call_id", "rephrase-1"), llmLogs.get(0).get("raw_completion_response"));
        assertEquals(answerMessages, llmLogs.get(1).get("messages"));
        assertEquals(Map.of("litellm_call_id", "call-99"), llmLogs.get(1).get("raw_completion_response"));
        assertFalse(String.valueOf(llmLogs).contains("sk-openai"), "secrets never logged");

        List<Map<String, Object>> events = asMaps(log.get("events"));
        assertEquals(2, events.size());
        assertEquals(List.of("type", "response", "llm_response_log", "time_elapsed"), keys(events.get(0)));
        assertEquals("llm_response", events.get(0).get("type"));
        assertEquals(ANSWER, events.get(0).get("response"));
        assertEquals(llmResponse, events.get(0).get("llm_response_log"));
        assertEquals(List.of("type", "data", "slot_eval_log", "time_elapsed"), keys(events.get(1)));
        assertEquals("slots_to_fill", events.get(1).get("type"));
        assertEquals(Map.of("answer", ANSWER), events.get(1).get("data"));
        double prediction = ((Number) events.get(0).get("time_elapsed")).doubleValue();
        double slots = ((Number) events.get(1).get("time_elapsed")).doubleValue();
        assertTrue(prediction > 0);
        assertEquals(prediction + slots, ((Number) log.get("time_elapsed")).doubleValue(), 1e-9);

        // ---- logged config: to_mongo() view, no _id, declared field order
        Map<String, Object> config = asMap(log.get("kairon_faq_action_config"));
        assertFalse(config.containsKey("_id"));
        assertEquals(List.of("name", "num_bot_responses", "failure_message", "user_question", "bot", "timestamp",
                "llm_type", "hyperparameters", "llm_prompts", "instructions", "set_slots", "dispatch_response",
                "process_media", "status"), keys(config));
        assertEquals("kb_answer", config.get("name"));
        assertEquals(2, config.get("num_bot_responses"));
        assertEquals("prompt fallback", config.get("failure_message"));
        assertEquals(9, asMaps(config.get("llm_prompts")).size());
        assertEquals(List.of("be concise"), config.get("instructions"));

        assertTrue(RecordingFailureMail.CALLS.isEmpty(), "no failure mail on success");
    }

    // ---------------------------------------------------------------- (2) database_action

    private static final String DB_POINTS = "{\"result\":{\"points\":[{\"id\":3,\"score\":0.91,"
            + "\"payload\":{\"answer\":\"A kanban board visualises work\"}}]},\"status\":\"ok\",\"time\":0.002}";

    private void registerDatabase(String name) {
        kit.register(name, "database_action");
        kit.put("database_action", kit.doc(
                "bot", kit.bot,
                "name", name,
                "status", true,
                "db_type", "qdrant",
                "collection", "faq",
                "payload", List.of(
                        kit.doc("type", "from_user_message", "value", "ignored", "query_type", "embedding_search"),
                        kit.doc("type", "from_slot", "value", "topic", "query_type", "embedding_search"),
                        kit.doc("type", "from_value", "query_type", "payload_search",
                                "value", "{\"filter\": {\"must\": [{\"key\": \"plan\", \"match\": {\"value\": \"gold\"}}]}, \"limit\": 3}")),
                "response", kit.doc("value", "Lookup ${data.status}", "dispatch", true,
                        "evaluation_type", "expression", "dispatch_type", "text"),
                "set_slots", List.of(kit.doc("name", "db_status", "value", "${data.status}", "evaluation_type", "expression")),
                "failure_response", "db fallback"));
    }

    @Test
    void databaseActionEmbeddingAndPayloadSearchThroughWebhook() {
        faq(true);
        registerDatabase("kb_lookup");
        cognitionSchema("faq", true);
        openaiSecret(List.of("gpt-4o-mini"));
        kit.pathBody(embedPath("openai"), "[[0.4,0.5]]");
        kit.pathBody(queryPath("faq"), DB_POINTS);

        Map<String, Object> body = kit.ok("kb_lookup", kit.slots("topic", "boards"), kit.latest(QUESTION),
                List.of(), Map.of(), SENDER, "kb_lookup", null, null);

        // envelope: composed response dispatched, set_slots + kairon_action_response
        assertEquals(List.of("events", "responses"), keys(body));
        assertEquals(1, kit.responses(body).size());
        assertEquals("Lookup ok", kit.text(body));
        assertEquals("ok", kit.slotValue(body, "db_status"));
        assertEquals("Lookup ok", kit.slotValue(body, Kairon.ACTION_RESPONSE));
        assertEquals(List.of("db_status", Kairon.ACTION_RESPONSE),
                asMaps(body.get("events")).stream().map(event -> event.get("name")).toList());

        // one embedding of the joined embedding_search text (invocation db_action_qdrant), then one query
        List<ParityKit.Hit> embeds = hits(embedPath("openai"));
        assertEquals(1, embeds.size());
        Map<String, Object> embedBody = Jsons.readMap(embeds.get(0).body());
        assertEquals(List.of(QUESTION + " boards"), embedBody.get("text"));
        assertEquals(SENDER, embedBody.get("user"));
        assertEquals("db_action_qdrant", asMap(embedBody.get("kwargs")).get("invocation"));
        assertEquals("sk-openai", asMap(embedBody.get("kwargs")).get("api_key"));
        List<ParityKit.Hit> queries = hits(queryPath("faq"));
        assertEquals(1, queries.size());
        assertTrue(indexOf(embeds.get(0)) < indexOf(queries.get(0)));
        assertEquals("POST", queries.get(0).method());
        assertEquals("{\"query\": [0.4, 0.5], \"filter\": {\"must\": [{\"key\": \"plan\", \"match\": {\"value\": \"gold\"}}]}, "
                        + "\"limit\": 3, \"with_payload\": true}",
                Jsons.pythonDumps(Jsons.readAny(queries.get(0).body())));
        assertTrue(ParityKit.API_KEY_PATHS.isEmpty(), "points/query never sends api-key: " + ParityKit.API_KEY_PATHS);
        assertTrue(ParityKit.HITS.stream().noneMatch(hit -> hit.path().contains("/completion/")), "no completion");

        // log
        Document log = kit.log("kb_lookup");
        // declared ActionServerLogs fields first (messages is declared after exception), then dynamic ones
        assertEquals(List.of("type", "intent", "action", "sender", "bot_response", "messages", "bot", "timestamp",
                        "status", "trigger_info", "request_id", "config", "payload", "response", "user_msg"),
                log.keySet().stream().filter(key -> !"_id".equals(key)).toList());
        assertEquals("database_action", log.get("type"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
        assertEquals("Lookup ok", log.get("bot_response"));
        assertEquals(SENDER, log.get("sender"));
        assertEquals(QUESTION, log.get("user_msg"));
        assertEquals("{'embedding_search': 'what is kanban boards', 'payload_search': {'filter': {'must': "
                + "[{'key': 'plan', 'match': {'value': 'gold'}}]}, 'limit': 3}}", log.get("payload"));
        assertEquals("{'result': {'points': [{'id': 3, 'score': 0.91, 'payload': {'answer': "
                + "'A kanban board visualises work'}}]}, 'status': 'ok', 'time': 0.002}", log.get("response"));
        List<?> messages = (List<?>) log.get("messages");
        assertEquals(Map.of("embedding_search", "what is kanban boards", "payload_search",
                Map.of("filter", Map.of("must", List.of(Map.of("key", "plan", "match", Map.of("value", "gold")))),
                        "limit", 3)), messages.get(0));
        assertEquals("evaluation_type: expression", ((List<?>) messages.get(1)).get(0));
        assertEquals("initiating slot evaluation", messages.get(2));
        Map<String, Object> config = asMap(log.get("config"));
        assertFalse(config.containsKey("_id"));
        assertEquals(List.of("name", "collection", "payload", "response", "set_slots", "db_type", "failure_response",
                "bot", "timestamp", "status"), keys(config));
        assertTrue(RecordingFailureMail.CALLS.isEmpty());
    }

    // ---------------------------------------------------------------- (3) failure scenarios

    /**
     * Completion 500: Python predict returns is_failure (no exception escapes), so the action logs Failed with the
     * status phrase, bot_response None (not failure_message), dispatches a None text and sends NO failure mail.
     */
    @Test
    void promptActionCompletionServerErrorFailsWithoutMail() {
        faq(true);
        registerFullPrompt("kb_500");
        cognitionSchema("kb_docs", true);
        openaiSecret(List.of("gpt-4o-mini"));
        llmAndQdrantOk();
        kit.pathStatus(completionPath("openai"), 500);
        settings.setVectorKey(null);

        Map<String, Object> body = postPrompt("kb_500");
        assertEquals(1, kit.responses(body).size());
        assertNull(kit.responses(body).get(0).get("text"), "content None dispatched, not failure_message");
        assertNull(kit.slotValue(body, Kairon.ACTION_RESPONSE));
        assertNull(kit.slotValue(body, Kairon.LLM_CALL_ID));
        // rephrase is the first completion and fails; the answer completion is never sent
        assertEquals(1, hits(embedPath("openai")).size());
        assertEquals(2, ParityKit.HITS.stream().filter(hit -> hit.path().endsWith("/points/search")).count());
        assertEquals(1, hits(completionPath("openai")).size());

        Document log = kit.log("kb_500");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("Internal Server Error", log.get("exception"));
        assertFalse(log.containsKey("bot_response"), "bot_response None is omitted");
        assertEquals(List.of(orderedMap("error", "Retrieving chat completion for the provided query. Internal Server Error")),
                log.get("llm_logs"));
        Map<String, Object> llmResponse = asMap(log.get("llm_response"));
        assertEquals(List.of("is_failure", "exception", "content"), keys(llmResponse));
        assertEquals(true, llmResponse.get("is_failure"));
        assertEquals("Internal Server Error", llmResponse.get("exception"));
        assertNull(llmResponse.get("content"));
        assertTrue(ParityKit.API_KEY_PATHS.isEmpty(), "vector.key unset: searches carry no api-key");
        assertEquals(List.of("m1", "m2"), log.get("media_ids"));
        assertNull(log.get("llm_call_id"));
        assertTrue(RecordingFailureMail.CALLS.isEmpty(), "prediction failure is not an exception: no mail");
    }

    /** Unknown model: exception path -> failure_message, failure mail, zero LLM-server / Qdrant traffic. */
    @Test
    void promptActionUnknownModelUsesFailureMessageMailsAndSkipsLlm() {
        faq(true);
        registerFullPrompt("kb_bad_model");
        cognitionSchema("kb_docs", true);
        openaiSecret(List.of("gpt-4o"));
        llmAndQdrantOk();

        Map<String, Object> body = postPrompt("kb_bad_model");
        assertEquals("prompt fallback", kit.text(body));
        assertEquals("prompt fallback", kit.slotValue(body, Kairon.ACTION_RESPONSE));
        Document log = kit.log("kb_bad_model");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("The model 'gpt-4o-mini' is not available for 'openai'.", log.get("exception"));
        assertEquals("prompt fallback", log.get("bot_response"));
        assertEquals(List.of(), log.get("llm_logs"));
        assertNull(log.get("media_ids"));
        assertTrue(ParityKit.HITS.stream().allMatch(hit -> hit.path().equals("/mock")),
                "only the nested http action ran: " + ParityKit.HITS);
        assertEquals(1, RecordingFailureMail.CALLS.size());
        assertEquals("kb_bad_model", RecordingFailureMail.CALLS.get(0).action());
        assertEquals(QUESTION, RecordingFailureMail.CALLS.get(0).userText());
    }

    /** FAQ disabled: prompt utters the FAQ text without mail; database fails with a mail and no dispatch. */
    @Test
    void faqDisabledPromptUttersFaqTextDatabaseMails() {
        registerFullPrompt("kb_faq_off");
        registerDatabase("db_faq_off");
        faq(false); // the only bot_settings document
        cognitionSchema("kb_docs", true);
        openaiSecret(List.of("gpt-4o-mini"));
        llmAndQdrantOk();

        Map<String, Object> promptBody = postPrompt("kb_faq_off");
        assertEquals(Kairon.FAQ_DISABLED, kit.text(promptBody));
        Document promptLog = kit.log("kb_faq_off");
        assertEquals(Kairon.FAIL, promptLog.get("status"));
        assertEquals(Kairon.FAQ_DISABLED, promptLog.get("exception"));
        assertEquals(Kairon.FAQ_DISABLED, promptLog.get("bot_response"));
        assertEquals(Map.of(), promptLog.get("kairon_faq_action_config"));
        assertNull(promptLog.get("llm_logs"));
        assertTrue(RecordingFailureMail.CALLS.isEmpty(), "no mail for FAQ disabled prompt_action");

        Map<String, Object> dbBody = kit.ok("db_faq_off", kit.slots("topic", "boards"), kit.latest(QUESTION),
                List.of(), Map.of(), SENDER, "db_faq_off", null, null);
        assertTrue(kit.responses(dbBody).isEmpty(), "config never loaded: dispatch stays false");
        assertEquals(Kairon.FAILED_DOT, kit.slotValue(dbBody, Kairon.ACTION_RESPONSE));
        Document dbLog = kit.log("db_faq_off");
        assertEquals(Kairon.FAIL, dbLog.get("status"));
        assertEquals(Kairon.FAQ_DISABLED, dbLog.get("exception"));
        assertEquals(Kairon.FAILED_DOT, dbLog.get("bot_response"));
        assertNull(dbLog.get("config"));
        assertEquals(List.of(), dbLog.get("messages"));
        assertEquals(1, RecordingFailureMail.CALLS.size(), "database_action mails on FAQ disabled");
        assertEquals("db_faq_off", RecordingFailureMail.CALLS.get(0).action());

        assertTrue(ParityKit.HITS.isEmpty(), "no LLM/Qdrant/nested traffic: " + ParityKit.HITS);
    }
}
