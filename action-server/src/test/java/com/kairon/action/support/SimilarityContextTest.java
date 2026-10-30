package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.llm.QdrantClient;
import com.kairon.action.support.llm.SimilarityContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-119: llm-vector-clients R4 c6-c8 (processor.py _process_similarity_prompt + asyncio.gather). */
class SimilarityContextTest {

    private StubServer stub;
    private SimilarityContext similarity;

    @BeforeEach
    void setUp() throws Exception {
        stub = StubServer.startConcurrent();
        ActionSettings settings = new ActionSettings();
        settings.setVectorDb(stub.url(""));
        settings.setRequestTimeout(1);
        settings.setLlmRequestTimeout(1);
        similarity = new SimilarityContext(new QdrantClient(new HttpCaller(settings), settings));
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    private static Map<String, Object> source(String name, String collection, String instructions) {
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("use_similarity_prompt", true);
        source.put("similarity_prompt_name", name);
        source.put("similarity_prompt_instructions", instructions);
        source.put("collection", collection);
        return source;
    }

    /** c6: both searches in flight at once (neither stub replies until both arrived); blocks in config order. */
    @Test
    void searchesRunConcurrentlyAndBlocksKeepConfigOrder() {
        CountDownLatch bothArrived = new CountDownLatch(2);
        List<Boolean> sawBoth = new java.util.concurrent.CopyOnWriteArrayList<>();
        stub.on("/collections/b_faq_embd/points/search", request -> {
            bothArrived.countDown();
            sawBoth.add(await(bothArrived));
            // Reply later than the second source, so completion order differs from config order.
            sleep(200);
            return StubServer.Reply.json(200, "{\"result\": [{\"payload\": {\"content\": \"first\"}}]}");
        });
        stub.on("/collections/b_docs_faq_embd/points/search", request -> {
            bothArrived.countDown();
            sawBoth.add(await(bothArrived));
            return StubServer.Reply.json(200, "{\"result\": [{\"payload\": {\"content\": \"second\"}}]}");
        });
        List<Object> sources = List.of(source("Default", "default", "use A"), source("Docs", "docs", "use B"));

        String context = similarity.attach("b", "ctx", sources, List.of(0.1));

        assertEquals(List.of(true, true), sawBoth);
        assertEquals("ctx\nInstructions on how to use Default:\n['first']\nuse A\n"
                + "\nInstructions on how to use Docs:\n['second']\nuse B\n", context);
    }

    /** c7: payload.content when present, else the payload without collection_name; c8 Python list repr. */
    @Test
    void hitValuesAndRendering() {
        stub.on("/collections/b_faq_embd/points/search", request -> StubServer.Reply.json(200,
                "{\"result\": [{\"payload\": {\"content\": \"it's\", \"collection_name\": \"x\"}},"
                        + " {\"payload\": {\"collection_name\": \"x\", \"q\": \"a\", \"n\": 1.5, \"ok\": true, \"z\": null}},"
                        + " {\"id\": 3}]}"));
        String block = similarity.render("b", source("FAQ", "default", "Answer briefly."), List.of(0.2));
        assertEquals("Instructions on how to use FAQ:\n[\"it's\", {'q': 'a', 'n': 1.5, 'ok': True, 'z': None}, {}]\n"
                + "Answer briefly.\n", block);
    }

    /** c8: no hits adds nothing (context unchanged, no separator). */
    @Test
    void emptyResultAddsNothing() {
        stub.on("/collections/b_faq_embd/points/search", request -> StubServer.Reply.json(200, "{\"result\": []}"));
        assertEquals(null, similarity.render("b", source("FAQ", "default", "i"), List.of(0.2)));
        assertEquals("ctx", similarity.attach("b", "ctx", List.of(source("FAQ", "default", "i")), List.of(0.2)));
    }

    /** Disabled sources are never searched; None name/instructions render as Python str(None). */
    @Test
    void disabledSourceSkippedAndNoneRendersAsNone() {
        stub.on("/collections/b_docs_faq_embd/points/search", request -> StubServer.Reply.json(200,
                "{\"result\": [{\"payload\": {\"content\": 7}}]}"));
        Map<String, Object> disabled = source("Off", "default", "x");
        disabled.put("use_similarity_prompt", false);
        Map<String, Object> enabled = new LinkedHashMap<>();
        enabled.put("use_similarity_prompt", true);
        enabled.put("collection", "docs");
        List<Object> sources = new ArrayList<>(List.of(disabled, enabled));

        assertEquals("c\nInstructions on how to use None:\n[7]\nNone\n", similarity.attach("b", "c", sources, List.of(1.0)));
        assertTrue(stub.at("/collections/b_faq_embd/points/search").isEmpty());
        assertEquals(1, stub.at("/collections/b_docs_faq_embd/points/search").size());
    }

    /** No sources: context returned as str(context). */
    @Test
    void noSources() {
        assertEquals("ctx", similarity.attach("b", "ctx", null, List.of(1.0)));
        assertEquals("ctx", similarity.attach("b", "ctx", List.of(), List.of(1.0)));
    }

    /** A failing search fails the whole attach (asyncio.gather without return_exceptions). */
    @Test
    void searchFailurePropagates() {
        stub.on("/collections/b_faq_embd/points/search", request -> StubServer.Reply.json(200, "{\"status\": \"ok\"}"));
        stub.on("/collections/b_docs_faq_embd/points/search", request -> StubServer.Reply.json(200, "{\"result\": []}"));
        ActionFailure failure = assertThrows(ActionFailure.class, () -> similarity.attach("b", "ctx",
                List.of(source("A", "default", "i"), source("B", "docs", "i")), List.of(1.0)));
        assertEquals("'result'", failure.getMessage());
    }

    /** Python `'content' in None` when a hit carries payload: null. */
    @Test
    void nullPayloadFails() {
        stub.on("/collections/b_faq_embd/points/search", request -> StubServer.Reply.json(200,
                "{\"result\": [{\"payload\": null}]}"));
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> similarity.render("b", source("A", "default", "i"), List.of(1.0)));
        assertEquals("argument of type 'NoneType' is not iterable", failure.getMessage());
    }

    private static boolean await(CountDownLatch latch) {
        try {
            return latch.await(3, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
