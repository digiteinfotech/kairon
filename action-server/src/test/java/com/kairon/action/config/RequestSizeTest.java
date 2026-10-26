package com.kairon.action.config;

import com.kairon.action.support.Jsons;
import io.micronaut.context.annotation.Value;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** cavekit-webhook-contract.md R6 c1: a valid webhook request with a 20 MB tracker is processed (no 413). */
@MicronautTest
class RequestSizeTest {

    private static final int TWENTY_MB = 20 * 1024 * 1024;

    @Inject
    EmbeddedServer server;

    @Value("${micronaut.server.max-request-size}")
    String maxRequestSize;

    @Value("${micronaut.server.max-request-buffer-size}")
    String maxRequestBufferSize;

    @Test
    void ceilingIsConfiguredAboveTwentyMegabytes() {
        assertEquals("64MB", maxRequestSize);
        assertEquals("64MB", maxRequestBufferSize);
    }

    @Test
    void twentyMegabyteTrackerIsProcessed() throws Exception {
        Map<String, Object> slots = new LinkedHashMap<>();
        slots.put("bot", "bot-size");
        slots.put("big", "x".repeat(TWENTY_MB));
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "sender-size");
        tracker.put("slots", slots);
        tracker.put("latest_message", Map.of("text", "bye"));
        tracker.put("events", List.of());
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("next_action", "kairon_voice_disconnect");
        body.put("tracker", tracker);
        body.put("domain", Map.of());
        byte[] payload = Jsons.write(body).getBytes(StandardCharsets.UTF_8);
        assertTrue(payload.length > TWENTY_MB);

        HttpRequest request = HttpRequest.newBuilder(URI.create("http://localhost:" + server.getPort() + "/webhook"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
                .build();
        HttpResponse<String> response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode(), response.body());
        Map<String, Object> reply = Jsons.readMap(response.body());
        assertTrue(reply.containsKey("responses"), response.body());
    }
}
