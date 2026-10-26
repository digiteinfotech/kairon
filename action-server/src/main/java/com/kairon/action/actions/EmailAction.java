package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** SMTP is not configured on this server. A valid request is logged and follows the success path. */
@Singleton
public class EmailAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(EmailAction.class);

    private final ActionSupport support;

    public EmailAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "email_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("email_action_config", context.bot, "action_name", context.actionName,
                "No Email action found for given action and bot");
        Object botResponse = config.get("response");
        boolean dispatch = ActionFlags.enabled(config, "dispatch_bot_response");
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            String from = address(config.get("from_email"), context, true);
            List<String> to = recipients(config.get("to_email"), context);
            Map<String, Object> trackerData = support.context(context.tracker, false);
            String subject = Maps.text(context.tracker.senderId) + " " + Maps.text(config.get("subject"));
            for (String mail : to) {
                String body = body(config, trackerData, context.bot, mail);
                LOG.info("smtp is not configured; email not sent to {} subject {}", mail, subject);
                LOG.debug("email body {}", body);
            }
        } catch (Exception e) {
            LOG.error("email action failed", e);
            exception = ActionFlags.message(e);
            botResponse = Kairon.FAILED;
            status = Kairon.FAIL;
            support.failureMail(context.bot, context.actionName, context.tracker.text(), exception);
        } finally {
            if (dispatch) {
                ActionFlags.utterText(context.dispatcher, botResponse);
            }
            support.save(context, type(), status, exception, botResponse, null);
        }
        return ActionFlags.response(botResponse);
    }

    private String body(Document config, Map<String, Object> trackerData, String bot, String mail) {
        Object custom = config.get("custom_text");
        String subject = Maps.text(config.get("subject"));
        if (Maps.truthy(custom)) {
            Object text = support.one(trackerData, custom, bot);
            return "<html><body><h3>" + subject + "</h3><p>" + (text == null ? "" : text) + "</p><p>" + mail + "</p></body></html>";
        }
        return support.emailBody(Maps.mapList(trackerData.get("chat_log")), subject);
    }

    private String address(Object spec, ActionContext context, boolean from) {
        Object value = resolve(spec, context);
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException(from
                    ? "Invalid 'from_email' type. It must be of type str."
                    : "Invalid 'to_email' type. It must be of type str or list.");
        }
        return text;
    }

    private List<String> recipients(Object spec, ActionContext context) {
        Object value = resolve(spec, context);
        List<String> mails = new ArrayList<>();
        if (value instanceof String text) {
            mails.add(text);
            return mails;
        }
        if (value instanceof List<?> list) {
            for (Object item : list) {
                mails.add(item == null ? null : String.valueOf(item));
            }
            return mails;
        }
        throw new IllegalArgumentException("Invalid 'to_email' type. It must be of type str or list.");
    }

    private Object resolve(Object spec, ActionContext context) {
        Map<String, Object> parameter = Maps.map(spec);
        if ("slot".equals(parameter.get("parameter_type"))) {
            return context.tracker.slotValue(Maps.str(parameter.get("value")));
        }
        return parameter.get("value");
    }
}
