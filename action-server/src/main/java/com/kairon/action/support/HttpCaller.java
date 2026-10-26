package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionFailure;
import jakarta.inject.Singleton;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Singleton
public class HttpCaller {

    private static final DateTimeFormatter STAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss").withZone(ZoneOffset.UTC);
    private static final int[] ALLOWED = {200, 201, 202, 204};

    private final HttpClient client = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NORMAL).build();
    private final ActionSettings settings;

    public HttpCaller(ActionSettings settings) {
        this.settings = settings;
    }

    public record Exchange(int status, Object body, Map<String, String> headers) {}

    /** Python execute_request_async: transport errors come back as status 0 and a null body. */
    public Exchange exchange(String method, String url, Map<String, ?> headers, Object body, String contentType) {
        try {
            HttpResponse<String> response = send(method, url, headers, body, contentType, false);
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
        } catch (ActionFailure e) {
            throw new ActionFailure("Failed to execute the url: " + e.getMessage(), e);
        } catch (Exception e) {
            throw new ActionFailure("Failed to execute the url: " + e.getMessage(), e);
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
        url = rewriteHttps(url);
        String verb = method == null ? "GET" : method.toUpperCase();
        Map<String, String> outbound = new LinkedHashMap<>();
        if (headers != null) {
            headers.forEach((key, value) -> {
                if (key != null && value != null) {
                    outbound.put(key, String.valueOf(value));
                }
            });
        }
        outbound.putIfAbsent(Kairon.TIMESTAMP, STAMP.format(Instant.now()));
        String target = url;
        HttpRequest.Builder builder = HttpRequest.newBuilder().timeout(Duration.ofSeconds(Math.max(settings.getRequestTimeout(), 1)));
        outbound.forEach(builder::header);
        if ("GET".equals(verb)) {
            target = withQuery(url, body);
            builder.uri(URI.create(target)).GET();
        } else if ("POST".equals(verb) || "PUT".equals(verb) || "DELETE".equals(verb)) {
            builder.uri(URI.create(target));
            byte[] bytes = encode(body, contentType);
            String type = "data".equals(contentType) ? "application/x-www-form-urlencoded" : "application/json";
            if (outbound.keySet().stream().noneMatch(key -> key.equalsIgnoreCase("Content-Type"))) {
                builder.header("Content-Type", type);
            }
            builder.method(verb, HttpRequest.BodyPublishers.ofByteArray(bytes));
        } else if (strictMethod) {
            throw new ActionFailure("Invalid request method!");
        } else {
            throw new IllegalArgumentException("Invalid request method!");
        }
        return client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
    }

    private static byte[] encode(Object body, String contentType) {
        if (body == null) {
            return new byte[0];
        }
        if ("data".equals(contentType) && body instanceof Map<?, ?> map) {
            StringBuilder form = new StringBuilder();
            map.forEach((key, value) -> {
                if (!form.isEmpty()) {
                    form.append('&');
                }
                form.append(URLEncoder.encode(String.valueOf(key), StandardCharsets.UTF_8));
                form.append('=');
                form.append(URLEncoder.encode(value == null ? "" : String.valueOf(value), StandardCharsets.UTF_8));
            });
            return form.toString().getBytes(StandardCharsets.UTF_8);
        }
        if (body instanceof String text) {
            return text.getBytes(StandardCharsets.UTF_8);
        }
        return Jsons.write(body).getBytes(StandardCharsets.UTF_8);
    }

    private static String withQuery(String url, Object body) {
        if (!(body instanceof Map<?, ?> map) || map.isEmpty()) {
            return url;
        }
        StringBuilder query = new StringBuilder();
        map.forEach((key, value) -> {
            if (value == null) {
                return;
            }
            if (!query.isEmpty()) {
                query.append('&');
            }
            query.append(URLEncoder.encode(String.valueOf(key), StandardCharsets.UTF_8));
            query.append('=');
            query.append(URLEncoder.encode(String.valueOf(value), StandardCharsets.UTF_8));
        });
        if (query.isEmpty()) {
            return url;
        }
        return url + (url.contains("?") ? "&" : "?") + query;
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

    public List<Object> multipart(String method, String url, Map<String, ?> headers, Map<String, Object> fields, List<MediaFile> files) {
        List<Object> responses = new ArrayList<>();
        for (MediaFile file : files) {
            try {
                String boundary = "----kairon" + System.nanoTime();
                byte[] payload = multipartBody(boundary, fields, file);
                Map<String, Object> outbound = new LinkedHashMap<>();
                if (headers != null) {
                    headers.forEach(outbound::put);
                }
                outbound.put("Content-Type", "multipart/form-data; boundary=" + boundary);
                HttpResponse<String> response = sendRaw(method, url, outbound, payload);
                if (!allowed(response.statusCode())) {
                    throw new ActionFailure("Got non-200 status code: " + response.statusCode() + " " + response.body());
                }
                responses.add(parse(response.body()));
            } catch (ActionFailure e) {
                throw new ActionFailure("Failed to execute the url: " + e.getMessage(), e);
            } catch (Exception e) {
                throw new ActionFailure("Failed to execute the url: " + e.getMessage(), e);
            }
        }
        return responses;
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

    private HttpResponse<String> sendRaw(String method, String url, Map<String, ?> headers, byte[] body) throws Exception {
        url = rewriteHttps(url);
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(Math.max(settings.getRequestTimeout(), 1)));
        if (headers != null) {
            headers.forEach((key, value) -> {
                if (value != null) {
                    builder.header(key, String.valueOf(value));
                }
            });
        }
        builder.header(Kairon.TIMESTAMP, STAMP.format(Instant.now()));
        builder.method(method.toUpperCase(), HttpRequest.BodyPublishers.ofByteArray(body));
        return client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
    }

    private static byte[] multipartBody(String boundary, Map<String, Object> fields, MediaFile file) {
        StringBuilder text = new StringBuilder();
        if (fields != null) {
            fields.forEach((key, value) -> {
                if ("media_ids".equals(key) || value == null) {
                    return;
                }
                text.append("--").append(boundary).append("\r\n");
                text.append("Content-Disposition: form-data; name=\"").append(key).append("\"\r\n\r\n");
                text.append(value).append("\r\n");
            });
        }
        text.append("--").append(boundary).append("\r\n");
        text.append("Content-Disposition: form-data; name=\"file\"; filename=\"").append(file.name()).append("\"\r\n");
        text.append("Content-Type: ").append(file.type()).append("\r\n\r\n");
        byte[] head = text.toString().getBytes(StandardCharsets.UTF_8);
        byte[] tail = ("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8);
        byte[] all = new byte[head.length + file.bytes().length + tail.length];
        System.arraycopy(head, 0, all, 0, head.length);
        System.arraycopy(file.bytes(), 0, all, head.length, file.bytes().length);
        System.arraycopy(tail, 0, all, head.length + file.bytes().length, tail.length);
        return all;
    }

    public record MediaFile(String name, String type, byte[] bytes) {}
}
