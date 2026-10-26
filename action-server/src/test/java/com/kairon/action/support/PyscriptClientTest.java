package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.actions.PyscriptAction;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.Dispatcher;
import com.kairon.action.runtime.TrackerState;
import com.sun.net.httpserver.HttpServer;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** outbound-clients R5: the pyscript evaluator call against a local stub server. */
class PyscriptClientTest {

    private static final String BOT = "pyscript-bot";
    private static final List<String> BODIES = new CopyOnWriteArrayList<>();
    private static final List<String> PATHS = new CopyOnWriteArrayList<>();
    private static volatile String reply = "{}";
    private static HttpServer server;
    private static String base;

    private MemoryActionCatalog catalog;
    private ActionSupport support;

    @BeforeAll
    static void start() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            PATHS.add(exchange.getRequestMethod() + " " + exchange.getRequestURI().getPath());
            BODIES.add(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] bytes = reply.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });
        server.start();
        base = "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @AfterAll
    static void stop() {
        server.stop(0);
    }

    @BeforeEach
    void setUp() {
        BODIES.clear();
        PATHS.clear();
        ActionSettings settings = new ActionSettings();
        settings.setPyscriptUrl(base + "/pyscript/evaluate");
        catalog = new MemoryActionCatalog();
        support = new ActionSupport(catalog, settings, new Tokens(settings), new HttpCaller(settings));
    }

    private static Map<String, Object> lastBody() {
        assertFalse(BODIES.isEmpty(), "pyscript stub was not called");
        return Jsons.readMap(BODIES.get(BODIES.size() - 1));
    }

    @Test
    void postsSourceCodeAndPredefinedObjects() {
        reply = "{\"statusCode\": 200, \"body\": {\"bot_response\": \"ok\"}}";
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("sender_id", "u1");
        context.put("slot", Map.of("bot", BOT));
        support.runPyscript("bot_response = 'ok'", context);

        assertEquals(List.of("POST /pyscript/evaluate"), PATHS);
        Map<String, Object> body = lastBody();
        assertEquals(List.of("source_code", "predefined_objects"), List.copyOf(body.keySet()));
        assertEquals("bot_response = 'ok'", body.get("source_code"));
        assertEquals(context, body.get("predefined_objects"));
    }

    @Test
    void nonTwoHundredStatusCodeRaises() {
        reply = "{\"statusCode\": 422, \"body\": \"boom\"}";
        ActionFailure failure = assertThrows(ActionFailure.class, () -> support.runPyscript("x = 1", Map.of()));
        assertTrue(failure.getMessage().startsWith("Pyscript evaluation failed: "), failure.getMessage());

        reply = "{\"body\": {\"bot_response\": \"no status\"}}";
        assertThrows(ActionFailure.class, () -> support.runPyscript("x = 1", Map.of()));
    }

    @Test
    void botSlotIsRemovedFromResultSlots() {
        reply = "{\"statusCode\": 200, \"body\": {\"bot_response\": \"hi\", \"slots\": {\"bot\": \"other\", \"city\": \"Pune\", \"n\": null}}}";
        ActionSupport.PyscriptResult result = support.evaluatePyscript("x", new LinkedHashMap<>());
        Map<String, Object> expected = new LinkedHashMap<>();
        expected.put("city", "Pune");
        expected.put("n", null);
        assertEquals(expected, result.slots());
    }

    @Test
    void outputIsBotResponseElseBodyElseEmpty() {
        reply = "{\"statusCode\": 200, \"body\": {\"bot_response\": {\"a\": 1}, \"x\": 2}}";
        assertEquals(Map.of("a", 1), support.evaluatePyscript("x", new LinkedHashMap<>()).output());

        // empty bot_response falls through to body, which is the whole result dict
        reply = "{\"statusCode\": 200, \"body\": {\"bot_response\": \"\", \"body\": {\"k\": \"v\"}}}";
        assertEquals(Map.of("k", "v"), support.evaluatePyscript("x", new LinkedHashMap<>()).output());

        // falsy body falls through to {}
        reply = "{\"statusCode\": 200, \"body\": {\"bot_response\": null, \"body\": {}}}";
        assertEquals(Map.of(), support.evaluatePyscript("x", new LinkedHashMap<>()).output());

        reply = "{\"statusCode\": 200, \"body\": {\"slots\": {}}}";
        assertEquals(Map.of(), support.evaluatePyscript("x", new LinkedHashMap<>()).output());
    }

    @Test
    void mediaIdsAreAppendedToOutput() {
        reply = "{\"statusCode\": 200, \"body\": {\"bot_response\": {\"text\": \"see\"}, \"media_ids\": [\"m1\", \"m2\"]}}";
        Object output = support.evaluatePyscript("x", new LinkedHashMap<>()).output();
        assertEquals("{\"text\": \"see\", \"media_ids\": [\"m1\", \"m2\"]}", Jsons.pythonDumps(output));

        reply = "{\"statusCode\": 200, \"body\": {\"media_ids\": [\"m3\"]}}";
        assertEquals(Map.of("media_ids", List.of("m3")), support.evaluatePyscript("x", new LinkedHashMap<>()).output());

        // Python: str.update raises AttributeError
        reply = "{\"statusCode\": 200, \"body\": {\"bot_response\": \"text\", \"media_ids\": [\"m4\"]}}";
        ActionFailure failure = assertThrows(ActionFailure.class, () -> support.evaluatePyscript("x", new LinkedHashMap<>()));
        assertEquals("'str' object has no attribute 'update'", failure.getMessage());
    }

    @Test
    void evaluatePyscriptMergesHttpResponseIntoContext() {
        reply = "{\"statusCode\": 200, \"body\": {\"bot_response\": \"ok\"}}";
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("data", Map.of("a", 1));
        data.put("context", new LinkedHashMap<>(Map.of("sender_id", "u1")));
        data.put("http_status_code", 200);
        data.put("response_headers", Map.of("h", "v"));
        support.evaluatePyscript("x", data);
        Map<String, Object> objects = Maps.map(lastBody().get("predefined_objects"));
        assertEquals(List.of("sender_id", "data", "response_headers", "http_status_code"), List.copyOf(objects.keySet()));
    }

    @Test
    void pyscriptActionSendsBuildContextWithKeyVaultAndNoBotKey() {
        reply = "{\"statusCode\": 200, \"body\": {\"bot_response\": \"done\"}}";
        catalog.put("pyscript_action_config", new Document("name", "py").append("bot", BOT).append("status", true)
                .append("source_code", "bot_response = 'done'").append("dispatch_response", true));
        catalog.put("key_vault", new Document("bot", BOT).append("key", "API_KEY").append("value", "secret-1"));
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "u1");
        tracker.put("slots", Map.of("bot", BOT));
        tracker.put("latest_message", Map.of("text", "hi"));
        tracker.put("events", List.of());
        new PyscriptAction(support).execute(new ActionContext(BOT, "py", TrackerState.from(tracker), new Dispatcher(), null, null));

        Map<String, Object> objects = Maps.map(lastBody().get("predefined_objects"));
        assertEquals(List.of("sender_id", "user_message", "slot", "intent", "chat_log", "key_vault", "latest_message",
                "kairon_user_msg", "session_started"), List.copyOf(objects.keySet()));
        assertEquals(Map.of("API_KEY", "secret-1"), objects.get("key_vault"));
    }
}
