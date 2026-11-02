package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * kairon_bot_response (bot_response.py). LLM rephrase is out of scope: the response is always uttered by name,
 * the log carries the bot's rephrase_response flag as enable_rephrasing, is_rephrased false and raw_gpt_response null.
 */
@Singleton
public class BotResponseAction implements KaironAction {

    private final ActionSupport support;

    public BotResponseAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "kairon_bot_response";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document settings = support.botSettings(context.bot).orElse(null);
        boolean enableRephrasing = settings != null && Maps.truthy(settings.get("rephrase_response"));
        // Python domain[DOMAIN.RESPONSES] is outside try: missing key is untyped KeyError "'responses'".
        if (context.domain == null || !context.domain.containsKey("responses")) {
            throw new ActionFailure("'responses'");
        }
        List<Map<String, Object>> responses = Maps.mapList(Maps.map(context.domain.get("responses")).get(context.actionName));
        Map<String, Object> botResponse = new LinkedHashMap<>();
        botResponse.put("response", context.actionName);
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            // random.choice(static_response) raises on an empty list before any rephrase decision
            if (responses.isEmpty()) {
                throw new IndexOutOfBoundsException("Cannot choose from an empty sequence");
            }
        } catch (RuntimeException e) {
            exception = e.getMessage();
            status = Kairon.FAIL;
            support.failureMail(context, e);
        }
        Map<String, Object> extra = new LinkedHashMap<>();
        extra.put("enable_rephrasing", enableRephrasing);
        extra.put("is_rephrased", false);
        extra.put("raw_gpt_response", null);
        support.save(context, type(), status, exception, botResponse, extra);
        context.dispatcher.response(context.actionName);
        return Maps.of(Kairon.ACTION_RESPONSE, botResponse);
    }
}
