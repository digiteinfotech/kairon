package com.kairon.action.server;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.runtime.RequestIds;
import io.micronaut.core.async.publisher.Publishers;
import io.micronaut.http.HttpHeaders;
import io.micronaut.http.HttpMethod;
import io.micronaut.http.HttpRequest;
import io.micronaut.http.HttpResponse;
import io.micronaut.http.HttpStatus;
import io.micronaut.http.MutableHttpHeaders;
import io.micronaut.http.MutableHttpResponse;
import io.micronaut.http.annotation.Filter;
import io.micronaut.http.filter.HttpServerFilter;
import io.micronaut.http.filter.ServerFilterChain;
import org.reactivestreams.Publisher;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Port of kairon/actions/server.py add_secure_headers and CORSMiddleware plus kairon/shared/middleware.py RequestIdMiddleware.
 * Values match the Python `secure==0.3.0` configuration as captured in tests/integration_test/services_test.py.
 */
@Filter("/**")
public class SecurityFilter implements HttpServerFilter {

    /** Header name to value, in the order the Python middleware writes them. */
    public static final Map<String, String> SECURE_HEADERS = secureHeaders();

    /** Starlette ALL_METHODS, the expansion of allow_methods=["*"], in its order. */
    static final List<String> CORS_METHODS = List.of("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT");
    private static final String REQUEST_METHOD = "Access-Control-Request-Method";
    private static final String REQUEST_HEADERS = "Access-Control-Request-Headers";

    private final List<String> allowedOrigins;
    private final boolean allowAllOrigins;
    private final String firstAllowedOrigin;

    public SecurityFilter(ActionSettings settings) {
        this.allowedOrigins = List.copyOf(settings.corsOrigins());
        this.allowAllOrigins = allowedOrigins.contains("*");
        this.firstAllowedOrigin = allowedOrigins.isEmpty() ? "*" : allowedOrigins.get(0);
    }

    @Override
    public Publisher<MutableHttpResponse<?>> doFilter(HttpRequest<?> request, ServerFilterChain chain) {
        String requestId = RequestIds.resolve(request.getHeaders().get(Kairon.REQUEST_ID));
        request.setAttribute(RequestIds.ATTRIBUTE, requestId);
        String origin = request.getHeaders().get(HttpHeaders.ORIGIN);
        boolean preflight = origin != null && request.getMethod() == HttpMethod.OPTIONS
                && request.getHeaders().contains(REQUEST_METHOD);
        Publisher<MutableHttpResponse<?>> upstream = preflight ? Publishers.just(preflight(request, origin)) : chain.proceed(request);
        boolean hasCookie = request.getHeaders().contains(HttpHeaders.COOKIE);
        return Publishers.map(upstream, response -> {
            MutableHttpHeaders headers = response.getHeaders();
            if (origin != null && !preflight) {
                simpleCors(headers, origin, hasCookie);
            }
            SECURE_HEADERS.forEach(headers::set);
            // kairon/actions/server.py add_secure_headers overrides whatever CORSMiddleware wrote.
            headers.set(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, origin != null ? origin : firstAllowedOrigin);
            headers.set(Kairon.REQUEST_ID, requestId);
            return response;
        });
    }

    boolean allowed(String origin) {
        return allowAllOrigins || allowedOrigins.contains(origin);
    }

    /** Starlette CORSMiddleware.preflight_response with allow_credentials=True and all methods and headers. */
    private MutableHttpResponse<?> preflight(HttpRequest<?> request, String origin) {
        List<String> failures = new ArrayList<>();
        if (!allowed(origin)) {
            failures.add("origin");
        }
        if (!CORS_METHODS.contains(request.getHeaders().get(REQUEST_METHOD))) {
            failures.add("method");
        }
        MutableHttpResponse<String> response = failures.isEmpty()
                ? HttpResponse.ok("OK")
                : HttpResponse.<String>status(HttpStatus.BAD_REQUEST).body("Disallowed CORS " + String.join(", ", failures));
        response.contentType("text/plain; charset=utf-8");
        MutableHttpHeaders headers = response.getHeaders();
        headers.set(HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS, String.join(", ", CORS_METHODS));
        headers.set(HttpHeaders.ACCESS_CONTROL_MAX_AGE, "600");
        headers.set(HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true");
        headers.set(HttpHeaders.VARY, HttpHeaders.ORIGIN);
        String requestedHeaders = request.getHeaders().get(REQUEST_HEADERS);
        if (requestedHeaders != null) {
            headers.set(HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS, requestedHeaders);
        }
        return response;
    }

    /** Starlette CORSMiddleware.simple_response: credentials always, Vary when the origin is echoed explicitly. */
    private void simpleCors(MutableHttpHeaders headers, String origin, boolean hasCookie) {
        headers.set(HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true");
        if ((allowAllOrigins && hasCookie) || (!allowAllOrigins && allowedOrigins.contains(origin))) {
            String vary = headers.get(HttpHeaders.VARY);
            headers.set(HttpHeaders.VARY, vary == null || vary.isBlank() ? HttpHeaders.ORIGIN : vary + ", " + HttpHeaders.ORIGIN);
        }
    }

    private static Map<String, String> secureHeaders() {
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Server", "Secure");
        headers.put("Strict-Transport-Security", "includeSubDomains; preload; max-age=31536000");
        headers.put("X-Frame-Options", "SAMEORIGIN");
        headers.put("X-XSS-Protection", "0");
        headers.put("X-Content-Type-Options", "nosniff");
        headers.put("Content-Security-Policy", "default-src 'self'; frame-ancestors 'self'; form-action 'self'; "
                + "base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; "
                + "img-src 'self' https:; script-src 'self' https: 'unsafe-inline'");
        headers.put("Referrer-Policy", "no-referrer");
        headers.put("Cache-Control", "must-revalidate");
        headers.put("Permissions-Policy", "accelerometer=(), autoplay=(), camera=(), document-domain=(), "
                + "encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), "
                + "microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()");
        headers.put("Cross-Origin-Embedder-Policy", "require-corp");
        headers.put("Cross-Origin-Opener-Policy", "same-origin");
        headers.put("Cross-Origin-Resource-Policy", "same-origin");
        return java.util.Collections.unmodifiableMap(headers);
    }
}
