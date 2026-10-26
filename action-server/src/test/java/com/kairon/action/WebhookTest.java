package com.kairon.action;

import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.support.Jsons;
import com.kairon.action.support.Tokens;
import com.sun.net.httpserver.HttpServer;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

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

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@MicronautTest
class WebhookTest {

    private static final String BOT = "bot-1";
    private static final HttpClient CLIENT = HttpClient.newHttpClient();
    private static final List<String> EVENT_PATHS = new ArrayList<>();
    private static HttpServer events;
    private static HttpServer city;
    private static int cityPort;

    @Inject
    EmbeddedServer server;

    @Inject
    MemoryActionCatalog catalog;

    @Inject
    Tokens tokens;

    @BeforeAll
    static void servers() throws Exception {
        events = HttpServer.create(new InetSocketAddress("127.0.0.1", 18771), 0);
        events.createContext("/api/events/dispatch", exchange -> {
            synchronized (EVENT_PATHS) {
                EVENT_PATHS.add(exchange.getRequestURI().getPath());
            }
            byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        events.start();
        city = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        city.createContext("/city", exchange -> {
            byte[] body = "{\"city\":\"Pune\"}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        city.start();
        cityPort = city.getAddress().getPort();
    }

    @AfterAll
    static void stopServers() {
        if (events != null) {
            events.stop(0);
        }
        if (city != null) {
            city.stop(0);
        }
    }

    @BeforeEach
    void reset() {
        catalog.clear();
        synchronized (EVENT_PATHS) {
            EVENT_PATHS.clear();
        }
    }

    @Test
    void rootAndHealth() throws Exception {
        HttpResponse<String> root = CLIENT.send(HttpRequest.newBuilder(uri("/")).GET().build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, root.statusCode());
        assertEquals("Kairon Action Server Up and Running", Jsons.readMap(root.body()).get("message"));
        HttpResponse<String> health = CLIENT.send(HttpRequest.newBuilder(uri("/healthcheck")).GET().build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, health.statusCode());
        assertEquals("health check ok", Jsons.readMap(health.body()).get("message"));
    }

    @Test
    void slotSetKeepsNullTimestamp() {
        register("set_place", "slot_set_action");
        catalog.put("slot_set_action", doc(
                "bot", BOT, "name", "set_place", "status", true,
                "set_slots", List.of(
                        new Document("name", "city").append("type", "from_value").append("value", "Pune"),
                        new Document("name", "temp").append("type", "reset_slot")
                )));
        Map<String, Object> body = ok(call("set_place", slots(), latest("hi"), null));
        Map<String, Object> city = event(body, "city");
        Map<String, Object> temp = event(body, "temp");
        assertEquals("Pune", city.get("value"));
        assertNull(city.get("timestamp"));
        assertTrue(city.containsKey("timestamp"));
        assertNull(temp.get("value"));
        assertEquals("slot", temp.get("event"));
        assertEquals(List.of(), body.get("responses"));
        assertEquals(Kairon.SUCCESS, logs("set_place").get(0).get("status"));
    }

    @Test
    void utterNamesTheResponse() {
        Map<String, Object> domain = Map.of("responses", Map.of("utter_greet", List.of(Map.of("text", "Hello"))));
        Map<String, Object> body = ok(call("utter_greet", slots(), latest("hi"), domain));
        Map<String, Object> message = responses(body).get(0);
        assertEquals("utter_greet", message.get("template"));
        assertEquals("utter_greet", message.get("response"));
        Map<String, Object> slot = map(event(body, Kairon.ACTION_RESPONSE).get("value"));
        assertEquals("utter_greet", slot.get("response"));
    }

    @Test
    void voiceDisconnectCustomJson() {
        Map<String, Object> body = ok(call("kairon_voice_disconnect", slots(), latest("bye"), null));
        assertEquals(true, map(responses(body).get(0).get("custom")).get("disconnect"));
        assertEquals(Kairon.SUCCESS, logs("kairon_voice_disconnect").get(0).get("status"));
    }

    @Test
    void blankNextActionIsJsonNull() throws Exception {
        Reply reply = post("{\"next_action\":\"\",\"tracker\":{}}");
        assertEquals(200, reply.status());
        assertEquals("null", reply.body().trim());
        assertTrue(catalog.all(Kairon.LOGS).isEmpty());
    }

    @Test
    void unsupportedTypeStays200() {
        register("odd", "not_a_type");
        Map<String, Object> body = ok(call("odd", slots(), latest("hi"), null));
        assertEquals(List.of(), body.get("events"));
        Document log = logs("odd").get(0);
        assertEquals(Kairon.FAIL, log.get("status"));
        assertNull(log.get("type"));
        assertTrue(String.valueOf(log.get("exception")).contains("not_a_type type action is not supported"));
    }

    @Test
    void missingActionStays200() {
        Map<String, Object> body = ok(call("missing", slots(), latest("hi"), null));
        assertEquals(List.of(), body.get("events"));
        Document log = logs("missing").get(0);
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("No action found for given bot and name", log.get("exception"));
    }

    @Test
    void missingBotSlotStays200() {
        Map<String, Object> body = ok(call("anything", Map.of(), latest("hi"), null));
        assertEquals(List.of(), body.get("events"));
        assertEquals("Bot id and action name not found in slot", logs("anything").get(0).get("exception"));
    }

    @Test
    void missingTrackerIs422() throws Exception {
        Reply reply = post("{\"next_action\":\"x\"}");
        assertEquals(422, reply.status());
        Map<String, Object> body = Jsons.readMap(reply.body());
        assertEquals(false, body.get("success"));
        assertEquals(422, ((Number) body.get("error_code")).intValue());
        assertEquals("tracker", body.get("message"));
        assertNull(body.get("data"));
    }

    @Test
    void emptyBodyIs422() throws Exception {
        Reply reply = post("   ");
        assertEquals(422, reply.status());
        assertEquals("Request body is empty", Jsons.readMap(reply.body()).get("message"));
    }

    @Test
    void liveAgentUnavailable() {
        register("talk", "live_agent_action");
        catalog.put("live_agent_action_config", doc("bot", BOT, "name", "talk", "status", true, "bot_response", "hello"));
        Map<String, Object> body = ok(call("talk", slots(), latest("hi"), null));
        assertEquals(List.of(), body.get("events"));
        Map<String, Object> custom = map(responses(body).get(0).get("custom"));
        assertEquals("live_agent", custom.get("action"));
        assertEquals("Live agent service is not available", custom.get("response"));
        assertEquals(Kairon.SUCCESS, logs("talk").get(0).get("status"));
    }

    @Test
    void liveAgentMissingConfigIsActionFailure() {
        register("talk", "live_agent_action");
        Map<String, Object> body = ok(call("talk", slots(), latest("hi"), null));
        assertEquals(Kairon.SORRY, responses(body).get(0).get("text"));
        Document log = logs("talk").get(0);
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("live_agent_action", log.get("type"));
        assertEquals("No Live Agent action found for given action and bot", log.get("exception"));
        assertEquals(1, logs("talk").size());
    }

    @Test
    void storePageTokenRoundTrip() {
        register("page", "store_page_action");
        catalog.put("store_page_action", doc(
                "bot", BOT, "name", "page", "status", true,
                "page_name", "checkout", "identifier_slot", "user_id", "callback_identifier", "cb"));
        catalog.put("bot_settings", doc("bot", BOT, "status", false, "store_page_token_expiry", 20));
        Map<String, Object> values = new LinkedHashMap<>(slots());
        values.put("user_id", "alice");
        Map<String, Object> body = ok(call("page", values, latest("hi"), null));
        assertEquals("alice", tokens.decrypt(String.valueOf(event(body, "user_identifier").get("value"))));
        Map<String, Object> claims = tokens.decryptClaims(String.valueOf(event(body, "temp_token").get("value")));
        assertEquals("store_page", claims.get("type"));
        assertNotNull(claims.get("exp"));
        assertEquals("checkout", event(body, "store_page_name").get("value"));
        assertNull(event(body, "callback_identifier").get("value"));
        assertEquals(Kairon.SUCCESS, logs("page").get(0).get("status"));
    }

    @Test
    void emptyStorePageIdentifierLogsTwice() {
        register("page", "store_page_action");
        catalog.put("store_page_action", doc(
                "bot", BOT, "name", "page", "status", true, "identifier_slot", "user_id"));
        Map<String, Object> body = ok(call("page", slots(), latest("hi"), null));
        assertEquals(List.of(), body.get("events"));
        List<Document> failed = logs("page");
        assertEquals(2, failed.size());
        assertEquals("store_page_action", failed.get(0).get("type"));
        assertNull(failed.get(1).get("type"));
        String message = "Slot 'user_id' is absent or empty for sender sender-1";
        assertEquals(message, failed.get(0).get("exception"));
        assertEquals(message, failed.get(1).get("exception"));
        assertEquals(Kairon.FAIL, failed.get(0).get("status"));
        assertEquals(Kairon.FAIL, failed.get(1).get("status"));
    }

    @Test
    void callbackSlotIsTheUrl() {
        register("ping", "callback_action");
        catalog.put("callback_action_config", doc(
                "bot", BOT, "name", "ping", "status", true,
                "callback_name", "hook", "dynamic_url_slot_name", "cb_url",
                "bot_response", "open {callback_url}"));
        catalog.put("callback_config", doc(
                "bot", BOT, "name", "hook", "validation_secret", "secret", "expire_in", 15));
        Map<String, Object> body = ok(call("ping", slots(), latest("hi"), null));
        String url = String.valueOf(event(body, "cb_url").get("value"));
        assertTrue(url.startsWith("http://callback.test/d/"));
        assertTrue(url.contains("/"));
        assertEquals("open " + url, responses(body).get(0).get("text"));
        assertEquals(Kairon.SUCCESS, logs("ping").get(0).get("status"));
        assertEquals(1, catalog.all("callback_data").size());
    }

    @Test
    void scheduleStoresJsonJob() {
        register("later", "schedule_action");
        catalog.put("schedule_action", doc(
                "bot", BOT, "name", "later", "status", true,
                "schedule_action", "checkout_flow", "timezone", "UTC",
                "schedule_time", new Document("key", "when").append("parameter_type", "value").append("value", "2026-10-26 12:00"),
                "params_list", List.of(), "schedule_action_type", "flow",
                "response_text", "scheduled", "dispatch_bot_response", true));
        Map<String, Object> body = ok(call("later", slots(), latest("hi"), null));
        assertEquals("scheduled", responses(body).get(0).get("text"));
        Document job = catalog.all("scheduler_jobs").get(0);
        assertEquals("execute_task", job.get("name"));
        assertEquals("Event", job.get("task_type"));
        assertEquals("checkout_flow", map(job.get("data")).get("flow_name"));
        synchronized (EVENT_PATHS) {
            assertEquals(1, EVENT_PATHS.size());
            assertTrue(EVENT_PATHS.get(0).startsWith("/api/events/dispatch/"));
            assertTrue(EVENT_PATHS.get(0).endsWith(String.valueOf(job.get("_id"))));
        }
        assertEquals(Kairon.SUCCESS, logs("later").get(0).get("status"));
    }

    @Test
    void parallelMergesChildSlots() {
        register("fan", "parallel_action");
        register("set_city", "slot_set_action");
        catalog.put("parallel_action_config", doc(
                "bot", BOT, "name", "fan", "status", true,
                "actions", List.of("set_city"), "dispatch_response_text", true, "response_text", "done"));
        catalog.put("slot_set_action", doc(
                "bot", BOT, "name", "set_city", "status", true,
                "set_slots", List.of(new Document("name", "city").append("type", "from_value").append("value", "Pune"))));
        Map<String, Object> body = ok(call("fan", slots(), latest("hi"), null));
        assertEquals("Pune", event(body, "city").get("value"));
        assertEquals("done", event(body, Kairon.ACTION_RESPONSE).get("value"));
        assertEquals("done", responses(body).get(0).get("text"));
        assertEquals(Kairon.SUCCESS, logs("fan").get(0).get("status"));
        assertEquals(Kairon.SUCCESS, logs("set_city").get(0).get("status"));
    }

    @Test
    void twoStageSearchButtons() {
        register("fallback", "two_stage_fallback");
        catalog.put("kairon_two_stage_fallback_action", doc(
                "bot", BOT, "name", "fallback", "status", true,
                "fallback_message", "Try these",
                "text_recommendations", new Document("count", 1).append("use_intent_ranking", false)));
        catalog.put("training_examples", doc("bot", BOT, "text", "book a flight", "status", true, "intent", "book"));
        Map<String, Object> body = ok(call("fallback", slots(), latest("flight"), null));
        Map<String, Object> message = responses(body).get(0);
        assertEquals("Try these", message.get("text"));
        Map<String, Object> button = map(list(message.get("buttons")).get(0));
        assertEquals("book a flight", button.get("text"));
        assertEquals("book a flight", button.get("payload"));
        assertEquals(Kairon.SUCCESS, logs("fallback").get(0).get("status"));
    }

    @Test
    void twoStageDefaultUtterance() {
        register("fallback", "two_stage_fallback");
        catalog.put("kairon_two_stage_fallback_action", doc(
                "bot", BOT, "name", "fallback", "status", true,
                "text_recommendations", new Document()));
        Map<String, Object> body = ok(call("fallback", slots(), latest("flight"), null));
        assertEquals(Kairon.UTTER_DEFAULT, responses(body).get(0).get("response"));
        assertEquals(Kairon.UTTER_DEFAULT, responses(body).get(0).get("template"));
    }

    @Test
    void nullIntentRankingEscapes() {
        register("fallback", "two_stage_fallback");
        catalog.put("kairon_two_stage_fallback_action", doc(
                "bot", BOT, "name", "fallback", "status", true,
                "text_recommendations", new Document("count", 1).append("use_intent_ranking", true)));
        Map<String, Object> body = ok(call("fallback", slots(), latest("flight"), null));
        assertEquals(List.of(), body.get("events"));
        assertEquals(List.of(), body.get("responses"));
        List<Document> failed = logs("fallback");
        assertEquals(1, failed.size());
        assertNull(failed.get(0).get("type"));
        assertEquals("intent_ranking", failed.get(0).get("exception"));
        assertEquals(Kairon.FAIL, failed.get(0).get("status"));
    }

    @Test
    void voiceMissingConfigIsProcessorFailure() {
        register("call_me", "voice_call_action");
        Map<String, Object> body = ok(call("call_me", slots(), latest("hi"), null));
        assertEquals(List.of(), body.get("events"));
        Document log = logs("call_me").get(0);
        assertNull(log.get("type"));
        assertEquals("No VoiceCallAction found for given action and bot", log.get("exception"));
        assertEquals(Kairon.FAIL, log.get("status"));
    }

    @Test
    void httpActionTemplatesCity() {
        register("lookup", "http_action");
        catalog.put("http_action_config", doc(
                "bot", BOT, "action_name", "lookup", "status", true,
                "http_url", "http://127.0.0.1:" + cityPort + "/city",
                "request_method", "GET", "content_type", "json",
                "response", new Document("dispatch", true).append("dispatch_type", "text")
                        .append("value", "${data.city}").append("evaluation_type", "expression")));
        Map<String, Object> body = ok(call("lookup", slots(), latest("hi"), null));
        assertEquals("Pune", responses(body).get(0).get("text"));
        assertEquals("Pune", event(body, Kairon.ACTION_RESPONSE).get("value"));
        assertEquals(200, ((Number) event(body, "http_status_code").get("value")).intValue());
        assertEquals(Kairon.SUCCESS, logs("lookup").get(0).get("status"));
    }

    @Test
    void fernetAndJwt() {
        assertEquals("plain", tokens.decrypt(tokens.encrypt("plain")));
        Map<String, Object> integration = tokens.decryptClaims(tokens.integrationToken(Map.of("sub", "sender-1", "bot", BOT)));
        assertEquals("integration", integration.get("type"));
        assertFalse(integration.containsKey("exp"));
        Map<String, Object> store = tokens.decryptClaims(tokens.storePageToken(Map.of("sub", "sender-1", "bot", BOT), 15, List.of()));
        assertEquals("store_page", store.get("type"));
        assertNotNull(store.get("exp"));
    }

    private void register(String name, String type) {
        catalog.put("actions", doc("bot", BOT, "name", name, "type", type, "status", true));
    }

    private Map<String, Object> ok(String json) {
        try {
            Reply reply = post(json);
            assertEquals(200, reply.status(), reply.body());
            return Jsons.readMap(reply.body());
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private Reply post(String json) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri("/webhook"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();
        HttpResponse<String> response = CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
        return new Reply(response.statusCode(), response.body());
    }

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + server.getPort() + path);
    }

    private String call(String action, Map<String, Object> slotValues, Map<String, Object> latest, Map<String, Object> domain) {
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "sender-1");
        tracker.put("slots", slotValues);
        tracker.put("latest_message", latest);
        tracker.put("events", List.of());
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("next_action", action);
        body.put("tracker", tracker);
        body.put("domain", domain == null ? Map.of() : domain);
        return Jsons.write(body);
    }

    private Map<String, Object> slots() {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("bot", BOT);
        return values;
    }

    private Map<String, Object> latest(String text) {
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("text", text);
        message.put("intent", Map.of("name", "greet"));
        return message;
    }

    private List<Document> logs(String action) {
        List<Document> found = new ArrayList<>();
        for (Document document : catalog.all(Kairon.LOGS)) {
            if (action.equals(document.get("action"))) {
                found.add(document);
            }
        }
        return found;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> event(Map<String, Object> body, String name) {
        for (Object item : list(body.get("events"))) {
            Map<String, Object> event = (Map<String, Object>) item;
            if (name.equals(event.get("name"))) {
                return event;
            }
        }
        throw new AssertionError("missing slot " + name + " in " + body);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> responses(Map<String, Object> body) {
        return (List<Map<String, Object>>) body.get("responses");
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        return (Map<String, Object>) value;
    }

    private List<?> list(Object value) {
        return (List<?>) value;
    }

    private Document doc(Object... pairs) {
        Document document = new Document();
        for (int i = 0; i + 1 < pairs.length; i += 2) {
            document.put(String.valueOf(pairs[i]), pairs[i + 1]);
        }
        return document;
    }

    private record Reply(int status, String body) {}
}
