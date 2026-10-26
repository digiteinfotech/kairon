package com.kairon.action.parity;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.UnaryOperator;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Serves a fixture's recorded upstream calls from local stubs and records what the server under test called.
 * <p>
 * Every distinct {@code http://} origin in the recorded URLs gets its own stub server on an ephemeral port, so a
 * recorded URL maps to exactly one stub URL ({@link #toStub}) and back ({@link #toRecorded}). All {@code https://}
 * origins share one stub, which the port reaches through {@code kairon.action.https-stub-base}
 * ({@link #httpsBase()}); for those only path and query are checked.
 * <p>
 * An incoming request is answered with the canned reply of the first not-yet-used recorded call with the same
 * method on the same stub whose recorded path and query match (placeholder-aware). A recorded call whose mock
 * raised is answered by closing the connection without a response. Requests that match nothing get a 599 reply
 * and are reported by {@link #verify}.
 */
final class UpstreamStubs implements AutoCloseable {

    /** Request headers never compared: transport-level, client-library defaults or connection management. */
    static final Set<String> TRANSPORT_HEADERS = Set.of("host", "user-agent", "accept-encoding", "accept", "connection",
            "content-length", "transfer-encoding", "expect", "upgrade", "http2-settings", "keep-alive");

    private static final Set<String> HOP_REPLY_HEADERS = Set.of("content-length", "transfer-encoding", "connection",
            "content-encoding", "date", "server");
    private static final String HTTPS = "https";
    private static final Pattern ORIGIN = Pattern.compile("^(https?://[^/?#]+)(.*)$", Pattern.DOTALL);

    /** One request the server under test made to a stub. {@code seq} is the recorded call it consumed, or -1. */
    record Hit(String stub, String method, String path, String query, Map<String, List<String>> headers, byte[] body, int seq) {
        String header(String name) {
            List<String> values = headers.get(name.toLowerCase(Locale.ROOT));
            return values == null || values.isEmpty() ? null : values.get(0);
        }

        String pathAndQuery() {
            return query == null || query.isEmpty() ? path : path + "?" + query;
        }

        String text() {
            return new String(body, StandardCharsets.UTF_8);
        }
    }

    private final List<Fixture.UpstreamCall> calls;
    private final Map<String, HttpServer> servers = new LinkedHashMap<>();
    /** recorded origin (or "https") to stub origin. */
    private final Map<String, String> stubOrigins = new LinkedHashMap<>();
    private final boolean[] used;
    private final List<Hit> hits = new CopyOnWriteArrayList<>();

    private UpstreamStubs(List<Fixture.UpstreamCall> calls) {
        this.calls = calls.stream().sorted((a, b) -> Integer.compare(a.seq(), b.seq())).toList();
        this.used = new boolean[this.calls.size()];
    }

    /** Starts the stubs for {@code fixture.upstream()}. Always starts the shared https stub. */
    static UpstreamStubs start(Fixture fixture) {
        return start(fixture.upstream());
    }

    static UpstreamStubs start(List<Fixture.UpstreamCall> calls) {
        UpstreamStubs stubs = new UpstreamStubs(calls);
        try {
            stubs.open(HTTPS);
            for (Fixture.UpstreamCall call : stubs.calls) {
                String origin = originOf(call.request().url());
                if (origin != null && origin.startsWith("http://") && !stubs.servers.containsKey(origin)) {
                    stubs.open(origin);
                }
            }
        } catch (IOException e) {
            stubs.close();
            throw new UncheckedIOException(e);
        }
        return stubs;
    }

    private void open(String key) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> handle(key, exchange));
        server.start();
        servers.put(key, server);
        stubOrigins.put(key, "http://127.0.0.1:" + server.getAddress().getPort());
    }

    /** Base URL for {@code ActionSettings.setHttpsStubBase}. */
    String httpsBase() {
        return stubOrigins.get(HTTPS);
    }

    /** Recorded origin to stub origin for every recorded {@code http://} origin. */
    Map<String, String> httpOrigins() {
        Map<String, String> out = new LinkedHashMap<>(stubOrigins);
        out.remove(HTTPS);
        return Collections.unmodifiableMap(out);
    }

    /** Replaces every recorded http origin inside {@code text} with its stub origin (for seed documents). */
    String toStub(String text) {
        return replaceOrigins(text, httpOrigins());
    }

    /** Replaces every stub origin inside {@code text} with the recorded origin (for comparing actual output). */
    String toRecorded(String text) {
        Map<String, String> reverse = new LinkedHashMap<>();
        httpOrigins().forEach((recorded, stub) -> reverse.put(stub, recorded));
        return replaceOrigins(text, reverse);
    }

    UnaryOperator<String> seedRewrite() {
        return this::toStub;
    }

    UnaryOperator<String> outputRewrite() {
        return this::toRecorded;
    }

    List<Hit> hits() {
        return List.copyOf(hits);
    }

    private static String replaceOrigins(String text, Map<String, String> mapping) {
        if (text == null || mapping.isEmpty()) {
            return text;
        }
        List<String> keys = new ArrayList<>(mapping.keySet());
        keys.sort((a, b) -> Integer.compare(b.length(), a.length()));
        String out = text;
        for (String key : keys) {
            // An origin ends at the authority: do not rewrite http://host inside http://host:8080 or http://host.x
            out = out.replaceAll(Pattern.quote(key) + "(?![\\w:.-])", Matcher.quoteReplacement(mapping.get(key)));
        }
        return out;
    }

    static String originOf(String url) {
        Matcher m = ORIGIN.matcher(url);
        return m.matches() ? m.group(1) : null;
    }

    static String pathAndQueryOf(String url) {
        Matcher m = ORIGIN.matcher(url);
        String rest = m.matches() ? m.group(2) : url;
        int hash = rest.indexOf('#');
        if (hash >= 0) {
            rest = rest.substring(0, hash);
        }
        return rest.isEmpty() ? "/" : rest;
    }

    private String stubKeyOf(Fixture.UpstreamCall call) {
        String origin = originOf(call.request().url());
        return origin != null && origin.startsWith("http://") ? origin : HTTPS;
    }

    private void handle(String key, HttpExchange exchange) throws IOException {
        try {
            Map<String, List<String>> headers = new TreeMap<>();
            exchange.getRequestHeaders().forEach((name, values) -> headers.put(name.toLowerCase(Locale.ROOT), List.copyOf(values)));
            byte[] body = exchange.getRequestBody().readAllBytes();
            URI uri = exchange.getRequestURI();
            String method = exchange.getRequestMethod().toUpperCase(Locale.ROOT);
            String pathAndQuery = uri.getRawQuery() == null ? uri.getRawPath() : uri.getRawPath() + "?" + uri.getRawQuery();
            int seq = claim(key, method, pathAndQuery);
            if (seq < 0 && retriesDroppedCall(key, method, pathAndQuery)) {
                // The JDK client transparently retries an idempotent request whose connection was dropped; the
                // retry is transport noise, not an extra upstream call, so it is dropped again and not recorded.
                throw new DroppedConnection("retry");
            }
            hits.add(new Hit(key, method, uri.getRawPath(), uri.getRawQuery(), headers, body, seq));
            if (seq < 0) {
                reply(exchange, 599, Map.of("Content-Type", List.of("text/plain")),
                        ("no recorded upstream call for " + method + " " + pathAndQuery).getBytes(StandardCharsets.UTF_8));
                return;
            }
            Fixture.UpstreamCall call = calls.get(seq);
            if (call.response() == null) {
                // Recorded mock raised: an exception escaping the handler makes the JDK server drop the connection
                // without a status line, which the client sees as a connection error.
                throw new DroppedConnection(call.error() == null ? "error" : call.error().type());
            }
            Map<String, List<String>> replyHeaders = new LinkedHashMap<>();
            for (Fixture.Header header : call.response().headers()) {
                if (!HOP_REPLY_HEADERS.contains(header.name().toLowerCase(Locale.ROOT))) {
                    replyHeaders.computeIfAbsent(header.name(), k -> new ArrayList<>()).add(header.value());
                }
            }
            Fixture.Body canned = call.response().body();
            if ("json".equals(canned.encoding()) && Fixture.values(call.response().headers(), "content-type").isEmpty()) {
                replyHeaders.put("Content-Type", List.of("application/json"));
            }
            reply(exchange, call.response().status(), replyHeaders, encode(canned));
        } finally {
            exchange.close();
        }
    }

    /** Thrown inside the handler to abort the exchange without a response. */
    private static final class DroppedConnection extends RuntimeException {
        DroppedConnection(String message) {
            super("simulated upstream failure: " + message, null, false, false);
        }
    }

    private synchronized int claim(String key, String method, String pathAndQuery) {
        for (int i = 0; i < calls.size(); i++) {
            Fixture.UpstreamCall call = calls.get(i);
            if (used[i] || !stubKeyOf(call).equals(key) || !call.request().method().equalsIgnoreCase(method)) {
                continue;
            }
            // Scratch bindings: claiming only routes the request; verify() does the binding comparison.
            if (Placeholders.matchString(pathAndQueryOf(call.request().url()), pathAndQuery, new Placeholders.Bindings())) {
                used[i] = true;
                return i;
            }
        }
        return -1;
    }

    private synchronized boolean retriesDroppedCall(String key, String method, String pathAndQuery) {
        if (hits.isEmpty()) {
            return false;
        }
        Hit last = hits.get(hits.size() - 1);
        if (last.seq() < 0 || calls.get(last.seq()).response() != null) {
            return false;
        }
        return last.stub().equals(key) && last.method().equals(method) && last.pathAndQuery().equals(pathAndQuery);
    }

    private static void reply(HttpExchange exchange, int status, Map<String, List<String>> headers, byte[] body) throws IOException {
        headers.forEach((name, values) -> values.forEach(value -> exchange.getResponseHeaders().add(name, value)));
        boolean noBody = body.length == 0 || status == 204 || status == 304 || "HEAD".equals(exchange.getRequestMethod());
        exchange.sendResponseHeaders(status, noBody ? -1 : body.length);
        if (!noBody) {
            exchange.getResponseBody().write(body);
        }
    }

    /** Bytes of a body envelope as they go over the wire. */
    static byte[] encode(Fixture.Body body) {
        return switch (body.encoding()) {
            case "empty" -> new byte[0];
            case "text" -> body.value().textValue().getBytes(StandardCharsets.UTF_8);
            case "base64" -> Base64.getDecoder().decode(body.value().textValue());
            case "form" -> formEncode(body.value()).getBytes(StandardCharsets.UTF_8);
            default -> body.value().toString().getBytes(StandardCharsets.UTF_8);
        };
    }

    private static String formEncode(JsonNode form) {
        StringBuilder out = new StringBuilder();
        form.properties().forEach(entry -> {
            if (!out.isEmpty()) {
                out.append('&');
            }
            JsonNode value = entry.getValue();
            out.append(java.net.URLEncoder.encode(entry.getKey(), StandardCharsets.UTF_8)).append('=')
                    .append(java.net.URLEncoder.encode(value.isTextual() ? value.textValue() : value.toString(), StandardCharsets.UTF_8));
        });
        return out.toString();
    }

    /**
     * Every recorded call must have been made once with the recorded method, URL, headers of interest and body,
     * and nothing else may have been called. Headers of interest are the recorded request headers minus
     * {@link #TRANSPORT_HEADERS}; extra actual headers are ignored. {@code Content-Type} compares the media type only
     * (multipart boundaries and charset parameters differ between clients). Call order is not asserted because
     * parallel actions fan out concurrently.
     */
    List<String> verify(JsonMatcher matcher) {
        List<String> out = new ArrayList<>();
        Map<Integer, Hit> bySeq = new LinkedHashMap<>();
        for (Hit hit : hits) {
            if (hit.seq() < 0) {
                out.add("unexpected upstream call " + hit.method() + " " + describe(hit) + " body=" + abbreviate(hit.text()));
            } else {
                bySeq.put(hit.seq(), hit);
            }
        }
        for (int i = 0; i < calls.size(); i++) {
            Fixture.UpstreamCall call = calls.get(i);
            String label = "upstream[seq=" + call.seq() + "] " + call.request().method() + " " + call.request().url();
            Hit hit = bySeq.get(i);
            if (hit == null) {
                out.add(label + ": was not called");
                continue;
            }
            if (!matcher.matchesString(pathAndQueryOf(call.request().url()), hit.pathAndQuery())) {
                out.add(label + ": URL was " + describe(hit));
            }
            compareHeaders(label, call.request().headers(), hit, matcher, out);
            for (String problem : compareBody(call.request().body(), hit.body(), matcher)) {
                out.add(label + ": body " + problem);
            }
        }
        return out;
    }

    private String describe(Hit hit) {
        return HTTPS.equals(hit.stub()) ? "https://<any>" + hit.pathAndQuery() : hit.stub() + hit.pathAndQuery();
    }

    private static void compareHeaders(String label, List<Fixture.Header> recorded, Hit hit, JsonMatcher matcher, List<String> out) {
        Map<String, List<String>> expected = new LinkedHashMap<>();
        for (Fixture.Header header : recorded) {
            String name = header.name().toLowerCase(Locale.ROOT);
            if (!TRANSPORT_HEADERS.contains(name)) {
                expected.computeIfAbsent(name, k -> new ArrayList<>()).add(header.value());
            }
        }
        expected.forEach((name, values) -> {
            List<String> actual = hit.headers().getOrDefault(name, List.of());
            if ("content-type".equals(name)) {
                String want = mediaType(values.get(0));
                String got = actual.isEmpty() ? null : mediaType(actual.get(0));
                if (!want.equals(got)) {
                    out.add(label + ": header content-type expected " + values.get(0) + " but was " + actual);
                }
                return;
            }
            if (actual.size() != values.size()) {
                out.add(label + ": header " + name + " expected " + values + " but was " + actual);
                return;
            }
            for (int i = 0; i < values.size(); i++) {
                if (!matcher.matchesString(values.get(i), actual.get(i))) {
                    out.add(label + ": header " + name + " expected " + values.get(i) + " but was " + actual.get(i));
                }
            }
        });
    }

    static String mediaType(String contentType) {
        int semi = contentType.indexOf(';');
        return (semi < 0 ? contentType : contentType.substring(0, semi)).trim().toLowerCase(Locale.ROOT);
    }

    /** Compares raw bytes with a recorded body envelope (placeholder-aware for json, text and form). */
    static List<String> compareBody(Fixture.Body expected, byte[] actual, JsonMatcher matcher) {
        String text = new String(actual, StandardCharsets.UTF_8);
        switch (expected.encoding()) {
            case "empty":
                return actual.length == 0 ? List.of() : List.of("expected empty but was " + abbreviate(text));
            case "json": {
                JsonNode parsed;
                try {
                    parsed = text.isEmpty() ? null : FixtureLoader.JSON.readTree(text);
                } catch (IOException e) {
                    parsed = null;
                }
                if (parsed == null) {
                    return List.of("expected JSON " + expected.value() + " but was " + abbreviate(text));
                }
                return matcher.compare(expected.value(), parsed);
            }
            case "text":
                return matcher.matchesString(expected.value().textValue(), text)
                        ? List.of() : List.of("expected \"" + expected.value().textValue() + "\" but was \"" + abbreviate(text) + "\"");
            case "form": {
                ObjectNode want = JsonNodeFactory.instance.objectNode();
                expected.value().properties().forEach(e -> want.put(e.getKey(),
                        e.getValue().isTextual() ? e.getValue().textValue() : e.getValue().toString()));
                return matcher.compare(want, formDecode(text));
            }
            case "base64":
                return java.util.Arrays.equals(Base64.getDecoder().decode(expected.value().textValue()), actual)
                        ? List.of() : List.of("bytes differ from recorded base64");
            default:
                return List.of("unknown encoding " + expected.encoding());
        }
    }

    private static ObjectNode formDecode(String text) {
        ObjectNode out = JsonNodeFactory.instance.objectNode();
        if (text.isEmpty()) {
            return out;
        }
        for (String pair : text.split("&")) {
            int eq = pair.indexOf('=');
            String name = URLDecoder.decode(eq < 0 ? pair : pair.substring(0, eq), StandardCharsets.UTF_8);
            String value = eq < 0 ? "" : URLDecoder.decode(pair.substring(eq + 1), StandardCharsets.UTF_8);
            out.put(name, value);
        }
        return out;
    }

    private static String abbreviate(String text) {
        return text.length() > 300 ? text.substring(0, 300) + "..." : text;
    }

    @Override
    public void close() {
        servers.values().forEach(server -> server.stop(0));
    }
}
