package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.runtime.ActionFailure;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-020: raising exchange (outbound-clients R2 c1-c4) and expression evaluator client (R6 c1-c4). */
class HttpCallerStrictTest {

    private static final String STAMP = "\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}";

    private StubServer stub;
    private ActionSettings settings;
    private HttpCaller caller;

    @BeforeEach
    void setUp() throws Exception {
        stub = StubServer.start();
        stub.on("/ok", request -> StubServer.Reply.json(200, "{\"ok\": true}"));
        stub.on("/fail", request -> StubServer.Reply.json(500, "{\"error\": \"boom\"}"));
        settings = new ActionSettings();
        settings.setRequestTimeout(5);
        settings.setEvaluatorUrl(stub.url("/eval"));
        caller = new HttpCaller(settings);
    }

    @AfterEach
    void tearDown() {
        stub.close();
    }

    @Test
    void nonSuccessStatusRaisesFailedToExecute() {
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> caller.executeStrict("POST", stub.url("/fail"), Map.of(), Map.of("a", 1), "json"));
        assertEquals("Failed to execute the url: Got non-200 status code: 500 {\"error\": \"boom\"}", failure.getMessage());
    }

    @Test
    void transportErrorRaisesFailedToExecute() {
        String closed = stub.url("/ok");
        stub.close();
        ActionFailure failure = assertThrows(ActionFailure.class, () -> caller.executeStrict("GET", closed, Map.of(), null, "json"));
        assertTrue(failure.getMessage().startsWith("Failed to execute the url:"), failure.getMessage());
    }

    @Test
    void invalidMethodRaises() {
        ActionFailure failure = assertThrows(ActionFailure.class, () -> caller.executeStrict("PATCH", stub.url("/ok"), Map.of(), null, "json"));
        assertEquals("Failed to execute the url: Invalid request method!", failure.getMessage());
        assertTrue(stub.requests.isEmpty());
    }

    @Test
    void getSendsParametersInTheQuery() {
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("q", "kairon bot");
        params.put("page", 2);
        assertEquals(Map.of("ok", true), caller.executeStrict("get", stub.url("/ok"), Map.of(), params, "json"));
        StubServer.Captured request = stub.requests.get(0);
        assertEquals("GET", request.method());
        assertEquals("q=kairon+bot&page=2", request.query());
        assertEquals(0, request.body().length);
    }

    @Test
    void postPutDeleteSendJsonOrFormBody() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("name", "a b");
        body.put("n", 1);
        for (String method : List.of("POST", "PUT", "DELETE")) {
            caller.executeStrict(method, stub.url("/ok"), Map.of(), body, "json");
            caller.executeStrict(method, stub.url("/ok"), Map.of(), body, "data");
        }
        assertEquals(6, stub.requests.size());
        for (int i = 0; i < 6; i += 2) {
            StubServer.Captured json = stub.requests.get(i);
            StubServer.Captured form = stub.requests.get(i + 1);
            assertEquals(List.of("POST", "PUT", "DELETE").get(i / 2), json.method());
            assertEquals(json.method(), form.method());
            assertNull(json.query());
            assertEquals("application/json", json.header("Content-Type"));
            assertEquals(Map.of("name", "a b", "n", 1), Jsons.readAny(json.text()));
            assertEquals("application/x-www-form-urlencoded", form.header("Content-Type"));
            assertEquals("name=a+b&n=1", form.text());
        }
    }

    @Test
    void timestampHeaderIsAddedToEachRequest() {
        caller.executeStrict("GET", stub.url("/ok"), Map.of(), null, "json");
        caller.executeStrict("POST", stub.url("/ok"), Map.of("X-Other", "1"), Map.of(), "json");
        caller.exchange("POST", stub.url("/ok"), null, null, "json");
        assertEquals(3, stub.requests.size());
        stub.requests.forEach(request -> assertTrue(request.header("X-TimeStamp").matches(STAMP), request.header("X-TimeStamp")));
    }

    private ActionSupport support() {
        return new ActionSupport(null, settings, null, caller);
    }

    @Test
    void evaluatorPostsScriptAndDataAndReturnsData() {
        stub.on("/eval", request -> StubServer.Reply.json(200, "{\"success\": true, \"data\": {\"value\": 42}}"));
        Object result = support().evaluateScript("${data.value}", Map.of("value", 42));
        assertEquals(Map.of("value", 42), result);
        StubServer.Captured request = stub.requests.get(0);
        assertEquals("POST", request.method());
        assertEquals("/eval", request.path());
        assertEquals("application/json", request.header("Content-Type"));
        assertEquals(Map.of("script", "${data.value}", "data", Map.of("value", 42)), Jsons.readAny(request.text()));
        assertTrue(request.header("X-TimeStamp").matches(STAMP));
        ActionSupport.ScriptEval eval = support().evaluateScriptLogged("${data.value}", Map.of("value", 42));
        assertEquals(Map.of("value", 42), eval.data());
        assertEquals("evaluation_type: script", eval.log().get(0));
        assertEquals("raise_err_on_failure: True", eval.log().get(3));
        assertTrue(eval.log().get(4).startsWith("Evaluator response: "), eval.log().get(4));
        assertTrue(eval.log().get(4).contains("'success': True"), eval.log().get(4));
    }

    @Test
    void evaluatorSuccessFalseRaisesExpressionEvaluationFailed() {
        stub.on("/eval", request -> StubServer.Reply.json(200, "{\"success\": false, \"data\": null, \"message\": \"bad\"}"));
        ActionFailure failure = assertThrows(ActionFailure.class, () -> support().evaluateScript("bad(", Map.of()));
        assertTrue(failure.getMessage().startsWith("Expression evaluation failed:"), failure.getMessage());
    }

    @Test
    void evaluatorNonSuccessStatusRaisesFailedToExecute() {
        stub.on("/eval", request -> StubServer.Reply.json(503, "{\"success\": true}"));
        ActionFailure failure = assertThrows(ActionFailure.class, () -> support().evaluateScript("x", Map.of()));
        assertTrue(failure.getMessage().startsWith("Failed to execute the url: Got non-200 status code: 503"), failure.getMessage());
    }
}
