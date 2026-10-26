package com.kairon.action.support;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * outbound-clients R7 c4. Golden files are the output of Python ActionUtility.prepare_message_trail +
 * prepare_email_body (functions extracted verbatim from kairon/shared/actions/utils.py, templates from
 * template/emails, frontend_url http://localhost:3000) for the same events.
 */
class EmailTemplatesTest {

    private ActionSupport support;

    @BeforeEach
    void setUp() {
        ActionSettings settings = new ActionSettings();
        settings.setFrontendUrl("http://localhost:3000");
        support = new ActionSupport(new MemoryActionCatalog(), settings, new Tokens(settings), new HttpCaller(settings));
    }

    private static Map<String, Object> event(Object... pairs) {
        Map<String, Object> map = new HashMap<>();
        for (int i = 0; i < pairs.length; i += 2) {
            map.put((String) pairs[i], pairs[i + 1]);
        }
        return map;
    }

    private static Map<String, Object> ordered(Object... pairs) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i < pairs.length; i += 2) {
            map.put((String) pairs[i], pairs[i + 1]);
        }
        return map;
    }

    private static List<Map<String, Object>> events() {
        List<Map<String, Object>> events = new ArrayList<>();
        events.add(event("event", "session_started", "timestamp", 1700000000.5));
        events.add(event("event", "user", "text", "hello"));
        events.add(event("event", "bot", "text", "Hi there", "data", Map.of()));
        events.add(event("event", "user", "text", "/greet"));
        events.add(event("event", "bot", "text", null, "data", ordered("buttons", List.of(
                ordered("text", "Yes", "payload", "/yes"), ordered("text", "No"), ordered("payload", "/x")))));
        events.add(event("event", "bot", "text", null, "data", ordered("custom", ordered("data", List.of(
                ordered("type", "paragraph", "children", List.of(ordered("text", "plain "), ordered("text", "bold", "bold", true),
                        ordered("text", "all", "bold", true, "italic", true, "strikethrough", true))),
                ordered("type", "image", "src", "https://x/img.png", "alt", "pic", "children", List.of(ordered("text", ""))),
                ordered("type", "link", "href", "https://kairon.ai", "children", List.of(ordered("text", "site"))),
                ordered("type", "video", "url", "https://video/v.mp4", "children", List.of(ordered("text", ""))),
                ordered("text", "raw text"))))));
        events.add(event("event", "bot", "text", null, "data", ordered("custom", ordered("disconnect", true, "msg", "it's"))));
        events.add(event("event", "bot", "text", null, "data", Map.of()));
        events.add(event("event", "user", "text", "café 😀"));
        return events;
    }

    private static String golden(String name) throws Exception {
        try (InputStream in = EmailTemplatesTest.class.getResourceAsStream("/golden/" + name)) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    @Test
    void chatLogHtmlMatchesPythonWithRecipient() throws Exception {
        List<Map<String, Object>> trail = support.messageTrail(events()).messages();
        assertEquals(golden("chatlog-with-email.html"), support.emailBody(trail, "Chat history", "user@example.com"));
    }

    @Test
    void chatLogHtmlMatchesPythonWithoutRecipient() throws Exception {
        List<Map<String, Object>> trail = support.messageTrail(events()).messages();
        assertEquals(golden("chatlog-no-email.html"), support.emailBody(trail, "Ticket"));
    }

    @Test
    void nonStringUserTextRaisesLikePython() {
        List<Map<String, Object>> trail = new ArrayList<>();
        trail.add(event("user", null));
        ActionFailure failure = assertThrows(ActionFailure.class, () -> support.emailBody(trail, "s"));
        assertEquals("replace() argument 2 must be str, not None", failure.getMessage());
    }
}
