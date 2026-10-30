package com.kairon.action.actions.prompt;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.actions.ActionFactory;
import com.kairon.action.actions.HttpAction;
import com.kairon.action.actions.PromptAction;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.Dispatcher;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.runtime.TrackerState;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Tokens;
import com.sun.net.httpserver.HttpServer;
import io.micronaut.context.ApplicationContext;
import org.bson.Document;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.lang.reflect.Field;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-114: prompt-db R4 c1-c4, the {@code action} prompt source. */
class NestedActionSourceTest {

    private static final String BOT = "bot-nested";

    /** Test action: records its context, utters, logs, and reports success with {@code response} unless failing. */
    static final class StubAction implements KaironAction {
        final String type;
        final ActionSupport support;
        boolean fail;
        Object response = "nested says hi";
        final List<ActionContext> seen = new ArrayList<>();

        StubAction(String type, ActionSupport support) {
            this.type = type;
            this.support = support;
        }

        @Override
        public String type() {
            return type;
        }

        @Override
        public Map<String, Object> execute(ActionContext context) {
            seen.add(context);
            context.dispatcher.text("uttered by " + context.actionName);
            support.save(context, type, fail ? Kairon.FAIL : Kairon.SUCCESS, fail ? "boom" : null,
                    fail ? "failed" : response, null);
            if (!fail) {
                context.succeeded(response);
            }
            return Map.of(Kairon.ACTION_RESPONSE, String.valueOf(response));
        }
    }

    MemoryActionCatalog catalog;
    ActionSupport support;
    StubAction stub;
    StubAction database;
    NestedActionSource source;
    ActionContext parent;
    HttpServer server;

    @BeforeEach
    void setUp() {
        ActionSettings settings = new ActionSettings();
        settings.setFernetKey("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=");
        catalog = new MemoryActionCatalog();
        support = new ActionSupport(catalog, settings, new Tokens(settings), new HttpCaller(settings));
        stub = new StubAction("test_nested", support);
        database = new StubAction("database_action", support);
        ActionFactory factory = new ActionFactory(List.of(stub, database, new HttpAction(support)), catalog);
        source = new NestedActionSource(() -> factory);
        register("lookup", "test_nested");
        register("db_lookup", "database_action");
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "user-1");
        tracker.put("slots", new LinkedHashMap<>(Map.of("bot", BOT)));
        tracker.put("latest_message", Map.of("text", "hello"));
        tracker.put("events", List.of());
        Map<String, Object> call = new LinkedHashMap<>();
        call.put("next_action", "kairon_prompt");
        call.put("trigger_info", Map.of("trigger_name", "kairon_prompt"));
        parent = new ActionContext(BOT, "kairon_prompt", TrackerState.from(tracker), new Dispatcher(),
                Map.of("slots", Map.of()), call);
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    private void register(String name, String type) {
        catalog.insert("actions", new Document("name", name).append("type", type).append("bot", BOT).append("status", true));
    }

    private static Map<String, Object> prompt(String name, String data, Object instructions) {
        Map<String, Object> prompt = new LinkedHashMap<>();
        prompt.put("name", name);
        prompt.put("data", data);
        prompt.put("instructions", instructions);
        prompt.put("type", "user");
        prompt.put("source", "action");
        prompt.put("is_enabled", true);
        return prompt;
    }

    private List<Document> logs(String action) {
        return catalog.all(Kairon.LOGS).stream().filter(d -> action.equals(d.get("action"))).toList();
    }

    // c1: resolved by name through action type resolution; same tracker, dispatcher, domain, request context.
    @Test
    void resolvesByNameAndRunsWithParentContext() {
        source.render(parent, prompt("Lookup", "lookup", null));
        assertEquals(1, stub.seen.size());
        ActionContext nested = stub.seen.get(0);
        assertEquals("lookup", nested.actionName);
        assertEquals(BOT, nested.bot);
        assertSame(parent.tracker, nested.tracker);
        assertSame(parent.dispatcher, nested.dispatcher);
        assertSame(parent.domain, nested.domain);
        assertSame(parent.actionCall, nested.actionCall);
        assertEquals(0, database.seen.size());
    }

    @Test
    void unknownNestedActionFailsThePromptLikePython() {
        assertThrows(RuntimeException.class, () -> source.render(parent, prompt("Missing", "nope", null)));
    }

    // c2: success appends "{name}:\n{response}\n" plus the instructions block when instructions exist.
    @Test
    void successAppendsResponseWithoutInstructions() {
        assertEquals("Lookup:\nnested says hi\n", source.render(parent, prompt("Lookup", "lookup", null)));
        assertEquals("Lookup:\nnested says hi\n", source.render(parent, prompt("Lookup", "lookup", "")));
    }

    @Test
    void successAppendsInstructionsBlock() {
        assertEquals("Lookup:\nnested says hi\nInstructions on how to use Lookup:\nUse it well\n\n",
                source.render(parent, prompt("Lookup", "lookup", "Use it well")));
    }

    @Test
    void successResponseIsPythonStr() {
        stub.response = null;
        assertEquals("Lookup:\nNone\n", source.render(parent, prompt("Lookup", "lookup", null)));
        stub.response = new LinkedHashMap<>(Map.of("a", 1));
        assertEquals("Lookup:\n{'a': 1}\n", source.render(parent, prompt("Lookup", "lookup", null)));
    }

    @Test
    void successFlagDoesNotLeakIntoParentContext() {
        source.render(parent, prompt("Lookup", "lookup", null));
        assertFalse(parent.isSuccess());
    }

    // c3: failure appends nothing; the nested utterances and log record remain.
    @Test
    void failedNestedActionAppendsNothingButKeepsUtterancesAndLog() {
        stub.fail = true;
        assertEquals("", source.render(parent, prompt("Lookup", "lookup", "Use it well")));
        assertEquals(List.of("uttered by lookup"),
                parent.dispatcher.messages.stream().map(m -> m.get("text")).toList());
        List<Document> logs = logs("lookup");
        assertEquals(1, logs.size());
        assertEquals(Kairon.FAIL, logs.get(0).get("status"));
    }

    // c4: database_action appends nothing even when it succeeds.
    @Test
    void nestedDatabaseActionAppendsNothingEvenOnSuccess() {
        assertEquals("", source.render(parent, prompt("Db", "db_lookup", "Use it well")));
        assertEquals(1, database.seen.size());
        assertTrue(database.seen.get(0).isSuccess());
        assertEquals(1, logs("db_lookup").size());
        assertEquals(List.of("uttered by db_lookup"),
                parent.dispatcher.messages.stream().map(m -> m.get("text")).toList());
    }

    // c2/c3 against a real action: http_action reports Python's is_success/response.
    @Test
    void realHttpActionSuccessAndFailure() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/up", exchange -> {
            byte[] body = "{\"city\":\"Pune\"}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        register("weather", "http_action");
        catalog.insert("http_action_config", new Document("bot", BOT).append("action_name", "weather")
                .append("status", true)
                .append("http_url", "http://127.0.0.1:" + server.getAddress().getPort() + "/up")
                .append("request_method", "GET").append("content_type", "json")
                .append("params_list", List.of())
                .append("response", new Document("dispatch", false).append("dispatch_type", "text")
                        .append("value", "${data.city}").append("evaluation_type", "expression"))
                .append("set_slots", List.of()));
        assertEquals("Weather:\nPune\n", source.render(parent, prompt("Weather", "weather", null)));

        register("broken", "http_action"); // no http_action_config: the action fails internally
        assertEquals("", source.render(parent, prompt("Broken", "broken", null)));
        assertEquals(Kairon.FAIL, logs("broken").get(0).get("status"));
    }

    @Test
    void wiredIntoPromptActionWithoutDiCycle() throws Exception {
        try (ApplicationContext context = ApplicationContext.run("test")) {
            PromptAction prompt = context.getBean(PromptAction.class);
            Field field = PromptAction.class.getDeclaredField("nested");
            field.setAccessible(true);
            assertNotNull(field.get(prompt));
            assertNotNull(context.getBean(ActionFactory.class));
        }
    }
}
