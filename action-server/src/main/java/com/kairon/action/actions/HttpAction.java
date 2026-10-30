package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Singleton
public class HttpAction implements KaironAction {

    private final ActionSupport support;

    public HttpAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "http_action";
    }

    /**
     * Python kairon/actions/definitions/http.py execute. The log carries {@code events[]} built from the
     * response, api_call, parameter and filled_slots sub-documents (preceded by the initial slots one when
     * set_slots is configured) and {@code time_elapsed} = api call + slot fill + pyscript + compose timings.
     * Timings keep Python's units: the api call in milliseconds of the sub-second part (timedelta.microseconds
     * / 1000), pyscript evaluations in seconds; an untimed step is the int 0.
     */
    @Override
    public Map<String, Object> execute(ActionContext context) {
        Map<String, Object> filled = new LinkedHashMap<>();
        Object botResponse = null;
        Object httpResponse = null;
        Integer statusCode = null;
        Map<String, Object> slotValues = new LinkedHashMap<>();
        boolean dispatch = true;
        String dispatchType = "text";
        String status = Kairon.SUCCESS;
        String exception = null;
        String url = null;
        String method = null;
        Map<String, Object> responseLog = event("response");
        Map<String, Object> apiCallLog = event("api_call");
        Map<String, Object> parameterLog = new LinkedHashMap<>();
        Map<String, Object> initialSlots = event("slots");
        Map<String, Object> finalSlots = event("filled_slots");
        Number timeElapsed = 0;
        Number timeTakenSlots = 0;
        Number timeTakenPyscript = 0;
        Number timeTakenCompose = 0;
        try {
            Document config = support.require("http_action_config", context.bot, "action_name", context.actionName,
                    "No HTTP action found for given action and bot");
            Map<String, Object> responseConfig = Maps.map(config.get("response"));
            dispatch = Maps.truthy(responseConfig.get("dispatch"));
            dispatchType = Maps.str(responseConfig.get("dispatch_type"));
            if (dispatchType == null) {
                dispatchType = "text";
            }
            List<Map<String, Object>> setSlots = Maps.mapList(config.get("set_slots"));
            if (!setSlots.isEmpty()) {
                List<Map<String, Object>> withValues = new ArrayList<>();
                for (Map<String, Object> slot : setSlots) {
                    Map<String, Object> copy = new LinkedHashMap<>(slot);
                    copy.put("slot_value", context.tracker.slotValue(Maps.str(slot.get("name"))));
                    withValues.add(copy);
                }
                initialSlots.put("data", withValues);
            }
            responseLog.put("dispatch_bot_response", responseConfig.get("dispatch"));
            responseLog.put("dispatch_type", responseConfig.get("dispatch_type"));
            responseLog.put("data", responseConfig.get("value"));
            responseLog.put("evaluation_type", responseConfig.containsKey("evaluation_type")
                    ? responseConfig.get("evaluation_type") : "expression");
            Map<String, Object> trackerData = support.context(context.tracker, true, context.bot);
            ActionSupport.Prepared headers = support.prepareRequest(trackerData, config.get("headers"), context.bot);
            apiCallLog.put("headers", headers.log());
            Map<String, Object> body;
            Object dynamic = config.get("dynamic_params");
            if (!Maps.isEmpty(dynamic)) {
                ActionSupport.PyscriptResult script = support.evaluatePyscript(String.valueOf(dynamic), trackerData);
                filled.putAll(script.slots());
                body = script.output() instanceof Map<?, ?> ? Maps.map(script.output()) : new LinkedHashMap<>();
                timeTakenPyscript = script.elapsed();
                parameterLog.put("type", "dynamic_params");
                parameterLog.put("data", dynamic);
                parameterLog.put("response", script.output() instanceof Map<?, ?> ? body : script.output());
                parameterLog.put("slots", script.slots());
                parameterLog.put("request_params", script.log());
                parameterLog.put("time_elapsed", timeTakenPyscript);
            } else {
                ActionSupport.Prepared params = support.prepareRequest(trackerData, config.get("params_list"), context.bot);
                body = params.body();
                parameterLog.put("type", "params_list");
                parameterLog.put("request_body", body);
                parameterLog.put("request_params", params.log());
            }
            method = Maps.str(config.get("request_method"));
            url = support.prepareUrl(Maps.str(config.get("http_url")), trackerData);
            // Python body.pop: the parameter log shares the body dict, so it too loses media_ids.
            Object media = body.remove("media_ids");
            List<Object> mediaIds = new ArrayList<>();
            if (media instanceof List<?> list) {
                mediaIds.addAll(list);
            } else if (media != null && !Maps.isEmpty(media)) {
                mediaIds.add(media);
            }
            Map<String, String> responseHeaders;
            if (!mediaIds.isEmpty()) {
                httpResponse = support.http().multipart(method, url, headers.body(), body, support.media(context.bot, mediaIds));
                statusCode = 200;
                responseHeaders = Map.of("Content-Type", "application/json");
            } else {
                long start = System.nanoTime();
                HttpCaller.Exchange exchange = support.http().exchange(method, url, headers.body(), body, Maps.str(config.get("content_type")));
                long micros = (System.nanoTime() - start) / 1_000;
                httpResponse = exchange.body();
                statusCode = exchange.statusCode();
                // aiohttp sets time_elapsed and headers only once a response arrives; `time_elapsed or 0`.
                responseHeaders = exchange.transportFailed() ? null : exchange.headers();
                double millis = (micros % 1_000_000) / 1000.0;
                timeElapsed = exchange.transportFailed() || millis == 0 ? (Number) 0 : (Number) millis;
            }
            apiCallLog.put("method", method);
            apiCallLog.put("url", url);
            apiCallLog.put("payload", body);
            apiCallLog.put("response", httpResponse);
            apiCallLog.put("status_code", statusCode);
            apiCallLog.put("time_elapsed", timeElapsed);
            apiCallLog.put("response_headers", responseHeaders);
            Map<String, Object> responseContext = new LinkedHashMap<>();
            responseContext.put("data", httpResponse);
            responseContext.put("context", trackerData);
            responseContext.put("http_status_code", statusCode);
            responseContext.put("response_headers", responseHeaders);
            ActionSupport.Composed composed = support.composeLogged(responseConfig, responseContext);
            botResponse = composed.result();
            timeTakenCompose = composed.elapsed();
            responseLog.put("response", botResponse);
            responseLog.put("bot_response_log", composed.log());
            responseLog.put("time_elapsed", timeTakenCompose);
            context.succeeded(botResponse);
            ActionSupport.SlotFill slotFill = support.fillSlotsLogged(config.get("set_slots"), responseContext);
            slotValues = slotFill.values();
            timeTakenSlots = slotFill.elapsed();
            finalSlots.put("data", slotValues);
            finalSlots.put("slot_eval_log", slotFill.log());
            finalSlots.put("time_elapsed", timeTakenSlots);
        } catch (Exception e) {
            exception = e.getMessage() == null ? e.toString() : e.getMessage();
            status = Kairon.FAIL;
            apiCallLog.put("exception", exception);
            if (!Maps.truthy(botResponse)) {
                botResponse = Kairon.FAILED;
            }
            responseLog.put("exception", botResponse);
            support.failureMail(context, e);
        } finally {
            if (dispatch) {
                ActionSupport.Utterance uttered = support.utterLogged(context.dispatcher, dispatchType, botResponse);
                botResponse = uttered.botResponse();
                if (uttered.message() != null) {
                    responseLog.put("message", uttered.message());
                }
            }
            List<Object> events = new ArrayList<>();
            if (initialSlots.containsKey("data")) {
                events.add(initialSlots);
            }
            events.add(responseLog);
            events.add(apiCallLog);
            events.add(parameterLog);
            events.add(finalSlots);
            // ActionServerLogs(...) keyword order: events, url, request_method, bot_response, fail_reason,
            // exception, bot, status, user_msg, time_elapsed, http_status_code.
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("events", events);
            extra.put("url", url);
            extra.put("request_method", method);
            extra.put("fail_reason", HttpCaller.failReason(httpResponse, statusCode == null ? 0 : statusCode));
            extra.put("user_msg", context.tracker.text());
            extra.put("time_elapsed", total(timeElapsed, timeTakenSlots, timeTakenPyscript, timeTakenCompose));
            extra.put("http_status_code", statusCode);
            support.save(context, type(), status, exception, botResponse, extra);
            filled.put(Kairon.ACTION_RESPONSE, botResponse);
            filled.put("http_status_code", statusCode);
            filled.putAll(slotValues);
        }
        return filled;
    }

    private static Map<String, Object> event(String type) {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("type", type);
        return event;
    }

    /** Python sum of int/float timings: stays int 0 when every step is untimed. */
    static Number total(Number... parts) {
        boolean integral = true;
        double sum = 0;
        long whole = 0;
        for (Number part : parts) {
            if (part instanceof Integer || part instanceof Long) {
                whole += part.longValue();
            } else {
                integral = false;
            }
            sum += part.doubleValue();
        }
        return integral ? (Number) (int) whole : (Number) sum;
    }
}
