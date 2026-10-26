package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-033: outbound-clients R1 c1-c8, the swallowing exchange used by http_action and parallel children. */
class HttpCallerExchangeTest {

    private StubServer stub;
    private HttpServer slow;
    private HttpCaller caller;

    @BeforeEach
    void setUp() throws Exception {
        stub = StubServer.start();
        ActionSettings settings = new ActionSettings();
        settings.setRequestTimeout(1);
        caller = new HttpCaller(settings);
    }

    @AfterEach
    void tearDown() {
        stub.close();
        if (slow != null) {
            slow.stop(0);
        }
    }

    @Test
    void defaultTimeoutIsSixtySeconds() {
        assertEquals(60, new ActionSettings().getRequestTimeout());
    }

    /** c1: two hops of 600 ms each fit inside a per-hop 1 s timeout but not inside one 1 s wall-clock budget. */
    @Test
    void deadlineCoversAllRedirectHops() throws Exception {
        AtomicInteger hits = new AtomicInteger();
        slow = slowServer(exchange -> {
            hits.incrementAndGet();
            pause(600);
            String path = exchange.getRequestURI().getPath();
            if (path.equals("/a") || path.equals("/b")) {
                exchange.getResponseHeaders().add("Location", path.equals("/a") ? "/b" : "/c");
                exchange.sendResponseHeaders(302, -1);
            } else {
                byte[] body = "{\"ok\": true}".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                exchange.getResponseBody().write(body);
            }
            exchange.close();
        });
        long start = System.nanoTime();
        HttpCaller.Exchange exchange = caller.exchange("GET", "http://127.0.0.1:" + slow.getAddress().getPort() + "/a", Map.of(), null, "json");
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;
        assertNull(exchange.statusCode());
        assertNull(exchange.body());
        assertTrue(elapsedMs < 1500, "exchange ran " + elapsedMs + " ms, past the 1 s wall-clock budget");
        assertTrue(hits.get() <= 2, "the third hop is never reached");
    }

    /** c1: headers arrive at once but the body drips for 3 s; the budget still applies to the body. */
    @Test
    void deadlineCoversResponseBody() throws Exception {
        slow = slowServer(exchange -> {
            exchange.sendResponseHeaders(200, 0);
            try (OutputStream out = exchange.getResponseBody()) {
                for (int i = 0; i < 15; i++) {
                    out.write(' ');
                    out.flush();
                    pause(200);
                }
            } catch (Exception ignored) {
                // client gave up
            }
        });
        long start = System.nanoTime();
        HttpCaller.Exchange exchange = caller.exchange("GET", "http://127.0.0.1:" + slow.getAddress().getPort() + "/drip", Map.of(), null, "json");
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;
        assertNull(exchange.statusCode());
        assertNull(exchange.body());
        assertTrue(elapsedMs < 1500, "exchange ran " + elapsedMs + " ms, past the 1 s wall-clock budget");
    }

    /** c2. */
    @Test
    void connectionRefusedYieldsNullBodyAndNullStatus() throws Exception {
        int port;
        try (ServerSocket socket = new ServerSocket(0)) {
            port = socket.getLocalPort();
        }
        HttpCaller.Exchange exchange = caller.exchange("POST", "http://127.0.0.1:" + port + "/x", Map.of(), Map.of("a", 1), "json");
        assertNull(exchange.body());
        assertNull(exchange.statusCode());
        assertTrue(exchange.transportFailed());
        assertNull(HttpCaller.failReason(exchange.body(), exchange.status()), "null status is not a failure");
    }

    /** c4: one request per call, even for gateway errors. */
    @ParameterizedTest
    @ValueSource(ints = {500, 502, 503, 504})
    void noRetryOnServerErrors(int status) {
        stub.on("/flaky", request -> StubServer.Reply.json(status, "{\"error\": \"down\"}"));
        HttpCaller.Exchange exchange = caller.exchange("GET", stub.url("/flaky"), Map.of(), null, "json");
        assertEquals(status, exchange.statusCode());
        assertEquals(Map.of("error", "down"), exchange.body());
        assertEquals(1, stub.at("/flaky").size());
        assertNotNull(HttpCaller.failReason(exchange.body(), exchange.status()));
    }

    /** c5: OK set is exactly {200, 201, 202, 204}. */
    @Test
    void okSetIsExact() {
        for (int status : List.of(200, 201, 202, 204)) {
            assertNull(HttpCaller.failReason("x", status), String.valueOf(status));
        }
        for (int status : List.of(203, 205, 206, 299, 301, 400, 404, 500)) {
            assertEquals("Got non-200 status code:" + status + " http_response:x", HttpCaller.failReason("x", status));
        }
        stub.on("/created", request -> StubServer.Reply.json(201, "{\"id\": 1}"));
        HttpCaller.Exchange exchange = caller.exchange("POST", stub.url("/created"), Map.of(), Map.of(), "json");
        assertEquals(201, exchange.statusCode());
        assertNull(HttpCaller.failReason(exchange.body(), exchange.status()));
    }

    /** c6-c8: timestamp header on every request, all four methods, json vs form body. */
    @Test
    void methodsBodiesAndTimestamp() {
        stub.on("/m", request -> StubServer.Reply.json(200, "{}"));
        for (String method : List.of("GET", "PUT", "POST", "DELETE")) {
            HttpCaller.Exchange exchange = caller.exchange(method, stub.url("/m"), Map.of("X-Custom", "1"), Map.of("k", "v w"), "json");
            assertEquals(200, exchange.statusCode(), method);
        }
        caller.exchange("POST", stub.url("/m"), Map.of(), Map.of("k", "v w"), "data");
        List<StubServer.Captured> seen = stub.at("/m");
        assertEquals(List.of("GET", "PUT", "POST", "DELETE", "POST"), seen.stream().map(StubServer.Captured::method).toList());
        for (StubServer.Captured request : seen) {
            String stamp = request.header(Kairon.TIMESTAMP);
            assertNotNull(stamp, request.method());
            assertTrue(stamp.matches("\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}"), stamp);
        }
        assertEquals("k=v+w", seen.get(0).query());
        assertFalse(seen.get(0).headers().containsKey("content-type"));
        for (int i = 1; i <= 3; i++) {
            assertEquals("application/json", seen.get(i).header("Content-Type"));
            assertEquals(Map.of("k", "v w"), Jsons.readAny(seen.get(i).text()));
        }
        assertEquals("application/x-www-form-urlencoded", seen.get(4).header("Content-Type"));
        assertEquals("k=v+w", seen.get(4).text());
    }

    private static HttpServer slowServer(com.sun.net.httpserver.HttpHandler handler) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", handler);
        server.setExecutor(Executors.newCachedThreadPool());
        server.start();
        return server;
    }

    private static void pause(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
