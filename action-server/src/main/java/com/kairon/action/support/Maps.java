package com.kairon.action.support;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class Maps {

    private Maps() {}

    public static Map<String, Object> map(Object value) {
        Map<String, Object> out = new LinkedHashMap<>();
        if (value instanceof Map<?, ?> raw) {
            raw.forEach((key, item) -> out.put(String.valueOf(key), item));
        }
        return out;
    }

    public static List<Map<String, Object>> mapList(Object value) {
        List<Map<String, Object>> out = new ArrayList<>();
        if (value instanceof List<?> list) {
            for (Object item : list) {
                out.add(map(item));
            }
        }
        return out;
    }

    public static List<Object> list(Object value) {
        if (value instanceof List<?> list) {
            return new ArrayList<>(list);
        }
        return new ArrayList<>();
    }

    public static String str(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    public static String text(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    /** Python {@code if not value} plus blank strings. */
    public static boolean isEmpty(Object value) {
        if (value == null) {
            return true;
        }
        if (value instanceof String text) {
            return text.isBlank();
        }
        if (value instanceof Collection<?> collection) {
            return collection.isEmpty();
        }
        if (value instanceof Map<?, ?> map) {
            return map.isEmpty();
        }
        if (value instanceof Boolean flag) {
            return !flag;
        }
        if (value instanceof Number number) {
            return number.doubleValue() == 0d;
        }
        return false;
    }

    /** Python truthiness. A blank-but-non-empty string is truthy. */
    public static boolean truthy(Object value) {
        if (value == null) {
            return false;
        }
        if (value instanceof String text) {
            return !text.isEmpty();
        }
        if (value instanceof Collection<?> collection) {
            return !collection.isEmpty();
        }
        if (value instanceof Map<?, ?> map) {
            return !map.isEmpty();
        }
        if (value instanceof Boolean flag) {
            return flag;
        }
        if (value instanceof Number number) {
            return number.doubleValue() != 0d;
        }
        return true;
    }

    public static Map<String, Object> of(Object... pairs) {
        Map<String, Object> out = new LinkedHashMap<>();
        for (int i = 0; i + 1 < pairs.length; i += 2) {
            out.put(String.valueOf(pairs[i]), pairs[i + 1]);
        }
        return out;
    }
}
