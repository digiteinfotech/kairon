package com.kairon.action.runtime;

import com.kairon.action.Kairon;
import com.kairon.action.support.Maps;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Rasa tracker fields the action server reads. */
public final class TrackerState {

    public final String senderId;
    public final Map<String, Object> slots;
    public final Map<String, Object> latestMessage;
    public final List<Map<String, Object>> events;
    public final String followupAction;
    private final Map<String, Object> raw;

    private TrackerState(String senderId, Map<String, Object> slots, Map<String, Object> latestMessage,
                         List<Map<String, Object>> events, String followupAction, Map<String, Object> raw) {
        this.senderId = senderId;
        this.slots = slots;
        this.latestMessage = latestMessage;
        this.events = events;
        this.followupAction = followupAction;
        this.raw = raw;
    }

    public static TrackerState from(Map<String, Object> tracker) {
        Map<String, Object> source = tracker == null ? Map.of() : tracker;
        return new TrackerState(
                Maps.str(source.get("sender_id")),
                Maps.map(source.get("slots")),
                Maps.map(source.get("latest_message")),
                Maps.mapList(source.get("events")),
                Maps.str(source.get("followup_action")),
                source
        );
    }

    public Object slotValue(String name) {
        return name == null ? null : slots.get(name);
    }

    /** Rasa get_intent_of_latest_message: ranking first, then intent.name. */
    public String intent() {
        List<Object> ranking = Maps.list(latestMessage.get("intent_ranking"));
        if (!ranking.isEmpty()) {
            String name = Maps.str(Maps.map(ranking.get(0)).get("name"));
            if (name != null) {
                return name;
            }
        }
        return Maps.str(Maps.map(latestMessage.get("intent")).get("name"));
    }

    public String text() {
        return Maps.str(latestMessage.get("text"));
    }

    public String entity(String name) {
        for (Object item : Maps.list(latestMessage.get("entities"))) {
            Map<String, Object> entity = Maps.map(item);
            if (name.equals(Maps.str(entity.get("entity")))) {
                return Maps.str(entity.get("value"));
            }
        }
        return null;
    }

    public String userText() {
        String message = text();
        if (!Maps.isEmpty(message) && message.startsWith("/")) {
            String entity = entity(Kairon.USER_MSG);
            if (!Maps.isEmpty(entity)) {
                return entity;
            }
        }
        return message;
    }

    /** Latest user event input_channel, then the tracker field. */
    public String latestInputChannel() {
        String found = null;
        for (Map<String, Object> event : events) {
            if ("user".equals(event.get("event")) && event.get("input_channel") != null) {
                found = String.valueOf(event.get("input_channel"));
            }
        }
        if (found != null) {
            return found;
        }
        Object channel = raw.get("latest_input_channel");
        return channel == null ? null : String.valueOf(channel);
    }

    public List<Map<String, Object>> intentRanking() {
        return Maps.mapList(latestMessage.get("intent_ranking"));
    }

    public Map<String, Object> copySlots() {
        return new LinkedHashMap<>(slots);
    }

    public List<Map<String, Object>> copyEvents() {
        List<Map<String, Object>> copy = new ArrayList<>();
        for (Map<String, Object> event : events) {
            copy.add(new LinkedHashMap<>(event));
        }
        return copy;
    }
}
