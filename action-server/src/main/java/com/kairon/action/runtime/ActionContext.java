package com.kairon.action.runtime;

import java.util.Map;

public final class ActionContext {

    public final String bot;
    public final String actionName;
    public final TrackerState tracker;
    public final Dispatcher dispatcher;
    public final Map<String, Object> domain;
    public final Map<String, Object> actionCall;

    public ActionContext(String bot, String actionName, TrackerState tracker, Dispatcher dispatcher,
                         Map<String, Object> domain, Map<String, Object> actionCall) {
        this.bot = bot;
        this.actionName = actionName;
        this.tracker = tracker;
        this.dispatcher = dispatcher;
        this.domain = domain == null ? Map.of() : domain;
        this.actionCall = actionCall == null ? Map.of() : actionCall;
    }

    public String trigger(String key, String fallback) {
        Object info = actionCall.get("trigger_info");
        if (!(info instanceof Map<?, ?> map) || map.get(key) == null) {
            return fallback;
        }
        return String.valueOf(map.get(key));
    }
}
