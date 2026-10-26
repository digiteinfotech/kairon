package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

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
        boolean rephrase = settings != null && Maps.truthy(settings.get("rephrase_response"));
        List<Map<String, Object>> responses = Maps.mapList(Maps.map(context.domain.get("responses")).get(context.actionName));
        Map<String, Object> botResponse = new LinkedHashMap<>();
        botResponse.put("response", context.actionName);
        String status = Kairon.SUCCESS;
        String exception = null;
        boolean rephrased = false;
        try {
            Map<String, Object> chosen = responses.get(ThreadLocalRandom.current().nextInt(responses.size()));
            String text = Maps.str(chosen.get("text"));
            if (!responses.isEmpty() && rephrase && !Maps.isEmpty(text) && !Maps.isEmpty(support.settings().getLlmUrl())) {
                Map<String, Object> body = new LinkedHashMap<>();
                body.put("bot", context.bot);
                body.put("text", text);
                body.put("invocation", "rephrase");
                HttpCaller.Exchange exchange = support.http().exchange("POST", support.settings().getLlmUrl(), Map.of(), body, "json");
                String content = Maps.str(Maps.map(exchange.body()).get("content"));
                if (!Maps.isEmpty(content) && exchange.status() == 200) {
                    rephrased = true;
                    botResponse = new LinkedHashMap<>();
                    botResponse.put("text", content);
                }
            }
        } catch (RuntimeException e) {
            exception = e.getMessage();
            status = Kairon.FAIL;
            support.failureMail(context.bot, context.actionName, context.tracker.text(), exception);
        }
        support.save(context, type(), status, exception, botResponse, Maps.of("enable_rephrasing", rephrase, "is_rephrased", rephrased));
        if (botResponse.containsKey("text") && !botResponse.containsKey("response")) {
            context.dispatcher.text(Maps.str(botResponse.get("text")));
        } else {
            context.dispatcher.response(Maps.str(botResponse.get("response")));
        }
        return Maps.of(Kairon.ACTION_RESPONSE, botResponse);
    }
}
