package com.kairon.action.server;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.runtime.RequestIds;
import com.kairon.action.support.Jsons;
import io.micronaut.http.HttpRequest;
import io.micronaut.http.HttpResponse;
import io.micronaut.http.HttpStatus;
import io.micronaut.http.MediaType;
import io.micronaut.http.annotation.Body;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.Post;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;

@Controller
public class WebhookController {

    private static final Logger LOG = LoggerFactory.getLogger(WebhookController.class);

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

    @Post(value = "/webhook", consumes = MediaType.APPLICATION_JSON, produces = MediaType.APPLICATION_JSON)
    public HttpResponse<String> webhook(HttpRequest<?> request, @Body String body) {
        RequestIds.set(request.getHeaders().get(Kairon.REQUEST_ID));
        try {
            if (body == null || body.isBlank()) {
                return error(422, "Request body is empty");
            }
            Map<String, Object> call = Jsons.readMap(body);
            Object version = call.get("version");
            if (version != null && !settings.getRasaSdkVersion().equals(String.valueOf(version))) {
                LOG.warn("Rasa SDK version {} is not the action server version {}", version, settings.getRasaSdkVersion());
            }
            Object result = processor.handle(call);
            if (result == null) {
                return json("null");
            }
            return json(Jsons.write(result));
        } catch (RuntimeException e) {
            return error(422, e.getMessage() == null ? e.toString() : e.getMessage());
        } finally {
            RequestIds.clear();
        }
    }

    private static HttpResponse<String> json(String body) {
        return HttpResponse.ok(body).contentType(MediaType.APPLICATION_JSON_TYPE);
    }

    private static HttpResponse<String> error(int code, String message) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("success", false);
        body.put("error_code", code);
        body.put("message", message);
        body.put("data", null);
        return HttpResponse.status(HttpStatus.valueOf(code)).body(Jsons.write(body)).contentType(MediaType.APPLICATION_JSON_TYPE);
    }
}
