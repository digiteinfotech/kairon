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
        try {
            Document config = support.require("http_action_config", context.bot, "action_name", context.actionName,
                    "No HTTP action found for given action and bot");
            Map<String, Object> responseConfig = Maps.map(config.get("response"));
            dispatch = Maps.truthy(responseConfig.get("dispatch"));
            dispatchType = Maps.str(responseConfig.get("dispatch_type"));
            if (dispatchType == null) {
                dispatchType = "text";
            }
            Map<String, Object> trackerData = support.context(context.tracker, true, context.bot);
            ActionSupport.Prepared headers = support.prepareRequest(trackerData, config.get("headers"), context.bot);
            Map<String, Object> body;
            Object dynamic = config.get("dynamic_params");
            if (!Maps.isEmpty(dynamic)) {
                ActionSupport.PyscriptResult script = support.evaluatePyscript(String.valueOf(dynamic), trackerData);
                filled.putAll(script.slots());
                body = script.output() instanceof Map<?, ?> ? Maps.map(script.output()) : new LinkedHashMap<>();
            } else {
                body = support.prepareRequest(trackerData, config.get("params_list"), context.bot).body();
            }
            method = Maps.str(config.get("request_method"));
            url = support.prepareUrl(Maps.str(config.get("http_url")), trackerData);
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
                HttpCaller.Exchange exchange = support.http().exchange(method, url, headers.body(), body, Maps.str(config.get("content_type")));
                httpResponse = exchange.body();
                statusCode = exchange.status() == 0 ? null : exchange.status();
                responseHeaders = exchange.headers();
            }
            Map<String, Object> responseContext = new LinkedHashMap<>();
            responseContext.put("data", httpResponse);
            responseContext.put("context", trackerData);
            responseContext.put("http_status_code", statusCode);
            responseContext.put("response_headers", responseHeaders);
            botResponse = support.compose(responseConfig, responseContext);
            slotValues = support.fillSlots(config.get("set_slots"), responseContext);
        } catch (Exception e) {
            exception = e.getMessage() == null ? e.toString() : e.getMessage();
            status = Kairon.FAIL;
            if (botResponse == null) {
                botResponse = Kairon.FAILED;
            }
            support.failureMail(context, e);
        } finally {
            if (dispatch) {
                botResponse = support.utter(context.dispatcher, dispatchType, botResponse);
            }
            support.save(context, type(), status, exception, botResponse, Maps.of(
                    "url", url,
                    "request_method", method,
                    "http_status_code", statusCode,
                    "fail_reason", HttpCaller.failReason(httpResponse, statusCode == null ? 0 : statusCode)
            ));
            filled.put(Kairon.ACTION_RESPONSE, botResponse);
            filled.put("http_status_code", statusCode);
            filled.putAll(slotValues);
        }
        return filled;
    }
}
