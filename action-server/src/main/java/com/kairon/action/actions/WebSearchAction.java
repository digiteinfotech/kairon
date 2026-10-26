package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Singleton
public class WebSearchAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(WebSearchAction.class);

    private final ActionSupport support;

    public WebSearchAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "web_search_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("web_search_action", context.bot, "name", context.actionName,
                "No Public search action found for given action and bot");
        Object botResponse = config.get("failure_response");
        Map<String, Object> slots = new LinkedHashMap<>();
        Object results = null;
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            String latest = context.tracker.userText();
            if (!Maps.isEmpty(latest)) {
                results = search(latest, config.get("topn"), config.get("website"), context.bot);
                if (results instanceof List<?> list && !list.isEmpty()) {
                    botResponse = support.formatSearch(cast(list));
                    if (!Maps.isEmpty(config.get("set_slot"))) {
                        slots.put(Maps.str(config.get("set_slot")), botResponse);
                    }
                }
            }
        } catch (Exception e) {
            LOG.error("web search failed", e);
            exception = ActionFlags.message(e);
            status = Kairon.FAIL;
            support.failureMail(context, e);
        } finally {
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("public_search_action_response", results);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        if (ActionFlags.enabled(config, "dispatch_response")) {
            ActionFlags.utterText(context.dispatcher, botResponse);
        }
        slots.put(Kairon.ACTION_RESPONSE, botResponse);
        return slots;
    }

    private List<Map<String, Object>> search(String text, Object topn, Object site, String bot) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("text", text);
        body.put("site", site == null ? "" : site);
        body.put("topn", topn);
        body.put("bot", bot);
        Object response = support.http().executeStrict("POST", support.settings().getWebSearchUrl(),
                Map.of("Content-Type", "application/json"), body, "json");
        Map<String, Object> map = Maps.map(response);
        Object code = map.get("error_code");
        if (!(code instanceof Number number) || number.intValue() != 0) {
            throw new ActionFailure(String.valueOf(response));
        }
        List<?> data = Maps.list(map.get("data"));
        if (data.isEmpty()) {
            throw new ActionFailure("No response retrieved!");
        }
        List<Map<String, Object>> results = new ArrayList<>();
        for (Object item : data) {
            Map<String, Object> row = Maps.map(item);
            Map<String, Object> mapped = new LinkedHashMap<>();
            mapped.put("title", row.get("title"));
            mapped.put("text", row.get("description"));
            mapped.put("link", row.get("url"));
            results.add(mapped);
        }
        return results;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> cast(List<?> list) {
        return (List<Map<String, Object>>) list;
    }
}
