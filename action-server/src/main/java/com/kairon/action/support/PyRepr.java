package com.kairon.action.support;

import java.math.BigDecimal;
import java.util.Map;

/** Python {@code str()} / {@code repr()} for the JSON-like values the action server handles. */
public final class PyRepr {

    private PyRepr() {}

    /** Python {@code str(value)}: strings are returned as-is, everything else as {@link #repr}. */
    public static String str(Object value) {
        if (value instanceof String text) {
            return text;
        }
        if (value instanceof Character ch) {
            return String.valueOf(ch);
        }
        return repr(value);
    }

    /** Python {@code repr(value)}; dict and list members are always rendered with repr. */
    public static String repr(Object value) {
        StringBuilder out = new StringBuilder();
        write(out, value);
        return out.toString();
    }

    private static void write(StringBuilder out, Object value) {
        if (value == null) {
            out.append("None");
        } else if (value instanceof Boolean flag) {
            out.append(flag ? "True" : "False");
        } else if (value instanceof CharSequence || value instanceof Character) {
            out.append(quote(String.valueOf(value)));
        } else if (value instanceof Double || value instanceof Float) {
            out.append(floatRepr(((Number) value).doubleValue()));
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
                write(out, entry.getKey());
                out.append(": ");
                write(out, entry.getValue());
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
                write(out, item);
            }
            out.append(']');
        } else if (value instanceof Object[] array) {
            write(out, java.util.Arrays.asList(array));
        } else {
            out.append(value);
        }
    }

    /** Python string repr: single quotes unless the text has {@code '} and no {@code "}. */
    public static String quote(String text) {
        char q = text.indexOf('\'') >= 0 && text.indexOf('"') < 0 ? '"' : '\'';
        StringBuilder out = new StringBuilder(text.length() + 2);
        out.append(q);
        text.codePoints().forEach(cp -> {
            if (cp == q || cp == '\\') {
                out.append('\\').appendCodePoint(cp);
            } else if (cp == '\t') {
                out.append("\\t");
            } else if (cp == '\n') {
                out.append("\\n");
            } else if (cp == '\r') {
                out.append("\\r");
            } else if (cp < 0x20 || cp == 0x7f) {
                out.append(String.format("\\x%02x", cp));
            } else if (cp < 0x7f) {
                out.appendCodePoint(cp);
            } else if (!printable(cp)) {
                if (cp <= 0xff) {
                    out.append(String.format("\\x%02x", cp));
                } else if (cp <= 0xffff) {
                    out.append(String.format("\\u%04x", cp));
                } else {
                    out.append(String.format("\\U%08x", cp));
                }
            } else {
                out.appendCodePoint(cp);
            }
        });
        out.append(q);
        return out.toString();
    }

    /** Python str.isprintable for a non-ASCII code point: not Other (C*) and not Separator (Z*). */
    private static boolean printable(int cp) {
        int type = Character.getType(cp);
        return switch (type) {
            case Character.CONTROL, Character.FORMAT, Character.SURROGATE, Character.PRIVATE_USE,
                 Character.UNASSIGNED, Character.LINE_SEPARATOR, Character.PARAGRAPH_SEPARATOR,
                 Character.SPACE_SEPARATOR -> false;
            default -> true;
        };
    }

    /** Python float repr: shortest round-trip digits, exponent form when exp &lt; -4 or &gt;= 16. */
    public static String floatRepr(double value) {
        if (Double.isNaN(value)) {
            return "nan";
        }
        if (Double.isInfinite(value)) {
            return value > 0 ? "inf" : "-inf";
        }
        if (value == 0.0) {
            return (1.0 / value) < 0 ? "-0.0" : "0.0";
        }
        // Double.toString yields the shortest round-trip digits (JDK 19+).
        BigDecimal decimal = new BigDecimal(Double.toString(Math.abs(value))).stripTrailingZeros();
        if (decimal.precision() == 2) {
            // Double.toString keeps two digits even when one round-trips (4.9E-324 vs Python 5e-324).
            BigDecimal shorter = decimal.round(new java.math.MathContext(1, java.math.RoundingMode.HALF_EVEN));
            if (shorter.doubleValue() == Math.abs(value)) {
                decimal = shorter.stripTrailingZeros();
            }
        }
        String digits = decimal.unscaledValue().toString();
        int decpt = digits.length() - decimal.scale();
        StringBuilder out = new StringBuilder();
        if (value < 0) {
            out.append('-');
        }
        if (decpt > -4 && decpt <= 16) {
            if (decpt <= 0) {
                out.append("0.").append("0".repeat(-decpt)).append(digits);
            } else if (decpt >= digits.length()) {
                out.append(digits).append("0".repeat(decpt - digits.length())).append(".0");
            } else {
                out.append(digits, 0, decpt).append('.').append(digits.substring(decpt));
            }
        } else {
            out.append(digits.charAt(0));
            if (digits.length() > 1) {
                out.append('.').append(digits.substring(1));
            }
            int exp = decpt - 1;
            out.append('e').append(exp < 0 ? '-' : '+');
            String magnitude = String.valueOf(Math.abs(exp));
            if (magnitude.length() < 2) {
                out.append('0');
            }
            out.append(magnitude);
        }
        return out.toString();
    }
}
