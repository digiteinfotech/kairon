package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.llm.QdrantClient;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-110: llm-vector-clients R4 c1-c5, c9. */
class QdrantClientSearchTest {

    private static final String HITS = "{\"result\": [{\"id\": 1, \"score\": 0.9, \"payload\": {\"content\": \"faq\"}}], \"status\": \"ok\"}";

    private StubServer stub;
    private ActionSettings settings;
    private QdrantClient qdrant;

    @BeforeEach
    void setUp() throws Exception {
        stub = StubServer.start();
        settings = new ActionSettings();
        settings.setVectorDb(stub.url(""));
        settings.setRequestTimeout(1);
        settings.setLlmRequestTimeout(1);
        qdrant = new QdrantClient(new HttpCaller(settings), settings);
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    /** c1 + c2 + c3: default collection, default limit/threshold, exact body. */
    @Test
    void defaultCollectionWithDefaults() {
        stub.on("/collections/bot1_faq_embd/points/search", request -> StubServer.Reply.json(200, HITS));
        List<?> hits = qdrant.search("bot1", Map.of("collection", "default"), List.of(0.1, 0.2));
        assertEquals(List.of(Map.of("id", 1, "score", 0.9, "payload", Map.of("content", "faq"))), hits);
        List<StubServer.Captured> captured = stub.at("/collections/bot1_faq_embd/points/search");
        assertEquals(1, captured.size());
        assertEquals("POST", captured.get(0).method());
        Map<String, Object> expected = new LinkedHashMap<>();
        expected.put("vector", List.of(0.1, 0.2));
        expected.put("limit", 10);
        expected.put("with_payload", true);
        expected.put("score_threshold", 0.7);
        assertEquals(expected, Jsons.readAny(captured.get(0).text()));
        assertEquals("{\"vector\": [0.1, 0.2], \"limit\": 10, \"with_payload\": true, \"score_threshold\": 0.7}",
                Jsons.pythonDumps(Jsons.readAny(captured.get(0).text())));
    }

    /** c2 + c3: named collection uses its top_results and similarity_threshold. */
    @Test
    void namedCollectionWithConfiguredLimits() {
        stub.on("/collections/bot1_python_faq_embd/points/search", request -> StubServer.Reply.json(200, "{\"result\": []}"));
        Map<String, Object> source = Map.of("collection", "python", "top_results", 3, "similarity_threshold", 0.45);
        assertEquals(List.of(), qdrant.search("bot1", source, List.of(1.0)));
        Object body = Jsons.readAny(stub.at("/collections/bot1_python_faq_embd/points/search").get(0).text());
        assertEquals(Map.of("vector", List.of(1.0), "limit", 3, "with_payload", true, "score_threshold", 0.45), body);
    }

    @Test
    void collectionNames() {
        assertEquals("b_faq_embd", QdrantClient.collectionName("b", "default"));
        assertEquals("b_docs_faq_embd", QdrantClient.collectionName("b", "docs"));
    }

    /** c4: api-key sent when vector.key is set. */
    @Test
    void apiKeySentWhenConfigured() {
        settings.setVectorKey("secret-key");
        stub.on("/collections/b_faq_embd/points/search", request -> StubServer.Reply.json(200, HITS));
        qdrant.search("b", Map.of("collection", "default"), List.of(0.5));
        StubServer.Captured captured = stub.at("/collections/b_faq_embd/points/search").get(0);
        assertEquals("secret-key", captured.header("api-key"));
        assertNull(captured.header("Authorization"));
    }

    /** c4: api-key omitted when vector.key is unset or blank. */
    @Test
    void apiKeyOmittedWhenUnset() {
        settings.setVectorKey("  ");
        stub.on("/collections/b_faq_embd/points/search", request -> StubServer.Reply.json(200, HITS));
        qdrant.search("b", Map.of("collection", "default"), List.of(0.5));
        assertNull(stub.at("/collections/b_faq_embd/points/search").get(0).header("api-key"));
    }

    /** c5: the 5 s search timeout applies, not action.request_timeout or llm.request_timeout (both 1 s here). */
    @Test
    void searchTimeoutIsFiveSeconds() {
        stub.on("/collections/b_faq_embd/points/search", request -> {
            pause(1500);
            return StubServer.Reply.json(200, HITS);
        });
        assertEquals(1, qdrant.search("b", Map.of("collection", "default"), List.of(0.5)).size());
    }

    /** c5: one request, no retry, even on 5xx; the failure propagates. */
    @Test
    void serverErrorSentOnceAndFails() {
        stub.on("/collections/b_faq_embd/points/search", request -> StubServer.Reply.json(503, "{}"));
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> qdrant.search("b", Map.of("collection", "default"), List.of(0.5)));
        assertTrue(failure.getMessage().startsWith("Failed to execute the url: 503, message='Service Unavailable'"), failure.getMessage());
        assertEquals(1, stub.at("/collections/b_faq_embd/points/search").size());
    }

    /** c9: a response without `result` fails. */
    @Test
    void missingResultFails() {
        stub.on("/collections/b_faq_embd/points/search", request -> StubServer.Reply.json(200, "{\"status\": \"ok\"}"));
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> qdrant.search("b", Map.of("collection", "default"), List.of(0.5)));
        assertEquals("'result'", failure.getMessage());
    }

    /** Python dict.get default applies only to absent keys; urljoin with an absolute path drops any base path. */
    @Test
    void explicitNullLimitsAndBasePath() {
        settings.setVectorDb(stub.url("/ignored/prefix"));
        stub.on("/collections/b_faq_embd/points/search", request -> StubServer.Reply.json(200, HITS));
        Map<String, Object> source = new HashMap<>();
        source.put("collection", "default");
        source.put("top_results", null);
        qdrant.search("b", source, List.of(0.5));
        Map<?, ?> body = (Map<?, ?>) Jsons.readAny(stub.at("/collections/b_faq_embd/points/search").get(0).text());
        assertTrue(body.containsKey("limit"));
        assertNull(body.get("limit"));
        assertEquals(0.7, body.get("score_threshold"));
    }

    private static void pause(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
