package com.kairon.action.support;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Golden strings printed by CPython 3.12 {@code str(value)} and {@code json.dumps(value)}
 * (templating-and-secrets R7). Regenerate with a script that prints both for the same values.
 */
class PyReprTest {

    private static Map<String, Object> map(Object... pairs) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i < pairs.length; i += 2) {
            map.put((String) pairs[i], pairs[i + 1]);
        }
        return map;
    }

    private static List<Object> list(Object... items) {
        return new ArrayList<>(Arrays.asList(items));
    }

    private static void golden(Object value, String repr, String json) {
        assertEquals(repr, PyRepr.str(value));
        assertEquals(json, Jsons.pythonDumps(value));
    }

    @Test
    void disconnect() {
        golden(map("disconnect", true), "{'disconnect': True}", "{\"disconnect\": true}");
    }

    @Test
    void quoteSwitchingBoolsNoneAndNesting() {
        Object value = map("a", "it's", "b", "say \"hi\"", "c", "both ' and \"", "d", null, "e", false,
                "f", list(1, 2.5, "x"), "g", map("n", 1e16));
        golden(value,
                "{'a': \"it's\", 'b': 'say \"hi\"', 'c': 'both \\' and \"', 'd': None, 'e': False, 'f': [1, 2.5, 'x'], 'g': {'n': 1e+16}}",
                "{\"a\": \"it's\", \"b\": \"say \\\"hi\\\"\", \"c\": \"both ' and \\\"\", \"d\": null, \"e\": false, \"f\": [1, 2.5, \"x\"], \"g\": {\"n\": 1e+16}}");
    }

    @Test
    void escapesAndNonAscii() {
        Object value = list("line\nbreak\ttab\rcr", "back\\slash", "café", "smile😀", "nul\000", "del\177",
                "zw​", "ls ", "nbsp ", "bell\007", "esc\033");
        golden(value,
                "['line\\nbreak\\ttab\\rcr', 'back\\\\slash', 'café', 'smile😀', 'nul\\x00', 'del\\x7f', 'zw\\u200b', 'ls\\u2028', 'nbsp\\xa0', 'bell\\x07', 'esc\\x1b']",
                "[\"line\\nbreak\\ttab\\rcr\", \"back\\\\slash\", \"caf\\u00e9\", \"smile\\ud83d\\ude00\", \"nul\\u0000\", \"del\\u007f\", \"zw\\u200b\", \"ls\\u2028\", \"nbsp\\u00a0\", \"bell\\u0007\", \"esc\\u001b\"]");
    }

    @Test
    void floatsFormatLikePython() {
        Object value = list(1.0, 0.1, 1e16, 1e15, 123456789012345678.0, 1e-05, 0.0001, -0.0, 1.5e-07, 3.14159, 2.5e+20,
                1e22, 100.0, 1.7976931348623157e308, 5e-324, 0.30000000000000004, 1234.5678, 9999999999999998.0,
                12345678901234567890.0);
        String expected = "[1.0, 0.1, 1e+16, 1000000000000000.0, 1.2345678901234568e+17, 1e-05, 0.0001, -0.0, 1.5e-07, 3.14159, 2.5e+20, 1e+22, 100.0, 1.7976931348623157e+308, 5e-324, 0.30000000000000004, 1234.5678, 9999999999999998.0, 1.2345678901234567e+19]";
        golden(value, expected, expected);
    }

    @Test
    void nonFiniteFloats() {
        golden(list(Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY, Double.NaN),
                "[inf, -inf, nan]", "[Infinity, -Infinity, NaN]");
    }

    @Test
    void integers() {
        String expected = "[0, -7, 9007199254740993, 9223372036854775807]";
        golden(list(0, -7, 9007199254740993L, Long.MAX_VALUE), expected, expected);
    }

    @Test
    void emptyContainers() {
        Object value = map("d", map(), "l", list(), "s", "", "nested", list(list(), list(map()), list(null, true)));
        golden(value,
                "{'d': {}, 'l': [], 's': '', 'nested': [[], [{}], [None, True]]}",
                "{\"d\": {}, \"l\": [], \"s\": \"\", \"nested\": [[], [{}], [null, true]]}");
    }

    @Test
    void insertionOrderPreserved() {
        Object value = map("z", 1, "a", 2, "m", map("y", 1, "b", 2));
        golden(value, "{'z': 1, 'a': 2, 'm': {'y': 1, 'b': 2}}", "{\"z\": 1, \"a\": 2, \"m\": {\"y\": 1, \"b\": 2}}");
    }

    @Test
    void topLevelStringStrAndRepr() {
        assertEquals("plain", PyRepr.str("plain"));
        assertEquals("'plain'", PyRepr.repr("plain"));
        assertEquals("\"it's\"", PyRepr.repr("it's"));
        assertEquals("'say \"hi\"'", PyRepr.repr("say \"hi\""));
        assertEquals("'both \\' and \"'", PyRepr.repr("both ' and \""));
    }
}
