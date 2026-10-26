package com.kairon.action.actions;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;
import com.kairon.action.Kairon;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.support.EmailTemplates;
import com.kairon.action.support.Jsons;
import com.kairon.action.support.Tokens;
import io.micronaut.runtime.server.EmbeddedServer;
import io.micronaut.test.extensions.junit5.annotation.MicronautTest;
import jakarta.inject.Inject;
import jakarta.mail.Multipart;
import jakarta.mail.internet.MimeMessage;
import org.bson.Document;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-040: integration-actions R2 c2-c3 (plus utterance, slot and log behaviour) against an in-process SMTP server. */
@MicronautTest
class EmailActionTest {

    private static final String BOT = "bot-mail";
    private static final HttpClient CLIENT = HttpClient.newHttpClient();
    private static final String FRONTEND = "http://front.test";

    @Inject
    EmbeddedServer server;

    @Inject
    MemoryActionCatalog catalog;

    @Inject
    Tokens tokens;

    private GreenMail greenMail;

    @BeforeEach
    void setUp() {
        catalog.clear();
        greenMail = new GreenMail(ServerSetupTest.SMTP.dynamicPort());
        greenMail.start();
        greenMail.setUser("bot@kairon.test", "smtp-user", "smtp-pass");
        catalog.put("actions", new Document("bot", BOT).append("name", "mail_me").append("type", "email_action").append("status", true));
        // Password comes from the bot key vault, Fernet-encrypted at rest.
        catalog.put("key_vault", new Document("bot", BOT).append("key", "SMTP_PASSWORD").append("value", tokens.encrypt("smtp-pass")));
    }

    @AfterEach
    void tearDown() {
        greenMail.stop();
    }

    private Document config(Object toEmail) {
        return new Document("bot", BOT).append("action_name", "mail_me").append("status", true)
                .append("smtp_url", "127.0.0.1")
                .append("smtp_port", greenMail.getSmtp().getPort())
                .append("smtp_userid", new Document("key", "smtp_userid").append("parameter_type", "value").append("value", "smtp-user"))
                .append("smtp_password", new Document("key", "smtp_password").append("parameter_type", "key_vault").append("value", "SMTP_PASSWORD"))
                .append("from_email", new Document("parameter_type", "slot").append("value", "sender_mail"))
                .append("to_email", new Document("parameter_type", "value").append("value", toEmail))
                .append("subject", "Order update")
                .append("response", "mail sent")
                .append("tls", false);
    }

    @Test
    void chatLogBodyOneMessagePerRecipientWithResolvedCredentials() throws Exception {
        List<String> recipients = List.of("first@example.com", "second@example.com");
        catalog.put("email_action_config", config(recipients));

        Map<String, Object> body = call();

        MimeMessage[] received = greenMail.getReceivedMessages();
        assertEquals(2, received.length, "one message per recipient");
        List<Map<String, Object>> chatLog = List.of(Map.of("user", "hi there"), Map.of("bot", Map.of("text", "hello user")));
        for (int i = 0; i < received.length; i++) {
            MimeMessage message = received[i];
            String recipient = recipients.get(i);
            assertEquals("sender-1 Order update", message.getSubject());
            assertEquals("bot@kairon.test", message.getFrom()[0].toString(), "from_email resolved from slot");
            assertEquals(1, message.getAllRecipients().length);
            assertEquals(recipient, message.getAllRecipients()[0].toString());
            String html = html(message);
            assertEquals(normalize(EmailTemplates.conversation(chatLog, "Order update", recipient, FRONTEND)), html);
            assertTrue(html.contains("hi there") && html.contains("hello user") && html.contains(recipient));
            assertFalse(html.contains("CONVERSATION_REPLACE") || html.contains("USER_EMAIL"));
        }
        assertEquals("mail sent", responses(body).get(0).get("text"));
        assertEquals("mail sent", slot(body, Kairon.ACTION_RESPONSE));
        Document log = log();
        assertEquals("email_action", log.get("type"));
        assertEquals("mail_me", log.get("action"));
        assertEquals(Kairon.SUCCESS, log.get("status"));
        assertEquals("mail sent", log.get("bot_response"));
        assertNull(log.get("exception"));
    }

    @Test
    void customTextBodyUsesPythonTemplate() throws Exception {
        Document config = config("only@example.com");
        config.append("custom_text", new Document("key", "custom_text").append("parameter_type", "slot").append("value", "note"));
        catalog.put("email_action_config", config);

        call();

        MimeMessage[] received = greenMail.getReceivedMessages();
        assertEquals(1, received.length);
        assertEquals("sender-1 Order update", received[0].getSubject());
        // ActionUtility.prepare_email_text over the Python template file itself.
        String template = Files.readString(Path.of("../template/emails/custom_text_mail.html"), StandardCharsets.UTF_8);
        String expected = template.replace("SUBJECT", "Order update").replace("USER_EMAIL", "only@example.com")
                .replace("CUSTOM_TEXT", "Please call me back").replace("BASE_URL", FRONTEND);
        assertEquals(normalize(expected), html(received[0]));
    }

    @Test
    void sendFailureUttersFailureAndLogsFailed() throws Exception {
        Document config = config("first@example.com");
        config.put("smtp_password", new Document("key", "smtp_password").append("parameter_type", "value").append("value", "wrong-pass"));
        catalog.put("email_action_config", config);

        Map<String, Object> body = call();

        assertEquals(0, greenMail.getReceivedMessages().length);
        assertEquals(Kairon.FAILED, responses(body).get(0).get("text"));
        assertEquals(Kairon.FAILED, slot(body, Kairon.ACTION_RESPONSE));
        Document log = log();
        assertEquals("email_action", log.get("type"));
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals(Kairon.FAILED, log.get("bot_response"));
        assertNotNull(log.get("exception"));
    }

    @Test
    void dispatchFalseSendsButUttersNothing() throws Exception {
        Document config = config("first@example.com");
        config.put("dispatch_bot_response", false);
        catalog.put("email_action_config", config);

        Map<String, Object> body = call();

        assertEquals(1, greenMail.getReceivedMessages().length);
        assertEquals(List.of(), body.get("responses"));
        assertEquals("mail sent", slot(body, Kairon.ACTION_RESPONSE));
    }

    private Map<String, Object> call() throws Exception {
        Map<String, Object> slots = new LinkedHashMap<>();
        slots.put("bot", BOT);
        slots.put("sender_mail", "bot@kairon.test");
        slots.put("note", "Please call me back");
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "sender-1");
        tracker.put("slots", slots);
        tracker.put("latest_message", Map.of("text", "hi there", "intent", Map.of("name", "greet")));
        tracker.put("events", List.of(
                Map.of("event", "user", "text", "hi there"),
                Map.of("event", "bot", "text", "hello user")));
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("next_action", "mail_me");
        request.put("tracker", tracker);
        request.put("domain", Map.of());
        HttpResponse<String> response = CLIENT.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + server.getPort() + "/webhook"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(Jsons.write(request))).build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode(), response.body());
        return Jsons.readMap(response.body());
    }

    private Document log() {
        List<Document> logs = catalog.all(Kairon.LOGS);
        assertEquals(1, logs.size());
        return logs.get(0);
    }

    private static String html(MimeMessage message) throws Exception {
        Multipart parts = (Multipart) message.getContent();
        assertEquals(1, parts.getCount());
        assertTrue(parts.getBodyPart(0).getContentType().startsWith("text/html"));
        return normalize(String.valueOf(parts.getBodyPart(0).getContent()));
    }

    private static String normalize(String text) {
        return text.replace("\r\n", "\n").strip();
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> responses(Map<String, Object> body) {
        return (List<Map<String, Object>>) body.get("responses");
    }

    @SuppressWarnings("unchecked")
    private static Object slot(Map<String, Object> body, String name) {
        for (Object item : (List<Object>) body.get("events")) {
            Map<String, Object> event = (Map<String, Object>) item;
            if (name.equals(event.get("name"))) {
                return event.get("value");
            }
        }
        throw new AssertionError("missing slot " + name + " in " + body);
    }
}
