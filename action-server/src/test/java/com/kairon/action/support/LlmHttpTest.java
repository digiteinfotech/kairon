package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.RequestIds;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.ServerSocket;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-108: llm-vector-clients R3 c1-c6. */
class LlmHttpTest {

    private StubServer stub;
    private ActionSettings settings;
    private LlmHttp llm;

    @BeforeEach
    void setUp() throws Exception {
        stub = StubServer.start();
        settings = new ActionSettings();
        settings.setRequestTimeout(1);
        settings.setLlmRequestTimeout(1);
        llm = new LlmHttp(new HttpCaller(settings), settings);
    }

    @AfterEach
    void tearDown() {
        stub.close();
        RequestIds.clear();
    }

    /** c1: request id and timestamp headers, JSON body, no Authorization. */
    @Test
    void sendsRequestIdAndTimestampWithoutAuthorization() {
        stub.on("/bot/completion/openai", request -> StubServer.Reply.json(200, "{\"formatted_response\": \"hi\"}"));
        RequestIds.set("rid-123");
        Object response = llm.post(stub.url("/bot/completion/openai"), Map.of("messages", List.of()));
        assertEquals(Map.of("formatted_response", "hi"), response);
        StubServer.Captured captured = stub.at("/bot/completion/openai").get(0);
        assertEquals("POST", captured.method());
        assertEquals("rid-123", captured.header(Kairon.REQUEST_ID));
        assertNotNull(captured.header(Kairon.TIMESTAMP));
        assertTrue(captured.header(Kairon.TIMESTAMP).matches("\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}"));
        assertNull(captured.header("Authorization"));
        assertTrue(captured.header("Content-Type").startsWith("application/json"));
        assertEquals(Map.of("messages", List.of()), Jsons.readAny(captured.text()));
    }

    /** c1: no request id header when the request has none. */
    @Test
    void omitsRequestIdWhenAbsent() {
        stub.on("/e", request -> StubServer.Reply.json(200, "[1, 2]"));
        RequestIds.clear();
        assertEquals(List.of(1, 2), llm.post(stub.url("/e"), Map.of()));
        StubServer.Captured captured = stub.at("/e").get(0);
        assertNull(captured.header(Kairon.REQUEST_ID));
        assertNotNull(captured.header(Kairon.TIMESTAMP));
        assertNull(captured.header("Authorization"));
    }

    /** c2: default 30 s; llm.request_timeout bounds the call, not action.request_timeout. */
    @Test
    void timeoutIsLlmRequestTimeout() {
        assertEquals(30, new ActionSettings().getLlmRequestTimeout());
        ActionSettings defaults = new ActionSettings();
        assertEquals(30, new LlmHttp(new HttpCaller(defaults), defaults).timeout());

        stub.on("/slow", request -> {
            pause(1500);
            return StubServer.Reply.json(200, "{\"ok\": true}");
        });
        settings.setRequestTimeout(1);
        settings.setLlmRequestTimeout(3);
        assertEquals(Map.of("ok", true), llm.post(stub.url("/slow"), Map.of()));
    }

    /** c2 + c5: past llm.request_timeout the call fails with `Request Timeout`. */
    @Test
    void slowServerFailsWithRequestTimeout() {
        stub.on("/slow", request -> {
            pause(2000);
            return StubServer.Reply.json(200, "{}");
        });
        settings.setRequestTimeout(30);
        settings.setLlmRequestTimeout(1);
        long start = System.nanoTime();
        ActionFailure failure = assertThrows(ActionFailure.class, () -> llm.post(stub.url("/slow"), Map.of()));
        assertEquals("Request Timeout", failure.getMessage());
        assertTrue((System.nanoTime() - start) / 1_000_000 < 1900);
    }

    /** c3 + c4: a 500 is not retried and fails with the Python phrase. */
    @Test
    void serverErrorIsSentOnceAndFailsWithPhrase() {
        stub.on("/boom", request -> StubServer.Reply.json(500, "{\"error\": \"x\"}"));
        ActionFailure failure = assertThrows(ActionFailure.class, () -> llm.post(stub.url("/boom"), Map.of()));
        assertEquals("Internal Server Error", failure.getMessage());
        assertEquals(1, stub.at("/boom").size());
    }

    /** c3: 502/503/504 are not retried either. */
    @Test
    void gatewayErrorsAreNotRetried() {
        stub.on("/b", request -> StubServer.Reply.json(503, "{}"));
        ActionFailure failure = assertThrows(ActionFailure.class, () -> llm.post(stub.url("/b"), Map.of()));
        assertEquals("Service Unavailable", failure.getMessage());
        assertEquals(1, stub.at("/b").size());
    }

    /** c4: 404 -> `Not Found`. */
    @Test
    void notFoundFailsWithPhrase() {
        ActionFailure failure = assertThrows(ActionFailure.class, () -> llm.post(stub.url("/missing"), Map.of()));
        assertEquals("Not Found", failure.getMessage());
    }

    /** c4 (P3): Python HTTPStatus phrases, not the JDK's. */
    @Test
    void phrasesFollowPythonHttpStatus() {
        assertEquals("Request Entity Too Large", LlmHttp.phrase(413));
        assertEquals("Unprocessable Entity", LlmHttp.phrase(422));
        assertEquals("I'm a Teapot", LlmHttp.phrase(418));
        assertEquals("Request Timeout", LlmHttp.phrase(408));
        assertEquals("599 is not a valid HTTPStatus", LlmHttp.phrase(599));
    }

    /** c5: a refused connection fails with `Service Unavailable`. */
    @Test
    void connectionFailureIsServiceUnavailable() throws Exception {
        int port;
        try (ServerSocket socket = new ServerSocket(0)) {
            port = socket.getLocalPort();
        }
        ActionFailure failure = assertThrows(ActionFailure.class, () -> llm.post("http://127.0.0.1:" + port + "/x", Map.of()));
        assertEquals("Service Unavailable", failure.getMessage());
    }

    /** c5: any other transport error is `Internal Server Error`. */
    @Test
    void otherTransportErrorIsInternalServerError() {
        ActionFailure failure = assertThrows(ActionFailure.class, () -> llm.post("ftp://127.0.0.1/x", Map.of()));
        assertEquals("Internal Server Error", failure.getMessage());
    }

    /** c6: a 2xx non-JSON body is returned as raw text. */
    @Test
    void textBodyIsKeptRaw() {
        stub.on("/text", request -> new StubServer.Reply(200, Map.of("Content-Type", "text/plain"), "plain answer"));
        assertEquals("plain answer", llm.post(stub.url("/text"), Map.of()));
        stub.on("/broken", request -> new StubServer.Reply(200, Map.of("Content-Type", "text/plain"), "{not json"));
        assertEquals("{not json", llm.post(stub.url("/broken"), Map.of()));
    }

    private static void pause(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
