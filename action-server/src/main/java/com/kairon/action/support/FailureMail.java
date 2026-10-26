package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.ActionCatalog;
import io.micronaut.context.annotation.Value;
import jakarta.inject.Inject;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.InputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executor;

/**
 * Port of Python ActionUtility.trigger_action_failure_mail (kairon/shared/actions/utils.py) and
 * MailUtility.format_and_send_mail("action_failure", ...) / __handle_action_failure (kairon/shared/utils.py)
 * over template/emails/action_failure.html.
 *
 * <p>The send is fire-and-forget (Python asyncio.create_task): {@link #trigger} returns at once and every
 * failure (unknown bot, invalid support address, SMTP error) is only logged. SMTP settings are the Python
 * email.yaml sender keys (EMAIL_SENDER_SERVICE, _PORT, _EMAIL, _PASSWORD, _USERID); MailUtility.trigger_smtp
 * always uses STARTTLS.
 */
@Singleton
public class FailureMail {

    private static final Logger LOG = LoggerFactory.getLogger(FailureMail.class);
    static final String TEMPLATE = load("action_failure.html");
    /** email.yaml action_failure_subject default. */
    static final String DEFAULT_SUBJECT = "kAIron Action Failure - BOT_NAME";
    /** first_name passed by trigger_action_failure_mail. */
    static final String FIRST_NAME = "Team kAIron";

    private final ActionCatalog catalog;
    private final ActionSettings settings;
    private final SmtpMailer mailer;
    private final SmtpMailer.SmtpConfig smtp;
    private final String sender;
    private final String subjectTemplate;
    private final Executor executor;

    @Inject
    public FailureMail(ActionCatalog catalog, ActionSettings settings, SmtpMailer mailer,
                       @Value("${email.sender.service:changeit}") String host,
                       @Value("${email.sender.port:587}") int port,
                       @Value("${email.sender.email:changeit@changeit.com}") String sender,
                       @Value("${email.sender.password:changeit}") String password,
                       @Value("${email.sender.userid:}") String userId,
                       @Value("${email.templates.action.failure:" + DEFAULT_SUBJECT + "}") String subjectTemplate) {
        this(catalog, settings, mailer, new SmtpMailer.SmtpConfig(host, port, userId, password, true), sender,
                subjectTemplate, task -> Thread.ofVirtual().name("action-failure-mail").start(task));
    }

    FailureMail(ActionCatalog catalog, ActionSettings settings, SmtpMailer mailer, SmtpMailer.SmtpConfig smtp,
                String sender, String subjectTemplate, Executor executor) {
        this.catalog = catalog;
        this.settings = settings;
        this.mailer = mailer;
        this.smtp = smtp;
        this.sender = sender;
        this.subjectTemplate = subjectTemplate == null || subjectTemplate.isBlank() ? DEFAULT_SUBJECT : subjectTemplate;
        this.executor = executor;
    }

    /** Python traceback.format_exc() stand-in: the Java stack trace of the handled exception. */
    public static String stackTrace(Throwable error) {
        if (error == null) {
            return "None";
        }
        StringWriter out = new StringWriter();
        error.printStackTrace(new PrintWriter(out));
        return out.toString();
    }

    /**
     * Schedule one action failure mail to the configured support address and return immediately.
     * Never throws.
     */
    public void trigger(String bot, String action, Map<String, Object> slotValues, Object userText, String stackTrace) {
        try {
            executor.execute(() -> {
                try {
                    deliver(bot, action, slotValues, userText, stackTrace);
                } catch (Exception e) {
                    LOG.error("action failure mail not sent bot={} action={}", bot, action, e);
                }
            });
        } catch (Exception e) {
            LOG.error("action failure mail not scheduled bot={} action={}", bot, action, e);
        }
    }

    /** The synchronous send: bot name lookup, template fill and one SMTP message to the support address. */
    void deliver(String bot, String action, Map<String, Object> slotValues, Object userText, String stackTrace) throws Exception {
        String botName = botName(bot);
        if (action == null) {
            // str.replace("ACTION_NAME", None) raises TypeError in Python; no mail goes out.
            throw new IllegalArgumentException("replace() argument 2 must be str, not None");
        }
        String email = settings.getSupportMail();
        String body = body(botName, action, stackTrace, userText, slotValues, settings.getActionServerUrl(), email,
                settings.getFrontendUrl());
        String subject = subjectTemplate.replace("BOT_NAME", botName);
        if (email == null || email.isBlank() || !email.contains("@")) {
            throw new IllegalArgumentException("Please check if email is valid");
        }
        mailer.send(smtp, sender, List.of(email), subject, body);
    }

    /** Bot.objects(id=bot).only("name").get().name; a missing bot raises DoesNotExist and no mail goes out. */
    String botName(String bot) {
        Document found = catalog.findById("bot", bot)
                .orElseThrow(() -> new IllegalStateException("Bot matching query does not exist."));
        Object name = found.get("name");
        if (name == null) {
            throw new IllegalStateException("Bot has no name");
        }
        return String.valueOf(name);
    }

    /** __handle_action_failure followed by the FIRST_NAME / USER_EMAIL / BASE_URL replacements of format_and_send_mail. */
    static String body(String botName, String action, String stackTrace, Object userText, Map<String, Object> slotValues,
                       String actionUrl, String email, String baseUrl) {
        String body = TEMPLATE;
        body = body.replace("BOT_NAME", botName);
        body = body.replace("ACTION_NAME", action);
        body = body.replace("STACK_TRACE", PyRepr.str(stackTrace == null ? "NA" : stackTrace));
        body = body.replace("USER_QUERY_HISTORY", PyRepr.str(userText));
        body = body.replace("SLOT_VALUES", PyRepr.str(slotValues == null ? Map.of() : slotValues));
        body = body.replace("ACTION_URL", PyRepr.str(actionUrl));
        body = body.replace("FIRST_NAME", FIRST_NAME);
        body = body.replace("USER_EMAIL", email == null ? "" : email);
        if (baseUrl != null && !baseUrl.isEmpty()) {
            body = body.replace("BASE_URL", baseUrl);
        }
        return body;
    }

    private static String load(String name) {
        try (InputStream in = FailureMail.class.getResourceAsStream("/templates/emails/" + name)) {
            if (in == null) {
                throw new IllegalStateException("missing email template " + name);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
