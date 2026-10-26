package com.kairon.action.runtime;

public final class RequestIds {

    private static final InheritableThreadLocal<String> CURRENT = new InheritableThreadLocal<>();

    private RequestIds() {}

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
