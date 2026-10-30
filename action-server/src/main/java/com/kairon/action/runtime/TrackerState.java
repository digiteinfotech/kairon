package com.kairon.action.runtime;

import com.kairon.action.Kairon;
import com.kairon.action.support.Maps;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.UnaryOperator;

/**
 * Rasa tracker fields the action server reads. Defaults follow rasa_sdk Tracker.from_dict:
 * slots {}, latest_message {}, events [], paused false, followup_action null,
 * active_loop = active_loop else active_form else {}, latest_action_name null, stack [].
 */
public final class TrackerState {

    public final String senderId;
    public final Map<String, Object> slots;
    public final Map<String, Object> latestMessage;
    public final List<Map<String, Object>> events;
    /** Raw `paused` value; false when absent. */
    public final Object paused;
    public final String followupAction;
    /** Raw `active_loop`, else raw `active_form`, else an empty map. */
    public final Object activeLoop;
    public final String latestActionName;
    /** Raw `stack` value; empty list when absent. */
    public final Object stack;
    private final Map<String, Object> raw;

    private TrackerState(String senderId, Map<String, Object> source) {
        this.senderId = senderId;
        this.slots = Maps.map(source.get("slots"));
        this.latestMessage = Maps.map(source.get("latest_message"));
        this.events = Maps.mapList(source.get("events"));
        this.paused = source.containsKey("paused") ? source.get("paused") : Boolean.FALSE;
        this.followupAction = Maps.str(source.get("followup_action"));
        this.activeLoop = source.containsKey("active_loop") ? source.get("active_loop")
                : source.containsKey("active_form") ? source.get("active_form") : new LinkedHashMap<>();
        this.latestActionName = Maps.str(source.get("latest_action_name"));
        this.stack = source.containsKey("stack") ? source.get("stack") : new ArrayList<>();
        this.raw = source;
    }

    /** Sender id taken verbatim. */
    public static TrackerState from(Map<String, Object> tracker) {
        return from(tracker, UnaryOperator.identity());
    }

    /**
     * Sender id passed through {@code senderDecrypt} when it is a non-empty string. A decrypt failure
     * (not a valid Fernet token under the configured key) keeps the sender id unchanged.
     */
    public static TrackerState from(Map<String, Object> tracker, UnaryOperator<String> senderDecrypt) {
        Map<String, Object> source = tracker == null ? Map.of() : tracker;
        return new TrackerState(resolveSenderId(Maps.str(source.get("sender_id")), senderDecrypt), source);
    }

    static String resolveSenderId(String senderId, UnaryOperator<String> senderDecrypt) {
        if (senderId == null || senderId.isEmpty() || senderDecrypt == null) {
            return senderId;
        }
        try {
            String decrypted = senderDecrypt.apply(senderId);
            return decrypted == null ? senderId : decrypted;
        } catch (RuntimeException e) {
            return senderId;
        }
    }

    public Object slotValue(String name) {
        return name == null ? null : slots.get(name);
    }

    /** rasa_sdk get_intent_of_latest_message(skip_fallback_intent=false): ranking[0], null without a ranking. */
    public String intent() {
        return intent(false);
    }

    /** rasa_sdk get_intent_of_latest_message: with skipFallback, nlu_fallback yields ranking[1]. */
    public String intent(boolean skipFallback) {
        List<Object> ranking = Maps.list(latestMessage.get("intent_ranking"));
        if (ranking.isEmpty()) {
            return null;
        }
        String name = Maps.str(Maps.map(ranking.get(0)).get("name"));
        if (skipFallback && "nlu_fallback".equals(name)) {
            return ranking.size() > 1 ? Maps.str(Maps.map(ranking.get(1)).get("name")) : null;
        }
        return name;
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
