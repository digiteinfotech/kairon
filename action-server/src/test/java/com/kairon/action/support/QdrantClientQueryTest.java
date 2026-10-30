package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.llm.CognitionSchemas;
import com.kairon.action.support.llm.LlmClient;
import com.kairon.action.support.llm.LlmSecrets;
import com.kairon.action.support.llm.QdrantClient;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-120: llm-vector-clients R5 c1-c10 (database_action point query, qdrant.py perform_operation). */
class QdrantClientQueryTest {

    private static final String FERNET = "WvNf7igjO89j9xdRtVMrW7bvVy67uV3ZM9yjwDHkC7E=";
    private static final String QUERY_PATH = "/collections/bot1_products_faq_embd/points/query";
    private static final String EMBED_PATH = "/bot1/aembedding/openai";
    private static final Map<String, String> SECRET = Map.of("api_key", "emb-key");
    private static final String POINTS = "{\"result\": {\"points\": [{\"id\": 1, \"payload\": {\"name\": \"x\"}}]}, \"status\": \"ok\"}";

    private StubServer stub;
    private ActionSettings settings;
    private QdrantClient qdrant;

    @BeforeEach
    void setUp() throws Exception {
        stub = StubServer.start();
        settings = new ActionSettings();
        settings.setVectorDb(stub.url(""));
        settings.setLlmServerUrl(stub.url(""));
        settings.setRequestTimeout(1);
        settings.setLlmRequestTimeout(1);
        settings.setFernetKey(FERNET);
        MemoryActionCatalog catalog = new MemoryActionCatalog();
        CognitionSchemas schemas = new CognitionSchemas(catalog, new LlmSecrets(catalog, new Tokens(settings)));
        LlmClient llm = new LlmClient(new LlmHttp(new HttpCaller(settings), settings), settings, schemas);
        qdrant = new QdrantClient(new HttpCaller(settings), settings, llm);
        stub.on(EMBED_PATH, request -> StubServer.Reply.json(200, "[[0.1, 0.2]]"));
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    private Object query(Object payload) {
        return qdrant.query("bot1", "products", payload, "openai", SECRET, "alice");
    }

    private Map<?, ?> sentBody() {
        return (Map<?, ?>) Jsons.readAny(stub.at(QUERY_PATH).get(0).text());
    }

    /** c1: POST {vector.db}/collections/{bot}_{collection}_faq_embd/points/query (default collection not special-cased). */
    @Test
    void postsToPointsQueryUrl() {
        stub.on(QUERY_PATH, request -> StubServer.Reply.json(200, POINTS));
        query(Map.of("payload_search", Map.of("filter", Map.of())));
        List<StubServer.Captured> captured = stub.at(QUERY_PATH);
        assertEquals(1, captured.size());
        assertEquals("POST", captured.get(0).method());

        String defaultPath = "/collections/bot1_default_faq_embd/points/query";
        stub.on(defaultPath, request -> StubServer.Reply.json(200, POINTS));
        qdrant.query("bot1", "default", Map.of("payload_search", Map.of("filter", Map.of())), "openai", SECRET, "u");
        assertEquals(1, stub.at(defaultPath).size());
    }

    /** c1: urljoin with an absolute path drops any base path of vector.db. */
    @Test
    void basePathDropped() {
        settings.setVectorDb(stub.url("/prefix"));
        stub.on(QUERY_PATH, request -> StubServer.Reply.json(200, POINTS));
        query(Map.of("payload_search", Map.of("filter", Map.of())));
        assertEquals(1, stub.at(QUERY_PATH).size());
    }

    /** c2 + c4: non-empty embedding_search -> query = embedding (invocation db_action_qdrant), then with_payload + limit 10. */
    @Test
    void embeddingSearchBecomesQuery() {
        stub.on(QUERY_PATH, request -> StubServer.Reply.json(200, POINTS));
        query(Map.of("embedding_search", "what is x"));
        assertEquals(List.of("query", "with_payload", "limit"), new ArrayList<>(sentBody().keySet()));
        assertEquals(List.of(0.1, 0.2), sentBody().get("query"));
        assertEquals(true, sentBody().get("with_payload"));
        assertEquals(10, sentBody().get("limit"));
        assertEquals("{\"query\": [0.1, 0.2], \"with_payload\": true, \"limit\": 10}",
                Jsons.pythonDumps(Jsons.readAny(stub.at(QUERY_PATH).get(0).text())));
        Map<?, ?> embed = (Map<?, ?>) Jsons.readAny(stub.at(EMBED_PATH).get(0).text());
        assertEquals(List.of("what is x"), embed.get("text"));
        assertEquals("alice", embed.get("user"));
        Map<?, ?> kwargs = (Map<?, ?>) embed.get("kwargs");
        assertEquals("db_action_qdrant", kwargs.get("invocation"));
        assertEquals("emb-key", kwargs.get("api_key"));
    }

    /** c2: empty or non-string embedding_search sends no query key and calls no embedding. */
    @Test
    void emptyOrNonStringEmbeddingSearchHasNoQuery() {
        stub.on(QUERY_PATH, request -> StubServer.Reply.json(200, POINTS));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("embedding_search", "");
        payload.put("payload_search", Map.of("filter", Map.of("must", List.of())));
        query(payload);
        payload.put("embedding_search", 42);
        query(payload);
        payload.put("embedding_search", null);
        query(payload);
        assertEquals(0, stub.at(EMBED_PATH).size());
        for (StubServer.Captured captured : stub.at(QUERY_PATH)) {
            Map<?, ?> body = (Map<?, ?>) Jsons.readAny(captured.text());
            assertTrue(!body.containsKey("query"), body.toString());
        }
    }

    /** c3 + c4: payload_search merged at top level; with_payload forced true; an explicit limit kept. */
    @Test
    void payloadSearchMergedTopLevel() {
        stub.on(QUERY_PATH, request -> StubServer.Reply.json(200, POINTS));
        Map<String, Object> search = new LinkedHashMap<>();
        search.put("filter", Map.of("must", List.of(Map.of("key", "name", "match", Map.of("value", "x")))));
        search.put("with_payload", false);
        search.put("limit", 3);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("embedding_search", "hi");
        payload.put("payload_search", search);
        query(payload);
        assertEquals(List.of("query", "filter", "with_payload", "limit"), new ArrayList<>(sentBody().keySet()));
        assertEquals(search.get("filter"), sentBody().get("filter"));
        assertEquals(true, sentBody().get("with_payload"));
        assertEquals(3, sentBody().get("limit"));
    }

    /** c3: payload_search may override query (dict.update after the embedding). */
    @Test
    void payloadSearchOverridesQuery() {
        stub.on(QUERY_PATH, request -> StubServer.Reply.json(200, POINTS));
        query(Map.of("embedding_search", "hi", "payload_search", Map.of("query", List.of(9))));
        assertEquals(List.of(9), sentBody().get("query"));
    }

    /** c4: Python `'limit' not in request`: an explicit null limit is kept. */
    @Test
    void explicitNullLimitKept() {
        stub.on(QUERY_PATH, request -> StubServer.Reply.json(200, POINTS));
        Map<String, Object> search = new HashMap<>();
        search.put("limit", null);
        query(Map.of("payload_search", search));
        assertTrue(sentBody().containsKey("limit"));
        assertNull(sentBody().get("limit"));
    }

    /** c5: no query and no payload_search -> No Operation to perform, nothing sent. */
    @Test
    void emptyRequestFails() {
        for (Object payload : List.of(Map.of(), Map.of("embedding_search", ""), Map.of("payload_search", Map.of()),
                Map.of("other", 1), List.of(1), "text")) {
            ActionFailure failure = assertThrows(ActionFailure.class, () -> query(payload));
            assertEquals("No Operation to perform", failure.getMessage());
        }
        Map<String, Object> nulls = new HashMap<>();
        nulls.put("embedding_search", null);
        nulls.put("payload_search", null);
        assertEquals("No Operation to perform", assertThrows(ActionFailure.class, () -> query(nulls)).getMessage());
        assertEquals(0, stub.requests.size());
    }

    /** c6: no api-key header even when vector.key is set (Python execute_http_request gets no headers). */
    @Test
    void noApiKeyEvenWhenConfigured() {
        settings.setVectorKey("secret-key");
        stub.on(QUERY_PATH, request -> StubServer.Reply.json(200, POINTS));
        query(Map.of("embedding_search", "hi"));
        StubServer.Captured captured = stub.at(QUERY_PATH).get(0);
        assertNull(captured.header("api-key"));
        assertNull(captured.header("Authorization"));
        assertTrue(captured.header(com.kairon.action.Kairon.TIMESTAMP) != null);
    }

    /** c7: timeout is action.request_timeout (default 60), not llm.request_timeout nor the 5 s search timeout. */
    @Test
    void timeoutIsActionRequestTimeout() {
        assertEquals(60, new ActionSettings().getRequestTimeout());
        stub.on(QUERY_PATH, request -> {
            pause(1500);
            return StubServer.Reply.json(200, POINTS);
        });
        ActionFailure failure = assertThrows(ActionFailure.class, () -> query(Map.of("payload_search", Map.of("f", 1))));
        assertTrue(failure.getMessage().startsWith("Failed to execute the url:"), failure.getMessage());

        settings.setRequestTimeout(3);
        assertEquals(Jsons.readAny(POINTS), query(Map.of("payload_search", Map.of("f", 1))));
    }

    /** c8: status outside 200/201/202/204 -> Got non-200 status code: {code} {body} (wrapped by the catch-all). */
    @Test
    void nonSuccessStatusFails() {
        stub.on(QUERY_PATH, request -> StubServer.Reply.json(400, "{\"status\": {\"error\": \"bad\"}}"));
        ActionFailure failure = assertThrows(ActionFailure.class, () -> query(Map.of("payload_search", Map.of("f", 1))));
        assertEquals("Failed to execute the url: Got non-200 status code: 400 {\"status\": {\"error\": \"bad\"}}",
                failure.getMessage());
        assertEquals(1, stub.at(QUERY_PATH).size());
    }

    /** c9: transport errors -> Failed to execute the url: ... */
    @Test
    void transportErrorFails() {
        settings.setVectorDb("http://127.0.0.1:1");
        ActionFailure failure = assertThrows(ActionFailure.class, () -> query(Map.of("payload_search", Map.of("f", 1))));
        assertTrue(failure.getMessage().startsWith("Failed to execute the url:"), failure.getMessage());
    }

    /** c10: success returns the full Qdrant JSON unmodified, or text for non-JSON; 201/202/204 accepted. */
    @Test
    void successReturnsBodyUnmodified() {
        stub.on(QUERY_PATH, request -> StubServer.Reply.json(200, POINTS));
        assertEquals(Jsons.readAny(POINTS), query(Map.of("payload_search", Map.of("f", 1))));
        stub.on(QUERY_PATH, request -> new StubServer.Reply(202, Map.of("Content-Type", "text/plain"), "accepted"));
        assertEquals("accepted", query(Map.of("payload_search", Map.of("f", 1))));
        stub.on(QUERY_PATH, request -> new StubServer.Reply(204, Map.of(), ""));
        assertEquals("", query(Map.of("payload_search", Map.of("f", 1))));
    }

    /** Embedding failure propagates and no Qdrant request is sent. */
    @Test
    void embeddingFailurePropagates() {
        stub.on(EMBED_PATH, request -> StubServer.Reply.json(500, "{}"));
        assertThrows(ActionFailure.class, () -> query(Map.of("embedding_search", "hi")));
        assertEquals(0, stub.at(QUERY_PATH).size());
    }

    private static void pause(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
