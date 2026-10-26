package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Singleton
public class PipedriveAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(PipedriveAction.class);

    private final ActionSupport support;

    public PipedriveAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "pipedrive_leads_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("pipedrive_leads_action", context.bot, "name", context.actionName,
                "No Pipedrive leads action found for given action and bot");
        Object botResponse = config.get("response");
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            Map<String, Object> trackerData = support.context(context.tracker, false);
            Object token = support.one(trackerData, config.get("api_token"), context.bot);
            String base = baseUrl(Maps.text(config.get("domain")));
            String apiToken = Maps.text(token);
            Map<String, Object> metadata = new LinkedHashMap<>();
            Maps.map(config.get("metadata")).forEach((key, slot) -> metadata.put(key, context.tracker.slotValue(Maps.str(slot))));
            if (Maps.truthy(metadata.get("org_name"))) {
                Map<String, Object> org = success(post(base, apiToken, "/organizations", Map.of("name", metadata.get("org_name"))), "organization");
                metadata.put("org_id", org.get("id"));
            }
            Map<String, Object> personBody = new LinkedHashMap<>();
            personBody.put("name", metadata.get("name"));
            personBody.put("org_id", metadata.get("org_id"));
            personBody.put("email", Maps.truthy(metadata.get("email")) ? ListOf(metadata.get("email")) : null);
            personBody.put("phone", Maps.truthy(metadata.get("phone")) ? ListOf(metadata.get("phone")) : null);
            Map<String, Object> person = success(post(base, apiToken, "/persons", personBody), "person");
            String title = Maps.text(context.tracker.senderId) + " " + Maps.text(config.get("title"));
            Map<String, Object> leadBody = new LinkedHashMap<>();
            leadBody.put("title", title);
            leadBody.put("person_id", person.get("id"));
            leadBody.put("organization_id", metadata.get("org_id"));
            Map<String, Object> lead = success(post(base, apiToken, "/leads", leadBody), "lead");
            Map<String, Object> note = new LinkedHashMap<>();
            note.put("content", support.messageTrailText(context.tracker.copyEvents()));
            note.put("lead_id", lead.get("id"));
            success(post(base, apiToken, "/notes", note), "note");
        } catch (Exception e) {
            LOG.error("pipedrive action failed", e);
            exception = ActionFlags.message(e);
            status = Kairon.FAIL;
            botResponse = Kairon.LEAD_FAIL;
            support.failureMail(context, e);
        } finally {
            support.save(context, type(), status, exception, botResponse, null);
        }
        ActionFlags.utterText(context.dispatcher, botResponse);
        return ActionFlags.response(botResponse);
    }

    private Object post(String base, String token, String path, Map<String, Object> body) {
        String url = base + path + "?api_token=" + URLEncoder.encode(token, StandardCharsets.UTF_8);
        return support.http().executeStrict("POST", url, Map.of("Content-Type", "application/json"), body, "json");
    }

    private static Map<String, Object> success(Object response, String what) {
        Map<String, Object> map = Maps.map(response);
        if (!Boolean.TRUE.equals(map.get("success"))) {
            String label = "note".equals(what) ? "attach note" : "create " + what;
            throw new ActionFailure("Failed to " + label + ": " + response);
        }
        return Maps.map(map.get("data"));
    }

    private static String baseUrl(String domain) {
        String host = domain;
        if (host.startsWith("https://")) {
            host = host.substring("https://".length());
        } else if (host.startsWith("http://")) {
            host = host.substring("http://".length());
        }
        int slash = host.indexOf('/');
        if (slash >= 0) {
            host = host.substring(0, slash);
        }
        if (!host.contains(".")) {
            host = host + ".pipedrive.com";
        }
        return "https://" + host + "/v1";
    }

    private static List<Object> ListOf(Object value) {
        return java.util.List.of(value);
    }
}
