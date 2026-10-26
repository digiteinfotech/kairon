package com.kairon.action.support;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-022: outbound-clients R7 c1-c3 (and the HTML body transport for c4). */
class SmtpMailerTest {

    private GreenMail greenMail;
    private final SmtpMailer mailer = new SmtpMailer();

    @BeforeEach
    void setUp() {
        greenMail = new GreenMail(ServerSetupTest.SMTP.dynamicPort());
        greenMail.start();
        greenMail.setUser("bot@kairon.test", "smtp-user", "smtp-pass");
        greenMail.setUser("owner@kairon.test", "owner@kairon.test", "owner-pass");
    }

    @AfterEach
    void tearDown() {
        greenMail.stop();
    }

    private SmtpMailer.SmtpConfig config(String user, String password, boolean tls) {
        return new SmtpMailer.SmtpConfig("127.0.0.1", greenMail.getSmtp().getPort(), user, password, tls);
    }

    @Test
    void sendsOneHtmlMessagePerRecipientWithSenderIdSubject() throws Exception {
        List<String> recipients = List.of("first@example.com", "second@example.com");
        mailer.sendEach(config("smtp-user", "smtp-pass", false), "bot@kairon.test", recipients, "user-42", "Order status",
                recipient -> "<html><body><p>Hello " + recipient + "</p></body></html>");

        MimeMessage[] received = greenMail.getReceivedMessages();
        assertEquals(2, received.length, "one message per recipient");
        for (int i = 0; i < received.length; i++) {
            MimeMessage message = received[i];
            assertEquals("user-42 Order status", message.getSubject());
            assertEquals("bot@kairon.test", message.getFrom()[0].toString());
            assertEquals(1, message.getAllRecipients().length);
            String recipient = recipients.get(i);
            assertEquals(recipient, message.getAllRecipients()[0].toString());
            assertTrue(message.getContentType().startsWith("multipart/alternative"), message.getContentType());
            Multipart parts = (Multipart) message.getContent();
            assertEquals(1, parts.getCount());
            assertTrue(parts.getBodyPart(0).getContentType().startsWith("text/html"), parts.getBodyPart(0).getContentType());
            assertEquals("<html><body><p>Hello " + recipient + "</p></body></html>", String.valueOf(parts.getBodyPart(0).getContent()).strip());
        }
    }

    @Test
    void loginFallsBackToSenderWhenUserIdBlank() throws Exception {
        mailer.send(config("", "owner-pass", false), "owner@kairon.test", List.of("a@example.com"), "s", "<p>x</p>");
        assertEquals(1, greenMail.getReceivedMessages().length);
    }

    @Test
    void wrongPasswordFailsLogin() {
        assertThrows(MessagingException.class,
                () -> mailer.send(config("smtp-user", "wrong", false), "bot@kairon.test", List.of("a@example.com"), "s", "<p>x</p>"));
        assertEquals(0, greenMail.getReceivedMessages().length);
    }

    @Test
    void wrongPortFails() {
        SmtpMailer.SmtpConfig closed = new SmtpMailer.SmtpConfig("127.0.0.1", greenMail.getSmtp().getPort() + 1, "smtp-user", "smtp-pass", false);
        assertThrows(MessagingException.class,
                () -> mailer.send(closed, "bot@kairon.test", List.of("a@example.com"), "s", "<p>x</p>"));
    }

    @Test
    void tlsFlagMeansRequiredStartTlsNeverImplicitSsl() {
        Properties tls = SmtpMailer.properties(config("u", "p", true));
        assertEquals("true", tls.getProperty("mail.smtp.starttls.enable"));
        assertEquals("true", tls.getProperty("mail.smtp.starttls.required"));
        assertEquals("false", tls.getProperty("mail.smtp.ssl.enable"));
        assertEquals("true", tls.getProperty("mail.smtp.auth"));
        assertEquals("10000", tls.getProperty("mail.smtp.timeout"));

        Properties plain = SmtpMailer.properties(config("u", "p", false));
        assertEquals("false", plain.getProperty("mail.smtp.starttls.enable"));
        assertEquals("false", plain.getProperty("mail.smtp.starttls.required"));
        assertEquals("false", plain.getProperty("mail.smtp.ssl.enable"));
    }

    @Test
    void tlsFlagNeverFallsBackToPlaintext() {
        // GreenMail's plain SMTP listener cannot complete a trusted STARTTLS handshake; smtplib.starttls() raises too.
        assertThrows(MessagingException.class,
                () -> mailer.send(config("smtp-user", "smtp-pass", true), "bot@kairon.test", List.of("a@example.com"), "s", "<p>x</p>"));
        assertEquals(0, greenMail.getReceivedMessages().length);
    }
}
