package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.support.llm.AnswerParams;
import com.kairon.action.support.llm.LlmClient;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/** T-118: llm-vector-clients R2 c5-c8 (message building, rephrase, perplexity). */
class LlmClientMessagesTest {

    private static final String PATH = "/bot1/completion/openai";
    private static final Map<String, Object> HYPER = Map.of("temperature", 0.0, "model", "gpt-4o-mini");
    private static final List<Map<String, Object>> HISTORY = List.of(
            Map.of("role", "user", "content", "earlier q"), Map.of("role", "assistant", "content", "earlier a"));

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

    private static AnswerParams params(String llmType, String queryPrompt, boolean useQueryPrompt,
                                       List<Map<String, Object>> history, Object hyper, Object instructions) {
        return new AnswerParams("bot1", "openai", llmType, "What is kairon?", "You are helpful", "CTX", "alice",
                "prompt_action", List.of("m1"), true, queryPrompt, useQueryPrompt, history, hyper, instructions);
    }

    private Map<?, ?> body(int index) {
        return (Map<?, ?>) Jsons.readAny(stub.at(PATH).get(index).text());
    }

    private static Map<String, Object> msg(String role, String content) {
        return Map.of("role", role, "content", content);
    }

    /** c6 + c7: [system, user] without history; user content without instructions. */
    @Test
    void mainMessagesWithoutHistoryOrInstructions() {
        stub.on(PATH, request -> StubServer.Reply.json(200,
                "{\"formatted_response\": \"ans\", \"response\": {\"litellm_call_id\": \"L1\"}}"));
        List<Map<String, Object>> logs = new ArrayList<>();
        LlmClient.Answer answer = client.answer(params("openai", null, false, List.of(), HYPER, List.of()), logs);

        assertEquals(1, stub.at(PATH).size());
        assertEquals(List.of(msg("system", "You are helpful"), msg("user", "CTX \nQ: What is kairon? \nA:")),
                body(0).get("messages"));
        assertEquals("prompt_action", body(0).get("invocation"));
        assertEquals(List.of("m1"), body(0).get("media_ids"));
        assertEquals(true, body(0).get("should_process_media"));
        assertEquals("alice", body(0).get("user"));
        assertEquals(HYPER, body(0).get("hyperparameters"));
        assertEquals("ans", answer.content());
        assertEquals("L1", answer.callId());

        assertEquals(1, logs.size());
        assertEquals(List.of("messages", "raw_completion_response", "type", "hyperparameters"),
                new ArrayList<>(logs.get(0).keySet()));
        assertEquals("answer_query", logs.get(0).get("type"));
        assertEquals(Map.of("litellm_call_id", "L1"), logs.get(0).get("raw_completion_response"));
    }

    /** c6 + c7: history between system and user; instructions joined with \n. */
    @Test
    void mainMessagesWithHistoryAndInstructions() {
        stub.on(PATH, request -> StubServer.Reply.json(200, "{\"formatted_response\": \"ans\"}"));
        client.answer(params("openai", null, false, HISTORY, HYPER, List.of("be brief", "cite")));

        List<?> messages = (List<?>) body(0).get("messages");
        assertEquals(4, messages.size());
        assertEquals(msg("system", "You are helpful"), messages.get(0));
        assertEquals(HISTORY.get(0), messages.get(1));
        assertEquals(HISTORY.get(1), messages.get(2));
        assertEquals(msg("user", "CTX \nbe brief\ncite \nQ: What is kairon? \nA:"), messages.get(3));
    }

    /** c7: null / empty-string instructions behave as absent; a string joins its characters. */
    @Test
    void instructionEdgeCases() {
        stub.on(PATH, request -> StubServer.Reply.json(200, "{\"formatted_response\": \"ans\"}"));
        client.answer(params("openai", null, false, null, HYPER, null));
        client.answer(params("openai", null, false, null, HYPER, List.of("")));
        client.answer(params("openai", null, false, null, HYPER, "ab"));
        String plain = "CTX \nQ: What is kairon? \nA:";
        assertEquals(plain, ((Map<?, ?>) ((List<?>) body(0).get("messages")).get(1)).get("content"));
        assertEquals(plain, ((Map<?, ?>) ((List<?>) body(1).get("messages")).get(1)).get("content"));
        assertEquals("CTX \na\nb \nQ: What is kairon? \nA:",
                ((Map<?, ?>) ((List<?>) body(2).get("messages")).get(1)).get("content"));
    }

    /** c5: rephrase completion first; its content replaces the query in the main completion. */
    @Test
    void rephraseRunsFirstAndReplacesQuery() {
        List<String> order = new ArrayList<>();
        stub.on(PATH, request -> {
            Map<?, ?> body = (Map<?, ?>) Jsons.readAny(request.text());
            order.add(String.valueOf(body.get("invocation")));
            return "prompt_action_rephrase".equals(body.get("invocation"))
                    ? StubServer.Reply.json(200, "{\"formatted_response\": \"Rephrased?\", \"response\": {\"id\": \"r\"}}")
                    : StubServer.Reply.json(200, "{\"formatted_response\": \"final\", \"response\": {\"id\": \"a\"}}");
        });
        List<Map<String, Object>> logs = new ArrayList<>();
        LlmClient.Answer answer = client.answer(params("openai", "Rephrase it", true, HISTORY, HYPER, List.of()), logs);

        assertEquals(List.of("prompt_action_rephrase", "prompt_action"), order);
        Map<?, ?> rephrase = body(0);
        assertEquals(List.of(msg("system", "You are helpful"),
                msg("user", "Rephrase it\n\n Q: What is kairon?\n A:")), rephrase.get("messages"));
        assertEquals(List.of(), rephrase.get("media_ids"));
        assertEquals(false, rephrase.get("should_process_media"));
        assertEquals(HYPER, rephrase.get("hyperparameters"));
        assertEquals("alice", rephrase.get("user"));

        List<?> main = (List<?>) body(1).get("messages");
        assertEquals(msg("user", "CTX \nQ: Rephrased? \nA:"), main.get(main.size() - 1));
        assertEquals(List.of("m1"), body(1).get("media_ids"));
        assertEquals("final", answer.content());

        assertEquals(List.of("rephrase_query", "answer_query"), logs.stream().map(log -> log.get("type")).toList());
        assertEquals(Map.of("id", "r"), logs.get(0).get("raw_completion_response"));
    }

    /** c5: no rephrase when disabled or when the query prompt is empty. */
    @Test
    void noRephraseWhenDisabledOrEmpty() {
        stub.on(PATH, request -> StubServer.Reply.json(200, "{\"formatted_response\": \"ans\"}"));
        client.answer(params("openai", "Rephrase it", false, null, HYPER, null));
        client.answer(params("openai", "", true, null, HYPER, null));
        client.answer(params("openai", null, true, null, HYPER, null));
        assertEquals(3, stub.at(PATH).size());
        for (int i = 0; i < 3; i++) {
            assertEquals("prompt_action", body(i).get("invocation"));
        }
    }

    /** c5: a failing main completion keeps the rephrase log entry already captured. */
    @Test
    void rephraseLogSurvivesMainFailure() {
        stub.on(PATH, request -> {
            Map<?, ?> body = (Map<?, ?>) Jsons.readAny(request.text());
            return "prompt_action_rephrase".equals(body.get("invocation"))
                    ? StubServer.Reply.json(200, "{\"formatted_response\": \"R\"}")
                    : StubServer.Reply.json(500, "{}");
        });
        List<Map<String, Object>> logs = new ArrayList<>();
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> client.answer(params("openai", "Rephrase it", true, null, HYPER, null), logs));
        assertEquals("Internal Server Error", failure.getMessage());
        assertEquals(List.of("rephrase_query"), logs.stream().map(log -> log.get("type")).toList());
    }

    /** c8: perplexity + search_domain_filter suffixes the query; endpoint uses endpointLlmType. */
    @Test
    void perplexityAppendsSearchDomainFilter() {
        stub.on(PATH, request -> StubServer.Reply.json(200, "{\"formatted_response\": \"ans\"}"));
        Map<String, Object> hyper = Map.of("model", "sonar", "search_domain_filter", List.of("d1.com", " d2.com ", " "));
        client.answer(params("perplexity", null, false, null, hyper, null));
        List<?> messages = (List<?>) body(0).get("messages");
        assertEquals(msg("user", "CTX \nQ: What is kairon? inurl:d1.com|d2.com \nA:"), messages.get(1));
    }

    /** c8: no suffix for other llm types, or without / with an empty filter. */
    @Test
    void perplexitySuffixOnlyWhenApplicable() {
        stub.on(PATH, request -> StubServer.Reply.json(200, "{\"formatted_response\": \"ans\"}"));
        Map<String, Object> filtered = Map.of("search_domain_filter", List.of("d1"));
        client.answer(params("openai", null, false, null, filtered, null));
        client.answer(params("perplexity", null, false, null, HYPER, null));
        client.answer(params("perplexity", null, false, null, Map.of("search_domain_filter", List.of()), null));
        String plain = "CTX \nQ: What is kairon? \nA:";
        for (int i = 0; i < 3; i++) {
            assertEquals(plain, ((Map<?, ?>) ((List<?>) body(i).get("messages")).get(1)).get("content"));
        }
    }

    /** c8: the rephrased query is what gets the perplexity suffix. */
    @Test
    void perplexitySuffixAppliedAfterRephrase() {
        stub.on(PATH, request -> {
            Map<?, ?> body = (Map<?, ?>) Jsons.readAny(request.text());
            return "prompt_action_rephrase".equals(body.get("invocation"))
                    ? StubServer.Reply.json(200, "{\"formatted_response\": \"R\"}")
                    : StubServer.Reply.json(200, "{\"formatted_response\": \"ans\"}");
        });
        client.answer(params("perplexity", "QP", true, null, Map.of("search_domain_filter", List.of("a", "b")), null));
        assertEquals("QP\n\n Q: What is kairon?\n A:",
                ((Map<?, ?>) ((List<?>) body(0).get("messages")).get(1)).get("content"));
        assertEquals("CTX \nQ: R inurl:a|b \nA:",
                ((Map<?, ?>) ((List<?>) body(1).get("messages")).get(1)).get("content"));
    }

    @Test
    void modifyUserMessageForPerplexityHelper() {
        assertEquals("q inurl:x|y", LlmClient.modifyUserMessageForPerplexity("q", "perplexity",
                Map.of("search_domain_filter", List.of("x", "y"))));
        assertEquals("q", LlmClient.modifyUserMessageForPerplexity("q", "openai",
                Map.of("search_domain_filter", List.of("x"))));
    }
}
