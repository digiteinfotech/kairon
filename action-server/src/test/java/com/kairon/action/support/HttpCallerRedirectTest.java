package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.runtime.ActionFailure;
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import java.io.FileInputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-017: outbound-clients R3 c1-c5, config-and-deploy R5 c2. */
class HttpCallerRedirectTest {

    private StubServer origin;
    private StubServer other;
    private HttpCaller caller;

    @BeforeEach
    void setUp() throws Exception {
        origin = StubServer.start();
        other = StubServer.start();
        ActionSettings settings = new ActionSettings();
        settings.setRequestTimeout(5);
        caller = new HttpCaller(settings);
    }

    @AfterEach
    void tearDown() {
        origin.close();
        other.close();
    }

    private void chain(int redirects) {
        for (int i = 0; i < redirects; i++) {
            String next = "/hop/" + (i + 1);
            origin.on("/hop/" + i, request -> StubServer.Reply.redirect(302, next));
        }
        origin.on("/hop/" + redirects, request -> StubServer.Reply.json(200, "{\"hops\": " + redirects + "}"));
    }

    @Test
    void followsTenRedirects() {
        chain(10);
        HttpCaller.Exchange exchange = caller.exchange("GET", origin.url("/hop/0"), Map.of(), null, "json");
        assertEquals(200, exchange.status());
        assertEquals(Map.of("hops", 10), exchange.body());
        assertEquals(11, origin.requests.size());
        assertEquals(Map.of("hops", 10), caller.executeStrict("GET", origin.url("/hop/0"), Map.of(), null, "json"));
    }

    @Test
    void eleventhRedirectFailsTheExchange() {
        chain(11);
        HttpCaller.Exchange exchange = caller.exchange("GET", origin.url("/hop/0"), Map.of(), null, "json");
        assertEquals(500, exchange.status());
        assertEquals("Failed to execute the url: Too many redirects: exceeded 10 redirects at " + origin.url("/hop/10"), exchange.error());
        assertNull(exchange.body());
        assertEquals(11, origin.requests.size(), "the 11th redirect target is never requested");
        ActionFailure failure = assertThrows(ActionFailure.class,
                () -> caller.executeStrict("GET", origin.url("/hop/0"), Map.of(), null, "json"));
        assertTrue(failure.getMessage().startsWith("Failed to execute the url: Too many redirects"), failure.getMessage());
    }

    @ParameterizedTest
    @ValueSource(ints = {301, 302, 303})
    void postRedirectBecomesBodilessGet(int status) {
        origin.on("/start", request -> StubServer.Reply.redirect(status, "/landing"));
        origin.on("/landing", request -> StubServer.Reply.json(200, "{\"ok\": true}"));
        HttpCaller.Exchange exchange = caller.exchange("POST", origin.url("/start"), Map.of(), Map.of("a", 1), "json");
        assertEquals(200, exchange.status());
        StubServer.Captured first = origin.at("/start").get(0);
        assertEquals("POST", first.method());
        assertEquals("{\"a\":1}", first.text());
        StubServer.Captured landing = origin.at("/landing").get(0);
        assertEquals("GET", landing.method());
        assertEquals(0, landing.body().length);
        assertNull(landing.header("Content-Type"));
    }

    @ParameterizedTest
    @ValueSource(ints = {307, 308})
    void temporaryAndPermanentRedirectKeepMethodAndBody(int status) {
        origin.on("/start", request -> StubServer.Reply.redirect(status, "/landing"));
        origin.on("/landing", request -> StubServer.Reply.json(200, "{\"ok\": true}"));
        Object body = caller.executeStrict("PUT", origin.url("/start"), Map.of(), Map.of("a", "b c"), "data");
        assertEquals(Map.of("ok", true), body);
        StubServer.Captured landing = origin.at("/landing").get(0);
        assertEquals("PUT", landing.method());
        assertEquals("a=b+c", landing.text());
        assertEquals("application/x-www-form-urlencoded", landing.header("Content-Type"));
    }

    @Test
    void credentialsAreNotSentToAnotherOrigin() {
        other.on("/landing", request -> StubServer.Reply.json(200, "{\"ok\": true}"));
        origin.on("/start", request -> StubServer.Reply.redirect(302, other.url("/landing")));
        Map<String, Object> headers = new LinkedHashMap<>();
        headers.put("Authorization", "Bearer secret");
        headers.put("Cookie", "session=abc");
        headers.put("Proxy-Authorization", "Basic xyz");
        headers.put("X-Custom", "kept");
        HttpCaller.Exchange exchange = caller.exchange("GET", origin.url("/start"), headers, null, "json");
        assertEquals(200, exchange.status());
        StubServer.Captured start = origin.at("/start").get(0);
        assertEquals("Bearer secret", start.header("Authorization"));
        assertEquals("session=abc", start.header("Cookie"));
        // java.net.http never sends Proxy-Authorization to an origin server, so it is absent even before the redirect;
        // HttpCaller strips it as well so the guarantee does not depend on the JDK.
        StubServer.Captured landing = other.at("/landing").get(0);
        assertNull(landing.header("Authorization"));
        assertNull(landing.header("Cookie"));
        assertNull(landing.header("Proxy-Authorization"));
        assertEquals("kept", landing.header("X-Custom"));
        assertNotNull(landing.header("X-TimeStamp"));
    }

    @Test
    void credentialsAreKeptOnSameOriginRedirect() {
        origin.on("/start", request -> StubServer.Reply.redirect(307, "/landing"));
        origin.on("/landing", request -> StubServer.Reply.json(200, "{}"));
        caller.executeStrict("POST", origin.url("/start"), Map.of("Authorization", "Bearer secret"), Map.of(), "json");
        assertEquals("Bearer secret", origin.at("/landing").get(0).header("Authorization"));
    }

    @Test
    void sameOriginComparesSchemeHostAndPort() {
        assertTrue(HttpCaller.sameOrigin("http://a.test/x", "http://A.test:80/y"));
        assertTrue(HttpCaller.sameOrigin("https://a.test/x", "https://a.test:443/y"));
        assertEquals(false, HttpCaller.sameOrigin("http://a.test/x", "https://a.test/x"));
        assertEquals(false, HttpCaller.sameOrigin("http://a.test/x", "http://b.test/x"));
        assertEquals(false, HttpCaller.sameOrigin("http://a.test:8080/x", "http://a.test:8081/x"));
    }

    @Test
    void invalidTlsCertificateFailsTheExchange(@TempDir Path dir) throws Exception {
        Path store = dir.resolve("self-signed.p12");
        Process keytool = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "keytool").toString(),
                "-genkeypair", "-alias", "stub", "-keyalg", "RSA", "-keysize", "2048", "-validity", "1",
                "-dname", "CN=127.0.0.1", "-storetype", "PKCS12", "-keystore", store.toString(),
                "-storepass", "changeit", "-keypass", "changeit")
                .redirectErrorStream(true).start();
        assertEquals(0, keytool.waitFor(), new String(keytool.getInputStream().readAllBytes(), StandardCharsets.UTF_8));
        KeyStore keys = KeyStore.getInstance("PKCS12");
        try (FileInputStream in = new FileInputStream(store.toFile())) {
            keys.load(in, "changeit".toCharArray());
        }
        KeyManagerFactory factory = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        factory.init(keys, "changeit".toCharArray());
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(factory.getKeyManagers(), null, null);
        HttpsServer server = HttpsServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.setHttpsConfigurator(new HttpsConfigurator(context));
        int[] hits = {0};
        server.createContext("/", exchange -> {
            hits[0]++;
            exchange.sendResponseHeaders(200, -1);
            exchange.close();
        });
        server.start();
        try {
            String url = "https://127.0.0.1:" + server.getAddress().getPort() + "/secure";
            HttpCaller.Exchange exchange = caller.exchange("GET", url, Map.of(), null, "json");
            assertEquals(503, exchange.status());
            assertEquals("Failed to connect to service: 127.0.0.1", exchange.error());
            ActionFailure failure = assertThrows(ActionFailure.class, () -> caller.executeStrict("GET", url, Map.of(), null, "json"));
            assertTrue(failure.getMessage().startsWith("Failed to execute the url:"), failure.getMessage());
            assertEquals(0, hits[0], "no request is served over an untrusted certificate");
        } finally {
            server.stop(0);
        }
    }
}
