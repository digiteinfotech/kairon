package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;

@Singleton
public class ZendeskAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(ZendeskAction.class);

    private final ActionSupport support;

    public ZendeskAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "zendesk_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("zendesk_action", context.bot, "name", context.actionName,
                "No Zendesk action found for given action and bot");
        Object botResponse = config.get("response");
        // Python subject = f"{sender} {action_config['subject']}" is outside try.
        ActionFlags.require(config, "subject");
        String subject = Maps.text(context.tracker.senderId) + " " + PyRepr.str(config.get("subject"));
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            Map<String, Object> trackerData = support.context(context.tracker, false);
            Object token = support.one(trackerData, config.get("api_token"), context.bot);
            ActionFlags.require(config, "subdomain");
            ActionFlags.require(config, "user_name");
            String comment = support.emailBody(Maps.mapList(trackerData.get("chat_log")), PyRepr.str(config.get("subject")));
            Map<String, Object> ticket = new LinkedHashMap<>();
            ticket.put("subject", subject);
            ticket.put("comment", Map.of("html_body", comment));
            ticket.put("tags", config.get("tags"));
            String url = "https://" + config.get("subdomain") + ".zendesk.com/api/v2/tickets.json";
            String user = Maps.text(config.get("user_name")) + "/token";
            Map<String, String> headers = Map.of(
                    "Authorization", HttpCaller.basic(user, Maps.str(token)),
                    "Content-Type", "application/json");
            support.http().executeStrict("POST", url, headers, Map.of("ticket", ticket), "json");
        } catch (Exception e) {
            LOG.error("zendesk action failed", e);
            exception = ActionFlags.message(e);
            status = Kairon.FAIL;
            botResponse = Kairon.JIRA_FAIL;
            support.failureMail(context, e);
        } finally {
            support.save(context, type(), status, exception, botResponse, null);
        }
        ActionFlags.utterText(context.dispatcher, botResponse);
        return ActionFlags.response(botResponse);
    }
}
