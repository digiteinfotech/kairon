package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.support.llm.AnswerParams;
import com.kairon.action.support.llm.CognitionSchemas;
import com.kairon.action.support.llm.LlmClient;
import com.kairon.action.support.llm.LlmProcessor;
import com.kairon.action.support.llm.QdrantClient;
import com.kairon.action.support.llm.SimilarityContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-121: llm-vector-clients R8 c1-c6 (processor.py predict + __get_answer log capture). */
class LlmProcessorTest {

    private static final String FERNET = "WvNf7igjO89j9xdRtVMrW7bvVy67uV3ZM9yjwDHkC7E=";
    private static final String EMBED = "/b/aembedding/openai";
    private static final String COMPLETION = "/b/completion/openai";
    private static final String SEARCH = "/collections/b_faq_embd/points/search";
    private static final Map<String, Object> HYPER = Map.of("temperature", 0.0);

    private StubServer stub;
    private LlmProcessor processor;
    private final List<Map<String, Object>> logs = new ArrayList<>();

    @BeforeEach
    void setUp() throws Exception {
        stub = StubServer.startConcurrent();
        ActionSettings settings = new ActionSettings();
        settings.setLlmServerUrl(stub.url(""));
        settings.setVectorDb(stub.url(""));
        settings.setRequestTimeout(2);
        settings.setLlmRequestTimeout(2);
        settings.setFernetKey(FERNET);
        MemoryActionCatalog catalog = new MemoryActionCatalog();
        CognitionSchemas schemas = new CognitionSchemas(catalog);
        LlmClient llm = new LlmClient(new LlmHttp(new HttpCaller(settings), settings), settings, schemas);
        SimilarityContext similarity = new SimilarityContext(new QdrantClient(new HttpCaller(settings), settings));
        processor = new LlmProcessor(llm, similarity);
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    private static AnswerParams params(String queryPrompt, boolean useQueryPrompt) {
        return new AnswerParams("b", "openai", "openai", "what is kairon?", "You are a bot", "ctx", "alice",
                "prompt_action", null, false, queryPrompt, useQueryPrompt, null, HYPER, List.of());
    }

    private static List<Object> sources() {
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("use_similarity_prompt", true);
        source.put("similarity_prompt_name", "Default");
        source.put("similarity_prompt_instructions", "use it");
        source.put("collection", "default");
        return List.of(source);
    }

    private void embeddingOk(long delayMs) {
        stub.on(EMBED, request -> {
            sleep(delayMs);
            return StubServer.Reply.json(200, "[[0.1, 0.2]]");
        });
    }

    private void searchOk() {
        stub.on(SEARCH, request -> StubServer.Reply.json(200, "{\"result\": [{\"payload\": {\"content\": \"kairon is a bot\"}}]}"));
    }

    private static String completionReply(String content, String callId) {
        return "{\"formatted_response\": \"" + content + "\", \"response\": {\"litellm_call_id\": \"" + callId + "\"}}";
    }

    private Map<?, ?> body(StubServer.Captured request) {
        return (Map<?, ?>) Jsons.readAny(request.text());
    }

    /** c1 + c5 + c6: embedding -> similarity -> completion; success shape; one answer_query log; elapsed covers all. */
    @Test
    void successReturnsContentContextAndCallId() {
        embeddingOk(150);
        searchOk();
        stub.on(COMPLETION, request -> {
            sleep(150);
            return StubServer.Reply.json(200, completionReply("Kairon is a bot", "call-1"));
        });

        LlmProcessor.Prediction prediction = processor.predict(params(null, false), "default", sources(),
                Map.of("api_key", "emb-key"), logs);

        String context = "ctx\nInstructions on how to use Default:\n['kairon is a bot']\nuse it\n";
        Map<String, Object> expected = new LinkedHashMap<>();
        expected.put("content", "Kairon is a bot");
        expected.put("similarity_context", context);
        expected.put("litellm_call_id", "call-1");
        assertEquals(expected, prediction.response());
        assertEquals(List.of("content", "similarity_context", "litellm_call_id"),
                new ArrayList<>(prediction.response().keySet()));
        assertFalse(prediction.isFailure());
        assertEquals("call-1", prediction.callId());

        // Order: embedding, then the search with that vector, then the completion carrying the context.
        assertEquals(List.of(EMBED, SEARCH, COMPLETION), stub.requests.stream().map(StubServer.Captured::path).toList());
        assertEquals(List.of(0.1, 0.2), body(stub.at(SEARCH).get(0)).get("vector"));
        assertEquals(List.of("what is kairon?"), body(stub.at(EMBED).get(0)).get("text"));
        List<?> messages = (List<?>) body(stub.at(COMPLETION).get(0)).get("messages");
        assertEquals(context + " \nQ: what is kairon? \nA:", ((Map<?, ?>) messages.get(1)).get("content"));

        assertEquals(1, logs.size());
        assertEquals(List.of("messages", "raw_completion_response", "type", "hyperparameters"),
                new ArrayList<>(logs.get(0).keySet()));
        assertEquals("answer_query", logs.get(0).get("type"));
        assertEquals(Map.of("litellm_call_id", "call-1"), logs.get(0).get("raw_completion_response"));
        assertEquals(HYPER, logs.get(0).get("hyperparameters"));

        // c6: wall-clock seconds of the whole prediction (both 150 ms stubs included).
        assertTrue(prediction.elapsedSeconds() >= 0.3, "elapsed " + prediction.elapsedSeconds());
        assertTrue(prediction.elapsedSeconds() < 5, "elapsed " + prediction.elapsedSeconds());
    }

    /** c2 + c4: embedding 500 -> embedding-stage error log, failure shape, no search or completion. */
    @Test
    void embeddingFailureIsCreatingEmbeddingStage() {
        stub.on(EMBED, request -> StubServer.Reply.json(500, "{\"detail\": \"boom\"}"));
        searchOk();

        LlmProcessor.Prediction prediction = processor.predict(params(null, false), "default", sources(),
                Map.of("api_key", "emb-key"), logs);

        assertFailure(prediction, "Internal Server Error");
        assertEquals(List.of(Map.of("error", "Creating a new embedding for the provided query. Internal Server Error")),
                logs);
        assertEquals(List.of(EMBED), stub.requests.stream().map(StubServer.Captured::path).toList());
        assertTrue(prediction.elapsedSeconds() >= 0);
    }

    /** c3 + c4: completion 500 after a good embedding -> completion-stage error log. */
    @Test
    void completionFailureIsRetrievingCompletionStage() {
        embeddingOk(0);
        searchOk();
        stub.on(COMPLETION, request -> StubServer.Reply.json(500, "{}"));

        LlmProcessor.Prediction prediction = processor.predict(params(null, false), "default", sources(),
                Map.of("api_key", "emb-key"), logs);

        assertFailure(prediction, "Internal Server Error");
        assertEquals(List.of(Map.of("error", "Retrieving chat completion for the provided query. Internal Server Error")),
                logs);
    }

    /** c3: a similarity search failure also happens after the embedding returned. */
    @Test
    void searchFailureIsRetrievingCompletionStage() {
        embeddingOk(0);
        stub.on(SEARCH, request -> StubServer.Reply.json(500, "{}"));

        LlmProcessor.Prediction prediction = processor.predict(params(null, false), "default", sources(),
                Map.of("api_key", "emb-key"), logs);

        assertTrue(prediction.isFailure());
        assertEquals(1, logs.size());
        assertTrue(((String) logs.get(0).get("error")).startsWith("Retrieving chat completion for the provided query. "),
                String.valueOf(logs.get(0)));
        assertEquals(0, stub.at(COMPLETION).size());
    }

    /** c1: rephrase then answer, logged in call order with the right types. */
    @Test
    void rephraseThenAnswerLogOrder() {
        embeddingOk(0);
        AtomicInteger calls = new AtomicInteger();
        stub.on(COMPLETION, request -> calls.incrementAndGet() == 1
                ? StubServer.Reply.json(200, completionReply("rephrased query", "call-r"))
                : StubServer.Reply.json(200, completionReply("final answer", "call-a")));

        LlmProcessor.Prediction prediction = processor.predict(params("Rephrase it", true), "default", List.of(),
                Map.of("api_key", "emb-key"), logs);

        assertEquals("final answer", prediction.content());
        assertEquals("call-a", prediction.callId());
        assertEquals(List.of("rephrase_query", "answer_query"), logs.stream().map(log -> log.get("type")).toList());
        assertEquals("prompt_action_rephrase", body(stub.at(COMPLETION).get(0)).get("invocation"));
        List<?> answerMessages = (List<?>) logs.get(1).get("messages");
        assertEquals("ctx \nQ: rephrased query \nA:", ((Map<?, ?>) answerMessages.get(1)).get("content"));
    }

    /** c1 + c3 interleaving: a rephrase that returned stays logged before the error entry of a failing answer. */
    @Test
    void rephraseThenFailingAnswerKeepsRephraseBeforeError() {
        embeddingOk(0);
        AtomicInteger calls = new AtomicInteger();
        stub.on(COMPLETION, request -> calls.incrementAndGet() == 1
                ? StubServer.Reply.json(200, completionReply("rephrased query", "call-r"))
                : StubServer.Reply.json(500, "{}"));

        LlmProcessor.Prediction prediction = processor.predict(params("Rephrase it", true), "default", List.of(),
                Map.of("api_key", "emb-key"), logs);

        assertFailure(prediction, "Internal Server Error");
        assertEquals(2, logs.size());
        assertEquals("rephrase_query", logs.get(0).get("type"));
        assertEquals(Map.of("error", "Retrieving chat completion for the provided query. Internal Server Error"),
                logs.get(1));
    }

    /** T-123: a None query fails in truncate_text (embedding stage) before any request; no "None" text embedded. */
    @Test
    void nullQueryFailsAtEmbeddingStageWithoutRequests() {
        embeddingOk(0);
        searchOk();
        AnswerParams p = params(null, false);
        AnswerParams noQuery = new AnswerParams(p.bot(), p.endpointLlmType(), p.llmType(), null, p.systemPrompt(),
                p.context(), p.user(), p.invocation(), p.mediaIds(), p.shouldProcessMedia(), p.queryPrompt(),
                p.useQueryPrompt(), p.previousBotResponses(), p.hyperparameters(), p.instructions());

        LlmProcessor.Prediction prediction = processor.predict(noQuery, "default", sources(),
                Map.of("api_key", "emb-key"), logs);

        assertFailure(prediction, "'NoneType' object is not iterable");
        assertEquals(List.of(Map.of("error",
                "Creating a new embedding for the provided query. 'NoneType' object is not iterable")), logs);
        assertTrue(stub.requests.isEmpty(), "no request: " + stub.requests);
    }

    /** T-123: a checked exception escaping the client still yields the failure shape (Python catches Exception). */
    @Test
    void checkedExceptionIsCaught() {
        LlmProcessor failing = processorThrowing(new java.io.IOException("io broke"));
        LlmProcessor.Prediction prediction = failing.predict(params(null, false), "default", sources(),
                Map.of("api_key", "emb-key"), logs);
        assertFailure(prediction, "io broke");
        assertEquals(List.of(Map.of("error", "Creating a new embedding for the provided query. io broke")), logs);
    }

    /** T-123: StackOverflowError (Python RecursionError is an Exception) is caught; null message reads as "". */
    @Test
    void stackOverflowIsCaught() {
        LlmProcessor failing = processorThrowing(new StackOverflowError());
        LlmProcessor.Prediction prediction = failing.predict(params(null, false), "default", sources(),
                Map.of("api_key", "emb-key"), logs);
        assertFailure(prediction, "");
        assertEquals(List.of(Map.of("error", "Creating a new embedding for the provided query. ")), logs);
    }

    private LlmProcessor processorThrowing(Throwable error) {
        ActionSettings settings = new ActionSettings();
        settings.setLlmServerUrl(stub.url(""));
        settings.setVectorDb(stub.url(""));
        settings.setFernetKey(FERNET);
        LlmClient throwing = new LlmClient(new LlmHttp(new HttpCaller(settings), settings), settings, null) {
            @Override
            public Object embed(String bot, String llmType, String text, Object user, Object invocation,
                                String collection, Map<String, String> embeddingSecret) {
                throw LlmProcessorTest.<RuntimeException>sneaky(error);
            }
        };
        return new LlmProcessor(throwing, new SimilarityContext(new QdrantClient(new HttpCaller(settings), settings)));
    }

    @SuppressWarnings("unchecked")
    private static <E extends Throwable> E sneaky(Throwable error) throws E {
        throw (E) error;
    }

    private static void assertFailure(LlmProcessor.Prediction prediction, String exception) {
        Map<String, Object> expected = new LinkedHashMap<>();
        expected.put("is_failure", true);
        expected.put("exception", exception);
        expected.put("content", null);
        assertEquals(expected, prediction.response());
        assertEquals(List.of("is_failure", "exception", "content"), new ArrayList<>(prediction.response().keySet()));
        assertTrue(prediction.isFailure());
        assertNull(prediction.content());
        assertNull(prediction.callId());
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
