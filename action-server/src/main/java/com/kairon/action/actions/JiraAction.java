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
public class JiraAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(JiraAction.class);

    private final ActionSupport support;

    public JiraAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "jira_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("jira_action", context.bot, "name", context.actionName,
                "No Jira action found for given action and bot");
        Object botResponse = config.get("response");
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            Map<String, Object> trackerData = support.context(context.tracker, false);
            Object token = support.one(trackerData, config.get("api_token"), context.bot);
            Map<String, Object> fields = new LinkedHashMap<>();
            fields.put("project", Map.of("key", config.get("project_key")));
            fields.put("issuetype", Map.of("name", config.get("issue_type")));
            fields.put("summary", Maps.text(context.tracker.senderId) + " " + Maps.text(config.get("summary")));
            fields.put("description", support.messageTrailText(context.tracker.copyEvents()));
            if (!Maps.isEmpty(config.get("parent_key"))) {
                fields.put("parent", Map.of("key", config.get("parent_key")));
            }
            String url = trimSlash(Maps.text(config.get("url"))) + "/rest/api/2/issue";
            Map<String, String> headers = Map.of(
                    "Authorization", HttpCaller.basic(Maps.str(config.get("user_name")), Maps.str(token)),
                    "Content-Type", "application/json");
            support.http().executeStrict("POST", url, headers, Map.of("fields", fields), "json");
        } catch (Exception e) {
            LOG.error("jira action failed", e);
            exception = ActionFlags.message(e);
            status = Kairon.FAIL;
            botResponse = Kairon.JIRA_FAIL;
            support.failureMail(context.bot, context.actionName, context.tracker.text(), exception);
        } finally {
            support.save(context, type(), status, exception, botResponse, null);
        }
        ActionFlags.utterText(context.dispatcher, botResponse);
        return ActionFlags.response(botResponse);
    }

    private static String trimSlash(String url) {
        if (url.endsWith("/")) {
            return url.substring(0, url.length() - 1);
        }
        return url;
    }
}
