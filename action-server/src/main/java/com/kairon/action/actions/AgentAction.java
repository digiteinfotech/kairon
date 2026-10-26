package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;

@Singleton
public class AgentAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(AgentAction.class);

    private final ActionSupport support;

    public AgentAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "agent_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("agent_action_config", context.bot, "name", context.actionName,
                "No AgentAction found for given action and bot");
        boolean dispatch = ActionFlags.enabled(config, "dispatch_bot_response");
        Object botResponse = null;
        Object apiResponse = null;
        String url = null;
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            String base = support.settings().getSimpleAgentUrl();
            if (base.endsWith("/")) {
                base = base.substring(0, base.length() - 1);
            }
            url = base + "/agents/" + context.bot + "/" + config.get("agent_id") + "/run/" + context.tracker.senderId + "/simple";
            String token = support.tokens().integrationToken(Map.of("sub", Maps.text(context.tracker.senderId), "bot", context.bot));
            Map<String, String> headers = new LinkedHashMap<>();
            headers.put("Accept", "application/json");
            headers.put("Content-Type", "application/json");
            headers.put("X-user", Maps.text(context.tracker.senderId));
            headers.put("Authorization", "Bearer " + token);
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("message", context.tracker.userText() == null ? "" : context.tracker.userText());
            body.put("session_id", null);
            body.put("metadata", Map.of());
            body.put("max_iterations", 1);
            HttpCaller.Exchange exchange = support.http().exchange("POST", url, headers, body, "json");
            apiResponse = exchange.body();
            HttpCaller.validate(apiResponse, exchange.status());
            if (apiResponse instanceof Map<?, ?> map) {
                Object output = Maps.map(map).get("output");
                botResponse = Maps.isEmpty(output) ? "" : output;
            } else {
                botResponse = apiResponse == null ? "" : String.valueOf(apiResponse);
            }
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("agent action failed", e);
            status = Kairon.FAIL;
            botResponse = Kairon.FAILED_DOT;
            support.failureMail(context, e);
        } finally {
            if (dispatch && Maps.truthy(botResponse)) {
                ActionFlags.utterText(context.dispatcher, botResponse);
            }
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("url", url);
            extra.put("api_response", apiResponse == null ? null : String.valueOf(apiResponse));
            support.save(context, type(), status, exception, botResponse, extra);
        }
        return ActionFlags.response(botResponse);
    }
}
