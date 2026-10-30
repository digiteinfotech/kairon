package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.Dispatcher;
import com.kairon.action.runtime.RequestIds;
import com.kairon.action.runtime.TrackerState;
import jakarta.inject.Inject;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Singleton
public class ActionSupport {

    private static final Logger LOG = LoggerFactory.getLogger(ActionSupport.class);
    private static final DateTimeFormatter STAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss").withZone(ZoneOffset.UTC);
    private static final Pattern KEY_VAULT = Pattern.compile("\\$\\$\\w+");
    private static final Pattern SLOT = Pattern.compile("\\$\\w+");
    private static final Pattern PLACEHOLDER = Pattern.compile("\\$\\{(.+?)}");

    private final ActionCatalog catalog;
    private final ActionSettings settings;
    private final Tokens tokens;
    private final HttpCaller http;
    private final FailureMail mail;

    public ActionSupport(ActionCatalog catalog, ActionSettings settings, Tokens tokens, HttpCaller http) {
        this(catalog, settings, tokens, http, null);
    }

    @Inject
    public ActionSupport(ActionCatalog catalog, ActionSettings settings, Tokens tokens, HttpCaller http, FailureMail mail) {
        this.catalog = catalog;
        this.settings = settings;
        this.tokens = tokens;
        this.http = http;
        this.mail = mail;
    }

    public ActionCatalog catalog() { return catalog; }
    public ActionSettings settings() { return settings; }
    public Tokens tokens() { return tokens; }
    public HttpCaller http() { return http; }

    public Document require(String collection, String bot, String field, String value, String missing) {
        return catalog.findActive(collection, bot, field, value).orElseThrow(() -> new ActionFailure(missing));
    }

    public Optional<Document> botSettings(String bot) {
        return catalog.findBotSettings(bot);
    }

    /**
     * ActionServerLogs declared fields in declaration order (kairon/shared/actions/data_objects.py).
     * mongoengine writes these first, then dynamic fields in the order they were passed, and omits None values.
     */
    public static final List<String> LOG_FIELDS = List.of(
            "type", "intent", "action", "sender", "headers", "url", "request_method", "request_params",
            "api_response", "bot_response", "exception", "messages", "bot", "timestamp", "status",
            "trigger_info", "request_id");

    public void save(ActionContext ctx, String type, String status, String exception, Object botResponse, Map<String, Object> extra) {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("type", type);
        values.put("intent", ctx.tracker.intent());
        values.put("action", ctx.actionName);
        values.put("sender", ctx.tracker.senderId);
        values.put("exception", exception);
        values.put("bot_response", logText(botResponse));
        values.put("bot", ctx.bot);
        values.put("status", status);
        values.put("user_msg", ctx.tracker.text());
        values.put("trigger_info", triggerInfo(ctx.actionCall.get("trigger_info")));
        values.put("request_id", RequestIds.get());
        if (extra != null) {
            // An extra re-supplying a base key (e.g. user_msg) takes the extra's position: mongoengine orders
            // dynamic fields by the ActionServerLogs(...) keyword order.
            extra.forEach((key, value) -> {
                values.remove(key);
                values.put(key, value);
            });
        }
        catalog.insert(Kairon.LOGS, logRecord(values));
    }

    /** Python catch-all ActionServerLogs(...) in kairon/actions/handlers/processor.py: no type, default trigger_info. */
    public void saveProcessorFailure(TrackerState tracker, String action, String exception) {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("intent", tracker.intent(true));
        values.put("action", action);
        values.put("sender", tracker.senderId);
        values.put("exception", exception);
        values.put("bot", tracker.slotValue("bot"));
        values.put("status", Kairon.FAIL);
        values.put("request_id", RequestIds.get());
        catalog.insert(Kairon.LOGS, logRecord(values));
    }

    /**
     * mongoengine to_mongo for ActionServerLogs: declared fields in {@link #LOG_FIELDS} order, then dynamic
     * fields in insertion order, None values omitted. Defaults: timestamp = now (BSON millisecond precision),
     * status = Success, trigger_info = TriggerInfo().
     */
    public static Document logRecord(Map<String, Object> values) {
        Map<String, Object> all = new LinkedHashMap<>(values);
        if (all.get("timestamp") == null) {
            all.put("timestamp", new Date());
        }
        if (all.get("status") == null) {
            all.put("status", Kairon.SUCCESS);
        }
        if (all.get("trigger_info") == null) {
            all.put("trigger_info", triggerInfo(null));
        }
        Document document = new Document();
        for (String field : LOG_FIELDS) {
            Object value = all.get(field);
            if (value != null) {
                document.put(field, value);
            }
        }
        all.forEach((key, value) -> {
            if (value != null && !LOG_FIELDS.contains(key)) {
                document.put(key, value);
            }
        });
        return document;
    }

    /**
     * TriggerInfo(**(action_call.get('trigger_info') or {})): the request values in declared order, a missing or
     * None member taking its default ("", "implicit", "").
     */
    public static Document triggerInfo(Object requested) {
        Map<?, ?> info = requested instanceof Map<?, ?> map ? map : Map.of();
        Document trigger = new Document();
        trigger.put("trigger_name", info.get("trigger_name") == null ? "" : info.get("trigger_name"));
        trigger.put("trigger_type", info.get("trigger_type") == null ? "implicit" : info.get("trigger_type"));
        trigger.put("trigger_id", info.get("trigger_id") == null ? "" : info.get("trigger_id"));
        return trigger;
    }

    /** {@code str(bot_response)} as the Python actions log it: strings as-is, dicts and lists as Python repr. */
    public static String logText(Object botResponse) {
        return botResponse == null ? null : PyRepr.str(botResponse);
    }

    /**
     * Python ActionUtility.trigger_action_failure_mail from an action's exception handler: bot, action name,
     * stack trace of {@code error}, current slot values and latest user text. Fire-and-forget.
     */
    public void failureMail(ActionContext ctx, Throwable error) {
        failureMail(ctx.bot, ctx.actionName, ctx.tracker, error);
    }

    /** trigger_action_failure_mail for the catch-all in kairon/actions/handlers/processor.py. */
    public void failureMail(String bot, String action, TrackerState tracker, Throwable error) {
        try {
            if (mail != null) {
                mail.trigger(bot, action, tracker == null ? Map.of() : tracker.copySlots(),
                        tracker == null ? null : tracker.text(), FailureMail.stackTrace(error));
            }
        } catch (Exception e) {
            LOG.error("action failure mail not triggered", e);
        }
    }

    /**
     * Legacy call shape without the tracker or exception object: slot values are unknown ({}) and the
     * exception text stands in for the stack trace. Prefer {@link #failureMail(ActionContext, Throwable)}.
     */
    public void failureMail(String bot, String action, String userText, String error) {
        try {
            if (mail != null) {
                mail.trigger(bot, action, Map.of(), userText, error);
            }
        } catch (Exception e) {
            LOG.error("action failure mail not triggered", e);
        }
    }

    /**
     * Python build_context(tracker, extract_keyvault). {@code key_vault} holds every decrypted
     * bot secret only when {@code keyVault} is requested, else an empty dict.
     */
    public Map<String, Object> context(TrackerState tracker, boolean keyVault) {
        Trail trail = messageTrail(tracker.events);
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("sender_id", tracker.senderId);
        context.put("user_message", tracker.text());
        context.put("slot", tracker.copySlots());
        context.put("intent", tracker.intent(true));
        context.put("chat_log", trail.messages());
        context.put("key_vault", keyVault ? secrets(Maps.str(tracker.slotValue("bot"))) : new LinkedHashMap<String, Object>());
        context.put("latest_message", tracker.latestMessage);
        context.put(Kairon.USER_MSG, tracker.entity(Kairon.USER_MSG));
        context.put("session_started", trail.started());
        return context;
    }

    /**
     * build_context followed by {@code tracker_data.update({'bot': bot})}, as the Python
     * http, callback, google_search and schedule actions do. {@code bot} is the last key.
     */
    public Map<String, Object> context(TrackerState tracker, boolean keyVault, String bot) {
        Map<String, Object> context = context(tracker, keyVault);
        context.put("bot", bot);
        return context;
    }

    public Object parameter(Map<String, Object> trackerData, Map<String, Object> param, String bot) {
        return parameterPair(trackerData, param, bot)[0];
    }

    public Object[] parameterPair(Map<String, Object> trackerData, Map<String, Object> param, String bot) {
        String type = Maps.str(param.get("parameter_type"));
        Object value;
        if ("sender_id".equals(type)) {
            value = trackerData.get("sender_id");
        } else if ("slot".equals(type)) {
            value = Maps.map(trackerData.get("slot")).get(Maps.str(param.get("value")));
        } else if ("user_message".equals(type)) {
            value = trackerData.get("user_message");
            if (!Maps.isEmpty(value) && String.valueOf(value).startsWith("/")) {
                Object entity = trackerData.get(Kairon.USER_MSG);
                if (!Maps.isEmpty(entity)) {
                    value = entity;
                }
            }
        } else if ("intent".equals(type)) {
            value = trackerData.get("intent");
        } else if ("chat_log".equals(type)) {
            Map<String, Object> log = new LinkedHashMap<>();
            log.put("sender_id", trackerData.get("sender_id"));
            log.put("session_started", trackerData.get("session_started"));
            log.put("conversation", trackerData.get("chat_log"));
            value = log;
        } else if ("key_vault".equals(type)) {
            value = secret(bot, Maps.str(param.get("value")), false);
        } else {
            value = param.get("value");
        }
        Object logged = value;
        if (Boolean.TRUE.equals(param.get("encrypt")) && !"chat_log".equals(type)) {
            if (!Maps.isEmpty(value) && "value".equals(type)) {
                value = decryptMaybe(String.valueOf(value));
            }
            if (!Maps.isEmpty(value)) {
                logged = mask(value);
            }
        }
        return new Object[]{value, logged};
    }

    public Prepared prepareRequest(Map<String, Object> trackerData, Object params, String bot) {
        Map<String, Object> body = new LinkedHashMap<>();
        Map<String, Object> log = new LinkedHashMap<>();
        for (Map<String, Object> param : Maps.mapList(params)) {
            Object[] pair = parameterPair(trackerData, param, bot);
            body.put(Maps.str(param.get("key")), pair[0]);
            log.put(Maps.str(param.get("key")), pair[1]);
        }
        return new Prepared(body, log);
    }

    public Prepared prepareRequestWithBot(Map<String, Object> trackerData, Object params, String bot) {
        Prepared prepared = prepareRequest(trackerData, params, bot);
        prepared.body().put("bot", bot);
        return prepared;
    }

    public Object one(Map<String, Object> trackerData, Object param, String bot) {
        if (!(param instanceof Map<?, ?>)) {
            return null;
        }
        Prepared prepared = prepareRequest(trackerData, List.of(param), bot);
        return prepared.body().get(Maps.str(Maps.map(param).get("key")));
    }

    public String prepareUrl(String url, Map<String, Object> trackerData) {
        if (url == null) {
            return "";
        }
        String user = Maps.text(trackerData.get("user_message"));
        if (!Maps.isEmpty(user) && user.startsWith("/")) {
            Object previous = trackerData.get(Kairon.USER_MSG);
            if (!Maps.isEmpty(previous)) {
                user = String.valueOf(previous);
            }
        }
        String resolved = url.replace("$SENDER_ID", Maps.text(trackerData.get("sender_id")));
        Object intent = trackerData.get("intent");
        resolved = resolved.replace("$INTENT", Maps.truthy(intent) ? String.valueOf(intent) : "");
        resolved = resolved.replace("$USER_MESSAGE", user == null ? "" : user);
        Matcher vault = KEY_VAULT.matcher(resolved);
        StringBuffer buffer = new StringBuffer();
        Map<String, Object> secrets = Maps.map(trackerData.get("key_vault"));
        while (vault.find()) {
            String name = vault.group().substring(2);
            vault.appendReplacement(buffer, Matcher.quoteReplacement(Maps.text(secrets.get(name))));
        }
        vault.appendTail(buffer);
        resolved = buffer.toString();
        Matcher slots = SLOT.matcher(resolved);
        buffer = new StringBuffer();
        Map<String, Object> slot = Maps.map(trackerData.get("slot"));
        while (slots.find()) {
            String name = slots.group().substring(1);
            slots.appendReplacement(buffer, Matcher.quoteReplacement(Maps.text(slot.get(name))));
        }
        slots.appendTail(buffer);
        return buffer.toString();
    }

    /** Port of Python Utility.get_masked_value: strategy from settings, empty kept, len <= 4 fully masked. */
    public String mask(Object value) {
        String text = String.valueOf(value);
        int keep = settings.getUnmaskedCharCount();
        if (text.isEmpty()) {
            return text;
        }
        if (text.length() <= 4) {
            return "*".repeat(text.length());
        }
        int len = text.length();
        String stars = "*".repeat(Math.max(0, len - keep));
        return switch (settings.getUnmaskedCharStrategy()) {
            case "from_left" -> text.substring(0, Math.min(keep, len)) + stars;
            case "from_right" -> stars + text.substring(Math.max(0, len - keep));
            default -> "*".repeat(len);
        };
    }

    public String decryptMaybe(String token) {
        if (token == null || !token.startsWith("gAAAA")) {
            return token;
        }
        try {
            return tokens.decrypt(token);
        } catch (RuntimeException e) {
            return token;
        }
    }

    public Map<String, Object> secrets(String bot) {
        Map<String, Object> secrets = new LinkedHashMap<>();
        for (Document document : catalog.findByBot("key_vault", bot)) {
            Object value = document.get("value");
            if (!Maps.isEmpty(value)) {
                value = decryptMaybe(String.valueOf(value));
            }
            secrets.put(Maps.str(document.get("key")), value);
        }
        return secrets;
    }

    public Object secret(String bot, String key, boolean raise) {
        for (Document document : catalog.findByBot("key_vault", bot)) {
            if (key != null && key.equals(document.get("key"))) {
                Object value = document.get("value");
                if (!Maps.isEmpty(value)) {
                    return decryptMaybe(String.valueOf(value));
                }
                return value;
            }
        }
        if (raise) {
            throw new ActionFailure("key '" + key + "' does not exists!");
        }
        return null;
    }

    public Object evaluateScript(String script, Object data) {
        if (Maps.isEmpty(settings.getEvaluatorUrl())) {
            throw new ActionFailure("Expression evaluation failed: evaluator url is not configured");
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("script", script);
        body.put("data", data);
        Object response = http.executeStrict("POST", settings.getEvaluatorUrl(), Map.of("Content-Type", "application/json"), body, "json");
        Map<String, Object> map = Maps.map(response);
        if (!Maps.truthy(map.get("success"))) {
            throw new ActionFailure("Expression evaluation failed: " + response);
        }
        return map.get("data");
    }

    /**
     * Python ActionUtility.evaluate_pyscript: output, log, slot values and elapsed seconds. Like Python, a truthy
     * {@code data["context"]} dict is updated in place with data, response_headers and http_status_code.
     */
    public PyscriptResult evaluatePyscript(String script, Map<String, Object> data) {
        long start = System.nanoTime();
        List<String> log = new ArrayList<>(List.of("evaluation_type: script", "script: " + script,
                "data: " + PyRepr.str(data), "raise_err_on_failure: True"));
        Map<String, Object> context;
        if (data.get("context") instanceof Map<?, ?> existing && !existing.isEmpty()) {
            context = mutableContext(data);
            context.put("data", data.get("data"));
            context.put("response_headers", data.get("response_headers"));
            context.put("http_status_code", data.get("http_status_code"));
        } else {
            context = data;
        }
        Map<String, Object> result = runPyscript(script, context);
        Map<String, Object> slots = filterSlots(result.get("slots"));
        Object output;
        if (Maps.truthy(result.get("bot_response"))) {
            output = result.get("bot_response");
        } else if (Maps.truthy(result.get("body"))) {
            output = result.get("body");
        } else {
            output = new LinkedHashMap<String, Object>();
        }
        if (Maps.truthy(result.get("media_ids"))) {
            if (!(output instanceof Map<?, ?> existing)) {
                // Python: output.update(...) on a non-dict raises AttributeError.
                throw new ActionFailure("'" + pyTypeName(output) + "' object has no attribute 'update'");
            }
            Map<String, Object> copy = new LinkedHashMap<>(Maps.map(existing));
            copy.put("media_ids", result.get("media_ids"));
            output = copy;
        }
        return new PyscriptResult(output, log, slots, (System.nanoTime() - start) / 1e9);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> mutableContext(Map<String, Object> data) {
        Object context = data.get("context");
        if (context instanceof LinkedHashMap<?, ?> mutable) {
            return (Map<String, Object>) mutable;
        }
        Map<String, Object> copy = new LinkedHashMap<>(Maps.map(context));
        try {
            data.put("context", copy);
        } catch (UnsupportedOperationException e) {
            // read-only caller map: evaluate on the copy only
        }
        return copy;
    }

    public Map<String, Object> runPyscript(String source, Map<String, Object> context) {
        if (Maps.isEmpty(settings.getPyscriptUrl())) {
            throw new ActionFailure("Pyscript evaluation failed: pyscript url is not configured");
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("source_code", source);
        body.put("predefined_objects", context);
        Object response = http.executeStrict("POST", settings.getPyscriptUrl(), Map.of("Content-Type", "application/json"), body, "json");
        Map<String, Object> map = Maps.map(response);
        Object code = map.get("statusCode");
        if (!(code instanceof Number number) || number.doubleValue() != 200.0) {
            throw new ActionFailure("Pyscript evaluation failed: " + response);
        }
        Object payload = map.get("body");
        if (payload instanceof String text) {
            payload = Jsons.readAny(text);
        }
        return payload instanceof Map<?, ?> ? Maps.map(payload) : Maps.of("body", payload);
    }

    private static String pyTypeName(Object value) {
        if (value instanceof String) {
            return "str";
        }
        if (value instanceof List<?>) {
            return "list";
        }
        if (value instanceof Boolean) {
            return "bool";
        }
        if (value instanceof Double || value instanceof Float) {
            return "float";
        }
        if (value instanceof Number) {
            return "int";
        }
        return value == null ? "NoneType" : "object";
    }

    public Map<String, Object> filterSlots(Object slots) {
        Map<String, Object> filtered = new LinkedHashMap<>();
        Maps.map(slots).forEach((key, value) -> {
            if (!"bot".equals(key)) {
                filtered.put(key, value);
            }
        });
        return filtered;
    }

    public Object compose(Map<String, Object> responseConfig, Map<String, Object> httpResponse) {
        return composeLogged(responseConfig, httpResponse).result();
    }

    /** Python ActionUtility.compose_response: result, evaluation log and time taken (int 0 unless a script ran). */
    public Composed composeLogged(Map<String, Object> responseConfig, Map<String, Object> httpResponse) {
        Object template = responseConfig.get("value");
        Object evaluationLog = responseConfig.containsKey("evaluation_type") ? responseConfig.get("evaluation_type") : "expression";
        String evaluation = Maps.str(responseConfig.get("evaluation_type"));
        if (evaluation == null || evaluation.isBlank()) {
            evaluation = "expression";
        }
        List<String> log = new ArrayList<>();
        if (Maps.isEmpty(template)) {
            log.add("evaluation_type: " + PyRepr.str(evaluationLog));
            log.add("data: " + PyRepr.str(httpResponse));
            log.add("Skipping evaluation as value is empty");
            return new Composed(null, log, 0);
        }
        if ("script".equals(evaluation)) {
            PyscriptResult script = evaluatePyscript(String.valueOf(template), httpResponse);
            return new Composed(script.output(), script.log(), script.elapsed());
        }
        Object status = httpResponse.get("http_status_code");
        int code = status instanceof Number number ? number.intValue() : 0;
        HttpCaller.validate(httpResponse, code);
        Object result = prepareResponse(String.valueOf(template), httpResponse);
        log.add("evaluation_type: " + PyRepr.str(evaluationLog));
        log.add("expression: " + template);
        log.add("data: " + PyRepr.str(httpResponse));
        log.add("response: " + PyRepr.str(result));
        return new Composed(result, log, 0);
    }

    public Map<String, Object> fillSlots(Object setSlots, Map<String, Object> httpResponse) {
        return fillSlotsLogged(setSlots, httpResponse).values();
    }

    /**
     * Python ActionUtility.fill_slots_from_response: slot values, slot_eval_log and the time taken of the last
     * successfully composed slot (Python overwrites it per slot).
     */
    public SlotFill fillSlotsLogged(Object setSlots, Map<String, Object> httpResponse) {
        Map<String, Object> values = new LinkedHashMap<>();
        List<String> log = new ArrayList<>(List.of("initiating slot evaluation"));
        Number timeTaken = 0;
        for (Map<String, Object> slot : Maps.mapList(setSlots)) {
            String name = Maps.str(slot.get("name"));
            Object value;
            try {
                log.add("Slot: " + name);
                Composed composed = composeLogged(slot, httpResponse);
                value = composed.result();
                timeTaken = composed.elapsed();
                log.addAll(composed.log());
            } catch (RuntimeException e) {
                LOG.error("slot evaluation failed", e);
                value = null;
                log.add("Evaluation error for " + name + ": " + (e.getMessage() == null ? e.toString() : e.getMessage()));
                log.add("Slot " + name + " eventually set to None.");
            }
            values.put(name, value);
        }
        return new SlotFill(values, log, timeTaken);
    }

    public Object prepareResponse(String template, Object httpResponse) {
        String parsed = attachResponse(template, httpResponse);
        Matcher matcher = PLACEHOLDER.matcher(parsed);
        List<String> keys = new ArrayList<>();
        while (matcher.find()) {
            keys.add(matcher.group(1));
        }
        if (keys.isEmpty()) {
            if (Maps.isEmpty(template)) {
                return httpResponse;
            }
            return parsed;
        }
        if (!(httpResponse instanceof Map<?, ?>) && !(httpResponse instanceof List<?>)) {
            throw new ActionFailure("Could not find value for keys in response");
        }
        for (String key : keys) {
            Object value = walk(httpResponse, key);
            parsed = parsed.replace("${" + key + "}", placeholder(value));
        }
        return parsed;
    }

    /** prepare_response: a dict value is rendered with json.dumps, anything else with Python str(). */
    static String placeholder(Object value) {
        if (value instanceof Map<?, ?>) {
            return Jsons.pythonDumps(value);
        }
        return PyRepr.str(value);
    }

    /**
     * Mask dict string values that equal a key-vault secret.
     * Masking follows the configured strategy via {@link #mask}.
     */
    public Object encryptSecrets(Object requestBody, Map<String, Object> trackerData) {
        if (!(requestBody instanceof Map<?, ?>)) {
            return null;
        }
        List<String> secrets = new ArrayList<>();
        for (Object value : Maps.map(trackerData.get("key_vault")).values()) {
            if (value != null) {
                secrets.add(String.valueOf(value));
            }
        }
        return maskSecrets(Maps.map(requestBody), secrets);
    }

    private Map<String, Object> maskSecrets(Map<String, Object> body, List<String> secrets) {
        Map<String, Object> masked = new LinkedHashMap<>();
        body.forEach((key, value) -> {
            if (value instanceof Map<?, ?> nested) {
                masked.put(key, maskSecrets(Maps.map(nested), secrets));
            } else if (value instanceof String text && secrets.contains(text)) {
                masked.put(key, mask(text));
            } else {
                masked.put(key, value);
            }
        });
        return masked;
    }

    public Object utter(Dispatcher dispatcher, String dispatchType, Object botResponse) {
        return utterLogged(dispatcher, dispatchType, botResponse).botResponse();
    }

    /**
     * Python ActionUtility.handle_utter_bot_response: the (possibly parsed) bot response plus the log message
     * {@code Failed to convert http response to json: <JSONDecodeError>} when a json dispatch gets non-JSON text.
     */
    public Utterance utterLogged(Dispatcher dispatcher, String dispatchType, Object botResponse) {
        if (!Maps.truthy(botResponse)) {
            return new Utterance(botResponse, null);
        }
        if ("json".equals(dispatchType)) {
            Object parsed = botResponse;
            if (botResponse instanceof String text) {
                String error = pythonJsonError(text);
                if (error != null) {
                    dispatcher.text(text);
                    return new Utterance(botResponse, "Failed to convert http response to json: " + error);
                }
                parsed = Jsons.readAny(text);
                if (parsed instanceof String) {
                    dispatcher.text(text);
                    return new Utterance(botResponse, null);
                }
            }
            if (parsed instanceof Map<?, ?> map) {
                dispatcher.custom(Maps.map(map));
            } else {
                dispatcher.text(String.valueOf(parsed));
            }
            return new Utterance(parsed, null);
        }
        if (botResponse instanceof List<?> list) {
            for (Object message : list) {
                if (message instanceof Map<?, ?> map) {
                    dispatcher.custom(Maps.map(map));
                } else {
                    dispatcher.text(String.valueOf(message));
                }
            }
        } else {
            dispatcher.text(String.valueOf(botResponse));
        }
        return new Utterance(botResponse, null);
    }

    /**
     * str(json.JSONDecodeError) for Python json.loads(text), or null when Python would parse it. Exact for
     * non-JSON text ("Expecting value") and trailing data ("Extra data"); a malformed document that starts
     * like JSON is reported as "Expecting value" at the parser's error offset (best effort).
     */
    static String pythonJsonError(String text) {
        int start = skipWhitespace(text, 0);
        if (start >= text.length()) {
            return jsonError("Expecting value", text, start);
        }
        try (com.fasterxml.jackson.core.JsonParser parser = Jsons.MAPPER.getFactory().createParser(text)) {
            int end;
            try {
                parser.nextToken();
                parser.skipChildren();
                parser.finishToken();
                end = (int) parser.currentLocation().getCharOffset();
            } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
                char first = text.charAt(start);
                if ("{[\"-0123456789tfnNI".indexOf(first) < 0) {
                    return jsonError("Expecting value", text, start);
                }
                long offset = e.getLocation() == null ? start : e.getLocation().getCharOffset();
                return jsonError("Expecting value", text, (int) Math.max(start, Math.min(offset, text.length())));
            }
            int rest = skipWhitespace(text, end);
            return rest < text.length() ? jsonError("Extra data", text, rest) : null;
        } catch (java.io.IOException e) {
            return jsonError("Expecting value", text, start);
        }
    }

    private static int skipWhitespace(String text, int from) {
        int pos = from;
        while (pos < text.length() && " \t\n\r".indexOf(text.charAt(pos)) >= 0) {
            pos++;
        }
        return pos;
    }

    private static String jsonError(String message, String text, int pos) {
        int line = 1;
        int lastNewline = -1;
        for (int i = 0; i < pos; i++) {
            if (text.charAt(i) == '\n') {
                line++;
                lastNewline = i;
            }
        }
        return message + ": line " + line + " column " + (pos - lastNewline) + " (char " + pos + ")";
    }

    public String formatSearch(List<Map<String, Object>> results) {
        StringBuilder formatted = new StringBuilder();
        for (Map<String, Object> result : results) {
            String link = "<a href = \"" + result.get("link") + "\" target=\"_blank\" >" + result.get("title") + "</a>";
            formatted.append(result.get("text")).append("\nTo know more, please visit: ").append(link).append("\n\n");
        }
        return formatted.toString().strip();
    }

    public Trail messageTrail(List<Map<String, Object>> events) {
        List<Map<String, Object>> messages = new ArrayList<>();
        String started = null;
        for (Map<String, Object> event : events) {
            if ("session_started".equals(event.get("event")) && event.get("timestamp") instanceof Number number) {
                started = STAMP.format(Instant.ofEpochMilli(Math.round(number.doubleValue() * 1000)));
            } else if ("bot".equals(event.get("event"))) {
                Map<String, Object> data = new LinkedHashMap<>();
                data.put("text", event.get("text"));
                if (event.get("data") instanceof Map<?, ?> extra) {
                    extra.forEach((key, value) -> data.put(String.valueOf(key), value));
                }
                messages.add(Map.of("bot", data));
            } else if ("user".equals(event.get("event"))) {
                messages.add(Maps.of("user", event.get("text")));
            }
        }
        return new Trail(started, messages);
    }

    public String messageTrailText(List<Map<String, Object>> events) {
        StringBuilder text = new StringBuilder();
        for (Map<String, Object> event : events) {
            Object kind = event.get("event");
            if ("user".equals(kind) || "bot".equals(kind)) {
                text.append(kind).append(": ").append(event.get("text")).append('\n');
            }
        }
        return text.toString();
    }

    /** Python prepare_email_body(chat_log, subject) with no recipient: USER_EMAIL stays as-is. */
    public String emailBody(List<Map<String, Object>> conversation, String subject) {
        return emailBody(conversation, subject, null);
    }

    /** Port of Python ActionUtility.prepare_email_body over template/emails/conversation.html. */
    public String emailBody(List<Map<String, Object>> conversation, String subject, String userEmail) {
        return EmailTemplates.conversation(conversation, subject, userEmail, Maps.text(settings.getFrontendUrl()));
    }

    public List<HttpCaller.MediaFile> media(String bot, List<Object> mediaIds) {
        List<HttpCaller.MediaFile> files = new ArrayList<>();
        for (Object mediaId : mediaIds) {
            Document found = null;
            for (Document document : catalog.findByBot("user_media_data", bot)) {
                if (String.valueOf(mediaId).equals(String.valueOf(document.get("media_id")))) {
                    found = document;
                    break;
                }
            }
            if (found == null) {
                throw new ActionFailure("One or more media files not found");
            }
            Object data = found.get("data");
            if (data == null) {
                data = found.get("bytes");
            }
            byte[] bytes;
            if (data instanceof byte[] raw) {
                bytes = raw;
            } else if (data instanceof String encoded) {
                bytes = Base64.getDecoder().decode(encoded);
            } else {
                throw new ActionFailure("One or more media files not found");
            }
            String name = Maps.text(found.get("filename"));
            if (name.isBlank()) {
                name = "file";
            }
            String type = Maps.text(found.get("content_type"));
            if (type.isBlank()) {
                type = "application/octet-stream";
            }
            files.add(new HttpCaller.MediaFile(name, type, bytes));
        }
        return files;
    }

    public Document callbackConfig(String bot, String name) {
        for (Document document : catalog.findByBot("callback_config", bot)) {
            if (name != null && name.equalsIgnoreCase(Maps.str(document.get("name")))) {
                return document;
            }
        }
        throw new ActionFailure("Callback Configuration with name '" + name + "' does not exist!");
    }

    public String callbackToken(Document config) {
        Map<String, Object> info = new LinkedHashMap<>();
        info.put("bot", config.get("bot"));
        info.put("callback_name", config.get("name"));
        Object secret = config.get("validation_secret");
        info.put("validation_secret", Maps.isEmpty(secret) ? secret : decryptMaybe(String.valueOf(secret)));
        info.put("expire_in", config.get("expire_in"));
        String token = tokens.encrypt(Jsons.pythonDumps(info));
        if (Maps.truthy(config.get("shorten_token"))) {
            // entry.token_value = token; entry.save(); return xor_encrypt_secret(entry.token_hash)
            config.put("token_value", token);
            if (config.get("_id") != null) {
                catalog.replace("callback_config", config.get("_id"), config);
            }
            Object hash = config.get("token_hash");
            if (hash == null) {
                throw new ActionFailure("'NoneType' object has no attribute 'encode'");
            }
            return shortSecret(String.valueOf(hash), settings.getAsyncCallbackAesKey(), settings.getAsyncCallbackAesIv());
        }
        return token;
    }

    /**
     * Python xor_encrypt_secret (kairon/shared/callback/data_objects.py): AES-CTR over the UTF-8 secret with
     * the hex key and hex IV (initial counter block), urlsafe base64 with the '=' padding stripped.
     */
    public static String shortSecret(String secret, String hexKey, String hexIv) {
        try {
            byte[] key = java.util.HexFormat.of().parseHex(hexKey == null ? "" : hexKey);
            byte[] iv = java.util.HexFormat.of().parseHex(hexIv == null ? "" : hexIv);
            javax.crypto.Cipher cipher = javax.crypto.Cipher.getInstance("AES/CTR/NoPadding");
            cipher.init(javax.crypto.Cipher.ENCRYPT_MODE, new javax.crypto.spec.SecretKeySpec(key, "AES"),
                    new javax.crypto.spec.IvParameterSpec(iv));
            byte[] encrypted = cipher.doFinal(secret.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(encrypted);
        } catch (java.security.GeneralSecurityException | IllegalArgumentException e) {
            throw new ActionFailure("Short callback token encryption failed: " + e.getMessage(), e);
        }
    }

    private static String attachResponse(String template, Object httpResponse) {
        Object data = httpResponse;
        if (httpResponse instanceof Map<?, ?> map && map.containsKey("data")) {
            data = map.get("data");
        }
        if (template != null && template.contains("${RESPONSE}")) {
            return template.replace("${RESPONSE}", Jsons.pythonDumps(data));
        }
        return template == null ? "" : template;
    }

    private static Object walk(Object node, String path) {
        Object current = node;
        try {
            for (String key : path.split("\\.")) {
                if (current instanceof Map<?, ?> map) {
                    if (!map.containsKey(key)) {
                        throw new IllegalStateException("'" + key + "'");
                    }
                    current = map.get(key);
                } else if (current instanceof List<?> list) {
                    current = list.get(Integer.parseInt(key));
                } else {
                    throw new IllegalStateException(key);
                }
            }
            return current;
        } catch (RuntimeException e) {
            throw new ActionFailure("Unable to retrieve value for key from HTTP response: " + e);
        }
    }

    public record Prepared(Map<String, Object> body, Map<String, Object> log) {}

    public record Trail(String started, List<Map<String, Object>> messages) {}

    public record PyscriptResult(Object output, List<String> log, Map<String, Object> slots, double elapsed) {}

    public record Composed(Object result, List<String> log, Number elapsed) {}

    public record SlotFill(Map<String, Object> values, List<String> log, Number elapsed) {}

    public record Utterance(Object botResponse, String message) {}
}
