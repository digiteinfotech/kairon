package com.kairon.action.support;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Function;

/** Minimal in-process HTTP stub that records every request it receives. */
final class StubServer implements AutoCloseable {

    record Captured(String method, String path, String query, Map<String, List<String>> headers, byte[] body) {
        String header(String name) {
            List<String> values = headers.get(name.toLowerCase(Locale.ROOT));
            return values == null || values.isEmpty() ? null : values.get(0);
        }

        String text() {
            return new String(body, StandardCharsets.UTF_8);
        }
    }

    record Reply(int status, Map<String, String> headers, String body) {
        static Reply json(int status, String body) {
            return new Reply(status, Map.of("Content-Type", "application/json"), body);
        }

        static Reply redirect(int status, String location) {
            return new Reply(status, Map.of("Location", location), "");
        }
    }

    private final HttpServer server;
    final List<Captured> requests = new CopyOnWriteArrayList<>();
    private final Map<String, Function<Captured, Reply>> routes = new ConcurrentHashMap<>();

    private StubServer(HttpServer server) {
        this.server = server;
        server.createContext("/", this::handle);
        server.start();
    }

    static StubServer start() throws IOException {
        return new StubServer(HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0));
    }

    StubServer on(String path, Function<Captured, Reply> handler) {
        routes.put(path, handler);
        return this;
    }

    String url(String path) {
        return "http://127.0.0.1:" + server.getAddress().getPort() + path;
    }

    List<Captured> at(String path) {
        return requests.stream().filter(request -> request.path().equals(path)).toList();
    }

    private void handle(HttpExchange exchange) throws IOException {
        Map<String, List<String>> headers = new TreeMap<>();
        exchange.getRequestHeaders().forEach((key, values) -> headers.put(key.toLowerCase(Locale.ROOT), List.copyOf(values)));
        byte[] body = exchange.getRequestBody().readAllBytes();
        Captured captured = new Captured(exchange.getRequestMethod(), exchange.getRequestURI().getRawPath(),
                exchange.getRequestURI().getRawQuery(), headers, body);
        requests.add(captured);
        Function<Captured, Reply> handler = routes.get(captured.path());
        Reply reply = handler == null ? Reply.json(404, "{\"error\": \"not found\"}") : handler.apply(captured);
        reply.headers().forEach((key, value) -> exchange.getResponseHeaders().add(key, value));
        byte[] bytes = reply.body().getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(reply.status(), bytes.length == 0 ? -1 : bytes.length);
        if (bytes.length > 0) {
            exchange.getResponseBody().write(bytes);
        }
        exchange.close();
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
