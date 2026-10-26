package com.kairon.action.server;

import io.micronaut.context.annotation.Property;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * T-035: cavekit-webhook-contract.md R4 c3-c4. Origins come from ALLOWED_ORIGIN (kairon.action.cors-origin);
 * behaviour mirrors Starlette CORSMiddleware(allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
 * wrapped by add_secure_headers, which sets Access-Control-Allow-Origin to the request Origin else the first origin.
 */
@MicronautTest
@Property(name = "kairon.action.cors-origin", value = "[\"https://a.test\", \"https://b.test\"]")
class CorsTest {

    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @Inject
    EmbeddedServer server;

    @Test
    void noOriginGetsFirstConfiguredOrigin() throws Exception {
        HttpResponse<String> response = send("GET", "/healthcheck", Map.of());
        assertEquals(200, response.statusCode());
        assertEquals(List.of("https://a.test"), response.headers().allValues("access-control-allow-origin"));
    }

    @Test
    void allowedOriginIsEchoedWithCredentials() throws Exception {
        HttpResponse<String> response = send("GET", "/healthcheck", Map.of("Origin", "https://b.test"));
        assertEquals(200, response.statusCode());
        assertEquals(List.of("https://b.test"), response.headers().allValues("access-control-allow-origin"));
        assertEquals(List.of("true"), response.headers().allValues("access-control-allow-credentials"));
        assertTrue(response.headers().firstValue("vary").orElse("").contains("Origin"));
        assertEquals(List.of("Secure"), response.headers().allValues("server"));
    }

    /** Python serves the request and add_secure_headers echoes the Origin even when it is not listed. */
    @Test
    void nonListedOriginIsServedAndEchoedLikePython() throws Exception {
        HttpResponse<String> response = send("GET", "/healthcheck", Map.of("Origin", "https://other.test"));
        assertEquals(200, response.statusCode());
        assertEquals(List.of("https://other.test"), response.headers().allValues("access-control-allow-origin"));
        assertEquals(List.of("true"), response.headers().allValues("access-control-allow-credentials"));
        assertTrue(response.headers().firstValue("vary").isEmpty());
    }

    @Test
    void preflightAllowsAllMethodsAndRequestedHeaders() throws Exception {
        HttpResponse<String> response = send("OPTIONS", "/webhook", Map.of(
                "Origin", "https://a.test",
                "Access-Control-Request-Method", "PATCH",
                "Access-Control-Request-Headers", "X-Anything, Content-Type"));
        assertEquals(200, response.statusCode());
        assertEquals("OK", response.body());
        assertEquals(List.of("https://a.test"), response.headers().allValues("access-control-allow-origin"));
        assertEquals(List.of("true"), response.headers().allValues("access-control-allow-credentials"));
        assertEquals(List.of("DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT"), response.headers().allValues("access-control-allow-methods"));
        assertEquals(List.of("X-Anything, Content-Type"), response.headers().allValues("access-control-allow-headers"));
        assertEquals(List.of("600"), response.headers().allValues("access-control-max-age"));
        assertEquals(List.of("Origin"), response.headers().allValues("vary"));
        assertEquals(List.of("same-origin"), response.headers().allValues("cross-origin-resource-policy"));
        assertTrue(response.headers().firstValue("x-kairon-request-id").isPresent());
    }

    @Test
    void preflightFromNonListedOriginIsRejected() throws Exception {
        HttpResponse<String> response = send("OPTIONS", "/webhook", Map.of(
                "Origin", "https://other.test",
                "Access-Control-Request-Method", "POST"));
        assertEquals(400, response.statusCode());
        assertEquals("Disallowed CORS origin", response.body());
        assertEquals(List.of("https://other.test"), response.headers().allValues("access-control-allow-origin"));
    }

    @Test
    void preflightWithUnknownMethodIsRejected() throws Exception {
        HttpResponse<String> response = send("OPTIONS", "/webhook", Map.of(
                "Origin", "https://b.test",
                "Access-Control-Request-Method", "TRACE"));
        assertEquals(400, response.statusCode());
        assertEquals("Disallowed CORS method", response.body());
    }

    private HttpResponse<String> send(String method, String path, Map<String, String> headers) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + server.getPort() + path))
                .method(method, HttpRequest.BodyPublishers.noBody());
        headers.forEach(builder::header);
        return CLIENT.send(builder.build(), HttpResponse.BodyHandlers.ofString());
    }
}
