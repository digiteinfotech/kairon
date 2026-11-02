package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import com.kairon.action.support.SmtpMailer;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Port of kairon/actions/definitions/email.py: one SMTP message per recipient through {@link SmtpMailer}.
 * As in Python, only {@code smtp_userid} and {@code smtp_password} go through parameter resolution;
 * {@code smtp_url}, {@code smtp_port} and {@code tls} are read from the config as stored.
 */
@Singleton
public class EmailAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(EmailAction.class);

    /** template/emails/custom_text_mail.html, read verbatim like Python Utility.email_conf. */
    private static final String CUSTOM_TEXT_MAIL = load("custom_text_mail.html");

    private final ActionSupport support;
    private final SmtpMailer mailer;

    public EmailAction(ActionSupport support, SmtpMailer mailer) {
        this.support = support;
        this.mailer = mailer;
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
            String from = address(spec(config, "from_email"), context, true);
            List<String> to = recipients(spec(config, "to_email"), context);
            Map<String, Object> trackerData = support.context(context.tracker, false);
            Object password = support.one(trackerData, config.get("smtp_password"), context.bot);
            Object userId = support.one(trackerData, config.get("smtp_userid"), context.bot);
            if (!to.isEmpty()) {
                // Python reads smtp_url/smtp_port/tls/subject inside the per-recipient loop.
                SmtpMailer.SmtpConfig smtp = new SmtpMailer.SmtpConfig(
                        Maps.str(required(config, "smtp_url")), port(required(config, "smtp_port")),
                        Maps.str(userId), Maps.str(password), Maps.truthy(required(config, "tls")));
                String subject = Maps.str(required(config, "subject"));
                mailer.sendEach(smtp, from, to, Maps.text(context.tracker.senderId), subject,
                        mail -> body(config, trackerData, context.bot, mail));
            }
        } catch (Exception e) {
            LOG.error("email action failed", e);
            exception = ActionFlags.message(e);
            botResponse = Kairon.FAILED;
            status = Kairon.FAIL;
            support.failureMail(context, e);
        } finally {
            if (dispatch) {
                ActionFlags.utterText(context.dispatcher, botResponse);
            }
            support.save(context, type(), status, exception, botResponse, null);
        }
        return ActionFlags.response(botResponse);
    }

    /** Python: prepare_email_text(custom text) when custom_text is set, else prepare_email_body(chat_log). */
    private String body(Document config, Map<String, Object> trackerData, String bot, String mail) {
        Object custom = config.get("custom_text");
        String subject = Maps.str(config.get("subject"));
        if (Maps.truthy(custom)) {
            Object text = support.one(trackerData, custom, bot);
            return customText(text, subject, mail, Maps.text(support.settings().getFrontendUrl()));
        }
        return support.emailBody(Maps.mapList(trackerData.get("chat_log")), subject, mail);
    }

    /** Port of ActionUtility.prepare_email_text over template/emails/custom_text_mail.html. */
    static String customText(Object text, String subject, String userEmail, String baseUrl) {
        String template = CUSTOM_TEXT_MAIL.replace("SUBJECT", requireStr(subject));
        if (!Maps.isEmpty(userEmail)) {
            template = template.replace("USER_EMAIL", userEmail);
        }
        template = template.replace("CUSTOM_TEXT", requireStr(text));
        return template.replace("BASE_URL", requireStr(baseUrl));
    }

    /** Python action_config['key'] raises KeyError('key') when the field is absent. */
    private static Object required(Document config, String key) {
        if (!config.containsKey(key)) {
            throw new ActionFailure("'" + key + "'");
        }
        return config.get(key);
    }

    /** Python action_config['from_email']['parameter_type']: missing is KeyError, None is TypeError. */
    private static Object spec(Document config, String key) {
        Object value = required(config, key);
        if (value == null) {
            throw new ActionFailure("'NoneType' object is not subscriptable");
        }
        return value;
    }

    private static int port(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        return Integer.parseInt(String.valueOf(value).strip());
    }

    /** Python str.replace(old, new) raises TypeError unless new is a str. */
    private static String requireStr(Object value) {
        if (value instanceof String text) {
            return text;
        }
        throw new ActionFailure("replace() argument 2 must be str, not "
                + (value == null ? "NoneType" : value.getClass().getSimpleName()));
    }

    private static String load(String name) {
        try (InputStream in = EmailAction.class.getResourceAsStream("/templates/emails/" + name)) {
            if (in == null) {
                throw new IllegalStateException("missing email template " + name);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
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
