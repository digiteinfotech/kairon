package com.kairon.action.server;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.RequestIds;
import io.micronaut.core.async.publisher.Publishers;
import io.micronaut.http.HttpRequest;
import io.micronaut.http.MutableHttpResponse;
import io.micronaut.http.annotation.Filter;
import io.micronaut.http.filter.HttpServerFilter;
import io.micronaut.http.filter.ServerFilterChain;
import org.reactivestreams.Publisher;

@Filter("/**")
public class SecurityFilter implements HttpServerFilter {

    @Override
    public Publisher<MutableHttpResponse<?>> doFilter(HttpRequest<?> request, ServerFilterChain chain) {
        String requestId = request.getHeaders().get(Kairon.REQUEST_ID);
        RequestIds.set(requestId);
        return Publishers.map(chain.proceed(request), response -> {
            try {
                response.getHeaders().add("X-Content-Type-Options", "nosniff");
                response.getHeaders().add("Referrer-Policy", "no-referrer");
                response.getHeaders().add("Content-Security-Policy", "frame-ancestors 'none'");
                response.getHeaders().add("Cache-Control", "no-cache, no-store, must-revalidate");
                if (requestId != null && !requestId.isBlank()) {
                    response.getHeaders().add(Kairon.REQUEST_ID, requestId);
                }
                return response;
            } finally {
                RequestIds.clear();
            }
        });
    }
}
