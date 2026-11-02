package com.kairon.action;

import com.kairon.action.actions.ActionFactory;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Tokens;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.bson.Document;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * T-048 (dispatch-and-logging R5 c3-c5, integration-actions R1 c12): http_action events[] and time_elapsed.
 * T-047 (core-actions R7 c12, integration-actions R10 c8, R13 c6): messages[] on pyscript, live_agent, callback logs.
 * Expected keys, order and strings follow kairon/actions/definitions/http.py:54-181 and
 * kairon/shared/actions/utils.py compose_response / fill_slots_from_response / evaluate_pyscript /
 * handle_json_response.
 */
@MicronautTest
class ActionLogEventsTest {

    @Inject
    EmbeddedServer server;
    @Inject
    MemoryActionCatalog catalog;
    @Inject
    Tokens tokens;
    @Inject
    ActionSupport support;
    @Inject
    ActionFactory factory;
    @Inject
    HttpCaller http;
    @Inject
    ActionSettings settings;

    ParityKit kit;

    @BeforeAll
    static void servers() throws Exception {
        ParityKit.startServers();
    }

    @AfterAll
    static void stop() {
        ParityKit.stopServers();
    }

    @BeforeEach
    void reset() {
        kit = new ParityKit(server, catalog, tokens, support, factory, http, settings);
        kit.restore();
        kit.resetState();
    }

    @Test
    void httpActionParamsListEventsHavePythonKeysOrderAndLogs() {
        kit.register("lookup", "http_action");
        kit.pathBody("/up", "{\"city\":\"Pune\"}");
        kit.put("http_action_config", kit.doc(
                "bot", kit.bot, "action_name", "lookup", "status", true,
                "http_url", ParityKit.STUB + "/up", "request_method", "POST", "content_type", "json",
                "headers", List.of(kit.param("Authorization", "value", "Bearer secret-token-123", true)),
                "params_list", List.of(kit.param("q", "value", "pune")),
                "response", kit.doc("dispatch", true, "dispatch_type", "text",
                        "value", "${data.city}", "evaluation_type", "expression"),
                "set_slots", List.of(
                        kit.doc("name", "city", "value", "${data.city}", "evaluation_type", "expression"),
                        kit.doc("name", "bad", "value", "${data.missing.key}", "evaluation_type", "expression"))));
        Map<String, Object> body = kit.ok("lookup", kit.slots("city", "Mumbai"), kit.latest("weather"));
        assertEquals("Pune", kit.text(body));
        assertEquals("Bearer secret-token-123", kit.hitPath("/up").auth());

        Document log = kit.log("lookup");
        List<String> keys = new ArrayList<>(log.keySet());
        keys.remove("_id");
        assertEquals(List.of("type", "intent", "action", "sender", "url", "request_method", "bot_response", "bot",
                "timestamp", "status", "trigger_info", "request_id", "events", "fail_reason", "user_msg", "time_elapsed",
                "http_status_code"), keys);
        // Python passes fail_reason=None on 2xx; as a dynamic field mongoengine stores it as null.
        assertTrue(log.containsKey("fail_reason"));
        assertNull(log.get("fail_reason"));

        List<Map<String, Object>> events = events(log);
        assertEquals(List.of("slots", "response", "api_call", "params_list", "filled_slots"),
                events.stream().map(e -> e.get("type")).toList());

        Map<String, Object> slots = events.get(0);
        assertEquals(List.of("type", "data"), keyList(slots));
        Map<String, Object> firstSlot = list(slots.get("data")).get(0);
        assertEquals(List.of("name", "value", "evaluation_type", "slot_value"), keyList(firstSlot));
        assertEquals("Mumbai", firstSlot.get("slot_value"));

        Map<String, Object> response = events.get(1);
        assertEquals(List.of("type", "dispatch_bot_response", "dispatch_type", "data", "evaluation_type", "response",
                "bot_response_log", "time_elapsed"), keyList(response));
        assertEquals(true, response.get("dispatch_bot_response"));
        assertEquals("${data.city}", response.get("data"));
        assertEquals("Pune", response.get("response"));
        assertEquals(0, response.get("time_elapsed"));
        List<String> composeLog = strings(response.get("bot_response_log"));
        assertEquals(4, composeLog.size());
        assertEquals("evaluation_type: expression", composeLog.get(0));
        assertEquals("expression: ${data.city}", composeLog.get(1));
        assertTrue(composeLog.get(2).startsWith("data: {'data': {'city': 'Pune'}, 'context': {"), composeLog.get(2));
        assertTrue(composeLog.get(2).contains("}, 'http_status_code': 200, 'response_headers': {"), composeLog.get(2));
        assertEquals("response: Pune", composeLog.get(3));

        Map<String, Object> apiCall = events.get(2);
        assertEquals(List.of("type", "headers", "method", "url", "payload", "response", "status_code", "time_elapsed",
                "response_headers"), keyList(apiCall));
        Object maskedAuth = asMap(apiCall.get("headers")).get("Authorization");
        assertNotEquals("Bearer secret-token-123", maskedAuth);
        assertTrue(String.valueOf(maskedAuth).contains("*"), String.valueOf(maskedAuth));
        assertEquals("POST", apiCall.get("method"));
        assertEquals(ParityKit.STUB + "/up", apiCall.get("url"));
        assertEquals(Map.of("q", "pune"), apiCall.get("payload"));
        assertEquals(Map.of("city", "Pune"), apiCall.get("response"));
        assertEquals(200, apiCall.get("status_code"));
        assertTrue(asMap(apiCall.get("response_headers")).keySet().stream().anyMatch("content-type"::equalsIgnoreCase),
                String.valueOf(apiCall));

        Map<String, Object> params = events.get(3);
        assertEquals(List.of("type", "request_body", "request_params"), keyList(params));
        assertEquals(Map.of("q", "pune"), params.get("request_body"));

        Map<String, Object> filled = events.get(4);
        assertEquals(List.of("type", "data", "slot_eval_log", "time_elapsed"), keyList(filled));
        Map<String, Object> filledData = asMap(filled.get("data"));
        assertEquals("Pune", filledData.get("city"));
        assertTrue(filledData.containsKey("bad") && filledData.get("bad") == null, String.valueOf(filledData));
        assertEquals(0, filled.get("time_elapsed"));
        List<String> slotLog = strings(filled.get("slot_eval_log"));
        assertEquals("initiating slot evaluation", slotLog.get(0));
        assertEquals("Slot: city", slotLog.get(1));
        assertEquals("evaluation_type: expression", slotLog.get(2));
        assertEquals("expression: ${data.city}", slotLog.get(3));
        assertEquals("response: Pune", slotLog.get(5));
        assertEquals("Slot: bad", slotLog.get(6));
        assertTrue(slotLog.get(7).startsWith("Evaluation error for bad: "), slotLog.get(7));
        assertEquals("Slot bad eventually set to None.", slotLog.get(8));
        assertEquals(9, slotLog.size());

        // time_elapsed = api call + slots (0) + pyscript (0) + compose (0)
        Number apiElapsed = (Number) apiCall.get("time_elapsed");
        assertEquals(apiElapsed.doubleValue(), ((Number) log.get("time_elapsed")).doubleValue());
        assertEquals(200, log.get("http_status_code"));
    }

    @Test
    void httpActionDynamicParamsAndScriptResponseSumFourTimings() {
        kit.register("dyn_lookup", "http_action");
        kit.pathBody("/up", "{\"ok\":true}");
        kit.script("build_body", "{\"statusCode\":200,\"body\":{\"body\":{\"q\":\"x\"},\"slots\":{\"s1\":\"v\",\"bot\":\"z\"}}}");
        kit.script("make_reply", "{\"statusCode\":200,\"body\":{\"bot_response\":\"scripted reply\"}}");
        kit.put("http_action_config", kit.doc(
                "bot", kit.bot, "action_name", "dyn_lookup", "status", true,
                "http_url", ParityKit.STUB + "/up", "request_method", "POST", "content_type", "json",
                "dynamic_params", "build_body",
                "response", kit.doc("dispatch", true, "dispatch_type", "text",
                        "value", "make_reply", "evaluation_type", "script")));
        Map<String, Object> body = kit.ok("dyn_lookup");
        assertEquals("scripted reply", kit.text(body));
        assertEquals("v", kit.slotValue(body, "s1"));

        Document log = kit.log("dyn_lookup");
        List<Map<String, Object>> events = events(log);
        assertEquals(List.of("response", "api_call", "dynamic_params", "filled_slots"),
                events.stream().map(e -> e.get("type")).toList());

        Map<String, Object> dynamic = events.get(2);
        assertEquals(List.of("type", "data", "response", "slots", "request_params", "time_elapsed"), keyList(dynamic));
        assertEquals("build_body", dynamic.get("data"));
        assertEquals(Map.of("q", "x"), dynamic.get("response"));
        assertEquals(Map.of("s1", "v"), dynamic.get("slots"));
        List<String> scriptLog = strings(dynamic.get("request_params"));
        assertEquals(4, scriptLog.size());
        assertEquals("evaluation_type: script", scriptLog.get(0));
        assertEquals("script: build_body", scriptLog.get(1));
        assertTrue(scriptLog.get(2).startsWith("data: {"), scriptLog.get(2));
        assertEquals("raise_err_on_failure: True", scriptLog.get(3));
        assertInstanceOf(Double.class, dynamic.get("time_elapsed"));

        Map<String, Object> response = events.get(0);
        assertEquals("script", response.get("evaluation_type"));
        assertEquals("scripted reply", response.get("response"));
        assertEquals("script: make_reply", strings(response.get("bot_response_log")).get(1));
        assertInstanceOf(Double.class, response.get("time_elapsed"));

        Map<String, Object> filled = events.get(3);
        assertEquals(Map.of(), filled.get("data"));
        assertEquals(List.of("initiating slot evaluation"), filled.get("slot_eval_log"));
        assertEquals(0, filled.get("time_elapsed"));

        double expected = ((Number) events.get(1).get("time_elapsed")).doubleValue()
                + 0
                + ((Number) dynamic.get("time_elapsed")).doubleValue()
                + ((Number) response.get("time_elapsed")).doubleValue();
        assertEquals(expected, ((Number) log.get("time_elapsed")).doubleValue(), 1e-12);
    }

    @Test
    void httpActionFailureAddsExceptionsToEvents() {
        kit.register("broken", "http_action");
        kit.pathBody("/down", "{\"error\":\"boom\"}");
        kit.pathStatus("/down", 500);
        kit.put("http_action_config", kit.doc(
                "bot", kit.bot, "action_name", "broken", "status", true,
                "http_url", ParityKit.STUB + "/down", "request_method", "GET", "content_type", "json",
                "params_list", List.of(),
                "response", kit.doc("dispatch", true, "dispatch_type", "text",
                        "value", "${data.city}", "evaluation_type", "expression")));
        Map<String, Object> body = kit.ok("broken");
        assertEquals(Kairon.FAILED, kit.text(body));
        Document log = kit.log("broken");
        assertEquals(Kairon.FAIL, log.get("status"));
        List<Map<String, Object>> events = events(log);
        assertEquals(List.of("response", "api_call", "params_list", "filled_slots"),
                events.stream().map(e -> e.get("type")).toList());
        assertEquals(List.of("type", "dispatch_bot_response", "dispatch_type", "data", "evaluation_type", "exception"),
                keyList(events.get(0)));
        assertEquals(Kairon.FAILED, events.get(0).get("exception"));
        assertEquals(List.of("type", "headers", "method", "url", "payload", "response", "status_code", "time_elapsed",
                "response_headers", "exception"), keyList(events.get(1)));
        assertEquals(500, events.get(1).get("status_code"));
        assertEquals(log.get("exception"), events.get(1).get("exception"));
        assertEquals(List.of("type"), keyList(events.get(3)));
        assertEquals("Got non-200 status code:500 http_response:{'error': 'boom'}", log.get("fail_reason"));
        assertEquals(500, log.get("http_status_code"));
        List<String> keys = new ArrayList<>(log.keySet());
        keys.remove("_id");
        assertEquals(List.of("events", "fail_reason", "user_msg", "time_elapsed", "http_status_code"),
                keys.subList(keys.size() - 5, keys.size()));
    }

    /** outbound-clients R1 c2 via integration-actions R1: a refused connection surfaces as status 503 like Python. */
    @Test
    void httpActionConnectionRefusedReports503() throws Exception {
        int port;
        try (java.net.ServerSocket socket = new java.net.ServerSocket(0)) {
            port = socket.getLocalPort();
        }
        kit.register("offline", "http_action");
        kit.put("http_action_config", kit.doc(
                "bot", kit.bot, "action_name", "offline", "status", true,
                "http_url", "http://127.0.0.1:" + port + "/x", "request_method", "GET", "content_type", "json",
                "params_list", List.of(),
                "response", kit.doc("dispatch", true, "dispatch_type", "text",
                        "value", "${data.city}", "evaluation_type", "expression")));
        Map<String, Object> body = kit.ok("offline");
        assertEquals(Kairon.FAILED, kit.text(body));
        assertEquals(503, kit.slotValue(body, "http_status_code"));
        Document log = kit.log("offline");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals("Got non-200 status code:503 http_response:None", log.get("fail_reason"));
        assertEquals(503, log.get("http_status_code"));
        Map<String, Object> apiCall = events(log).get(1);
        assertEquals("api_call", apiCall.get("type"));
        assertEquals(503, apiCall.get("status_code"));
        assertEquals(null, apiCall.get("response"));
        assertTrue(apiCall.containsKey("response_headers") && apiCall.get("response_headers") == null, String.valueOf(apiCall));
        assertEquals(0, apiCall.get("time_elapsed"));
        // compose_response validates against the response context, so its repr follows http_response:
        assertTrue(String.valueOf(apiCall.get("exception")).startsWith("Got non-200 status code:503 http_response:{'data': None, "), String.valueOf(apiCall.get("exception")));
        assertEquals(log.get("exception"), apiCall.get("exception"));
    }

    @Test
    void pyscriptJsonDispatchOfTextLogsConversionMessage() {
        kit.register("py_json", "pyscript_action");
        kit.script("reply_text", "{\"statusCode\":200,\"body\":{\"bot_response\":\"hello there\",\"type\":\"json\"}}");
        kit.put("pyscript_action_config", kit.doc("bot", kit.bot, "name", "py_json", "status", true,
                "source_code", "reply_text", "dispatch_response", true));
        Map<String, Object> body = kit.ok("py_json");
        assertEquals("hello there", kit.text(body));
        Document log = kit.log("py_json");
        assertEquals(List.of("Failed to convert http response to json: Expecting value: line 1 column 1 (char 0)"),
                log.get("messages"));
        List<String> keys = new ArrayList<>(log.keySet());
        assertTrue(keys.indexOf("config") < keys.indexOf("user_msg"), "config before user_msg: " + keys);
        assertTrue(keys.indexOf("messages") < keys.indexOf("bot"), "messages is a declared field: " + keys);
    }

    @Test
    void pyscriptTextDispatchLogsEmptyMessages() {
        kit.register("py_text", "pyscript_action");
        kit.script("reply_plain", "{\"statusCode\":200,\"body\":{\"bot_response\":\"plain\"}}");
        kit.put("pyscript_action_config", kit.doc("bot", kit.bot, "name", "py_text", "status", true,
                "source_code", "reply_plain", "dispatch_response", true));
        kit.ok("py_text");
        assertEquals(List.of(), kit.log("py_text").get("messages"));
    }

    @Test
    void pyscriptJsonDispatchOfJsonTextLogsNoMessage() {
        kit.register("py_obj", "pyscript_action");
        kit.script("reply_obj", "{\"statusCode\":200,\"body\":{\"bot_response\":\"{\\\"a\\\": 1}\",\"type\":\"json\"}}");
        kit.put("pyscript_action_config", kit.doc("bot", kit.bot, "name", "py_obj", "status", true,
                "source_code", "reply_obj", "dispatch_response", true));
        Map<String, Object> body = kit.ok("py_obj");
        assertEquals(Map.of("a", 1), kit.responses(body).get(0).get("custom"));
        assertEquals(List.of(), kit.log("py_obj").get("messages"));
    }

    @Test
    void liveAgentLogCarriesMessages() {
        kit.register("talk", "live_agent_action");
        kit.put("live_agent_action_config", kit.doc("bot", kit.bot, "name", "live_agent_action", "status", true, "bot_response", "hello"));
        kit.ok("talk");
        Document log = kit.log("talk");
        assertEquals(List.of(), log.get("messages"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
    }

    @Test
    void liveAgentFailureLogCarriesMessages() {
        kit.register("talk_missing", "live_agent_action");
        kit.ok("talk_missing");
        Document log = kit.log("talk_missing");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals(List.of(), log.get("messages"));
    }

    @Test
    void callbackLogCarriesMessages() {
        kit.register("ping", "callback_action");
        kit.put("callback_action_config", kit.doc("bot", kit.bot, "name", "ping", "status", true,
                "callback_name", "hook", "dynamic_url_slot_name", "cb_url", "bot_response", "open {callback_url}"));
        kit.put("callback_config", kit.doc("bot", kit.bot, "name", "hook", "validation_secret", "secret", "expire_in", 15));
        Map<String, Object> body = kit.ok("ping");
        assertTrue(kit.text(body).startsWith("open http://callback.test/d/"));
        Document log = kit.log("ping");
        assertEquals(Kairon.SUCCESS, log.get("status"));
        assertEquals(List.of(), log.get("messages"));
        List<String> keys = new ArrayList<>(log.keySet());
        keys.remove("_id");
        assertEquals(List.of("user_msg", "callback_url", "callback_url_slot", "identifier", "metadata"),
                keys.subList(keys.size() - 5, keys.size()));
        assertFalse(keys.contains("exception"));
    }

    /** T-112: Python callback_action initialises metadata_log = [], so a failure before metadata logs []. */
    @Test
    void callbackFailureLogsEmptyMetadataList() {
        kit.register("ping_missing", "callback_action");
        kit.ok("ping_missing");
        Document log = kit.log("ping_missing");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertTrue(log.containsKey("metadata"));
        assertEquals(List.of(), log.get("metadata"));
    }

    /** T-112: Python schedule action initialises schedule_data_log = {}, so a failure before data logs {}. */
    @Test
    void scheduleFailureLogsEmptyDataMap() {
        kit.register("sched_missing", "schedule_action");
        kit.ok("sched_missing");
        Document log = kit.log("sched_missing");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertTrue(log.containsKey("data"));
        assertEquals(Map.of(), log.get("data"));
    }

    /** T-112: Python form_validation ActionServerLogs(...) never passes user_msg. */
    @Test
    void formValidationLogHasNoUserMsg() {
        kit.register("validate_form", "form_validation_action");
        kit.ok("validate_form", kit.slots("requested_slot", "age", "age", 10), kit.latest("ten"));
        Document log = kit.log("validate_form");
        assertEquals("form_validation_action", log.get("type"));
        assertFalse(log.containsKey("user_msg"), log.toJson());
    }

    /** T-112: Python prompt action reads media_ids only after config load, so a FAQ-gate failure logs null. */
    @Test
    void promptFaqDisabledLogsNullMediaIds() {
        kit.put("bot_settings", kit.doc("bot", kit.bot, "status", true,
                "llm_settings", kit.doc("enable_faq", false)));
        kit.register("ask_llm", "prompt_action");
        kit.ok("ask_llm", kit.slots("media_ids", List.of("m1")), kit.latest("what is kanban"));
        Document log = kit.log("ask_llm");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertTrue(log.containsKey("media_ids"));
        assertNull(log.get("media_ids"));
    }

    /** gap #1: Python CallbackData has FloatField timestamp, state=0, execution_mode="async". */
    @Test
    void callbackDataRecordMatchesPythonModelTypes() {
        kit.register("ping", "callback_action");
        kit.put("callback_action_config", kit.doc("bot", kit.bot, "name", "ping", "status", true,
                "callback_name", "hook", "dynamic_url_slot_name", "cb_url", "bot_response", "open {callback_url}"));
        kit.put("callback_config", kit.doc("bot", kit.bot, "name", "hook", "validation_secret", "secret", "expire_in", 15));
        kit.ok("ping");
        Document record = kit.catalog.all("callback_data").get(0);
        assertTrue(record.get("timestamp") instanceof Double, "timestamp must be a float epoch");
        assertEquals(0, record.get("state"));
        assertEquals("async", record.get("execution_mode"));
    }

    @Test
    void callbackFailureLogCarriesMessages() {
        kit.register("ping_missing", "callback_action");
        kit.ok("ping_missing");
        Document log = kit.log("ping_missing");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals(List.of(), log.get("messages"));
    }

    /** T-039 follow-up: email, parallel and razorpay failure mails carry slot values and the stack trace. */
    @Test
    void emailParallelRazorpayFailureMailsCarrySlotsAndStackTrace() {
        kit.register("mail_me", "email_action");
        kit.put("email_action_config", kit.doc("bot", kit.bot, "action_name", "mail_me", "status", true,
                "from_email", kit.doc("value", "missing_from", "parameter_type", "slot"),
                "to_email", kit.doc("value", List.of("a@b.test"), "parameter_type", "value"),
                "response", "sent", "dispatch_bot_response", true));
        kit.register("fan_out", "parallel_action");
        kit.put("parallel_action_config", kit.doc("bot", kit.bot, "name", "fan_out", "status", true));
        kit.register("pay", "razorpay_action");
        kit.put("razorpay_action", kit.doc("bot", kit.bot, "name", "pay", "status", true,
                "api_key", kit.param("api_key", "value", "k"), "api_secret", kit.param("api_secret", "value", "s"),
                "amount", kit.param("amount", "value", "")));
        for (String action : List.of("mail_me", "fan_out", "pay")) {
            RecordingFailureMail.CALLS.clear();
            kit.ok(action, kit.slots("order_id", "o-7"), kit.latest("help " + action));
            assertEquals(Kairon.FAIL, kit.log(action).get("status"), action);
            assertEquals(1, RecordingFailureMail.CALLS.size(), action);
            RecordingFailureMail.Call mail = RecordingFailureMail.CALLS.get(0);
            assertEquals(action, mail.action());
            assertEquals("help " + action, mail.userText());
            assertEquals("o-7", mail.slots().get("order_id"), action);
            assertTrue(mail.stackTrace().contains("\tat com.kairon.action.actions."), action + ": " + mail.stackTrace());
        }
    }

    @Test
    void pythonJsonErrorMatchesJsonDecodeErrorText() {
        assertEquals("Expecting value: line 1 column 1 (char 0)", com.kairon.action.support.ActionSupportJsonAccess.error("hello"));
        assertEquals("Expecting value: line 2 column 3 (char 3)", com.kairon.action.support.ActionSupportJsonAccess.error("\n  oops"));
        assertEquals("Extra data: line 1 column 4 (char 3)", com.kairon.action.support.ActionSupportJsonAccess.error("{} x"));
        assertEquals(null, com.kairon.action.support.ActionSupportJsonAccess.error("{\"a\": [1, 2]}"));
        assertEquals(null, com.kairon.action.support.ActionSupportJsonAccess.error("\"text\""));
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> events(Document log) {
        return (List<Map<String, Object>>) log.get("events");
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> list(Object value) {
        return (List<Map<String, Object>>) value;
    }

    @SuppressWarnings("unchecked")
    private static List<String> strings(Object value) {
        return (List<String>) value;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        return (Map<String, Object>) value;
    }

    private static List<String> keyList(Map<String, Object> map) {
        return new ArrayList<>(map.keySet());
    }
}
