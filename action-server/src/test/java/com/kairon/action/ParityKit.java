package com.kairon.action;

import com.kairon.action.actions.ActionFactory;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.Dispatcher;
import com.kairon.action.runtime.RequestIds;
import com.kairon.action.runtime.TrackerState;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Jsons;
import com.kairon.action.support.Maps;
import com.kairon.action.support.Tokens;
import com.sun.net.httpserver.HttpServer;
import io.micronaut.runtime.server.EmbeddedServer;
import org.bson.Document;

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
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Shared stub, catalog, and webhook helpers for the Python parity suite. */
final class ParityKit {

    static final String BOT = "6697add6b8e47524eb983373";
    static final String STUB = "http://127.0.0.1:18780";
    static final String FERNET = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=";

    static final List<Hit> HITS = new CopyOnWriteArrayList<>();
    static final ConcurrentHashMap<String, String> PATH_BODIES = new ConcurrentHashMap<>();
    static final ConcurrentHashMap<String, Integer> PATH_STATUS = new ConcurrentHashMap<>();
    static final ConcurrentHashMap<String, String> SCRIPT_BODIES = new ConcurrentHashMap<>();
    /** Paths of requests that carried an {@code api-key} header (Qdrant auth). */
    static final List<String> API_KEY_PATHS = new CopyOnWriteArrayList<>();
    static volatile int forcedStatus;
    static volatile String bodyOverride;

    private static HttpServer stub;
    private static HttpServer events;
    static int eventsPort;

    final EmbeddedServer server;
    final MemoryActionCatalog catalog;
    final Tokens tokens;
    final ActionSupport support;
    final ActionFactory factory;
    final HttpCaller http;
    final ActionSettings settings;
    final HttpClient client = HttpClient.newHttpClient();

    String bot = BOT;

    record Hit(String method, String path, String query, String auth, String body, String timestamp) {}

    record Reply(int status, String body) {}

    ParityKit(EmbeddedServer server, MemoryActionCatalog catalog, Tokens tokens, ActionSupport support,
              ActionFactory factory, HttpCaller http, ActionSettings settings) {
        this.server = server;
        this.catalog = catalog;
        this.tokens = tokens;
        this.support = support;
        this.factory = factory;
        this.http = http;
        this.settings = settings;
    }

    static void startServers() throws Exception {
        stub = HttpServer.create(new InetSocketAddress("127.0.0.1", 18780), 0);
        stub.createContext("/", exchange -> {
            byte[] raw = exchange.getRequestBody().readAllBytes();
            String body = new String(raw, StandardCharsets.UTF_8);
            String path = exchange.getRequestURI().getPath();
            String query = exchange.getRequestURI().getRawQuery();
            String method = exchange.getRequestMethod();
            if (exchange.getRequestHeaders().containsKey("api-key")) {
                API_KEY_PATHS.add(path);
            }
            HITS.add(new Hit(method, path, query, exchange.getRequestHeaders().getFirst("Authorization"), body,
                    exchange.getRequestHeaders().getFirst(Kairon.TIMESTAMP)));
            String payload = resolveBody(method, path, body);
            int status = resolveStatus(path);
            byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        stub.start();
        events = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        events.createContext("/", exchange -> {
            String request = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            // POST /api/events/schedule/action answers with the scheduling envelope; everything else (dispatch GET)
            // with the dispatch reply.
            byte[] body = ("/api/events/schedule/action".equals(exchange.getRequestURI().getPath())
                    ? "{\"success\":true,\"error_code\":0,\"data\":{\"job_id\":\"" + Jsons.readMap(request).get("job_id")
                            + "\"},\"message\":\"Scheduled action job created!\"}"
                    : "{\"message\":\"Scheduled event dispatch!\",\"data\":null}").getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        events.start();
        eventsPort = events.getAddress().getPort();
    }

    static void stopServers() {
        if (stub != null) {
            stub.stop(0);
        }
        if (events != null) {
            events.stop(0);
        }
    }

    static void resetStub() {
        HITS.clear();
        PATH_BODIES.clear();
        PATH_STATUS.clear();
        SCRIPT_BODIES.clear();
        API_KEY_PATHS.clear();
        forcedStatus = 0;
        bodyOverride = null;
    }

    void resetState() {
        bot = BOT;
        catalog.clear();
        resetStub();
        RequestIds.clear();
    }

    void restore() {
        settings.setLiveAgentEnabled(false);
        settings.setFernetKey(FERNET);
        settings.setPyscriptUrl(STUB + "/pyscript");
        settings.setEvaluatorUrl(STUB + "/eval");
        settings.setLlmUrl(STUB + "/llm");
        settings.setVectorUrl(STUB + "/vector");
        settings.setVectorDb(STUB);
        settings.setVectorKey(null);
        settings.setLlmServerUrl(STUB);
        settings.setEventsServerUrl("http://127.0.0.1:18771");
        settings.setVoiceCallUrl(STUB + "/voice");
        settings.setWebSearchUrl(STUB + "/websearch");
        settings.setHttpsStubBase(STUB);
        settings.setSimpleAgentUrl(STUB + "/agent");
        settings.setLiveAgentUrl(STUB + "/live");
        settings.setCallbackBaseUrl("http://callback.test");
        settings.setLiveAgentToken("live-token");
        RequestIds.clear();
    }

    void useEvents() {
        settings.setEventsServerUrl("http://127.0.0.1:" + eventsPort);
    }

    Document doc(Object... pairs) {
        Document document = new Document();
        for (int i = 0; i + 1 < pairs.length; i += 2) {
            document.put(String.valueOf(pairs[i]), pairs[i + 1]);
        }
        return document;
    }

    Document param(String key, String type, Object value) {
        return doc("key", key, "parameter_type", type, "value", value);
    }

    Document param(String key, String type, Object value, boolean encrypt) {
        Document document = param(key, type, value);
        document.put("encrypt", encrypt);
        return document;
    }

    void register(String name, String type) {
        catalog.put("actions", doc("bot", bot, "name", name, "type", type, "status", true));
    }

    void put(String collection, Document document) {
        catalog.put(collection, document);
    }

    Map<String, Object> slots(Object... extra) {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("bot", bot);
        for (int i = 0; i + 1 < extra.length; i += 2) {
            values.put(String.valueOf(extra[i]), extra[i + 1]);
        }
        return values;
    }

    Map<String, Object> latest(String text) {
        return latest(text, "greet", null);
    }

    Map<String, Object> latest(String text, String intent, List<Map<String, Object>> entities) {
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("text", text);
        Map<String, Object> named = new LinkedHashMap<>();
        named.put("name", intent);
        message.put("intent", named);
        message.put("intent_ranking", List.of(Map.of("name", intent)));
        if (entities != null) {
            message.put("entities", entities);
        }
        return message;
    }

    Map<String, Object> entity(String name, String value) {
        return Maps.of("entity", name, "value", value);
    }

    void faqOn() {
        put("bot_settings", doc("bot", bot, "status", true, "llm_settings", doc("enable_faq", true)));
    }

    void voiceChannel() {
        put("channels", doc("bot", bot, "connector_type", "voice", "config", doc(
                "telephony_provider", "twilio", "phone_number", "+10000000000", "account_sid", "AC1")));
    }

    void schema(String collection) {
        put("cognition_schema", doc("bot", bot, "collection_name", collection, "status", true,
                "schema_metadata", doc("training_needed", false)));
    }

    Map<String, Object> ok(String action) {
        return ok(action, slots(), latest("hi"), List.of(), Map.of(), "default", action, null, null);
    }

    Map<String, Object> ok(String action, Map<String, Object> slotValues, Map<String, Object> message) {
        return ok(action, slotValues, message, List.of(), Map.of(), "default", action, null, null);
    }

    Map<String, Object> ok(String action, Map<String, Object> slotValues, Map<String, Object> message,
                           List<?> events, Map<String, Object> domain, String sender, String followup,
                           String requestId, String channel) {
        Reply reply = post(action, slotValues, message, events, domain, sender, followup, requestId, channel);
        assertEquals(200, reply.status(), reply.body());
        return Jsons.readMap(reply.body());
    }

    Reply post(String action, Map<String, Object> slotValues, Map<String, Object> message, List<?> events,
               Map<String, Object> domain, String sender, String followup, String requestId, String channel) {
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", sender);
        tracker.put("slots", slotValues);
        tracker.put("latest_message", message == null ? Map.of() : message);
        tracker.put("events", events == null ? List.of() : events);
        if (followup != null) {
            tracker.put("followup_action", followup);
        }
        if (channel != null) {
            tracker.put("latest_input_channel", channel);
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("next_action", action);
        body.put("tracker", tracker);
        body.put("domain", domain == null ? Map.of() : domain);
        return send("POST", "/webhook", Jsons.write(body), requestId);
    }

    Reply send(String method, String path, String json, String requestId) {
        try {
            HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + server.getPort() + path));
            if (requestId != null) {
                builder.header(Kairon.REQUEST_ID, requestId);
            }
            if ("GET".equals(method)) {
                builder.GET();
            } else {
                builder.header("Content-Type", "application/json");
                builder.POST(HttpRequest.BodyPublishers.ofString(json == null ? "" : json));
            }
            HttpResponse<String> response = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            return new Reply(response.statusCode(), response.body());
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    ActionContext context(String action, Map<String, Object> slotValues, Map<String, Object> message, List<?> events, String sender) {
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", sender);
        tracker.put("slots", slotValues);
        tracker.put("latest_message", message == null ? Map.of() : message);
        tracker.put("events", events == null ? List.of() : events);
        String botId = Maps.str(slotValues.get("bot"));
        return new ActionContext(botId == null ? bot : botId, action, TrackerState.from(tracker), new Dispatcher(), Map.of(), Map.of());
    }

    Map<String, Object> execute(String action, Map<String, Object> slotValues, Map<String, Object> message) {
        return factory.get(bot, action).execute(context(action, slotValues, message, List.of(), "default"));
    }

    ActionFailure failureOf(org.junit.jupiter.api.function.Executable executable) {
        return assertThrows(ActionFailure.class, executable);
    }

    List<Document> logs(String action) {
        List<Document> found = new ArrayList<>();
        for (Document document : catalog.all(Kairon.LOGS)) {
            if (action.equals(document.get("action"))) {
                found.add(document);
            }
        }
        return found;
    }

    Document log(String action) {
        List<Document> found = logs(action);
        assertTrue(!found.isEmpty(), "no log for " + action + " in " + catalog.all(Kairon.LOGS));
        return found.get(found.size() - 1);
    }

    @SuppressWarnings("unchecked")
    Map<String, Object> event(Map<String, Object> body, String name) {
        for (Object item : (List<?>) body.get("events")) {
            Map<String, Object> event = (Map<String, Object>) item;
            if (name.equals(event.get("name"))) {
                return event;
            }
        }
        throw new AssertionError("missing slot " + name + " in " + body);
    }

    Object slotValue(Map<String, Object> body, String name) {
        return event(body, name).get("value");
    }

    @SuppressWarnings("unchecked")
    List<Map<String, Object>> responses(Map<String, Object> body) {
        return (List<Map<String, Object>>) body.get("responses");
    }

    String text(Map<String, Object> body) {
        List<Map<String, Object>> messages = responses(body);
        assertTrue(!messages.isEmpty(), "no responses in " + body);
        return String.valueOf(messages.get(0).get("text"));
    }

    Hit hit() {
        assertTrue(!HITS.isEmpty(), "stub received no requests");
        return HITS.get(HITS.size() - 1);
    }

    Hit hitPath(String part) {
        Hit found = null;
        for (Hit hit : HITS) {
            if (hit.path().contains(part)) {
                found = hit;
            }
        }
        assertTrue(found != null, "no hit containing " + part + " in " + HITS);
        return found;
    }

    void script(String source, String body) {
        SCRIPT_BODIES.put(source, body);
    }

    void pathBody(String path, String body) {
        PATH_BODIES.put(path, body);
    }

    void pathStatus(String path, int status) {
        PATH_STATUS.put(path, status);
    }

    private static String resolveBody(String method, String path, String requestBody) {
        if (path.contains("pyscript")) {
            String source = sourceOf(requestBody);
            if (source != null && SCRIPT_BODIES.containsKey(source)) {
                return SCRIPT_BODIES.get(source);
            }
        }
        String best = longest(PATH_BODIES.keySet(), path);
        if (best != null) {
            return PATH_BODIES.get(best);
        }
        if (bodyOverride != null) {
            return bodyOverride;
        }
        return defaultBody(method, path, requestBody);
    }

    private static int resolveStatus(String path) {
        String best = longest(PATH_STATUS.keySet(), path);
        if (best != null) {
            return PATH_STATUS.get(best);
        }
        return forcedStatus == 0 ? 200 : forcedStatus;
    }

    private static String longest(Iterable<String> keys, String path) {
        String best = null;
        for (String key : keys) {
            if (path.contains(key) && (best == null || key.length() > best.length())) {
                best = key;
            }
        }
        return best;
    }

    private static String sourceOf(String body) {
        if (body == null || body.isBlank() || !body.strip().startsWith("{")) {
            return null;
        }
        try {
            Object source = Jsons.readMap(body).get("source_code");
            return source == null ? null : String.valueOf(source);
        } catch (RuntimeException e) {
            return null;
        }
    }

    private static String defaultBody(String method, String path, String requestBody) {
        if (path.contains("/pyscript")) {
            return "{\"statusCode\":200,\"body\":{\"bot_response\":\"scripted\",\"slots\":{\"place\":\"Pune\"},\"type\":\"text\"}}";
        }
        if (path.contains("/eval")) {
            return "{\"success\":true,\"data\":\"ok\"}";
        }
        if (path.contains("/vector")) {
            return "{\"result\":[{\"id\":\"1\"}]}";
        }
        if (path.contains("/llm")) {
            return "{\"content\":\"llm-answer\"}";
        }
        if (path.contains("/websearch")) {
            return "{\"error_code\":0,\"data\":[{\"title\":\"T\",\"description\":\"D\",\"url\":\"http://e\"}]}";
        }
        if (path.endsWith("/conversation/request")) {
            return "{\"data\":{\"msg\":\"agent ready\"}}";
        }
        if (path.contains("/agent")) {
            return "{\"output\":\"agent-out\"}";
        }
        if (path.contains("/voice")) {
            return "{\"call_sid\":\"CA1\"}";
        }
        if (path.contains("/customsearch/v1")) {
            return "{\"items\":[{\"title\":\"T\",\"snippet\":\"S\",\"link\":\"http://l\"}]}";
        }
        if (path.contains("/submissions")) {
            return "{\"inlineMessage\":\"ok\"}";
        }
        if (path.contains("/v1/payment_links")) {
            return "{\"short_url\":\"https://rzp/x\"}";
        }
        if (path.contains("/api/v2/tickets.json")) {
            return "{\"ticket\":{\"id\":1}}";
        }
        if (path.contains("/rest/api/2/issue") || path.contains("/jira")) {
            return "{\"key\":\"K-1\"}";
        }
        if (path.contains("/v1/organizations") || path.contains("/v1/persons") || path.contains("/v1/leads") || path.contains("/v1/notes")) {
            return "{\"success\":true,\"data\":{\"id\":1}}";
        }
        if (path.contains("/mock")) {
            if ("POST".equals(method)) {
                return "Data added successfully";
            }
            if ("PUT".equals(method)) {
                return "Data updated successfully";
            }
            if ("DELETE".equals(method)) {
                boolean auth = false;
                for (Hit hit : HITS) {
                    if (hit.path().contains("/mock") && "DELETE".equals(hit.method())) {
                        auth = hit.auth() != null;
                    }
                }
                if (!auth) {
                    return "Data updated successfully";
                }
                return requestBody == null || requestBody.isBlank() ? "Data deleted successfully" : "Data deleted successfully";
            }
            return "{\"data\":\"test_data\",\"test_class\":[{\"key\":\"value\"},{\"key2\":\"value2\"}]}";
        }
        return "{}";
    }
}
