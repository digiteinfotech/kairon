package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Jsons;
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
public class TwoStageFallbackAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(TwoStageFallbackAction.class);

    private final ActionSupport support;

    public TwoStageFallbackAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "two_stage_fallback";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("kairon_two_stage_fallback_action", context.bot, "name", context.actionName,
                "Two stage fallback action config not found");
        if (!config.containsKey("text_recommendations")) {
            throw new IllegalArgumentException("text_recommendations");
        }
        String exception = null;
        List<Map<String, Object>> recommendations = new ArrayList<>();
        Object recommendationsConfig = config.get("text_recommendations");
        Map<String, Object> textRecommendations = Maps.map(recommendationsConfig);
        if (Maps.truthy(recommendationsConfig) && Maps.truthy(textRecommendations.get("count"))) {
            int count = count(textRecommendations.get("count"));
            if (Maps.truthy(textRecommendations.get("use_intent_ranking"))) {
                Object ranking = context.tracker.latestMessage.get("intent_ranking");
                if (ranking == null) {
                    throw new NullPointerException("intent_ranking");
                }
                if (!(ranking instanceof List<?>)) {
                    throw new IllegalArgumentException("intent_ranking");
                }
                List<Map<String, Object>> intents = Maps.mapList(ranking);
                for (int i = 1; i < intents.size() && i < 1 + count; i++) {
                    try {
                        String text = exampleText(context.bot, Maps.str(intents.get(i).get("name")));
                        recommendations.add(Maps.of("text", text, "payload", text));
                    } catch (Exception e) {
                        exception = ActionFlags.message(e);
                        LOG.error("two stage example lookup failed", e);
                    }
                }
            } else {
                // MongoProcessor.search_training_examples: $text search, ordered by text score, limited to count
                String query = context.tracker.text();
                if (query != null && !query.isBlank()) {
                    for (Document document : support.catalog().searchText("training_examples", context.bot, query, count)) {
                        Object text = document.get("text");
                        recommendations.add(Maps.of("text", text, "payload", text));
                    }
                }
            }
        }
        if (Maps.truthy(config.get("trigger_rules"))) {
            for (Map<String, Object> rule : Maps.mapList(config.get("trigger_rules"))) {
                if (!rule.containsKey("payload") || rule.get("payload") == null) {
                    throw new IllegalArgumentException("payload");
                }
                String payload = String.valueOf(rule.get("payload"));
                Map<String, Object> button = new LinkedHashMap<>();
                if (Maps.truthy(rule.get("is_dynamic_msg"))) {
                    button.put("payload", "/" + payload + "{\"" + Kairon.USER_MSG + "\": \"" + py(context.tracker.text()) + "\"}");
                } else if (!Maps.isEmpty(rule.get("message"))) {
                    button.put("payload", "/" + payload + "{\"" + Kairon.USER_MSG + "\": \"" + py(rule.get("message")) + "\"}");
                } else {
                    button.put("payload", "/" + payload);
                }
                if (!rule.containsKey("text")) {
                    throw new IllegalArgumentException("text");
                }
                button.put("text", rule.get("text"));
                recommendations.add(button);
            }
        }
        if (!recommendations.isEmpty()) {
            context.dispatcher.buttons(Maps.str(config.get("fallback_message")), recommendations);
        } else {
            context.dispatcher.response(Kairon.UTTER_DEFAULT);
        }
        support.save(context, type(), Kairon.SUCCESS, exception, Jsons.pythonDumps(recommendations), null);
        return Map.of();
    }

    private String exampleText(String bot, String intent) {
        for (Document document : support.catalog().findByBot("training_examples", bot)) {
            if (active(document.get("status")) && intent != null
                    && intent.equalsIgnoreCase(Maps.str(document.get("intent")))) {
                String text = Maps.str(document.get("text"));
                if (text == null) {
                    break;
                }
                return text;
            }
        }
        throw new IllegalStateException("StopIteration");
    }

    private static int count(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        throw new IllegalArgumentException("count");
    }

    private static boolean active(Object status) {
        if (status instanceof Boolean flag) {
            return flag;
        }
        return "true".equalsIgnoreCase(String.valueOf(status));
    }

    private static String py(Object value) {
        return value == null ? "None" : String.valueOf(value);
    }
}
