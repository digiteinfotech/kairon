package com.kairon.action.parity;

import com.fasterxml.jackson.databind.JsonNode;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

/**
 * Placeholder-aware structural comparison of an expected (recorded) JSON tree with an actual one.
 * <ul>
 *   <li>A string that is exactly a token matches any value of that token's shape; indexed tokens bind through
 *   the shared {@link Placeholders.Bindings} so repeated indices must agree.</li>
 *   <li>A string embedding tokens (URLs, {@code Bearer {{JWT}}}) matches as a template.</li>
 *   <li>Object key order is ignored; array order is not.</li>
 *   <li>Numbers compare by value, including extended-JSON wrappers ({@code $numberInt}, {@code $numberLong},
 *   {@code $numberDouble}, {@code $numberDecimal}), so {@code 1}, {@code 1.0} and {@code {"$numberLong":"1"}}
 *   are equal.</li>
 *   <li>Optionally, named top-level keys are skipped and any pair of {@code $date} values is treated as equal.</li>
 *   <li>Optionally ({@link #ignoringVolatile()}), run-time measurements that no recording can reproduce are
 *   skipped: a field named {@code time_elapsed} at any depth whose recorded and actual values are both numbers
 *   (its presence is still asserted), and a {@code date} key of any {@code response_headers} object, whether
 *   present on either side or both (the replay stubs always send a {@code Date} header; Python mocks never do).</li>
 * </ul>
 * Mismatches are reported as {@code path: detail} strings; bindings are only kept for a comparison that passes.
 */
final class JsonMatcher {

    private final Placeholders.Bindings bindings;
    private final Set<String> ignoredTopLevel;
    private final boolean ignoreDates;
    private final boolean ignoreVolatile;

    /** Numeric duration fields, at any depth, whose values differ on every run. */
    static final String DURATION_FIELD = "time_elapsed";
    /** Object holding upstream reply headers in action logs; its {@code date} entry is volatile. */
    static final String RESPONSE_HEADERS = "response_headers";

    JsonMatcher(Placeholders.Bindings bindings) {
        this(bindings, Set.of(), false, false);
    }

    private JsonMatcher(Placeholders.Bindings bindings, Set<String> ignoredTopLevel, boolean ignoreDates,
                        boolean ignoreVolatile) {
        this.bindings = bindings;
        this.ignoredTopLevel = ignoredTopLevel;
        this.ignoreDates = ignoreDates;
        this.ignoreVolatile = ignoreVolatile;
    }

    JsonMatcher ignoringTopLevel(Set<String> keys) {
        return new JsonMatcher(bindings, Set.copyOf(keys), ignoreDates, ignoreVolatile);
    }

    JsonMatcher ignoringDates() {
        return new JsonMatcher(bindings, ignoredTopLevel, true, ignoreVolatile);
    }

    /** Skips {@code time_elapsed} numbers and {@code response_headers.date}; see the class comment. */
    JsonMatcher ignoringVolatile() {
        return new JsonMatcher(bindings, ignoredTopLevel, ignoreDates, true);
    }

    Placeholders.Bindings bindings() {
        return bindings;
    }

    /** Mismatches between expected and actual; empty when they match. Bindings change only on a full match. */
    List<String> compare(JsonNode expected, JsonNode actual) {
        Placeholders.Bindings trial = bindings.copy();
        List<String> out = new ArrayList<>();
        walk("$", expected, actual, trial, out, true);
        if (out.isEmpty()) {
            bindings.adopt(trial);
        }
        return out;
    }

    boolean matches(JsonNode expected, JsonNode actual) {
        return compare(expected, actual).isEmpty();
    }

    /** Template match of a single string (header value, URL, text body). */
    boolean matchesString(String expected, String actual) {
        return Placeholders.matchString(expected, actual, bindings);
    }

    private void walk(String path, JsonNode expected, JsonNode actual, Placeholders.Bindings b, List<String> out, boolean top) {
        if (actual == null || actual.isMissingNode()) {
            out.add(path + ": missing, expected " + expected);
            return;
        }
        if (expected.isTextual()) {
            String text = expected.textValue();
            Placeholders.Token token = Placeholders.whole(text);
            if (token != null) {
                if (!Placeholders.matchToken(token, actual, b)) {
                    out.add(path + ": " + actual + " does not satisfy " + text + bound(token, b));
                }
                return;
            }
            if (Placeholders.containsToken(text)) {
                if (!actual.isTextual() || !Placeholders.matchString(text, actual.textValue(), b)) {
                    out.add(path + ": " + actual + " does not match template \"" + text + "\"");
                }
                return;
            }
        }
        if (ignoreDates && isDate(expected) && isDate(actual)) {
            return;
        }
        BigDecimal left = number(expected);
        BigDecimal right = number(actual);
        if (left != null || right != null) {
            if (left == null || right == null || left.compareTo(right) != 0) {
                out.add(path + ": expected " + expected + " but was " + actual);
            }
            return;
        }
        if (expected.isObject()) {
            if (!actual.isObject()) {
                out.add(path + ": expected object but was " + actual);
                return;
            }
            Set<String> keys = new TreeSet<>();
            expected.fieldNames().forEachRemaining(keys::add);
            actual.fieldNames().forEachRemaining(keys::add);
            for (String key : keys) {
                if (top && ignoredTopLevel.contains(key)) {
                    continue;
                }
                String child = path + "." + key;
                JsonNode e = expected.get(key);
                JsonNode a = actual.get(key);
                if (ignoreVolatile && isVolatile(path, key, e, a)) {
                    continue;
                }
                if (e == null) {
                    out.add(child + ": unexpected field with value " + a);
                } else if (a == null) {
                    out.add(child + ": missing, expected " + e);
                } else {
                    walk(child, e, a, b, out, false);
                }
            }
            return;
        }
        if (expected.isArray()) {
            if (!actual.isArray()) {
                out.add(path + ": expected array but was " + actual);
                return;
            }
            if (expected.size() != actual.size()) {
                out.add(path + ": expected " + expected.size() + " items but was " + actual.size() + " (" + actual + ")");
                return;
            }
            Iterator<JsonNode> e = expected.elements();
            Iterator<JsonNode> a = actual.elements();
            int i = 0;
            while (e.hasNext()) {
                walk(path + "[" + i++ + "]", e.next(), a.next(), b, out, false);
            }
            return;
        }
        if (!expected.equals(actual)) {
            out.add(path + ": expected " + expected + " but was " + actual);
        }
    }

    private static boolean isVolatile(String parentPath, String key, JsonNode expected, JsonNode actual) {
        if (DURATION_FIELD.equals(key)) {
            return expected != null && actual != null && number(expected) != null && number(actual) != null;
        }
        return "date".equalsIgnoreCase(key) && parentPath.endsWith("." + RESPONSE_HEADERS);
    }

    private static String bound(Placeholders.Token token, Placeholders.Bindings b) {
        String key = token.key();
        String value = key == null ? null : b.get(key);
        return value == null ? "" : " (bound to " + value + ")";
    }

    private static boolean isDate(JsonNode node) {
        return node.isObject() && node.size() == 1 && node.has("$date");
    }

    /** The numeric value of a JSON number or of an extended-JSON numeric wrapper, else null. */
    static BigDecimal number(JsonNode node) {
        if (node.isNumber()) {
            return node.decimalValue();
        }
        JsonNode inner = unwrapNumber(node);
        if (inner == null) {
            return null;
        }
        try {
            return new BigDecimal(inner.textValue());
        } catch (NumberFormatException e) {
            return null; // NaN / Infinity: compared structurally by the caller
        }
    }

    private static final Set<String> NUMERIC_WRAPPERS = new LinkedHashSet<>(
            List.of("$numberInt", "$numberLong", "$numberDouble", "$numberDecimal"));

    static JsonNode unwrapNumber(JsonNode node) {
        if (node.isObject() && node.size() == 1) {
            String key = node.fieldNames().next();
            JsonNode inner = node.get(key);
            if (NUMERIC_WRAPPERS.contains(key) && inner.isTextual()) {
                return inner;
            }
        }
        return null;
    }
}
