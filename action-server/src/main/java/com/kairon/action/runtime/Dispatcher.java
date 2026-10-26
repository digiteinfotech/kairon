package com.kairon.action.runtime;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Matches rasa_sdk CollectingDispatcher.utter_message: every key is present,
 * and both template and response receive the response name.
 */
public final class Dispatcher {

    public final List<Map<String, Object>> messages = new ArrayList<>();

    public void utterMessage(String text, String image, Map<String, Object> jsonMessage, String response,
                             String attachment, List<?> buttons, List<?> elements, Map<String, Object> kwargs) {
        String resolved = response;
        if ((resolved == null || resolved.isEmpty()) && kwargs != null && kwargs.get("template") != null) {
            resolved = String.valueOf(kwargs.get("template"));
        }
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("text", text);
        message.put("buttons", buttons == null ? List.of() : buttons);
        message.put("elements", elements == null ? List.of() : elements);
        message.put("custom", jsonMessage == null || jsonMessage.isEmpty() ? Map.of() : jsonMessage);
        message.put("template", resolved);
        message.put("response", resolved);
        message.put("image", image);
        message.put("attachment", attachment);
        if (kwargs != null) {
            message.putAll(kwargs);
        }
        messages.add(message);
    }

    public void text(String text) {
        utterMessage(text, null, null, null, null, null, null, null);
    }

    public void response(String name) {
        utterMessage(null, null, null, name, null, null, null, null);
    }

    public void custom(Map<String, Object> json) {
        utterMessage(null, null, json, null, null, null, null, null);
    }

    public void buttons(String text, List<?> buttons) {
        utterMessage(text, null, null, null, null, buttons, null, null);
    }
}
