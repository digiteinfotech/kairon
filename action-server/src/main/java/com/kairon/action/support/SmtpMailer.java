package com.kairon.action.support;

import jakarta.inject.Singleton;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.Transport;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Properties;
import java.util.function.Function;

/**
 * Port of Python MailUtility.trigger_email (kairon/shared/utils.py): plain SMTP connect, STARTTLS
 * when the tls flag is set (never implicit SSL), login with the user id or else the sender address,
 * and a multipart/alternative message with a single HTML part.
 */
@Singleton
public class SmtpMailer {

    /** smtplib.SMTP(..., timeout=10). */
    static final int TIMEOUT_MILLIS = 10_000;

    /** Resolved SMTP settings. {@code userId} may be blank, in which case the sender address logs in. */
    public record SmtpConfig(String host, int port, String userId, String password, boolean tls) {}

    /** email_action subject: {@code "{sender_id} {subject}"}. */
    public static String subject(String senderId, String subject) {
        return senderId + " " + subject;
    }

    /**
     * email_action loop: one message (and one SMTP session) per recipient, subject
     * {@code "{sender_id} {subject}"}, HTML body built per recipient.
     */
    public void sendEach(SmtpConfig config, String from, List<String> recipients, String senderId, String subject,
                         Function<String, String> htmlBody) throws MessagingException {
        String fullSubject = subject(senderId, subject);
        for (String recipient : recipients) {
            send(config, from, List.of(recipient), fullSubject, htmlBody.apply(recipient));
        }
    }

    /** trigger_email: one message to all given recipients over one SMTP session. */
    public void send(SmtpConfig config, String from, List<String> recipients, String subject, String html) throws MessagingException {
        Session session = Session.getInstance(properties(config));
        MimeMessage message = new MimeMessage(session);
        message.setFrom(new InternetAddress(from));
        message.setRecipients(Message.RecipientType.TO, String.join(",", recipients));
        message.setSubject(subject, StandardCharsets.UTF_8.name());
        MimeBodyPart part = new MimeBodyPart();
        part.setContent(html == null ? "" : html, "text/html; charset=utf-8");
        MimeMultipart alternative = new MimeMultipart("alternative");
        alternative.addBodyPart(part);
        message.setContent(alternative);
        message.saveChanges();
        InternetAddress[] to = recipients.stream().map(SmtpMailer::address).toArray(InternetAddress[]::new);
        String login = config.userId() == null || config.userId().isBlank() ? from : config.userId();
        try (Transport transport = session.getTransport("smtp")) {
            transport.connect(config.host(), config.port(), login, config.password());
            transport.sendMessage(message, to);
        }
    }

    static Properties properties(SmtpConfig config) {
        Properties props = new Properties();
        props.put("mail.smtp.host", config.host());
        props.put("mail.smtp.port", String.valueOf(config.port()));
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.ssl.enable", "false");
        props.put("mail.smtp.connectiontimeout", String.valueOf(TIMEOUT_MILLIS));
        props.put("mail.smtp.timeout", String.valueOf(TIMEOUT_MILLIS));
        props.put("mail.smtp.writetimeout", String.valueOf(TIMEOUT_MILLIS));
        // smtplib.starttls() raises when the server does not offer STARTTLS, so it is required, not opportunistic.
        props.put("mail.smtp.starttls.enable", String.valueOf(config.tls()));
        props.put("mail.smtp.starttls.required", String.valueOf(config.tls()));
        return props;
    }

    private static InternetAddress address(String text) {
        try {
            return new InternetAddress(text);
        } catch (MessagingException e) {
            throw new IllegalArgumentException("Invalid email address: " + text, e);
        }
    }
}
