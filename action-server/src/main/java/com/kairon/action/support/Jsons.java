package com.kairon.action.support;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class Jsons {

    public static final ObjectMapper MAPPER = new ObjectMapper()
            .setSerializationInclusion(JsonInclude.Include.ALWAYS)
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    private static final TypeReference<LinkedHashMap<String, Object>> MAP_TYPE = new TypeReference<>() {};

    private Jsons() {}

    public static String write(Object value) {
        try {
            return MAPPER.writeValueAsString(value);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    public static Map<String, Object> readMap(String json) {
        if (json == null || json.isBlank() || "null".equals(json.trim())) {
            return new LinkedHashMap<>();
        }
        try {
            return MAPPER.readValue(json, MAP_TYPE);
        } catch (Exception e) {
            throw new IllegalArgumentException("Request body is not a JSON object", e);
        }
    }

    public static Object readAny(String json) {
        try {
            return MAPPER.readValue(json, Object.class);
        } catch (Exception e) {
            return json;
        }
    }

    /**
     * Python json.dumps defaults: ", " and ": " separators, ensure_ascii, float repr
     * (NaN/Infinity allowed), insertion order.
     */
    public static String pythonDumps(Object value) {
        StringBuilder out = new StringBuilder();
        writePython(out, value);
        return out.toString();
    }

    private static void writePython(StringBuilder out, Object value) {
        if (value == null) {
            out.append("null");
        } else if (value instanceof String text) {
            out.append(quote(text));
        } else if (value instanceof Boolean || value instanceof Integer || value instanceof Long) {
            out.append(value);
        } else if (value instanceof Double || value instanceof Float) {
            out.append(pythonFloat(((Number) value).doubleValue()));
        } else if (value instanceof Number number) {
            out.append(number);
        } else if (value instanceof Map<?, ?> map) {
            out.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!first) {
                    out.append(", ");
                }
                first = false;
                out.append(quote(key(entry.getKey()))).append(": ");
                writePython(out, entry.getValue());
            }
            out.append('}');
        } else if (value instanceof Iterable<?> iterable) {
            out.append('[');
            boolean first = true;
            for (Object item : iterable) {
                if (!first) {
                    out.append(", ");
                }
                first = false;
                writePython(out, item);
            }
            out.append(']');
        } else if (value instanceof Object[] array) {
            writePython(out, java.util.Arrays.asList(array));
        } else {
            out.append(quote(String.valueOf(value)));
        }
    }

    /** json.dumps float: repr, with NaN/Infinity/-Infinity for the non-finite values. */
    private static String pythonFloat(double value) {
        if (Double.isNaN(value)) {
            return "NaN";
        }
        if (Double.isInfinite(value)) {
            return value > 0 ? "Infinity" : "-Infinity";
        }
        return PyRepr.floatRepr(value);
    }

    /** json.dumps key coercion: str as-is, True/False/None as JSON literals, floats via repr. */
    private static String key(Object key) {
        if (key == null) {
            return "null";
        }
        if (key instanceof Double || key instanceof Float) {
            return pythonFloat(((Number) key).doubleValue());
        }
        return String.valueOf(key);
    }

    public static String quote(String text) {
        StringBuilder out = new StringBuilder(text.length() + 2);
        out.append('"');
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (ch < 0x20 || ch > 0x7e) {
                        out.append(String.format("\\u%04x", (int) ch));
                    } else {
                        out.append(ch);
                    }
                }
            }
        }
        out.append('"');
        return out.toString();
    }

    public static List<Object> asList(Object value) {
        if (value instanceof List<?> list) {
            return new ArrayList<>(list);
        }
        return new ArrayList<>();
    }
}
