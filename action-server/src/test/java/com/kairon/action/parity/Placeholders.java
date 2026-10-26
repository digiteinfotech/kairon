package com.kairon.action.parity;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Placeholder tokens of fixture-schema.md ({@code {{TIMESTAMP}}}, {@code {{UUID:1}}}, ...) and the per-fixture
 * {@link Bindings} that make indexed tokens consistent: the first value matched by {@code {{UUID:1}}} is what every
 * other {@code {{UUID:1}}} in the same fixture must match, and two different indices of one kind may not bind the
 * same value.
 */
final class Placeholders {

    static final Pattern TOKEN = Pattern.compile(
            "\\{\\{(TIMESTAMP|DATETIME|EPOCH|OBJECT_ID|UUID_HEX|UUID|JWT|REQUEST_ID)(?::([0-9]+))?}}");

    private static final Map<String, String> SHAPES = Map.of(
            "DATETIME", "\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}(?::\\d{2}(?:\\.\\d+)?)?(?:Z|[+-]\\d{2}:?\\d{2})?",
            "EPOCH", "\\d+(?:\\.\\d+)?",
            "OBJECT_ID", "[0-9a-fA-F]{24}",
            "UUID", "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            "UUID_HEX", "[0-9a-fA-F]{32}",
            "JWT", "[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]*",
            "REQUEST_ID", ".+?",
            "TIMESTAMP", ".+?");

    private Placeholders() {
    }

    /** A token occurrence: kind (e.g. UUID) and index, or null index for unindexed tokens. */
    record Token(String kind, String index) {
        String key() {
            return index == null ? null : kind + ":" + index;
        }
    }

    static boolean containsToken(String text) {
        return text != null && TOKEN.matcher(text).find();
    }

    /** The token when {@code text} is exactly one token, else null. */
    static Token whole(String text) {
        if (text == null) {
            return null;
        }
        Matcher m = TOKEN.matcher(text);
        return m.matches() ? new Token(m.group(1), m.group(2)) : null;
    }

    /**
     * Matches {@code actual} against an expected string that may embed tokens (for example a URL ending in
     * {@code /dispatch/{{UUID_HEX:1}}} or {@code Bearer {{JWT}}}). Binds indexed tokens on success only.
     */
    static boolean matchString(String expected, String actual, Bindings bindings) {
        if (actual == null) {
            return false;
        }
        if (!containsToken(expected)) {
            return expected.equals(actual);
        }
        List<Token> tokens = new ArrayList<>();
        StringBuilder regex = new StringBuilder();
        Matcher m = TOKEN.matcher(expected);
        int last = 0;
        while (m.find()) {
            regex.append(Pattern.quote(expected.substring(last, m.start())));
            regex.append('(').append(SHAPES.get(m.group(1))).append(')');
            tokens.add(new Token(m.group(1), m.group(2)));
            last = m.end();
        }
        regex.append(Pattern.quote(expected.substring(last)));
        Matcher actualMatch = Pattern.compile(regex.toString(), Pattern.DOTALL).matcher(actual);
        if (!actualMatch.matches()) {
            return false;
        }
        Bindings trial = bindings.copy();
        for (int i = 0; i < tokens.size(); i++) {
            if (!trial.bind(tokens.get(i), actualMatch.group(i + 1))) {
                return false;
            }
        }
        bindings.adopt(trial);
        return true;
    }

    /**
     * Matches a whole-value token against any JSON value. BSON-shaped values are accepted where the token stands
     * for them: {@code {{TIMESTAMP}}} matches a {@code $date} object, an ISO string or a number;
     * {@code {{OBJECT_ID:n}}} matches {@code {"$oid": hex}} or a 24-hex string; {@code {{EPOCH}}} matches a
     * number, numeric string or numeric extended-JSON wrapper.
     */
    static boolean matchToken(Token token, JsonNode actual, Bindings bindings) {
        if (actual == null || actual.isNull() || actual.isMissingNode()) {
            return false;
        }
        switch (token.kind()) {
            case "TIMESTAMP":
                return actual.isObject() && actual.has("$date") || actual.isTextual() && !actual.textValue().isEmpty()
                        || actual.isNumber();
            case "EPOCH":
                if (actual.isNumber()) {
                    return true;
                }
                JsonNode number = JsonMatcher.unwrapNumber(actual);
                if (number != null) {
                    return true;
                }
                break;
            case "OBJECT_ID":
                if (actual.isObject() && actual.size() == 1 && actual.get("$oid") != null && actual.get("$oid").isTextual()) {
                    return bindWhole(token, actual.get("$oid").textValue(), bindings);
                }
                break;
            default:
                break;
        }
        if (!actual.isTextual()) {
            return false;
        }
        return bindWhole(token, actual.textValue(), bindings);
    }

    private static boolean bindWhole(Token token, String value, Bindings bindings) {
        if (!Pattern.compile(SHAPES.get(token.kind()), Pattern.DOTALL).matcher(value).matches()) {
            return false;
        }
        Bindings trial = bindings.copy();
        if (!trial.bind(token, value)) {
            return false;
        }
        bindings.adopt(trial);
        return true;
    }

    /** Index-to-value map shared by every comparison of one fixture replay. */
    static final class Bindings {
        private final Map<String, String> byKey = new HashMap<>();
        private final Map<String, String> byValue = new HashMap<>();

        boolean bind(Token token, String value) {
            String key = token.key();
            if (key == null) {
                return true;
            }
            String bound = byKey.get(key);
            if (bound != null) {
                return bound.equals(value);
            }
            String kindValue = token.kind() + "=" + value;
            String owner = byValue.get(kindValue);
            if (owner != null && !owner.equals(key)) {
                return false;
            }
            byKey.put(key, value);
            byValue.put(kindValue, key);
            return true;
        }

        String get(String key) {
            return byKey.get(key);
        }

        Map<String, String> asMap() {
            return Map.copyOf(byKey);
        }

        Bindings copy() {
            Bindings copy = new Bindings();
            copy.byKey.putAll(byKey);
            copy.byValue.putAll(byValue);
            return copy;
        }

        void adopt(Bindings other) {
            byKey.clear();
            byKey.putAll(other.byKey);
            byValue.clear();
            byValue.putAll(other.byValue);
        }
    }
}
