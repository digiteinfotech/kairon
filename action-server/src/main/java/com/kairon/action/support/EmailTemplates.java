package com.kairon.action.support;

import com.kairon.action.runtime.ActionFailure;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

/** Port of Python ActionUtility.prepare_email_body and its template/emails/*.html templates. */
public final class EmailTemplates {

    private static final String CONVERSATION = load("conversation.html");
    private static final String BOT_MSG = load("bot_msg_conversation.html");
    private static final String USER_MSG = load("user_msg_conversation.html");
    private static final String BUTTONS = load("button.html");

    /** The literal Python wraps each button text in before joining them with "\n". */
    private static final String BUTTON = "\n"
            + "                <div style=\"font-size: 14px; color: #000000; font-weight: 400; padding: 12px; overflow: hidden; word-wrap: break-word;\n"
            + "                            border: 2px solid #ffffff; margin: 8px 0px 0px 0px; text-align: center; border-radius: 20px; background: transparent;\n"
            + "                            background-color: inherit; color: #000; max-width: 250px; box-sizing: border-box;\">\n"
            + "                    BUTTON_TEXT\n"
            + "                </div>\n"
            + "                ";

    private EmailTemplates() {}

    public static String conversation(List<Map<String, Object>> events, String subject, String userEmail, String baseUrl) {
        StringBuilder html = new StringBuilder();
        for (Map<String, Object> event : events) {
            String first = event.isEmpty() ? null : String.valueOf(event.keySet().iterator().next());
            String msg = "";
            if ("bot".equals(first)) {
                msg = BOT_MSG.replace("BOT_MESSAGE", botReply(Maps.map(event.get("bot"))));
            } else if ("user".equals(first)) {
                Object user = event.containsKey("user") ? event.get("user") : "";
                msg = USER_MSG.replace("USER_MESSAGE", requireStr(user));
            }
            html.append(msg);
        }
        String output = html.toString();
        String template = CONVERSATION.replace("SUBJECT", requireStr(subject));
        if (!Maps.isEmpty(userEmail)) {
            template = template.replace("USER_EMAIL", userEmail);
        }
        // Python applies the CONVERSATION_REPLACE substitution twice.
        template = template.replace("CONVERSATION_REPLACE", output);
        template = template.replace("CONVERSATION_REPLACE", output);
        return template.replace("BASE_URL", requireStr(baseUrl));
    }

    private static String botReply(Map<String, Object> reply) {
        if (Maps.truthy(reply.get("text"))) {
            return requireStr(reply.get("text"));
        }
        if (Maps.truthy(reply.get("buttons"))) {
            StringBuilder buttons = new StringBuilder();
            for (Object button : Maps.list(reply.get("buttons"))) {
                Map<String, Object> btn = Maps.map(button);
                Object text = btn.containsKey("text") ? btn.get("text") : "";
                buttons.append('\n').append(BUTTON.replace("BUTTON_TEXT", requireStr(text)));
            }
            return BUTTONS.replace("ALL_BUTTONS", buttons.toString());
        }
        if (Maps.truthy(reply.get("custom"))) {
            Map<String, Object> custom = Maps.map(reply.get("custom"));
            if (Maps.truthy(custom.get("data"))) {
                StringBuilder joined = new StringBuilder();
                for (Object item : Maps.list(custom.get("data"))) {
                    joined.append(customReply(Maps.map(item)));
                }
                return joined.toString();
            }
            return PyRepr.str(reply.get("custom"));
        }
        return "";
    }

    private static String customReply(Map<String, Object> data) {
        if (data.get("text") != null) {
            return requireStr(data.get("text"));
        }
        if (!data.containsKey("children")) {
            throw new ActionFailure("'children'");
        }
        StringBuilder joined = new StringBuilder();
        for (Object child : Maps.list(data.get("children"))) {
            joined.append(customReply(Maps.map(child)));
        }
        String reply = joined.toString();
        Object type = data.get("type");
        if ("image".equals(type)) {
            String alt = PyRepr.str(data.get("alt"));
            reply = "<span><img src=\"" + PyRepr.str(data.get("src")) + "\" alt=\"" + alt
                    + "\" width=\"150\" height=\"150\"/><br/><p>" + alt + "</p></span>";
        } else if ("paragraph".equals(type)) {
            StringBuilder paragraph = new StringBuilder();
            for (Object item : Maps.list(data.get("children"))) {
                Map<String, Object> child = Maps.map(item);
                String text = child.containsKey("text") ? PyRepr.str(child.get("text")) : "";
                if (Maps.truthy(child.get("bold"))) {
                    text = "<b>" + text + "</b>";
                }
                if (Maps.truthy(child.get("italic"))) {
                    text = "<i>" + text + "</i>";
                }
                if (Maps.truthy(child.get("strikethrough"))) {
                    text = "<s>" + text + "</s>";
                }
                paragraph.append(text);
            }
            reply = paragraph.toString();
        } else if ("link".equals(type)) {
            reply = "<a target=\"_blank\" href=\"" + PyRepr.str(data.get("href")) + "\">" + reply + "</a>";
        } else if ("video".equals(type)) {
            String url = PyRepr.str(data.get("url"));
            reply = "<a target=\"_blank\" href=\"" + url + "\">" + url + "</a>";
        }
        return reply;
    }

    /** Python str.replace(old, new) raises TypeError unless new is a str. */
    private static String requireStr(Object value) {
        if (value instanceof String text) {
            return text;
        }
        throw new ActionFailure("replace() argument 2 must be str, not " + pyType(value));
    }

    private static String pyType(Object value) {
        if (value == null) {
            return "None";
        }
        if (value instanceof Boolean) {
            return "bool";
        }
        if (value instanceof Double || value instanceof Float) {
            return "float";
        }
        if (value instanceof Number) {
            return "int";
        }
        if (value instanceof Map<?, ?>) {
            return "dict";
        }
        if (value instanceof List<?>) {
            return "list";
        }
        return value.getClass().getSimpleName();
    }

    private static String load(String name) {
        try (InputStream in = EmailTemplates.class.getResourceAsStream("/templates/emails/" + name)) {
            if (in == null) {
                throw new IllegalStateException("missing email template " + name);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
