package com.kairon.action.server;

import io.micronaut.context.annotation.Property;
import io.micronaut.context.annotation.Requires;
import io.micronaut.http.MediaType;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.PathVariable;
import io.micronaut.http.annotation.Produces;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.zip.GZIPInputStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * T-055: cavekit-webhook-contract.md R4 c1 (X-Kairon-Request-ID echo) and c5 (gzip over 1 KB).
 * Python: register_request_id_middleware and GZipMiddleware() in kairon/actions/server.py; Starlette 0.41.3
 * GZipMiddleware defaults to minimum_size=500, compresslevel=9, mirrored by micronaut.server.netty.compression-*.
 */
@MicronautTest
@Property(name = "request-id-gzip-test", value = "true")
class RequestIdAndGzipTest {

    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @Inject
    EmbeddedServer server;

    @Test
    void suppliedRequestIdIsEchoed() throws Exception {
        HttpResponse<byte[]> response = send("/healthcheck", Map.of("X-Kairon-Request-ID", "abc"));
        assertEquals(200, response.statusCode());
        assertEquals(List.of("abc"), response.headers().allValues("x-kairon-request-id"));
    }

    @Test
    void missingRequestIdIsGeneratedAsUuid4() throws Exception {
        HttpResponse<byte[]> response = send("/healthcheck", Map.of());
        String id = response.headers().firstValue("x-kairon-request-id").orElseThrow();
        assertEquals(4, UUID.fromString(id).version());
    }

    @Test
    void bodyOverOneKbIsGzippedWhenAccepted() throws Exception {
        String expected = "x".repeat(2048);
        HttpResponse<byte[]> response = send("/gzip-probe/2048", Map.of("Accept-Encoding", "gzip",
                "X-Kairon-Request-ID", "gz-1"));
        assertEquals(200, response.statusCode());
        assertEquals(List.of("gzip"), response.headers().allValues("content-encoding"));
        assertEquals(List.of("gz-1"), response.headers().allValues("x-kairon-request-id"));
        assertTrue(response.body().length < expected.length());
        assertEquals(expected, gunzip(response.body()));
    }

    /** Starlette compresses from 500 bytes; Micronaut's default threshold (1024) would leave this plain. */
    @Test
    void bodyAtPythonMinimumSizeIsGzipped() throws Exception {
        HttpResponse<byte[]> response = send("/gzip-probe/600", Map.of("Accept-Encoding", "gzip"));
        assertEquals(List.of("gzip"), response.headers().allValues("content-encoding"));
        assertEquals("x".repeat(600), gunzip(response.body()));
    }

    @Test
    void noGzipWithoutAcceptEncodingOrBelowMinimum() throws Exception {
        HttpResponse<byte[]> plain = send("/gzip-probe/2048", Map.of());
        assertTrue(plain.headers().firstValue("content-encoding").isEmpty());
        assertEquals("x".repeat(2048), new String(plain.body(), StandardCharsets.UTF_8));

        HttpResponse<byte[]> small = send("/gzip-probe/100", Map.of("Accept-Encoding", "gzip"));
        assertTrue(small.headers().firstValue("content-encoding").isEmpty());
        assertEquals("x".repeat(100), new String(small.body(), StandardCharsets.UTF_8));
    }

    private HttpResponse<byte[]> send(String path, Map<String, String> headers) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create("http://localhost:" + server.getPort() + path)).GET();
        headers.forEach(builder::header);
        return CLIENT.send(builder.build(), HttpResponse.BodyHandlers.ofByteArray());
    }

    private static String gunzip(byte[] body) throws IOException {
        try (GZIPInputStream in = new GZIPInputStream(new ByteArrayInputStream(body))) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    /** Test-only endpoint returning a plain body of the requested size. */
    @Requires(property = "request-id-gzip-test", value = "true")
    @Controller("/gzip-probe")
    static class GzipProbeController {
        @Get("/{size}")
        @Produces(MediaType.TEXT_PLAIN)
        String body(@PathVariable int size) {
            return "x".repeat(size);
        }
    }
}
