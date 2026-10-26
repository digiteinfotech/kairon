package com.kairon.action.runtime;

import java.util.UUID;

/**
 * Request id for the current request (kairon/shared/middleware.py RequestIdMiddleware).
 * The incoming X-Kairon-Request-ID is stripped; when it is absent or blank a UUID4 is generated.
 */
public final class RequestIds {

    /** Request attribute holding the resolved id, so blocking worker threads can pick it up. */
    public static final String ATTRIBUTE = "kairon.request_id";

    private static final InheritableThreadLocal<String> CURRENT = new InheritableThreadLocal<>();

    private RequestIds() {}

    /** Stripped incoming header value, else a new random UUID4 string. */
    public static String resolve(String incoming) {
        String stripped = incoming == null ? "" : incoming.strip();
        return stripped.isEmpty() ? UUID.randomUUID().toString() : stripped;
    }

    public static void set(String requestId) {
        if (requestId == null || requestId.isBlank()) {
            CURRENT.remove();
        } else {
            CURRENT.set(requestId);
        }
    }

    public static String get() {
        return CURRENT.get();
    }

    public static void clear() {
        CURRENT.remove();
    }
}
