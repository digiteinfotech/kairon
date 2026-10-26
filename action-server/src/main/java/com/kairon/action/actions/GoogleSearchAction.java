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

/** Searches with the Custom Search API. Without an API key the action fails closed and keeps failure_response. */
@Singleton
public class GoogleSearchAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(GoogleSearchAction.class);

    private final ActionSupport support;

    public GoogleSearchAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "google_search_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("google_search_action", context.bot, "name", context.actionName,
                "No Google search action found for given action and bot");
        Object botResponse = config.get("failure_response");
        Map<String, Object> slots = new LinkedHashMap<>();
        Object results = null;
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            String latest = context.tracker.userText();
            Map<String, Object> trackerData = support.context(context.tracker, true, context.bot);
            Object searchTerm = Maps.truthy(config.get("search_term"))
                    ? support.one(trackerData, config.get("search_term"), context.bot)
                    : latest;
            Object apiKey = support.one(trackerData, config.get("api_key"), context.bot);
            if (!Maps.isEmpty(latest)) {
                if (Maps.isEmpty(apiKey)) {
                    // Python falls back to googlesearch scraping with "<term> site: <website>"; the port fails closed.
                    throw new ActionFailure("Google search requires an api key; global search for '"
                            + globalSearchTerm(Maps.text(searchTerm), config.get("website")) + "' is not supported");
                }
                results = search(Maps.text(apiKey), Maps.text(config.get("search_engine_id")), Maps.text(searchTerm), config.get("num_results"));
                if (results instanceof List<?> list && !list.isEmpty()) {
                    botResponse = support.formatSearch(cast(list));
                    if (!Maps.isEmpty(config.get("set_slot"))) {
                        slots.put(Maps.str(config.get("set_slot")), botResponse);
                    }
                }
            }
        } catch (Exception e) {
            LOG.error("google search failed", e);
            exception = ActionFlags.message(e);
            status = Kairon.FAIL;
            support.failureMail(context.bot, context.actionName, context.tracker.text(), exception);
        } finally {
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("google_response", results);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        if (ActionFlags.enabled(config, "dispatch_response")) {
            ActionFlags.utterText(context.dispatcher, botResponse);
        }
        slots.put(Kairon.ACTION_RESPONSE, botResponse);
        return slots;
    }

    static final String CSE_URL = "https://customsearch.googleapis.com/customsearch/v1";

    /**
     * The request googleapiclient sends for service.cse().list(q=, cx=, num=) (utils.py:560-561):
     * q, cx, num (dropped when None), key, alt=json. Python pops `website` before this call
     * (utils.py:550), so the API-key path never sends siteSearch.
     */
    static Map<String, Object> cseQuery(String apiKey, String engine, String term, Object num) {
        Map<String, Object> query = new LinkedHashMap<>();
        query.put("q", term);
        query.put("cx", engine);
        if (num != null) {
            query.put("num", num);
        }
        query.put("key", apiKey);
        query.put("alt", "json");
        return query;
    }

    /** utils.py:555: the keyless global-search term, f"{search_term} site: {website}" when website is set. */
    static String globalSearchTerm(String term, Object website) {
        return Maps.truthy(website) ? term + " site: " + website : term;
    }

    private Object search(String apiKey, String engine, String term, Object num) {
        Map<String, Object> query = cseQuery(apiKey, engine, term, num);
        Object response = support.http().executeStrict("GET", CSE_URL, Map.of(), query, "json");
        List<Map<String, Object>> results = new ArrayList<>();
        for (Map<String, Object> item : Maps.mapList(Maps.map(response).get("items"))) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("title", item.get("title"));
            row.put("text", item.get("snippet"));
            row.put("link", item.get("link"));
            results.add(row);
        }
        return results;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> cast(List<?> list) {
        return (List<Map<String, Object>>) list;
    }
}
