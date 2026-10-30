package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.llm.LlmClient;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

/** T-116: llm-vector-clients R2 c1-c4, c9. */
class LlmClientCompletionTest {

    private static final List<Map<String, Object>> MESSAGES = List.of(
            Map.of("role", "system", "content", "sys"), Map.of("role", "user", "content", "Q: hi \nA:"));
    private static final Map<String, Object> HYPER = Map.of("temperature", 0.0, "model", "gpt-4o-mini");

    private StubServer stub;
    private LlmClient client;

    @BeforeEach
    void setUp() throws Exception {
        stub = StubServer.start();
        ActionSettings settings = new ActionSettings();
        settings.setLlmServerUrl(stub.url(""));
        settings.setRequestTimeout(1);
        settings.setLlmRequestTimeout(1);
        client = new LlmClient(new LlmHttp(new HttpCaller(settings), settings), settings);
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    /** c1: POST to {llm.url}/{url-quoted bot}/completion/{llm_type}. */
    @Test
    void postsToQuotedBotCompletionUrl() {
        stub.on("/my%20bot/completion/openai", request -> StubServer.Reply.json(200, "{\"formatted_response\": \"ok\"}"));
        client.complete("my bot", "openai", MESSAGES, HYPER, "alice", "prompt_action", null, false);
        List<StubServer.Captured> captured = stub.at("/my%20bot/completion/openai");
        assertEquals(1, captured.size());
        assertEquals("POST", captured.get(0).method());
        assertEquals("/my%20bot/completion/openai", stub.requests.get(0).path());
    }

    /** c2: body keys in Python order; media_ids [] when none. */
    @Test
    void bodyHasPythonKeysAndEmptyMediaIds() {
        stub.on("/bot1/completion/openai", request -> StubServer.Reply.json(200, "{\"formatted_response\": \"ok\"}"));
        client.complete("bot1", "openai", MESSAGES, HYPER, "alice", "prompt_action", null, false);
        client.complete("bot1", "openai", MESSAGES, HYPER, "alice", "prompt_action", List.of(), true);
        client.complete("bot1", "openai", MESSAGES, HYPER, "alice", null, List.of("m1", "m2"), true);

        List<StubServer.Captured> captured = stub.at("/bot1/completion/openai");
        Map<?, ?> first = (Map<?, ?>) Jsons.readAny(captured.get(0).text());
        assertEquals(List.of("messages", "hyperparameters", "user", "invocation", "media_ids", "should_process_media"),
                new ArrayList<>(first.keySet()));
        assertEquals(MESSAGES, first.get("messages"));
        assertEquals(HYPER, first.get("hyperparameters"));
        assertEquals("alice", first.get("user"));
        assertEquals("prompt_action", first.get("invocation"));
        assertEquals(List.of(), first.get("media_ids"));
        assertEquals(false, first.get("should_process_media"));

        Map<?, ?> second = (Map<?, ?>) Jsons.readAny(captured.get(1).text());
        assertEquals(List.of(), second.get("media_ids"));
        assertEquals(true, second.get("should_process_media"));

        Map<?, ?> third = (Map<?, ?>) Jsons.readAny(captured.get(2).text());
        assertEquals(List.of("m1", "m2"), third.get("media_ids"));
        assertEquals(true, third.containsKey("invocation"));
        assertNull(third.get("invocation"));
    }

    /** c3: object response -> content formatted_response, raw response. */
    @Test
    void objectResponseSplitsContentAndRaw() {
        stub.on("/b/completion/openai", request -> StubServer.Reply.json(200,
                "{\"formatted_response\": \"answer\", \"response\": {\"id\": \"x\", \"choices\": []}}"));
        LlmClient.Completion completion = client.complete("b", "openai", MESSAGES, HYPER, "u", "prompt_action", null, false);
        assertEquals("answer", completion.content());
        assertEquals(Map.of("id", "x", "choices", List.of()), completion.raw());
    }

    /** c3: missing keys -> null like dict.get. */
    @Test
    void objectResponseWithoutKeysGivesNulls() {
        stub.on("/b/completion/openai", request -> StubServer.Reply.json(200, "{\"other\": 1}"));
        LlmClient.Completion completion = client.complete("b", "openai", MESSAGES, HYPER, "u", "prompt_action", null, false);
        assertNull(completion.content());
        assertNull(completion.raw());
        assertNull(completion.callId());
    }

    /** c3: non-object response (list / text) -> both are the body as-is. */
    @Test
    void nonObjectResponseIsBothContentAndRaw() {
        stub.on("/b/completion/openai", request -> StubServer.Reply.json(200, "[\"a\", \"b\"]"));
        LlmClient.Completion list = client.complete("b", "openai", MESSAGES, HYPER, "u", "prompt_action", null, false);
        assertEquals(List.of("a", "b"), list.content());
        assertEquals(List.of("a", "b"), list.raw());
        assertNull(list.callId());

        stub.on("/b/completion/openai", request -> new StubServer.Reply(200, Map.of("Content-Type", "text/plain"), "plain"));
        LlmClient.Completion text = client.complete("b", "openai", MESSAGES, HYPER, "u", "prompt_action", null, false);
        assertEquals("plain", text.content());
        assertEquals("plain", text.raw());
        assertNull(text.callId());
    }

    /** c4: litellm_call_id preferred, else openrouter_call_id (falsy litellm id falls through). */
    @Test
    void callIdPrefersLitellmThenOpenrouter() {
        stub.on("/b/completion/openai", request -> StubServer.Reply.json(200,
                "{\"formatted_response\": \"a\", \"response\": {\"litellm_call_id\": \"L1\", \"openrouter_call_id\": \"O1\"}}"));
        assertEquals("L1", client.complete("b", "openai", MESSAGES, HYPER, "u", "i", null, false).callId());

        stub.on("/b/completion/openai", request -> StubServer.Reply.json(200,
                "{\"formatted_response\": \"a\", \"response\": {\"openrouter_call_id\": \"O1\"}}"));
        assertEquals("O1", client.complete("b", "openai", MESSAGES, HYPER, "u", "i", null, false).callId());

        stub.on("/b/completion/openai", request -> StubServer.Reply.json(200,
                "{\"formatted_response\": \"a\", \"response\": {\"litellm_call_id\": \"\", \"openrouter_call_id\": \"O2\"}}"));
        assertEquals("O2", client.complete("b", "openai", MESSAGES, HYPER, "u", "i", null, false).callId());

        stub.on("/b/completion/openai", request -> StubServer.Reply.json(200,
                "{\"formatted_response\": \"a\", \"response\": {\"id\": 1}}"));
        assertNull(client.complete("b", "openai", MESSAGES, HYPER, "u", "i", null, false).callId());

        stub.on("/b/completion/openai", request -> StubServer.Reply.json(200,
                "{\"formatted_response\": \"a\", \"response\": \"text raw\"}"));
        assertNull(client.complete("b", "openai", MESSAGES, HYPER, "u", "i", null, false).callId());
    }

    /** c9: status outside 200-204 fails per R3 (LlmHttp): >= 400 -> Internal Server Error, 206 -> its phrase. */
    @Test
    void nonOkStatusFailsPerTransportRules() {
        stub.on("/b/completion/openai", request -> StubServer.Reply.json(422, "{\"error\": \"bad\"}"));
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> client.complete("b", "openai", MESSAGES, HYPER, "u", "i", null, false));
        assertEquals("Internal Server Error", failure.getMessage());
        assertEquals(1, stub.at("/b/completion/openai").size());

        stub.on("/b/completion/openai", request -> StubServer.Reply.json(206, "{\"formatted_response\": \"a\"}"));
        failure = assertThrows(ActionFailure.class,
                () -> client.complete("b", "openai", MESSAGES, HYPER, "u", "i", null, false));
        assertEquals("Partial Content", failure.getMessage());
    }

    /** urllib.parse.quote: safe '/', unreserved kept, UTF-8 percent-encoded. */
    @Test
    void quoteFollowsUrllib() {
        assertEquals("a%20b/c_d.e-f~g", LlmClient.quote("a b/c_d.e-f~g"));
        assertEquals("%C3%A9%3F%26", LlmClient.quote("é?&"));
    }
}
