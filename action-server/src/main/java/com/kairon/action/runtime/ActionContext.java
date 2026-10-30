package com.kairon.action.runtime;

import java.util.Map;

public final class ActionContext {

    public final String bot;
    public final String actionName;
    public final TrackerState tracker;
    public final Dispatcher dispatcher;
    public final Map<String, Object> domain;
    public final Map<String, Object> actionCall;

    private volatile boolean success;
    private volatile Object response;

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

    /**
     * Python {@code self.__is_success = True; self.__response = response}: recorded by the actions whose Python
     * class sets them (http, google_search, live_agent, agent, parallel) at the same point. A prompt_action
     * {@code action} source reads it after running a nested action; nothing else consults it.
     */
    public void succeeded(Object response) {
        this.response = response;
        this.success = true;
    }

    /** Python {@code action.is_success}: false unless this execution called {@link #succeeded}. */
    public boolean isSuccess() {
        return success;
    }

    /** Python {@code action.response}: the value passed to {@link #succeeded}, else null. */
    public Object response() {
        return response;
    }
}
