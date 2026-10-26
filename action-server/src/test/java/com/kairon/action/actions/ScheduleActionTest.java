package com.kairon.action.actions;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.support.Jsons;
import com.sun.net.httpserver.HttpServer;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.bson.Document;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * T-049: orchestration-actions R2 c3-c5, c10. schedule_action submits through the events server scheduling
 * endpoint (body compared with the reference `equivalent_schedule_request`), treats non-200 or
 * success != true as a failed submission (no dispatch GET), dispatches once on success, and writes no job document.
 */
@MicronautTest
class ScheduleActionTest {

    private static final HttpClient CLIENT = HttpClient.newHttpClient();
    private static final Path REFERENCE = Path.of("..", "tests", "testing_data", "schedule_reference_jobs");
    private static final String OK_ENVELOPE =
            "{\"success\":true,\"error_code\":0,\"data\":{\"job_id\":\"%s\"},\"message\":\"Scheduled action job created!\"}";

    record Hit(String method, String path, String contentType, String body) {}

    @Inject
    EmbeddedServer server;

    @Inject
    MemoryActionCatalog catalog;

    @Inject
    ActionSettings settings;

    private HttpServer events;
    private final List<Hit> hits = new CopyOnWriteArrayList<>();
    private volatile int scheduleStatus;
    private volatile String scheduleBody;
    private volatile int dispatchStatus;
    private String previousEventsUrl;

    @BeforeEach
    void setUp() throws Exception {
        catalog.clear();
        hits.clear();
        scheduleStatus = 200;
        scheduleBody = null;
        dispatchStatus = 200;
        events = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        events.createContext("/", exchange -> {
            String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            String path = exchange.getRequestURI().getPath();
            hits.add(new Hit(exchange.getRequestMethod(), path, exchange.getRequestHeaders().getFirst("Content-Type"), body));
            int status;
            String reply;
            if (path.equals(ScheduleAction.SCHEDULE_PATH)) {
                status = scheduleStatus;
                Object jobId = Jsons.readMap(body).get("job_id");
                reply = scheduleBody != null ? scheduleBody : String.format(OK_ENVELOPE, jobId);
            } else {
                status = dispatchStatus;
                reply = "{\"message\":\"Scheduled event dispatch!\",\"data\":null,\"success\":true,\"error_code\":0}";
            }
            byte[] bytes = reply.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        events.start();
        previousEventsUrl = settings.getEventsServerUrl();
        settings.setEventsServerUrl("http://127.0.0.1:" + events.getAddress().getPort());
    }

    @AfterEach
    void tearDown() {
        settings.setEventsServerUrl(previousEventsUrl);
        events.stop(0);
    }

    @Test
    void pyscriptPostsTheReferenceRequestThenDispatchesOnce() throws Exception {
        Map<String, Object> fixture = fixture("pyscript_job.json");
        seed(fixture, true);

        Map<String, Object> body = call(fixture);

        String jobId = assertReferenceRequest(fixture);
        assertDispatchedOnce(jobId);
        assertNoJobStoreWrite();
        assertEquals("scheduled", responses(body).get(0).get("text"));
        assertEquals(List.of(), body.get("events"));
        Document log = log();
        assertEquals("schedule_action", log.get("type"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
        assertEquals(List.of(), log.get("messages"));
        assertEquals("reference_callback_script", log.get("schedule_action"));
        assertEquals("2030-01-15 10:30:00", log.get("schedule_time"));
        assertEquals("Asia/Kolkata", log.get("timezone"));
        assertEquals(Map.of("pyscript_code", "bot_response = 'hello world'", "type", "pyscript"), log.get("execution_info"));
        assertEquals("scheduled", log.get("bot_response"));
        assertNull(log.get("exception"));
        assertTrue(log.containsKey("data"));
    }

    @Test
    void flowPostsTheReferenceRequestThenDispatchesOnce() throws Exception {
        Map<String, Object> fixture = fixture("flow_job.json");
        seed(fixture, false);

        Map<String, Object> body = call(fixture);

        String jobId = assertReferenceRequest(fixture);
        assertDispatchedOnce(jobId);
        assertNoJobStoreWrite();
        assertEquals("scheduled", responses(body).get(0).get("text"));
        Document log = log();
        assertEquals(Kairon.SUCCESS, log.get("status"));
        assertEquals(Map.of("flow", "reference_flow", "type", "flow"), log.get("execution_info"));
        assertEquals(List.of(), log.get("messages"));
    }

    @Test
    void envelopeSuccessFalseIsAFailedSubmissionWithoutDispatch() throws Exception {
        Map<String, Object> fixture = fixture("flow_job.json");
        seed(fixture, false);
        scheduleStatus = 200;
        scheduleBody = "{\"success\":false,\"error_code\":422,\"data\":null,\"message\":\"timezone: timezone must be an IANA zone name or empty\"}";

        Map<String, Object> body = call(fixture);

        assertFailedWithoutDispatch(body);
        assertTrue(String.valueOf(log().get("exception")).contains("timezone must be an IANA zone name or empty"));
    }

    @Test
    void non200StatusIsAFailedSubmissionWithoutDispatch() throws Exception {
        Map<String, Object> fixture = fixture("pyscript_job.json");
        seed(fixture, true);
        scheduleStatus = 500;
        scheduleBody = "{\"success\":true,\"error_code\":0,\"data\":null,\"message\":\"odd\"}";

        Map<String, Object> body = call(fixture);

        assertFailedWithoutDispatch(body);
    }

    @Test
    void unreachableEventsServerFailsTheAction() throws Exception {
        Map<String, Object> fixture = fixture("flow_job.json");
        seed(fixture, false);
        int closed;
        try (ServerSocket socket = new ServerSocket(0)) {
            closed = socket.getLocalPort();
        }
        settings.setEventsServerUrl("http://127.0.0.1:" + closed);

        Map<String, Object> body = call(fixture);

        assertEquals(Kairon.SORRY, responses(body).get(0).get("text"));
        assertEquals(Kairon.FAIL, log().get("status"));
        assertTrue(hits.isEmpty());
        assertNoJobStoreWrite();
    }

    @Test
    void dispatchNon200FailsAfterOneSubmission() throws Exception {
        Map<String, Object> fixture = fixture("flow_job.json");
        seed(fixture, false);
        dispatchStatus = 404;

        Map<String, Object> body = call(fixture);

        assertEquals(2, hits.size());
        assertEquals("POST", hits.get(0).method());
        assertEquals("GET", hits.get(1).method());
        assertEquals(Kairon.SORRY, responses(body).get(0).get("text"));
        Document log = log();
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals(Kairon.SORRY, log.get("bot_response"));
        assertEquals(List.of(), log.get("messages"));
    }

    @Test
    void dispatchFalseUttersNothing() throws Exception {
        Map<String, Object> fixture = fixture("flow_job.json");
        seed(fixture, false, false);

        Map<String, Object> body = call(fixture);

        assertEquals(List.of(), body.get("responses"));
        assertEquals(Kairon.SUCCESS, log().get("status"));
    }

    @Test
    void runAtFollowsDateutilIsoformat() {
        assertEquals("2030-01-15T10:30:00", ScheduleAction.runAt("2030-01-15 10:30:00"));
        assertEquals("2030-01-15T10:30:00", ScheduleAction.runAt("2030-01-15 10:30"));
        assertEquals("2030-01-15T10:30:00", ScheduleAction.runAt("2030-01-15T10:30:00"));
        assertEquals("2030-01-15T00:00:00", ScheduleAction.runAt("2030-01-15"));
        assertEquals("2030-01-15T10:30:00.250000", ScheduleAction.runAt("2030-01-15T10:30:00.25"));
        assertEquals("2030-01-15T10:30:00+00:00", ScheduleAction.runAt("2030-01-15T10:30:00Z"));
        assertEquals("2030-01-15T10:30:00+05:30", ScheduleAction.runAt("2030-01-15T10:30:00+05:30"));
    }

    // --- helpers ---

    @SuppressWarnings("unchecked")
    private String assertReferenceRequest(Map<String, Object> fixture) {
        List<Hit> posts = hits.stream().filter(hit -> hit.path().equals(ScheduleAction.SCHEDULE_PATH)).toList();
        assertEquals(1, posts.size(), "exactly one scheduling POST");
        Hit post = posts.get(0);
        assertEquals("POST", post.method());
        assertTrue(post.contentType().startsWith("application/json"), post.contentType());
        Map<String, Object> sent = Jsons.readMap(post.body());
        String jobId = String.valueOf(sent.get("job_id"));
        assertTrue(jobId.matches("[0-9a-f]{32}"), jobId);
        assertEquals('7', jobId.charAt(12), "UUIDv7");
        Map<String, Object> expected = new LinkedHashMap<>((Map<String, Object>) fixture.get("equivalent_schedule_request"));
        expected.put("job_id", jobId);
        assertEquals(expected, sent);
        assertEquals(List.copyOf(expected.keySet()), List.copyOf(sent.keySet()), "body key order");
        return jobId;
    }

    private void assertDispatchedOnce(String jobId) {
        assertEquals(2, hits.size(), "one POST then one dispatch GET: " + hits);
        assertEquals(ScheduleAction.SCHEDULE_PATH, hits.get(0).path());
        assertEquals("GET", hits.get(1).method());
        assertEquals("/api/events/dispatch/" + jobId, hits.get(1).path());
    }

    private void assertFailedWithoutDispatch(Map<String, Object> body) {
        assertEquals(1, hits.size(), "no dispatch GET after a failed submission: " + hits);
        assertEquals("POST", hits.get(0).method());
        assertEquals(Kairon.SORRY, responses(body).get(0).get("text"));
        Document log = log();
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals(Kairon.SORRY, log.get("bot_response"));
        assertEquals(List.of(), log.get("messages"));
        assertNoJobStoreWrite();
    }

    private void assertNoJobStoreWrite() {
        assertEquals(List.of(), catalog.all("scheduler_jobs"));
        assertEquals(List.of(), catalog.all("kscheduler"));
    }

    @SuppressWarnings("unchecked")
    private void seed(Map<String, Object> fixture, boolean pyscript) {
        seed(fixture, pyscript, true);
    }

    @SuppressWarnings("unchecked")
    private void seed(Map<String, Object> fixture, boolean pyscript, boolean dispatch) {
        Map<String, Object> inputs = (Map<String, Object>) fixture.get("inputs");
        String bot = String.valueOf(inputs.get("bot"));
        Map<String, Object> actionConfig = (Map<String, Object>) inputs.get("action_config");
        String name = String.valueOf(actionConfig.get("name"));
        catalog.put("actions", new Document("bot", bot).append("name", name).append("type", "schedule_action").append("status", true));
        Document config = new Document("bot", bot).append("status", true);
        actionConfig.forEach((key, value) -> config.append(key, toBson(value)));
        config.append("response_text", "scheduled").append("dispatch_bot_response", dispatch);
        catalog.put("schedule_action", config);
        if (pyscript) {
            catalog.put("callback_config", new Document("bot", bot).append("name", actionConfig.get("schedule_action"))
                    .append("pyscript_code", inputs.get("callback_pyscript_code")));
        }
    }

    @SuppressWarnings("unchecked")
    private static Object toBson(Object value) {
        if (value instanceof Map<?, ?> map) {
            Document document = new Document();
            ((Map<String, Object>) map).forEach((key, item) -> document.append(key, toBson(item)));
            return document;
        }
        if (value instanceof List<?> list) {
            return list.stream().map(ScheduleActionTest::toBson).toList();
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> call(Map<String, Object> fixture) throws Exception {
        Map<String, Object> inputs = (Map<String, Object>) fixture.get("inputs");
        Map<String, Object> actionConfig = (Map<String, Object>) inputs.get("action_config");
        Map<String, Object> slots = new LinkedHashMap<>();
        slots.put("bot", inputs.get("bot"));
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", inputs.get("sender_id"));
        tracker.put("slots", slots);
        tracker.put("latest_message", Map.of("text", "remind me", "intent", Map.of("name", "remind")));
        tracker.put("events", List.of());
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("next_action", actionConfig.get("name"));
        request.put("tracker", tracker);
        request.put("domain", Map.of());
        HttpResponse<String> response = CLIENT.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + server.getPort() + "/webhook"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(Jsons.write(request))).build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode(), response.body());
        return Jsons.readMap(response.body());
    }

    private static Map<String, Object> fixture(String name) throws Exception {
        return Jsons.readMap(Files.readString(REFERENCE.resolve(name)));
    }

    private Document log() {
        List<Document> logs = catalog.all(Kairon.LOGS);
        assertEquals(1, logs.size());
        return logs.get(0);
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> responses(Map<String, Object> body) {
        return (List<Map<String, Object>>) body.get("responses");
    }
}
