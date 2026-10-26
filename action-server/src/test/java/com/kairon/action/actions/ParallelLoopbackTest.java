package com.kairon.action.actions;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.support.Jsons;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * T-044 end to end: children loop back over HTTP into the server under test (own-webhook URL set to the
 * embedded server by the test-scope OwnWebhookUrl listener). Covers orchestration-actions R1 c7 and c10.
 */
@MicronautTest
class ParallelLoopbackTest {

    private static final String BOT = "bot-loop";

    @Inject
    EmbeddedServer server;

    @Inject
    MemoryActionCatalog catalog;

    @Inject
    ActionSettings settings;

    @Test
    void childrenRunThroughOwnWebhookAndCarryParentTrigger() throws Exception {
        catalog.clear();
        assertEquals("http://127.0.0.1:" + server.getPort() + "/webhook", settings.getActionServerUrl());
        register("fan", "parallel_action");
        register("set_city", "slot_set_action");
        register("say_hi", "kairon_bot_response");
        register("mail_broken", "email_action");
        catalog.put("parallel_action_config", new Document("bot", BOT).append("name", "fan").append("status", true)
                .append("actions", List.of("set_city", "say_hi", "mail_broken"))
                .append("dispatch_response_text", true).append("response_text", "done"));
        catalog.put("slot_set_action", new Document("bot", BOT).append("name", "set_city").append("status", true)
                .append("set_slots", List.of(new Document("name", "city").append("type", "from_value").append("value", "Pune"))));
        catalog.put("bot_response_action", new Document("bot", BOT).append("name", "say_hi").append("status", true)
                .append("response", "hello from child").append("dispatch_response", true));
        // No smtp_url: the email child fails (Failed log) but the parent stays Success.
        catalog.put("email_action_config", new Document("bot", BOT).append("action_name", "mail_broken").append("status", true)
                .append("from_email", new Document("parameter_type", "value").append("value", "a@b.test"))
                .append("to_email", new Document("parameter_type", "value").append("value", "c@d.test"))
                .append("subject", "s").append("response", "ok"));

        Map<String, Object> request = new LinkedHashMap<>();
        Map<String, Object> slots = new LinkedHashMap<>();
        slots.put("bot", BOT);
        request.put("next_action", "fan");
        request.put("tracker", Map.of("sender_id", "sender-9", "slots", slots,
                "latest_message", Map.of("text", "hi", "intent", Map.of("name", "greet")), "events", List.of()));
        request.put("domain", Map.of());
        HttpResponse<String> response = HttpClient.newHttpClient().send(
                HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + server.getPort() + "/webhook"))
                        .header("Content-Type", "application/json").header(Kairon.REQUEST_ID, "loop-req")
                        .POST(HttpRequest.BodyPublishers.ofString(Jsons.write(request))).build(),
                HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode(), response.body());
        Map<String, Object> body = Jsons.readMap(response.body());

        List<?> responses = (List<?>) body.get("responses");
        assertEquals(1, responses.size(), "child utterances discarded: " + responses);
        assertEquals("done", ((Map<?, ?>) responses.get(0)).get("text"));

        Document parent = only("fan");
        assertEquals(Kairon.SUCCESS, parent.get("status"));
        assertEquals("loop-req", parent.get("request_id"));
        String trigger = String.valueOf(parent.get("_id"));
        for (String child : List.of("set_city", "mail_broken")) {
            Document log = only(child);
            Map<?, ?> info = (Map<?, ?>) log.get("trigger_info");
            assertEquals("fan", info.get("trigger_name"));
            assertEquals("parallel_action", info.get("trigger_type"));
            assertEquals(trigger, info.get("trigger_id"));
            assertEquals("loop-req", log.get("request_id"));
        }
        assertEquals(Kairon.FAIL, only("mail_broken").get("status"));
        boolean city = ((List<?>) body.get("events")).stream()
                .anyMatch(e -> "city".equals(((Map<?, ?>) e).get("name")) && "Pune".equals(((Map<?, ?>) e).get("value")));
        assertEquals(true, city, String.valueOf(body.get("events")));
    }

    private void register(String name, String type) {
        catalog.put("actions", new Document("bot", BOT).append("name", name).append("type", type).append("status", true));
    }

    private Document only(String action) {
        List<Document> logs = catalog.all(Kairon.LOGS).stream().filter(d -> action.equals(d.get("action"))).toList();
        assertEquals(1, logs.size(), action + " logs: " + logs);
        return logs.get(0);
    }
}
