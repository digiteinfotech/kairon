package com.kairon.action.support;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;
import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.MemoryActionCatalog;
import jakarta.mail.Multipart;
import jakarta.mail.internet.MimeMessage;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-039: dispatch-and-logging R6 (failure mail to the support address). */
class FailureMailTest {

    private static final String BOT = "6697add6b8e47524eb983373";

    private GreenMail greenMail;
    private MemoryActionCatalog catalog;
    private ActionSettings settings;

    @BeforeEach
    void setUp() {
        greenMail = new GreenMail(ServerSetupTest.SMTP.dynamicPort());
        greenMail.start();
        greenMail.setUser("noreply@kairon.test", "smtp-user", "smtp-pass");
        catalog = new MemoryActionCatalog();
        catalog.put("bot", new Document("_id", new ObjectId(BOT)).append("name", "Support Bot"));
        settings = new ActionSettings();
        settings.setSupportMail("support@kairon.test");
        settings.setActionServerUrl("http://actions.test/webhook");
        settings.setFrontendUrl("https://app.kairon.test");
    }

    @AfterEach
    void tearDown() {
        greenMail.stop();
    }

    private FailureMail mail(int port, java.util.concurrent.Executor executor) {
        return new FailureMail(catalog, settings, new SmtpMailer(),
                new SmtpMailer.SmtpConfig("127.0.0.1", port, "smtp-user", "smtp-pass", false),
                "noreply@kairon.test", "kAIron Action Failure - BOT_NAME", executor);
    }

    private static Map<String, Object> slots() {
        Map<String, Object> slots = new LinkedHashMap<>();
        slots.put("bot", BOT);
        slots.put("city", null);
        slots.put("ok", true);
        return slots;
    }

    @Test
    void sendsOneMessageToSupportAddressWithFailureDetails() throws Exception {
        FailureMail mail = mail(greenMail.getSmtp().getPort(), Runnable::run);
        String trace = FailureMail.stackTrace(new IllegalStateException("upstream down"));
        mail.trigger(BOT, "http_weather", slots(), "what is the weather", trace);
        MimeMessage[] received = greenMail.getReceivedMessages();
        assertEquals(1, received.length);
        MimeMessage message = received[0];
        assertEquals("kAIron Action Failure - Support Bot", message.getSubject());
        assertEquals("support@kairon.test", message.getAllRecipients()[0].toString());
        assertEquals("noreply@kairon.test", message.getFrom()[0].toString());
        String body = String.valueOf(((Multipart) message.getContent()).getBodyPart(0).getContent());
        assertTrue(body.contains("Support Bot"), "bot name");
        assertTrue(body.contains("http_weather"), "action name");
        assertTrue(body.contains("java.lang.IllegalStateException: upstream down"), "exception text");
        assertTrue(body.contains("at com.kairon.action.support.FailureMailTest"), "stack trace");
        assertTrue(body.contains("{'bot': '" + BOT + "', 'city': None, 'ok': True}"), "slot values as Python str(dict)");
        assertTrue(body.contains("what is the weather"), "latest user text");
        assertTrue(body.contains("http://actions.test/webhook"), "action url");
        assertTrue(body.contains("Hi <strong>Team kAIron</strong>,"), "first name");
        assertTrue(body.contains("https://app.kairon.test/assets/logo/kAIron.png"), "base url");
    }

    @Test
    void bodyFollowsPythonTemplateReplacements() {
        String body = FailureMail.body("B", "act", "trace", null, Map.of(), "http://u", "s@x.test", "https://f");
        assertTrue(body.contains(">None</pre>"), "user text None renders as Python str(None)");
        assertTrue(body.contains(">{}</pre>"), "empty slots render as {}");
        assertFalse(body.contains("BOT_NAME") || body.contains("ACTION_NAME") || body.contains("STACK_TRACE")
                || body.contains("SLOT_VALUES") || body.contains("USER_QUERY_HISTORY") || body.contains("ACTION_URL")
                || body.contains("FIRST_NAME") || body.contains("BASE_URL"));
    }

    @Test
    void triggerReturnsBeforeTheSendCompletes() throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch sent = new CountDownLatch(1);
        FailureMail mail = mail(greenMail.getSmtp().getPort(), task -> Thread.ofVirtual().start(() -> {
            try {
                release.await(10, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            task.run();
            sent.countDown();
        }));
        mail.trigger(BOT, "act", slots(), "hi", "trace");
        assertEquals(1, sent.getCount(), "trigger returned while the send is still pending");
        assertEquals(0, greenMail.getReceivedMessages().length);
        release.countDown();
        assertTrue(sent.await(10, TimeUnit.SECONDS));
        assertEquals(1, greenMail.getReceivedMessages().length);
    }

    @Test
    void smtpFailureIsSwallowed() {
        FailureMail mail = mail(greenMail.getSmtp().getPort() + 1, Runnable::run);
        mail.trigger(BOT, "act", slots(), "hi", "trace");
        assertEquals(0, greenMail.getReceivedMessages().length);
    }

    @Test
    void unknownBotSendsNothing() {
        FailureMail mail = mail(greenMail.getSmtp().getPort(), Runnable::run);
        mail.trigger("000000000000000000000000", "act", slots(), "hi", "trace");
        mail.trigger(null, "act", slots(), "hi", "trace");
        assertEquals(0, greenMail.getReceivedMessages().length);
    }

    @Test
    void actionSupportRoutesContextFailureToMail() {
        FailureMail mail = mail(greenMail.getSmtp().getPort(), Runnable::run);
        ActionSupport support = new ActionSupport(catalog, settings, null, null, mail);
        support.failureMail(BOT, "act", (com.kairon.action.runtime.TrackerState) null, new RuntimeException("x"));
        assertEquals(1, greenMail.getReceivedMessages().length);
    }
}
