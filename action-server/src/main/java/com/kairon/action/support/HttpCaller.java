package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionFailure;
import jakarta.inject.Singleton;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

@Singleton
public class HttpCaller {

    private static final DateTimeFormatter STAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss").withZone(ZoneOffset.UTC);
    private static final int[] ALLOWED = {200, 201, 202, 204};
    /** aiohttp max_redirects default. The 11th redirect response fails the exchange. */
    static final int MAX_REDIRECTS = 10;
    private static final Set<Integer> REDIRECTS = Set.of(301, 302, 303, 307, 308);
    /** Never forwarded to a different origin after a redirect. */
    private static final Set<String> CREDENTIALS = Set.of("authorization", "cookie", "proxy-authorization");
    /** Headers java.net.http refuses from callers; the client computes them itself. */
    private static final Set<String> RESTRICTED = Set.of("connection", "content-length", "expect", "host", "upgrade");
    private static final String FORM = "application/x-www-form-urlencoded";
    private static final String JSON = "application/json";
    /** requests.utils.requote_uri safe set plus RFC 3986 unreserved punctuation. */
    private static final String URI_SAFE = "!#$%&'()*+,/:;=?@[]~-._";

    /**
     * The JDK never follows redirects here: {@link #execute} owns hop counting, method rewriting and
     * credential stripping so behaviour does not depend on the client library version
     * (GHSA-q6gh-6v2r-hjv3). TLS certificates are verified against the JDK default trust store.
     */
    private final HttpClient client = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).build();
    private final ActionSettings settings;

    public HttpCaller(ActionSettings settings) {
        this.settings = settings;
    }

    public record Exchange(int status, Object body, Map<String, String> headers) {}

    /** Python execute_request_async: transport errors come back as status 0 and a null body. */
    public Exchange exchange(String method, String url, Map<String, ?> headers, Object body, String contentType) {
        try {
            // aiohttp client: `request_body if request_body else {}`
            Object payload = body == null ? new LinkedHashMap<String, Object>() : body;
            HttpResponse<String> response = send(method, url, headers, payload, contentType, false);
            return new Exchange(response.statusCode(), parse(response.body()), headerMap(response));
        } catch (Exception e) {
            return new Exchange(0, null, Map.of());
        }
    }

    /** Python execute_http_request: non-2xx and transport errors become ActionFailure. */
    public Object executeStrict(String method, String url, Map<String, ?> headers, Object body, String contentType) {
        try {
            HttpResponse<String> response = send(method, url, headers, body, contentType, true);
            if (!allowed(response.statusCode())) {
                throw new ActionFailure("Got non-200 status code: " + response.statusCode() + " " + response.body());
            }
            return parse(response.body());
        } catch (Exception e) {
            throw new ActionFailure("Failed to execute the url: " + message(e), e);
        }
    }

    public static String basic(String username, String password) {
        String token = Base64.getEncoder().encodeToString(((username == null ? "" : username) + ":" + (password == null ? "" : password)).getBytes(StandardCharsets.UTF_8));
        return "Basic " + token;
    }

    public static String failReason(Object body, int status) {
        if (status == 0 || allowed(status)) {
            return null;
        }
        return "Got non-200 status code:" + status + " http_response:" + body;
    }

    public static void validate(Object body, int status) {
        String reason = failReason(body, status);
        if (reason != null) {
            throw new ActionFailure(reason);
        }
    }

    private HttpResponse<String> send(String method, String url, Map<String, ?> headers, Object body, String contentType, boolean strictMethod) throws Exception {
        String verb = method == null ? "GET" : method.toUpperCase(Locale.ROOT);
        Map<String, String> outbound = new LinkedHashMap<>();
        if (headers != null) {
            headers.forEach((key, value) -> {
                if (key != null && value != null) {
                    outbound.put(key, String.valueOf(value));
                }
            });
        }
        outbound.putIfAbsent(Kairon.TIMESTAMP, STAMP.format(Instant.now()));
        String target = requote(url);
        byte[] bytes = null;
        if ("GET".equals(verb)) {
            target = withQuery(target, body);
        } else if ("POST".equals(verb) || "PUT".equals(verb) || "DELETE".equals(verb)) {
            bytes = encode(body, contentType);
            if (bytes != null && !hasHeader(outbound, "Content-Type")) {
                outbound.put("Content-Type", "data".equals(contentType) ? FORM : JSON);
            }
        } else if (strictMethod) {
            throw new ActionFailure("Invalid request method!");
        } else {
            throw new IllegalArgumentException("Invalid request method!");
        }
        return execute(verb, target, outbound, bytes);
    }

    /**
     * Sends the request and follows redirects like aiohttp: at most {@link #MAX_REDIRECTS} hops,
     * 303 (non-HEAD) and 301/302 on POST become a bodiless GET, 307/308 keep method and body, and
     * Authorization, Cookie and Proxy-Authorization are dropped once the origin changes.
     * The request timeout is one wall-clock budget across all hops including the response body.
     */
    HttpResponse<String> execute(String method, String url, Map<String, String> headers, byte[] body) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(Math.max(settings.getRequestTimeout(), 1));
        String verb = method;
        String current = url;
        byte[] payload = body;
        Map<String, String> outbound = new LinkedHashMap<>(headers);
        for (int hop = 0; ; hop++) {
            HttpResponse<String> response = await(build(verb, current, outbound, payload, deadline), deadline);
            int status = response.statusCode();
            String location = response.headers().firstValue("Location").orElse(null);
            if (!REDIRECTS.contains(status) || location == null) {
                return response;
            }
            if (hop >= MAX_REDIRECTS) {
                throw new IOException("Too many redirects: exceeded " + MAX_REDIRECTS + " redirects at " + current);
            }
            String next = resolve(current, requote(location));
            if ((status == 303 && !"HEAD".equals(verb)) || ((status == 301 || status == 302) && "POST".equals(verb))) {
                verb = "GET";
                payload = null;
                outbound.keySet().removeIf(key -> key.equalsIgnoreCase("Content-Type") || key.equalsIgnoreCase("Content-Length"));
            }
            if (!sameOrigin(current, next)) {
                outbound.keySet().removeIf(key -> CREDENTIALS.contains(key.toLowerCase(Locale.ROOT)));
            }
            current = next;
        }
    }

    private HttpRequest build(String verb, String url, Map<String, String> headers, byte[] payload, long deadline) throws HttpTimeoutException {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(rewriteHttps(url)))
                .timeout(Duration.ofNanos(remaining(deadline)));
        headers.forEach((key, value) -> {
            if (!RESTRICTED.contains(key.toLowerCase(Locale.ROOT))) {
                builder.header(key, value);
            }
        });
        builder.method(verb, payload == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofByteArray(payload));
        return builder.build();
    }

    private HttpResponse<String> await(HttpRequest request, long deadline) throws Exception {
        CompletableFuture<HttpResponse<String>> future = client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
        try {
            return future.get(remaining(deadline), TimeUnit.NANOSECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            throw new HttpTimeoutException("request timed out");
        } catch (ExecutionException e) {
            if (e.getCause() instanceof Exception cause) {
                throw cause;
            }
            throw e;
        }
    }

    private static long remaining(long deadline) throws HttpTimeoutException {
        long left = deadline - System.nanoTime();
        if (left <= 0) {
            throw new HttpTimeoutException("request timed out");
        }
        return left;
    }

    private static String resolve(String base, String location) {
        URI root = URI.create(base);
        if (root.getRawPath() == null || root.getRawPath().isEmpty()) {
            root = URI.create(root.getScheme() + "://" + root.getRawAuthority() + "/");
        }
        return root.resolve(URI.create(location)).toString();
    }

    static boolean sameOrigin(String first, String second) {
        URI a = URI.create(first);
        URI b = URI.create(second);
        return lower(a.getScheme()).equals(lower(b.getScheme()))
                && lower(a.getHost()).equals(lower(b.getHost()))
                && port(a) == port(b);
    }

    private static String lower(String text) {
        return text == null ? "" : text.toLowerCase(Locale.ROOT);
    }

    private static int port(URI uri) {
        if (uri.getPort() != -1) {
            return uri.getPort();
        }
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    private static boolean hasHeader(Map<String, ?> headers, String name) {
        return headers.keySet().stream().anyMatch(key -> key.equalsIgnoreCase(name));
    }

    private static String message(Exception e) {
        Throwable error = e;
        if (e instanceof ActionFailure && e.getCause() != null) {
            error = e.getCause();
        }
        String text = error.getMessage();
        return text == null ? error.getClass().getSimpleName() : text;
    }

    /** Request body bytes; null means no body (requests with json=None). */
    private static byte[] encode(Object body, String contentType) {
        if (body == null) {
            return null;
        }
        if ("data".equals(contentType) && body instanceof Map<?, ?> map) {
            return formEncode(map).getBytes(StandardCharsets.UTF_8);
        }
        if (body instanceof String text) {
            return text.getBytes(StandardCharsets.UTF_8);
        }
        return Jsons.write(body).getBytes(StandardCharsets.UTF_8);
    }

    /** Python urlencode(doseq=True) with quote_plus, over requests' key/value expansion. */
    static String formEncode(Map<?, ?> map) {
        StringBuilder out = new StringBuilder();
        for (String[] pair : pairs(map)) {
            if (!out.isEmpty()) {
                out.append('&');
            }
            out.append(quotePlus(pair[0])).append('=').append(quotePlus(pair[1]));
        }
        return out.toString();
    }

    /**
     * requests _encode_params: null values dropped, a list sends one key per non-null element,
     * a nested dict sends its keys (Python iterates a dict's keys), scalars use Python str().
     */
    static List<String[]> pairs(Map<?, ?> map) {
        List<String[]> pairs = new ArrayList<>();
        map.forEach((key, value) -> {
            if (value == null) {
                return;
            }
            Iterable<?> values;
            if (value instanceof Map<?, ?> nested) {
                values = nested.keySet();
            } else if (value instanceof Collection<?> collection) {
                values = collection;
            } else {
                values = List.of(value);
            }
            for (Object item : values) {
                if (item != null) {
                    pairs.add(new String[]{pyStr(key), pyStr(item)});
                }
            }
        });
        return pairs;
    }

    static String withQuery(String url, Object body) {
        if (!(body instanceof Map<?, ?> map) || map.isEmpty()) {
            return url;
        }
        String query = formEncode(map);
        if (query.isEmpty()) {
            return url;
        }
        return url + (url.contains("?") ? "&" : "?") + query;
    }

    /** urllib.parse.quote_plus: unreserved characters kept, space as '+', everything else %XX. */
    static String quotePlus(String text) {
        StringBuilder out = new StringBuilder();
        for (byte b : text.getBytes(StandardCharsets.UTF_8)) {
            int c = b & 0xff;
            if (alnum(c) || c == '_' || c == '.' || c == '-' || c == '~') {
                out.append((char) c);
            } else if (c == ' ') {
                out.append('+');
            } else {
                out.append('%').append(String.format("%02X", c));
            }
        }
        return out.toString();
    }

    /** requests.utils.requote_uri: percent-encode characters illegal in a URI, keep valid escapes. */
    static String requote(String url) {
        if (url == null) {
            return null;
        }
        StringBuilder out = new StringBuilder();
        byte[] bytes = url.getBytes(StandardCharsets.UTF_8);
        for (int i = 0; i < bytes.length; i++) {
            int c = bytes[i] & 0xff;
            if (c == '%') {
                boolean escape = i + 2 < bytes.length && hex(bytes[i + 1]) && hex(bytes[i + 2]);
                out.append(escape ? "%" : "%25");
            } else if (alnum(c) || (c < 0x80 && URI_SAFE.indexOf(c) >= 0)) {
                out.append((char) c);
            } else {
                out.append('%').append(String.format("%02X", c));
            }
        }
        return out.toString();
    }

    private static boolean alnum(int c) {
        return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
    }

    private static boolean hex(byte b) {
        return (b >= '0' && b <= '9') || (b >= 'a' && b <= 'f') || (b >= 'A' && b <= 'F');
    }

    /** Python str() of a form/query value. */
    static String pyStr(Object value) {
        return value instanceof String text ? text : pyRepr(value);
    }

    private static String pyRepr(Object value) {
        if (value == null) {
            return "None";
        }
        if (value instanceof String text) {
            return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'";
        }
        if (value instanceof Boolean flag) {
            return flag ? "True" : "False";
        }
        if (value instanceof Double || value instanceof Float) {
            return pyFloat(((Number) value).doubleValue());
        }
        if (value instanceof Map<?, ?> map) {
            StringBuilder out = new StringBuilder("{");
            map.forEach((key, item) -> {
                if (out.length() > 1) {
                    out.append(", ");
                }
                out.append(pyRepr(key)).append(": ").append(pyRepr(item));
            });
            return out.append('}').toString();
        }
        if (value instanceof Collection<?> collection) {
            StringBuilder out = new StringBuilder("[");
            for (Object item : collection) {
                if (out.length() > 1) {
                    out.append(", ");
                }
                out.append(pyRepr(item));
            }
            return out.append(']').toString();
        }
        return String.valueOf(value);
    }

    /** Python float repr: shortest round-trip digits, plain between 1e-4 and 1e16, else d.ddde+XX. */
    static String pyFloat(double d) {
        if (Double.isNaN(d)) {
            return "nan";
        }
        if (Double.isInfinite(d)) {
            return d > 0 ? "inf" : "-inf";
        }
        String text = Double.toString(d);
        double abs = Math.abs(d);
        if (abs == 0 || (abs >= 1e-4 && abs < 1e16)) {
            if (!text.contains("E")) {
                return text;
            }
            String plain = new BigDecimal(text).stripTrailingZeros().toPlainString();
            return plain.contains(".") ? plain : plain + ".0";
        }
        String[] parts = text.split("E");
        String mantissa = parts[0].endsWith(".0") ? parts[0].substring(0, parts[0].length() - 2) : parts[0];
        int exponent = Integer.parseInt(parts[1]);
        return mantissa + "e" + (exponent < 0 ? "-" : "+") + String.format("%02d", Math.abs(exponent));
    }

    private static Object parse(String body) {
        if (body == null || body.isBlank()) {
            return body == null ? "" : body;
        }
        String trimmed = body.strip();
        if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
            return Jsons.readAny(trimmed);
        }
        return body;
    }

    private static Map<String, String> headerMap(HttpResponse<String> response) {
        Map<String, String> headers = new LinkedHashMap<>();
        response.headers().map().forEach((key, values) -> headers.put(key, String.join(",", values)));
        return headers;
    }

    private static boolean allowed(int status) {
        for (int code : ALLOWED) {
            if (code == status) {
                return true;
            }
        }
        return false;
    }

    /** Form fields are included, as with Python `data=request_body, files=...`. */
    public List<Object> multipart(String method, String url, Map<String, ?> headers, Map<String, Object> fields, List<MediaFile> files) {
        return multipart(method, url, headers, fields, files, "data");
    }

    /**
     * One multipart request carrying one `file` part per media item, mirroring
     * requests.request(..., files=[("file", (name, bytes, mime)), ...]). requests drops a `json`
     * body when files are present, so fields are only sent for content type `data`.
     * Returns a single-element list holding the parsed response.
     */
    public List<Object> multipart(String method, String url, Map<String, ?> headers, Map<String, Object> fields, List<MediaFile> files, String contentType) {
        try {
            String verb = method == null ? "POST" : method.toUpperCase(Locale.ROOT);
            String boundary = UUID.randomUUID().toString().replace("-", "");
            byte[] payload = multipartBody(boundary, "json".equals(contentType) ? null : fields, files);
            Map<String, String> outbound = new LinkedHashMap<>();
            if (headers != null) {
                headers.forEach((key, value) -> {
                    if (key != null && value != null && !key.equalsIgnoreCase("Content-Type")) {
                        outbound.put(key, String.valueOf(value));
                    }
                });
            }
            outbound.putIfAbsent(Kairon.TIMESTAMP, STAMP.format(Instant.now()));
            outbound.put("Content-Type", "multipart/form-data; boundary=" + boundary);
            HttpResponse<String> response = execute(verb, requote(url), outbound, payload);
            if (!allowed(response.statusCode())) {
                throw new ActionFailure("Got non-200 status code: " + response.statusCode() + " " + response.body());
            }
            List<Object> responses = new ArrayList<>();
            responses.add(parse(response.body()));
            return responses;
        } catch (Exception e) {
            throw new ActionFailure("Failed to execute the url: " + message(e), e);
        }
    }

    /** Production leaves this empty. Tests point https provider hosts at a local stub. */
    private String rewriteHttps(String url) {
        String base = settings.getHttpsStubBase();
        if (base == null || base.isBlank() || url == null || !url.startsWith("https://")) {
            return url;
        }
        int slash = url.indexOf('/', "https://".length());
        String rest = slash < 0 ? "/" : url.substring(slash);
        String root = base.endsWith("/") ? base.substring(0, base.length() - 1) : base;
        return root + rest;
    }

    static byte[] multipartBody(String boundary, Map<String, Object> fields, List<MediaFile> files) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        if (fields != null) {
            Map<String, Object> form = new LinkedHashMap<>(fields);
            form.remove("media_ids");
            for (String[] pair : pairs(form)) {
                write(out, "--" + boundary + "\r\n");
                write(out, "Content-Disposition: form-data; name=\"" + pair[0] + "\"\r\n\r\n");
                write(out, pair[1] + "\r\n");
            }
        }
        for (MediaFile file : files) {
            write(out, "--" + boundary + "\r\n");
            write(out, "Content-Disposition: form-data; name=\"file\"; filename=\"" + file.name() + "\"\r\n");
            write(out, "Content-Type: " + file.type() + "\r\n\r\n");
            out.writeBytes(file.bytes());
            write(out, "\r\n");
        }
        write(out, "--" + boundary + "--\r\n");
        return out.toByteArray();
    }

    private static void write(ByteArrayOutputStream out, String text) {
        out.writeBytes(text.getBytes(StandardCharsets.UTF_8));
    }

    public record MediaFile(String name, String type, byte[] bytes) {}
}
