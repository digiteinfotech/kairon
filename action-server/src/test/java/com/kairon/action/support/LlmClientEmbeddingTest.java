package com.kairon.action.support;

import com.knuddels.jtokkit.Encodings;
import com.knuddels.jtokkit.api.Encoding;
import com.knuddels.jtokkit.api.EncodingType;
import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.llm.CognitionSchemas;
import com.kairon.action.support.llm.LlmClient;
import com.kairon.action.support.llm.LlmSecrets;
import org.bson.Document;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

/** T-117: llm-vector-clients R1 c1-c8, R7 c3. */
class LlmClientEmbeddingTest {

    private static final String FERNET = "WvNf7igjO89j9xdRtVMrW7bvVy67uV3ZM9yjwDHkC7E=";
    private static final String BOT = "my bot";
    private static final String PATH = "/my%20bot/aembedding/openai";
    private static final Map<String, String> SECRET = Map.of("api_key", "emb-key");
    private static final Encoding CL100K = Encodings.newDefaultEncodingRegistry().getEncoding(EncodingType.CL100K_BASE);

    private StubServer stub;
    private MemoryActionCatalog catalog;
    private Tokens tokens;
    private LlmClient client;

    @BeforeEach
    void setUp() throws Exception {
        stub = StubServer.start();
        ActionSettings settings = new ActionSettings();
        settings.setLlmServerUrl(stub.url(""));
        settings.setRequestTimeout(1);
        settings.setLlmRequestTimeout(1);
        settings.setFernetKey(FERNET);
        tokens = new Tokens(settings);
        catalog = new MemoryActionCatalog();
        CognitionSchemas schemas = new CognitionSchemas(catalog);
        client = new LlmClient(new LlmHttp(new HttpCaller(settings), settings), settings, schemas);
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    private void schema(String collection, Document metadata) {
        catalog.put(ActionCatalog.COGNITION_SCHEMA, new Document("bot", BOT).append("collection_name", collection)
                .append("schema_metadata", metadata));
    }

    private Map<?, ?> body(int index) {
        return (Map<?, ?>) Jsons.readAny(stub.at(PATH).get(index).text());
    }

    private Map<?, ?> kwargs(int index) {
        return (Map<?, ?>) body(index).get("kwargs");
    }

    /** c1: POST to {llm.url}/{url-quoted bot}/aembedding/{llm_type}. */
    @Test
    void postsToQuotedBotEmbeddingUrl() {
        stub.on(PATH, request -> StubServer.Reply.json(200, "[[0.1, 0.2]]"));
        client.embed(BOT, "openai", "hello", "alice", "prompt_action", "default", SECRET);
        assertEquals(1, stub.requests.size());
        assertEquals("POST", stub.requests.get(0).method());
        assertEquals(PATH, stub.requests.get(0).path());
    }

    /** c2: body {text, user, kwargs}; a single string is a one-element text list. */
    @Test
    void singleTextSentAsOneElementList() {
        stub.on(PATH, request -> StubServer.Reply.json(200, "[[0.1]]"));
        client.embed(BOT, "openai", "hello", "alice", "prompt_action", "default", SECRET);
        client.embedAll(BOT, "openai", List.of("a", "b"), "bob", "prompt_action", "default", SECRET);
        assertEquals(List.of("text", "user", "kwargs"), new ArrayList<>(body(0).keySet()));
        assertEquals(List.of("hello"), body(0).get("text"));
        assertEquals("alice", body(0).get("user"));
        assertEquals(List.of("a", "b"), body(1).get("text"));
        assertEquals("bob", body(1).get("user"));
    }

    /** c3: kwargs.invocation passed through (prompt_action / db_action_qdrant). */
    @Test
    void invocationPassedThrough() {
        stub.on(PATH, request -> StubServer.Reply.json(200, "[[0.1]]"));
        client.embed(BOT, "openai", "q", "u", "prompt_action", "default", SECRET);
        client.embed(BOT, "openai", "q", "u", "db_action_qdrant", "default", SECRET);
        assertEquals("prompt_action", kwargs(0).get("invocation"));
        assertEquals("db_action_qdrant", kwargs(1).get("invocation"));
    }

    /** c4 + R7 c3: collection/model only when training_needed false; missing schema = training needed. */
    @Test
    void collectionAndModelOnlyWhenTrainingNotNeeded() {
        schema("Products", new Document("training_needed", false).append("model_id", "text-embedding-3-small"));
        schema("trained", new Document("training_needed", true).append("model_id", "m"));
        stub.on(PATH, request -> StubServer.Reply.json(200, "[[0.1]]"));

        client.embed(BOT, "openai", "q", "u", "prompt_action", "Products", SECRET);
        client.embed(BOT, "openai", "q", "u", "prompt_action", "trained", SECRET);
        client.embed(BOT, "openai", "q", "u", "prompt_action", "missing", SECRET);
        client.embed(BOT, "openai", "q", "u", "prompt_action", "products", SECRET);

        assertEquals(List.of("invocation", "collection", "model", "truncated_texts", "api_key"),
                new ArrayList<>(kwargs(0).keySet()));
        assertEquals("Products", kwargs(0).get("collection"));
        assertEquals("text-embedding-3-small", kwargs(0).get("model"));
        for (int i = 1; i < 4; i++) {
            assertEquals(List.of("invocation", "truncated_texts", "api_key"), new ArrayList<>(kwargs(i).keySet()));
        }
    }

    /** c4: schema with training_needed false but no model_id uses the default model id. */
    @Test
    void untrainedSchemaWithoutModelIdUsesDefault() {
        schema("faq", new Document("training_needed", false));
        stub.on(PATH, request -> StubServer.Reply.json(200, "[[0.1]]"));
        client.embed(BOT, "openai", "q", "u", "prompt_action", "faq", SECRET);
        assertEquals("text-embedding-3-large", kwargs(0).get("model"));
    }

    /** c5: truncated_texts cut to 8191 cl100k_base tokens; short text unchanged. */
    @Test
    void truncatedTextsCutTo8191Tokens() {
        String longText = "word ".repeat(9000);
        assertEquals(true, CL100K.countTokens(longText) >= 9000);
        stub.on(PATH, request -> StubServer.Reply.json(200, "[[0.1], [0.2]]"));
        client.embedAll(BOT, "openai", List.of(longText, "short text"), "u", "prompt_action", "default", SECRET);

        List<?> truncated = (List<?>) kwargs(0).get("truncated_texts");
        assertEquals(2, truncated.size());
        assertEquals(8191, CL100K.countTokens((String) truncated.get(0)));
        assertEquals(longText.substring(0, ((String) truncated.get(0)).length()), truncated.get(0));
        assertEquals("short text", truncated.get(1));
        assertEquals(List.of(longText, "short text"), body(0).get("text"));
    }

    /** c6: kwargs.api_key is the embedding secret's api_key (LlmSecrets.embeddingSecret, R6). */
    @Test
    void apiKeyFromEmbeddingSecret() {
        catalog.put(ActionCatalog.LLM_SECRET, new Document("bot", BOT).append("llm_type", "openai")
                .append("api_key", tokens.encrypt("openai-key")));
        catalog.put(ActionCatalog.LLM_SECRET, new Document("bot", BOT).append("llm_type", "anthropic")
                .append("api_key", tokens.encrypt("anthropic-key")));
        Map<String, String> embeddingSecret = new LlmSecrets(catalog, tokens).embeddingSecret(BOT, "anthropic");
        stub.on("/my%20bot/aembedding/anthropic", request -> StubServer.Reply.json(200, "[[0.1]]"));

        client.embed(BOT, "anthropic", "q", "u", "prompt_action", "default", embeddingSecret);
        Map<?, ?> body = (Map<?, ?>) Jsons.readAny(stub.at("/my%20bot/aembedding/anthropic").get(0).text());
        assertEquals("openai-key", ((Map<?, ?>) body.get("kwargs")).get("api_key"));
    }

    /** c6: a secret without api_key sends null (dict.get). */
    @Test
    void missingApiKeyIsNull() {
        stub.on(PATH, request -> StubServer.Reply.json(200, "[[0.1]]"));
        client.embed(BOT, "openai", "q", "u", "prompt_action", "default", Map.of());
        assertEquals(true, kwargs(0).containsKey("api_key"));
        assertEquals(null, kwargs(0).get("api_key"));
    }

    /** c7: single input + list response -> first element; list input -> full response; non-list as-is. */
    @Test
    void singleInputReturnsFirstVector() {
        stub.on(PATH, request -> StubServer.Reply.json(200, "[[0.1, 0.2], [0.3]]"));
        assertEquals(List.of(0.1, 0.2), client.embed(BOT, "openai", "q", "u", "prompt_action", "default", SECRET));
        assertEquals(List.of(List.of(0.1, 0.2), List.of(0.3)),
                client.embedAll(BOT, "openai", List.of("q"), "u", "prompt_action", "default", SECRET));

        stub.on(PATH, request -> StubServer.Reply.json(200, "{\"data\": 1}"));
        assertEquals(Map.of("data", 1), client.embed(BOT, "openai", "q", "u", "prompt_action", "default", SECRET));

        stub.on(PATH, request -> StubServer.Reply.json(200, "[]"));
        ActionFailure empty = assertThrows(ActionFailure.class,
                () -> client.embed(BOT, "openai", "q", "u", "prompt_action", "default", SECRET));
        assertEquals("list index out of range", empty.getMessage());
    }

    /** c8: status outside 200-204 fails per R3; exactly one request. */
    @Test
    void nonOkStatusFailsPerTransportRules() {
        stub.on(PATH, request -> StubServer.Reply.json(500, "{\"error\": \"boom\"}"));
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> client.embed(BOT, "openai", "q", "u", "prompt_action", "default", SECRET));
        assertEquals("Internal Server Error", failure.getMessage());
        assertEquals(1, stub.at(PATH).size());

        stub.on(PATH, request -> StubServer.Reply.json(206, "[[0.1]]"));
        failure = assertThrows(ActionFailure.class,
                () -> client.embed(BOT, "openai", "q", "u", "prompt_action", "default", SECRET));
        assertEquals("Partial Content", failure.getMessage());
        assertFalse(stub.at(PATH).isEmpty());
    }
}
