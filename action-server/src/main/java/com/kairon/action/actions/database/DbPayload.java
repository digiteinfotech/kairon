package com.kairon.action.actions.database;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectReader;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.TrackerState;
import com.kairon.action.support.Jsons;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;

import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;

/** Python ActionUtility.get_payload (kairon/shared/actions/utils.py): builds the database_action query payload. */
public final class DbPayload {

    public static final String PAYLOAD_SEARCH = "payload_search";
    public static final String EMBEDDING_SEARCH = "embedding_search";

    /** json.loads: whole input must be one JSON value, trailing data is an error. */
    private static final ObjectReader JSON = Jsons.MAPPER.readerFor(Object.class)
            .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    private DbPayload() {
    }

    public static Map<String, Object> build(Object spec, TrackerState tracker) {
        Map<String, Object> request = new LinkedHashMap<>();
        for (Map<String, Object> item : Maps.mapList(spec)) {
            Object value = value(item, tracker);
            if (PAYLOAD_SEARCH.equals(item.get("query_type"))) {
                request.put(PAYLOAD_SEARCH, value instanceof String text ? parse(text) : value);
            } else if (!request.containsKey(EMBEDDING_SEARCH)) {
                request.put(EMBEDDING_SEARCH, value);
            } else {
                Object current = request.get(EMBEDDING_SEARCH);
                if (!(current instanceof String text)) {
                    throw new ActionFailure("unsupported operand type(s) for +=: '" + pyType(current) + "' and 'str'");
                }
                request.put(EMBEDDING_SEARCH, text + " " + PyRepr.str(value));
            }
        }
        return request;
    }

    private static Object value(Map<String, Object> item, TrackerState tracker) {
        Object type = item.get("type");
        if ("from_slot".equals(type)) {
            return tracker.slotValue(Maps.str(item.get("value")));
        }
        if ("from_user_message".equals(type)) {
            return tracker.userText();
        }
        return item.get("value");
    }

    private static Object parse(String text) {
        try {
            return JSON.readValue(text);
        } catch (Exception e) {
            throw new ActionFailure("Error converting payload to JSON: " + text);
        }
    }

    private static String pyType(Object value) {
        if (value == null) {
            return "NoneType";
        }
        if (value instanceof Boolean) {
            return "bool";
        }
        if (value instanceof Integer || value instanceof Long || value instanceof java.math.BigInteger) {
            return "int";
        }
        if (value instanceof Number) {
            return "float";
        }
        if (value instanceof Map<?, ?>) {
            return "dict";
        }
        if (value instanceof Collection<?>) {
            return "list";
        }
        return value.getClass().getSimpleName();
    }
}
