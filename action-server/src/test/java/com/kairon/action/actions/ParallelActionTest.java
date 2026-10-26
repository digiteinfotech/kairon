package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.support.Jsons;
import com.sun.net.httpserver.HttpServer;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import io.micronaut.test.support.TestPropertyProvider;
import jakarta.inject.Inject;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * T-044: orchestration-actions R1 c2-c3, c5 (plus c4, c6, c7, c8, c9). The own-webhook URL is pointed at a
 * stub that records each child POST and answers with canned child responses.
 */
@MicronautTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ParallelActionTest implements TestPropertyProvider {

    private static final String BOT = "bot-par";
    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    /** One child POST as the stub saw it, plus the parent log records present at that moment. */
    record Child(String requestId, Map<String, Object> body, List<Document> logsAtCall) {}

    private final List<Child> children = new CopyOnWriteArrayList<>();
    private HttpServer stub;

    @Inject
    EmbeddedServer server;

    @Inject
    MemoryActionCatalog catalog;

    @Override
    public Map<String, String> getProperties() {
        try {
            stub = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        stub.createContext("/self/webhook", exchange -> {
            Map<String, Object> body = Jsons.readMap(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            children.add(new Child(exchange.getRequestHeaders().getFirst(Kairon.REQUEST_ID), body, catalog.all(Kairon.LOGS)));
            String reply;
            int status = 200;
            switch (String.valueOf(body.get("next_action"))) {
                case "child_a" -> {
                    sleep(300); // finishes last, yet child_b still wins: merge follows child order, not timing
                    reply = "{\"events\":[{\"event\":\"slot\",\"timestamp\":null,\"name\":\"city\",\"value\":\"Pune\"},"
                            + "{\"event\":\"slot\",\"timestamp\":null,\"name\":\"zip\",\"value\":\"411001\"},"
                            + "{\"event\":\"bot\",\"text\":\"not a slot\"}],"
                            + "\"responses\":[{\"text\":\"child a speaks\"}]}";
                }
                case "child_b" -> reply = "{\"events\":[{\"event\":\"slot\",\"timestamp\":null,\"name\":\"city\",\"value\":\"Mumbai\"}],"
                        + "\"responses\":[{\"text\":\"child b speaks\"}]}";
                default -> {
                    status = 500;
                    reply = "Internal Server Error";
                }
            }
            byte[] bytes = reply.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", status == 200 ? "application/json" : "text/plain");
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        stub.start();
        return Map.of("kairon.action.action-server-url", "http://127.0.0.1:" + stub.getAddress().getPort() + "/self/webhook");
    }

    @AfterAll
    void stopStub() {
        stub.stop(0);
    }

    @BeforeEach
    void reset() {
        catalog.clear();
        children.clear();
        catalog.put("actions", new Document("bot", BOT).append("name", "fan").append("type", "parallel_action").append("status", true));
    }

    private void config(boolean dispatch) {
        catalog.put("parallel_action_config", new Document("bot", BOT).append("name", "fan").append("status", true)
                .append("actions", List.of("child_a", "child_b", "child_broken"))
                .append("dispatch_response_text", dispatch).append("response_text", "all done"));
    }

    @Test
    void childrenPostToOwnWebhookAndSlotsMergeInChildOrder() throws Exception {
        config(true);
        Map<String, Object> request = request();

        Map<String, Object> body = post(request, "parent-req-1");

        // c3 one POST per child at the configured URL, c5 parent request id header
        assertEquals(3, children.size());
        List<String> names = new ArrayList<>();
        for (Child child : children) {
            names.add(String.valueOf(child.body().get("next_action")));
            assertEquals("parent-req-1", child.requestId());
        }
        names.sort(String::compareTo);
        assertEquals(List.of("child_a", "child_b", "child_broken"), names);

        // c2 the pre-created record exists before any child call and matches Python
        // ActionServerLogs(request_id=...).save(): mongoengine defaults plus request_id; its _id is the trigger_id
        Document parent = catalog.all(Kairon.LOGS).get(0);
        String trigger = String.valueOf(parent.get("_id"));
        java.util.Date created = null;
        for (Child child : children) {
            List<Document> before = child.logsAtCall();
            assertEquals(1, before.size());
            Document pre = before.get(0);
            assertEquals(List.of("_id", "timestamp", "status", "trigger_info", "request_id"), List.copyOf(pre.keySet()));
            assertEquals(trigger, String.valueOf(pre.get("_id")));
            assertTrue(pre.get("timestamp") instanceof java.util.Date);
            assertEquals(Kairon.SUCCESS, pre.get("status"));
            assertEquals(new Document("trigger_name", "").append("trigger_type", "implicit").append("trigger_id", ""), pre.get("trigger_info"));
            assertEquals("parent-req-1", pre.get("request_id"));
            created = (java.util.Date) pre.get("timestamp");
        }

        // c4 child body = original request with next_action and trigger_info replaced
        for (Child child : children) {
            Map<String, Object> expected = new LinkedHashMap<>(request);
            expected.put("next_action", child.body().get("next_action"));
            expected.put("trigger_info", Map.of("trigger_name", "fan", "trigger_type", "parallel_action", "trigger_id", trigger));
            assertEquals(expected, child.body());
        }

        // c6 child utterances discarded; slot events merged last-write-wins in child order
        assertEquals(List.of(Map.of("text", "all done")), stripNulls(body.get("responses")));
        assertEquals("Mumbai", slot(body, "city"));
        assertEquals("411001", slot(body, "zip"));
        assertEquals("all done", slot(body, Kairon.ACTION_RESPONSE));

        // c7 broken child does not fail the parent; c9 record filled in place
        List<Document> logs = catalog.all(Kairon.LOGS);
        assertEquals(1, logs.size());
        Document filled = logs.get(0);
        assertEquals(trigger, String.valueOf(filled.get("_id")));
        assertEquals("parallel_action", filled.get("type"));
        assertEquals("fan", filled.get("action"));
        assertEquals("sender-1", filled.get("sender"));
        assertEquals("all done", filled.get("bot_response"));
        assertEquals(null, filled.get("exception"));
        assertEquals(Kairon.SUCCESS, filled.get("status"));
        assertEquals("hi", filled.get("user_msg"));
        assertEquals("parent-req-1", filled.get("request_id"));
        assertEquals(new Document("trigger_name", "").append("trigger_type", "implicit").append("trigger_id", ""), filled.get("trigger_info"));
        assertEquals(created, filled.get("timestamp"), "fill keeps the pre-record creation timestamp");
    }

    @Test
    void noDispatchMeansNoUtteranceAndNoActionResponse() throws Exception {
        config(false);

        Map<String, Object> body = post(request(), null);

        assertEquals(3, children.size());
        for (Child child : children) {
            assertFalse(child.requestId() == null || child.requestId().isBlank(), "generated parent id is propagated");
        }
        String generated = children.get(0).requestId();
        assertTrue(children.stream().allMatch(child -> generated.equals(child.requestId())));
        assertEquals(List.of(), body.get("responses"));
        assertEquals("Mumbai", slot(body, "city"));
        assertFalse(hasSlot(body, Kairon.ACTION_RESPONSE));
        Document filled = catalog.all(Kairon.LOGS).get(0);
        assertEquals(Kairon.SUCCESS, filled.get("status"));
        assertEquals(null, filled.get("bot_response"));
        assertEquals(generated, filled.get("request_id"));
    }

    private Map<String, Object> request() {
        Map<String, Object> slots = new LinkedHashMap<>();
        slots.put("bot", BOT);
        slots.put("city", null);
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "sender-1");
        tracker.put("slots", slots);
        tracker.put("latest_message", Map.of("text", "hi", "intent", Map.of("name", "greet")));
        tracker.put("events", List.of());
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("next_action", "fan");
        request.put("sender_id", "sender-1");
        request.put("tracker", tracker);
        request.put("domain", Map.of("slots", Map.of()));
        request.put("version", "3.6.21");
        return request;
    }

    private Map<String, Object> post(Map<String, Object> request, String requestId) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + server.getPort() + "/webhook"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(Jsons.write(request)));
        if (requestId != null) {
            builder.header(Kairon.REQUEST_ID, requestId);
        }
        HttpResponse<String> response = CLIENT.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode(), response.body());
        return Jsons.readMap(response.body());
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> stripNulls(Object responses) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object item : (List<Object>) responses) {
            Map<String, Object> copy = new LinkedHashMap<>();
            ((Map<String, Object>) item).forEach((key, value) -> {
                if (value != null && !(value instanceof List<?> list && list.isEmpty())
                        && !(value instanceof Map<?, ?> map && map.isEmpty())) {
                    copy.put(key, value);
                }
            });
            out.add(copy);
        }
        return out;
    }

    @SuppressWarnings("unchecked")
    private static boolean hasSlot(Map<String, Object> body, String name) {
        for (Object item : (List<Object>) body.get("events")) {
            if (name.equals(((Map<String, Object>) item).get("name"))) {
                return true;
            }
        }
        return false;
    }

    @SuppressWarnings("unchecked")
    private static Object slot(Map<String, Object> body, String name) {
        Object found = null;
        boolean seen = false;
        for (Object item : (List<Object>) body.get("events")) {
            Map<String, Object> event = (Map<String, Object>) item;
            if (name.equals(event.get("name"))) {
                found = event.get("value");
                seen = true;
            }
        }
        if (!seen) {
            throw new AssertionError("missing slot " + name + " in " + body);
        }
        return found;
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
