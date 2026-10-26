package com.kairon.action.server;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectReader;
import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.runtime.RequestIds;
import com.kairon.action.support.Jsons;
import io.micronaut.core.annotation.Nullable;
import io.micronaut.http.HttpRequest;
import io.micronaut.http.HttpResponse;
import io.micronaut.http.HttpStatus;
import io.micronaut.http.MediaType;
import io.micronaut.http.annotation.Body;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.Post;
import io.micronaut.scheduling.TaskExecutors;
import io.micronaut.scheduling.annotation.ExecuteOn;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Port of the kairon/actions/server.py routes. Blocking work (Mongo, SMTP, outbound HTTP) runs on the
 * blocking executor (virtual threads on Java 21), never on the Netty event loop.
 * <p>
 * Error contract (Python FastAPI behaviour): body validation failures return HTTP 200 with
 * {@code {"success":false,"error_code":422,"message":[...],"data":null}}; a missing tracker or sender_id
 * is an unhandled error and returns HTTP 500; action failures return HTTP 200 with empty events and
 * responses. No response uses the 422 status code.
 */
@Controller
@ExecuteOn(TaskExecutors.BLOCKING)
public class WebhookController {

    private static final Logger LOG = LoggerFactory.getLogger(WebhookController.class);
    private static final ObjectReader STRICT_JSON = Jsons.MAPPER.reader()
            .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
            .forType(Object.class);

    private final ActionProcessor processor;
    private final ActionSettings settings;

    public WebhookController(ActionProcessor processor, ActionSettings settings) {
        this.processor = processor;
        this.settings = settings;
    }

    @Get
    public HttpResponse<String> root() {
        return json("{\"message\":\"Kairon Action Server Up and Running\"}");
    }

    @Get("/healthcheck")
    public HttpResponse<String> health() {
        return json("{\"message\":\"health check ok\"}");
    }

    @Post(value = "/webhook", consumes = MediaType.ALL, produces = MediaType.APPLICATION_JSON)
    public HttpResponse<String> webhook(HttpRequest<?> request, @Body @Nullable String body) {
        String requestId = request.getAttribute(RequestIds.ATTRIBUTE, String.class)
                .orElseGet(() -> RequestIds.resolve(request.getHeaders().get(Kairon.REQUEST_ID)));
        RequestIds.set(requestId);
        try {
            Object parsed;
            if (body == null || body.isEmpty()) {
                return validationError(error("missing", List.of("body"), "Field required", null, null));
            }
            if (!isJson(request.getContentType().orElse(null))) {
                return validationError(error("dict_type", List.of("body"), "Input should be a valid dictionary", body, null));
            }
            try {
                parsed = STRICT_JSON.readValue(body);
            } catch (JsonProcessingException e) {
                long position = e.getLocation() == null ? 0 : Math.max(0, e.getLocation().getCharOffset());
                return validationError(error("json_invalid", List.<Object>of("body", position), "JSON decode error",
                        new LinkedHashMap<>(), Map.of("error", String.valueOf(e.getOriginalMessage()))));
            }
            if (parsed == null) {
                return validationError(error("missing", List.of("body"), "Field required", null, null));
            }
            if (!(parsed instanceof Map<?, ?>)) {
                return validationError(error("dict_type", List.of("body"), "Input should be a valid dictionary", parsed, null));
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> call = (Map<String, Object>) parsed;
            Object version = call.get("version");
            if (version != null && !settings.getRasaSdkVersion().equals(String.valueOf(version))) {
                LOG.warn("Rasa SDK version {} is not the action server version {}", version, settings.getRasaSdkVersion());
            }
            Object result = processor.handle(call);
            return json(result == null ? "null" : Jsons.write(result));
        } catch (RuntimeException e) {
            LOG.error("Unhandled webhook error", e);
            return HttpResponse.<String>status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Internal Server Error")
                    .contentType(MediaType.TEXT_PLAIN_TYPE);
        } finally {
            RequestIds.clear();
        }
    }

    /** FastAPI parses the body as JSON only for application/json or application/*+json content types. */
    private static boolean isJson(@Nullable MediaType contentType) {
        if (contentType == null || !"application".equalsIgnoreCase(contentType.getType())) {
            return false;
        }
        String subtype = contentType.getSubtype().toLowerCase();
        return subtype.equals("json") || subtype.endsWith("+json");
    }

    private static Map<String, Object> error(String type, List<Object> loc, String msg, Object input,
                                             @Nullable Map<String, Object> ctx) {
        Map<String, Object> error = new LinkedHashMap<>();
        error.put("type", type);
        error.put("loc", new ArrayList<>(loc));
        error.put("msg", msg);
        error.put("input", input);
        if (ctx != null) {
            error.put("ctx", ctx);
        }
        return error;
    }

    private static HttpResponse<String> validationError(Map<String, Object> error) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("success", false);
        body.put("error_code", 422);
        body.put("message", List.of(error));
        body.put("data", null);
        return json(Jsons.write(body));
    }

    private static HttpResponse<String> json(String body) {
        return HttpResponse.ok(body).contentType(MediaType.APPLICATION_JSON_TYPE);
    }
}
