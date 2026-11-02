package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.Dispatcher;
import com.kairon.action.support.Maps;
import org.bson.Document;

import java.util.LinkedHashMap;
import java.util.Map;

final class ActionFlags {

    private ActionFlags() {}

    /** Missing key defaults to true, matching dict.get(key, True). */
    static boolean enabled(Document config, String key) {
        return !config.containsKey(key) || Maps.truthy(config.get(key));
    }

    /** Python {@code config[key]}: missing key is KeyError; {@code str(KeyError('x'))} is {@code "'x'"}. */
    static Object require(Map<String, ?> config, String key) {
        if (!config.containsKey(key)) {
            throw new ActionFailure("'" + key + "'");
        }
        return config.get(key);
    }

    static Map<String, Object> response(Object value) {
        Map<String, Object> slots = new LinkedHashMap<>();
        slots.put(Kairon.ACTION_RESPONSE, value);
        return slots;
    }

    static String message(Exception exception) {
        return exception.getMessage() == null ? exception.toString() : exception.getMessage();
    }

    static void utterText(Dispatcher dispatcher, Object value) {
        dispatcher.text(value == null ? null : String.valueOf(value));
    }
}
