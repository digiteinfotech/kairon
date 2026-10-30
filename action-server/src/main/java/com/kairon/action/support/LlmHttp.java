package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.RequestIds;
import jakarta.inject.Singleton;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * Transport for calls to the kairon LLM server (kairon/shared/llm/processor.py __get_embedding /
 * __get_completion): ActionUtility.execute_request_async with `X-Kairon-Request-ID` when a request id
 * exists, the `X-TimeStamp` header, no Authorization, timeout `llm.request_timeout`, one attempt, and
 * `raise Exception(HTTPStatus(status_code).phrase)` when the status is not 200-204.
 */
@Singleton
public class LlmHttp {

    /** processor.py: `status_code not in [200, 201, 202, 203, 204]`. */
    private static final Set<Integer> OK = Set.of(200, 201, 202, 203, 204);

    /** Python http.HTTPStatus phrase table (not the JDK's reason phrases). */
    private static final Map<Integer, String> PHRASES = Map.ofEntries(
            Map.entry(100, "Continue"), Map.entry(101, "Switching Protocols"), Map.entry(102, "Processing"),
            Map.entry(103, "Early Hints"), Map.entry(200, "OK"), Map.entry(201, "Created"), Map.entry(202, "Accepted"),
            Map.entry(203, "Non-Authoritative Information"), Map.entry(204, "No Content"), Map.entry(205, "Reset Content"),
            Map.entry(206, "Partial Content"), Map.entry(207, "Multi-Status"), Map.entry(208, "Already Reported"),
            Map.entry(226, "IM Used"), Map.entry(300, "Multiple Choices"), Map.entry(301, "Moved Permanently"),
            Map.entry(302, "Found"), Map.entry(303, "See Other"), Map.entry(304, "Not Modified"), Map.entry(305, "Use Proxy"),
            Map.entry(307, "Temporary Redirect"), Map.entry(308, "Permanent Redirect"), Map.entry(400, "Bad Request"),
            Map.entry(401, "Unauthorized"), Map.entry(402, "Payment Required"), Map.entry(403, "Forbidden"),
            Map.entry(404, "Not Found"), Map.entry(405, "Method Not Allowed"), Map.entry(406, "Not Acceptable"),
            Map.entry(407, "Proxy Authentication Required"), Map.entry(408, "Request Timeout"), Map.entry(409, "Conflict"),
            Map.entry(410, "Gone"), Map.entry(411, "Length Required"), Map.entry(412, "Precondition Failed"),
            Map.entry(413, "Request Entity Too Large"), Map.entry(414, "Request-URI Too Long"),
            Map.entry(415, "Unsupported Media Type"), Map.entry(416, "Requested Range Not Satisfiable"),
            Map.entry(417, "Expectation Failed"), Map.entry(418, "I'm a Teapot"), Map.entry(421, "Misdirected Request"),
            Map.entry(422, "Unprocessable Entity"), Map.entry(423, "Locked"), Map.entry(424, "Failed Dependency"),
            Map.entry(425, "Too Early"), Map.entry(426, "Upgrade Required"), Map.entry(428, "Precondition Required"),
            Map.entry(429, "Too Many Requests"), Map.entry(431, "Request Header Fields Too Large"),
            Map.entry(451, "Unavailable For Legal Reasons"), Map.entry(500, "Internal Server Error"),
            Map.entry(501, "Not Implemented"), Map.entry(502, "Bad Gateway"), Map.entry(503, "Service Unavailable"),
            Map.entry(504, "Gateway Timeout"), Map.entry(505, "HTTP Version Not Supported"),
            Map.entry(506, "Variant Also Negotiates"), Map.entry(507, "Insufficient Storage"), Map.entry(508, "Loop Detected"),
            Map.entry(510, "Not Extended"), Map.entry(511, "Network Authentication Required"));

    private final HttpCaller http;
    private final ActionSettings settings;

    public LlmHttp(HttpCaller http, ActionSettings settings) {
        this.http = http;
        this.settings = settings;
    }

    /**
     * JSON POST to the LLM server. Returns the parsed JSON body, or the raw text when the 2xx body is not JSON.
     * Any other outcome throws {@link ActionFailure} whose message is the Python HTTPStatus phrase of the
     * response status for a 2xx/3xx outside the OK set, of 500 for any >= 400 response, or of 503 (connection failure), 408 (timeout) or 500 (other transport error).
     */
    public Object post(String url, Object body) {
        Map<String, Object> headers = new LinkedHashMap<>();
        String requestId = RequestIds.get();
        if (requestId != null) {
            headers.put(Kairon.REQUEST_ID, requestId);
        }
        HttpCaller.Exchange exchange = http.exchange("POST", url, headers, body, "json", timeout());
        if (!OK.contains(exchange.status())) {
            // Python RetryClient(raise_for_status=True) raises before status_code is set, so any real >= 400
            // response is reported as 500; transport failures keep 503/408/500 and other non-OK statuses their phrase.
            int reported = !exchange.transportFailed() && exchange.status() >= 400 ? 500 : exchange.status();
            throw new ActionFailure(phrase(reported));
        }
        return exchange.body();
    }

    /** `environment['llm'].get('request_timeout', 30)`; a falsy value falls back to action.request_timeout. */
    int timeout() {
        int seconds = settings.getLlmRequestTimeout();
        return seconds > 0 ? seconds : settings.getRequestTimeout();
    }

    /** HTTPStatus(code).phrase; an unknown code raises ValueError like Python. */
    public static String phrase(int status) {
        String phrase = PHRASES.get(status);
        return phrase != null ? phrase : status + " is not a valid HTTPStatus";
    }
}
