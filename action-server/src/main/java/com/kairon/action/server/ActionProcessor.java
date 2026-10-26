package com.kairon.action.server;

import com.kairon.action.actions.ActionFactory;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.Dispatcher;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.runtime.TrackerState;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Singleton
public class ActionProcessor {

    private static final Logger LOG = LoggerFactory.getLogger(ActionProcessor.class);

    private final ActionFactory factory;
    private final ActionSupport support;

    public ActionProcessor(ActionFactory factory, ActionSupport support) {
        this.factory = factory;
        this.support = support;
    }

    /** Blank next_action returns null. Failures return 200 with empty events and any messages already uttered. */
    public Object handle(Map<String, Object> call) {
        String actionName = Maps.str(call.get("next_action"));
        if (actionName == null || actionName.isBlank()) {
            return null;
        }
        if (!call.containsKey("tracker")) {
            throw new IllegalArgumentException("tracker");
        }
        TrackerState tracker = TrackerState.from(Maps.map(call.get("tracker")));
        Dispatcher dispatcher = new Dispatcher();
        String bot = Maps.str(tracker.slotValue("bot"));
        try {
            if (Maps.isEmpty(bot) || Maps.isEmpty(actionName)) {
                throw new ActionFailure("Bot id and action name not found in slot");
            }
            KaironAction action = factory.get(bot, actionName);
            ActionContext context = new ActionContext(bot, actionName, tracker, dispatcher, Maps.map(call.get("domain")), call);
            Map<String, Object> slots = action.execute(context);
            if (slots == null) {
                slots = Map.of();
            }
            List<Object> events = new ArrayList<>();
            for (Map.Entry<String, Object> entry : slots.entrySet()) {
                Map<String, Object> event = new LinkedHashMap<>();
                event.put("event", "slot");
                event.put("timestamp", null);
                event.put("name", entry.getKey());
                event.put("value", entry.getValue());
                events.add(event);
            }
            return response(validate(events), dispatcher);
        } catch (Exception e) {
            LOG.error("action failed: {}", actionName, e);
            String message = e.getMessage() == null ? e.toString() : e.getMessage();
            support.saveProcessorFailure(tracker, actionName, message);
            support.failureMail(bot, actionName, tracker.text(), message);
            return response(List.of(), dispatcher);
        }
    }

    private static Map<String, Object> response(List<Object> events, Dispatcher dispatcher) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("events", events);
        body.put("responses", dispatcher.messages);
        return body;
    }

    private static List<Object> validate(List<Object> events) {
        List<Object> kept = new ArrayList<>();
        for (Object event : events) {
            if (event instanceof Map<?, ?> map && map.get("event") != null) {
                kept.add(event);
            }
        }
        return kept;
    }
}
