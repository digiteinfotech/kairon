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
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

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

    @Inject
    ProbeAction probe;

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
        events.createContext("/api/events/schedule/action", exchange -> {
            String job = String.valueOf(Jsons.readMap(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8)).get("job_id"));
            synchronized (EVENT_PATHS) {
                EVENT_PATHS.add(exchange.getRequestURI().getPath());
            }
            byte[] body = ("{\"success\":true,\"error_code\":0,\"data\":{\"job_id\":\"" + job + "\"},\"message\":\"ok\"}")
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        events.start();
        city =HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
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
        probe.reset();
        RecordingFailureMail.CALLS.clear();
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
    void missingOrWhitespaceNextActionIsJsonNull() throws Exception {
        for (String json : List.of("{\"tracker\":{}}", "{\"next_action\":\"   \",\"tracker\":{}}",
                "{\"next_action\":null}", "{\"next_action\":\" \\t\"}")) {
            Reply reply = post(json);
            assertEquals(200, reply.status(), json);
            assertEquals("null", reply.body().trim(), json);
        }
        assertTrue(catalog.all(Kairon.LOGS).isEmpty());
    }

    @Test
    void missingTrackerIs500() throws Exception {
        register("probe", ProbeAction.TYPE);
        Reply reply = post("{\"next_action\":\"probe\"}");
        assertEquals(500, reply.status());
        assertEquals(0, probe.executions);
        assertTrue(catalog.all(Kairon.LOGS).isEmpty());
    }

    @Test
    void missingSenderIdIs500() throws Exception {
        register("probe", ProbeAction.TYPE);
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("slots", slots());
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("next_action", "probe");
        body.put("tracker", tracker);
        Reply reply = post(Jsons.write(body));
        assertEquals(500, reply.status());
        assertEquals(0, probe.executions);
        assertTrue(catalog.all(Kairon.LOGS).isEmpty());
    }

    @Test
    void nonObjectTrackerIs500() throws Exception {
        for (String json : List.of("{\"next_action\":\"probe\",\"tracker\":null}",
                "{\"next_action\":\"probe\",\"tracker\":[1]}")) {
            assertEquals(500, post(json).status(), json);
        }
        assertEquals(0, probe.executions);
    }

    @Test
    void emptyBodyIsErrorEnvelope() throws Exception {
        Map<String, Object> error = envelopeError(post(""));
        assertEquals("missing", error.get("type"));
        assertEquals(List.of("body"), error.get("loc"));
        assertEquals("Field required", error.get("msg"));
    }

    @Test
    void jsonNullBodyIsErrorEnvelope() throws Exception {
        assertEquals("missing", envelopeError(post("null")).get("type"));
    }

    @Test
    void invalidJsonIsErrorEnvelope() throws Exception {
        for (String json : List.of("   ", "{not json", "{\"a\":1} trailing")) {
            Map<String, Object> error = envelopeError(post(json));
            assertEquals("json_invalid", error.get("type"), json);
            assertEquals("JSON decode error", error.get("msg"), json);
            assertEquals("body", list(error.get("loc")).get(0), json);
        }
    }

    @Test
    void nonObjectBodyIsErrorEnvelope() throws Exception {
        for (String json : List.of("[1,2]", "\"text\"", "5", "true")) {
            Map<String, Object> error = envelopeError(post(json));
            assertEquals("dict_type", error.get("type"), json);
            assertEquals("Input should be a valid dictionary", error.get("msg"), json);
        }
    }

    @Test
    void nonJsonContentTypeIsErrorEnvelope() throws Exception {
        register("probe", ProbeAction.TYPE);
        HttpRequest request = HttpRequest.newBuilder(uri("/webhook"))
                .header("Content-Type", "text/plain")
                .POST(HttpRequest.BodyPublishers.ofString(call("probe", slots(), latest("hi"), null)))
                .build();
        HttpResponse<String> response = CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
        Map<String, Object> error = envelopeError(new Reply(response.statusCode(), response.body(), response.headers()));
        assertEquals("dict_type", error.get("type"));
        assertEquals(0, probe.executions);
    }

    @Test
    void noRequestReturns422Status() throws Exception {
        for (String json : List.of("", "   ", "{bad", "[]", "null", "{\"next_action\":\"x\"}",
                "{\"next_action\":\"x\",\"tracker\":{}}", "{\"next_action\":\"\"}")) {
            int status = post(json).status();
            assertTrue(status == 200 || status == 500, json + " -> " + status);
        }
    }

    @Test
    void catchAllReturnsEmptyEventsAndResponses() throws Exception {
        Reply silent = post(call("nothing_uttered", slots(), latest("hi"), null));
        assertEquals(200, silent.status());
        assertEquals("{\"events\":[],\"responses\":[]}", silent.body().trim());

        register("probe", ProbeAction.TYPE);
        Map<String, Object> values = slots();
        values.put("probe_fail", true);
        Reply reply = post(call("probe", values, latest("hi"), null));
        assertEquals(200, reply.status());
        Map<String, Object> body = Jsons.readMap(reply.body());
        assertEquals(List.of(), body.get("events"));
        assertEquals(1, responses(body).size());
        assertEquals("uttered before failure", responses(body).get(0).get("text"));
        assertEquals(1, probe.executions);
        List<Document> failed = logs("probe");
        assertEquals(1, failed.size());
        assertNull(failed.get(0).get("type"));
        assertEquals("probe failure", failed.get(0).get("exception"));
        assertEquals(reply.header(Kairon.REQUEST_ID), failed.get(0).get("request_id"));
    }

    /** T-038/T-039: dispatch-and-logging R3 c4-c6, R4 c5-c6, c10, R6 c1, c4-c5. */
    @Test
    void catchAllLogFieldsOrderTriggerInfoAndOneMail() throws Exception {
        register("probe", ProbeAction.TYPE);
        Map<String, Object> values = slots();
        values.put("probe_fail", true);
        Reply reply = post(call("probe", values, latest("hi there"), null));
        assertEquals(200, reply.status());
        Document log = logs("probe").get(0);
        List<String> keys = new ArrayList<>(log.keySet());
        keys.remove("_id");
        assertEquals(List.of("intent", "action", "sender", "exception", "bot", "timestamp", "status", "trigger_info", "request_id"), keys);
        assertEquals(new Document("trigger_name", "").append("trigger_type", "implicit").append("trigger_id", ""), log.get("trigger_info"));
        assertEquals(reply.header(Kairon.REQUEST_ID), log.get("request_id"));
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals(1, RecordingFailureMail.CALLS.size(), "one failure mail");
        RecordingFailureMail.Call mail = RecordingFailureMail.CALLS.get(0);
        assertEquals(BOT, mail.bot());
        assertEquals("probe", mail.action());
        assertEquals("hi there", mail.userText());
        assertEquals(true, mail.slots().get("probe_fail"));
        assertTrue(mail.stackTrace().contains("java.lang.IllegalStateException: probe failure"), mail.stackTrace());
        assertTrue(mail.stackTrace().contains("ProbeAction.execute"), mail.stackTrace());
    }

    /** T-038: dispatch-and-logging R4 c5-c6, c10; core-actions R6 c8 style null omission. */
    @Test
    void actionLogKeepsRequestTriggerInfoAndDeclaredOrder() throws Exception {
        register("set_place", "slot_set_action");
        catalog.put("slot_set_action", doc(
                "bot", BOT, "name", "set_place", "status", true,
                "set_slots", List.of(new Document("name", "city").append("type", "from_value").append("value", "Pune"))));
        Map<String, Object> body = Jsons.readMap(call("set_place", slots(), latest("hi"), null));
        body.put("trigger_info", Map.of("trigger_type", "agentic_flow", "trigger_id", "flow-7"));
        Reply reply = post(Jsons.write(body));
        assertEquals(200, reply.status());
        Document log = logs("set_place").get(0);
        Document trigger = (Document) log.get("trigger_info");
        assertEquals(List.of("trigger_name", "trigger_type", "trigger_id"), new ArrayList<>(trigger.keySet()));
        assertEquals("", trigger.get("trigger_name"));
        assertEquals("agentic_flow", trigger.get("trigger_type"));
        assertEquals("flow-7", trigger.get("trigger_id"));
        assertEquals(reply.header(Kairon.REQUEST_ID), log.get("request_id"));
        List<String> keys = new ArrayList<>(log.keySet());
        keys.remove("_id");
        List<String> declared = keys.stream().filter(com.kairon.action.support.ActionSupport.LOG_FIELDS::contains).toList();
        assertEquals(declared, keys.subList(0, declared.size()), "declared fields come first: " + keys);
        assertEquals(com.kairon.action.support.ActionSupport.LOG_FIELDS.stream().filter(declared::contains).toList(), declared);
        assertTrue(log.values().stream().noneMatch(java.util.Objects::isNull), "null fields omitted: " + log);
        assertTrue(RecordingFailureMail.CALLS.isEmpty(), "slot_set sends no mail");
    }

    /** T-039/T-037: an in-action failure handler mails once; bot_response logged as Python repr. */
    @Test
    void inActionFailureMailsOnceAndLogsRepr() {
        Map<String, Object> domain = Map.of("responses", Map.of("utter_empty", List.of()));
        Map<String, Object> body = ok(call("utter_empty", slots(), latest("hello"), domain));
        assertEquals("utter_empty", responses(body).get(0).get("response"));
        Document log = logs("utter_empty").get(0);
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("{'response': 'utter_empty'}", log.get("bot_response"));
        assertEquals(1, RecordingFailureMail.CALLS.size());
        RecordingFailureMail.Call mail = RecordingFailureMail.CALLS.get(0);
        assertEquals("utter_empty", mail.action());
        assertEquals("hello", mail.userText());
        assertEquals(BOT, mail.slots().get("bot"));
        assertTrue(mail.stackTrace().contains("Cannot choose from an empty sequence"), mail.stackTrace());
    }

    @Test
    void voiceDisconnectLogsPythonRepr() {
        ok(call("kairon_voice_disconnect", slots(), latest("bye"), null));
        assertEquals("{'disconnect': True}", logs("kairon_voice_disconnect").get(0).get("bot_response"));
    }

    @Test
    void successKeepsUtteredResponses() {
        register("probe", ProbeAction.TYPE);
        Map<String, Object> body = ok(call("probe", slots(), latest("hi"), null));
        assertEquals("uttered before failure", responses(body).get(0).get("text"));
        assertEquals("sender-1", event(body, "probe_sender").get("value"));
    }

    @Test
    void nextActionIsStrippedNotLowercased() {
        register("My_Probe", ProbeAction.TYPE);
        Map<String, Object> body = ok(call("  My_Probe \t", slots(), latest("hi"), null));
        assertEquals("sender-1", event(body, "probe_sender").get("value"));
        assertEquals(1, probe.executions);
        Map<String, Object> missed = ok(call("my_probe", slots(), latest("hi"), null));
        assertEquals(List.of(), missed.get("events"));
        assertEquals(1, probe.executions);
        assertEquals("No action found for given bot and name", logs("my_probe").get(0).get("exception"));
    }

    @Test
    void webhookRunsOffTheEventLoop() {
        register("probe", ProbeAction.TYPE);
        ok(call("probe", slots(), latest("hi"), null));
        Thread thread = probe.lastThread;
        assertNotNull(thread);
        assertFalse(thread.getName().toLowerCase().contains("eventloop"), thread.getName());
        assertTrue(thread.isVirtual(), "blocking executor uses virtual threads: " + thread);
    }

    @Test
    void fernetSenderIdIsDecrypted() {
        register("probe", ProbeAction.TYPE);
        String token = tokens.encrypt("user@x.com");
        Map<String, Object> body = ok(callAs(token, "probe"));
        assertEquals("user@x.com", event(body, "probe_sender").get("value"));
        Map<String, Object> plain = ok(callAs("not-a-token", "probe"));
        assertEquals("not-a-token", event(plain, "probe_sender").get("value"));
    }

    @Test
    void trackerDefaultsReachTheAction() {
        register("probe", ProbeAction.TYPE);
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "sender-1");
        tracker.put("slots", slots());
        tracker.put("active_form", Map.of("name", "f"));
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("next_action", "probe");
        body.put("tracker", tracker);
        body.put("unknown_key", 1);
        ok(Jsons.write(body));
        assertEquals(false, probe.lastTracker.paused);
        assertEquals(Map.of("name", "f"), probe.lastTracker.activeLoop);
        assertNull(probe.lastTracker.latestActionName);
        assertEquals(List.of(), probe.lastTracker.stack);
        assertEquals(List.of(), probe.lastTracker.events);
        assertEquals(Map.of(), probe.lastTracker.latestMessage);
    }

    @Test
    void requestIdEchoedOrGenerated() throws Exception {
        assertEquals("abc", send("/", "abc", null).header(Kairon.REQUEST_ID));
        UUID uuid = UUID.fromString(send("/", null, null).header(Kairon.REQUEST_ID));
        assertEquals(4, uuid.version());
        Reply webhook = post("{\"next_action\":\"\"}");
        assertEquals(4, UUID.fromString(webhook.header(Kairon.REQUEST_ID)).version());
    }

    @Test
    void secureHeadersMatchPython() throws Exception {
        Map<String, String> expected = new LinkedHashMap<>();
        expected.put("server", "Secure");
        expected.put("strict-transport-security", "includeSubDomains; preload; max-age=31536000");
        expected.put("x-frame-options", "SAMEORIGIN");
        expected.put("x-xss-protection", "0");
        expected.put("x-content-type-options", "nosniff");
        expected.put("content-security-policy", "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'");
        expected.put("referrer-policy", "no-referrer");
        expected.put("cache-control", "must-revalidate");
        expected.put("permissions-policy", "accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()");
        expected.put("cross-origin-embedder-policy", "require-corp");
        expected.put("cross-origin-opener-policy", "same-origin");
        expected.put("cross-origin-resource-policy", "same-origin");
        expected.put("access-control-allow-origin", "*");
        for (Reply reply : List.of(send("/", null, null), send("/healthcheck", null, null),
                post("{\"next_action\":\"\"}"), post(""))) {
            for (Map.Entry<String, String> entry : expected.entrySet()) {
                assertEquals(List.of(entry.getValue()), reply.headers().allValues(entry.getKey()), entry.getKey());
            }
        }
        Reply cors = send("/healthcheck", null, "https://app.example.com");
        assertEquals(List.of("https://app.example.com"), cors.headers().allValues("access-control-allow-origin"));
    }

    @Test
    void healthBodiesAreExact() throws Exception {
        Reply root = send("/", null, null);
        assertEquals(200, root.status());
        assertEquals(Map.of("message", "Kairon Action Server Up and Running"), Jsons.readMap(root.body()));
        Reply health = send("/healthcheck", null, null);
        assertEquals(200, health.status());
        assertEquals(Map.of("message", "health check ok"), Jsons.readMap(health.body()));
    }

    @Test
    void webhookNeedsNoAuthorization() {
        register("probe", ProbeAction.TYPE);
        Map<String, Object> body = ok(call("probe", slots(), latest("hi"), null));
        assertEquals("sender-1", event(body, "probe_sender").get("value"));
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
    void scheduleSubmitsThroughEventsServer() {
        register("later", "schedule_action");
        catalog.put("schedule_action", doc(
                "bot", BOT, "name", "later", "status", true,
                "schedule_action", "checkout_flow", "timezone", "UTC",
                "schedule_time", new Document("key", "when").append("parameter_type", "value").append("value", "2026-10-26 12:00"),
                "params_list", List.of(), "schedule_action_type", "flow",
                "response_text", "scheduled", "dispatch_bot_response", true));
        Map<String, Object> body = ok(call("later", slots(), latest("hi"), null));
        assertEquals("scheduled", responses(body).get(0).get("text"));
        assertEquals(List.of(), catalog.all("scheduler_jobs"));
        synchronized (EVENT_PATHS) {
            assertEquals(2, EVENT_PATHS.size());
            assertEquals("/api/events/schedule/action", EVENT_PATHS.get(0));
            assertTrue(EVENT_PATHS.get(1).matches("/api/events/dispatch/[0-9a-f]{32}"));
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
        return new Reply(response.statusCode(), response.body(), response.headers());
    }

    private Reply send(String path, String requestId, String origin) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri(path)).GET();
        if (requestId != null) {
            builder.header(Kairon.REQUEST_ID, requestId);
        }
        if (origin != null) {
            builder.header("Origin", origin);
        }
        HttpResponse<String> response = CLIENT.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        return new Reply(response.statusCode(), response.body(), response.headers());
    }

    private Map<String, Object> envelopeError(Reply reply) {
        assertEquals(200, reply.status(), reply.body());
        Map<String, Object> body = Jsons.readMap(reply.body());
        assertEquals(List.of("success", "error_code", "message", "data"), List.copyOf(body.keySet()));
        assertEquals(false, body.get("success"));
        assertEquals(422, ((Number) body.get("error_code")).intValue());
        assertNull(body.get("data"));
        List<?> message = list(body.get("message"));
        assertEquals(1, message.size());
        return map(message.get(0));
    }

    private String callAs(String sender, String action) {
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", sender);
        tracker.put("slots", slots());
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("next_action", action);
        body.put("tracker", tracker);
        return Jsons.write(body);
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

    private record Reply(int status, String body, HttpHeaders headers) {
        String header(String name) {
            return headers.firstValue(name).orElse(null);
        }
    }
}
