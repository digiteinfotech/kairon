package com.kairon.action.server;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.RequestIds;
import io.micronaut.context.env.Environment;
import io.micronaut.core.async.publisher.Publishers;
import io.micronaut.core.type.Argument;
import io.micronaut.http.HttpHeaders;
import io.micronaut.http.HttpRequest;
import io.micronaut.http.MutableHttpHeaders;
import io.micronaut.http.MutableHttpResponse;
import io.micronaut.http.annotation.Filter;
import io.micronaut.http.filter.HttpServerFilter;
import io.micronaut.http.filter.ServerFilterChain;
import org.reactivestreams.Publisher;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Port of kairon/actions/server.py add_secure_headers plus kairon/shared/middleware.py RequestIdMiddleware.
 * Values match the Python `secure==0.3.0` configuration as captured in tests/integration_test/services_test.py.
 */
@Filter("/**")
public class SecurityFilter implements HttpServerFilter {

    /** Header name to value, in the order the Python middleware writes them. */
    public static final Map<String, String> SECURE_HEADERS = secureHeaders();

    private static final String CORS_ORIGINS = "kairon.action.cors-origins";
    private static final String MICRONAUT_CORS_ORIGINS = "micronaut.server.cors.configurations.all.allowed-origins";

    private final String firstAllowedOrigin;

    public SecurityFilter(Environment environment) {
        this.firstAllowedOrigin = firstOrigin(environment);
    }

    @Override
    public Publisher<MutableHttpResponse<?>> doFilter(HttpRequest<?> request, ServerFilterChain chain) {
        String requestId = RequestIds.resolve(request.getHeaders().get(Kairon.REQUEST_ID));
        request.setAttribute(RequestIds.ATTRIBUTE, requestId);
        String origin = request.getHeaders().get(HttpHeaders.ORIGIN);
        return Publishers.map(chain.proceed(request), response -> {
            MutableHttpHeaders headers = response.getHeaders();
            SECURE_HEADERS.forEach(headers::set);
            headers.set(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, origin != null ? origin : firstAllowedOrigin);
            headers.set(Kairon.REQUEST_ID, requestId);
            return response;
        });
    }

    private static String firstOrigin(Environment environment) {
        for (String property : List.of(CORS_ORIGINS, MICRONAUT_CORS_ORIGINS)) {
            List<String> origins = environment.getProperty(property, Argument.listOf(String.class)).orElse(List.of());
            if (!origins.isEmpty()) {
                return origins.get(0);
            }
        }
        return "*";
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
