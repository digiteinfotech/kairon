package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Jsons;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/** Posts the vector payload to the configured vector service. Embedding clients stay on that service. */
@Singleton
public class DatabaseAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(DatabaseAction.class);

    private final ActionSupport support;

    public DatabaseAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "database_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = null;
        Object response = null;
        Object botResponse = null;
        Object requestBody = null;
        String exception = null;
        String status = Kairon.SUCCESS;
        boolean dispatch = false;
        String failure = Kairon.FAILED_DOT;
        Map<String, Object> filled = new LinkedHashMap<>();
        try {
            if (faqDisabled(context.bot)) {
                throw new ActionFailure(Kairon.FAQ_DISABLED);
            }
            config = support.require("database_action", context.bot, "name", context.actionName,
                    "No Vector action found for given action and bot");
            Map<String, Object> responseConfig = Maps.map(config.get("response"));
            if (!responseConfig.containsKey("dispatch")) {
                throw new IllegalArgumentException("dispatch");
            }
            dispatch = Maps.truthy(responseConfig.get("dispatch"));
            failure = Maps.str(config.get("failure_response"));
            String collection = Maps.str(config.get("collection"));
            requestBody = payload(config.get("payload"), context);
            boolean trainingNeeded = trainingNeeded(context.bot, collection);
            if (Maps.isEmpty(support.settings().getVectorUrl())) {
                throw new ActionFailure("vector url is not configured");
            }
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("bot", context.bot);
            body.put("collection", collection);
            body.put("collection_name", context.bot + "_" + collection + "_faq_embd");
            body.put("db_type", config.get("db_type"));
            body.put("payload", requestBody);
            body.put("user", context.tracker.senderId);
            body.put("training_needed", trainingNeeded);
            response = support.http().executeStrict("POST", support.settings().getVectorUrl(),
                    Map.of("Content-Type", "application/json"), body, "json");
            Map<String, Object> responseContext = new LinkedHashMap<>();
            responseContext.put("data", response);
            responseContext.put("context", support.context(context.tracker, true));
            botResponse = support.compose(responseConfig, responseContext);
            filled.putAll(support.fillSlots(config.get("set_slots"), responseContext));
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("database action failed", e);
            status = Kairon.FAIL;
            botResponse = failure;
            support.failureMail(context.bot, context.actionName, context.tracker.text(), exception);
        } finally {
            if (dispatch) {
                ActionFlags.utterText(context.dispatcher, botResponse);
            }
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("config", config);
            extra.put("payload", requestBody == null ? null : String.valueOf(requestBody));
            extra.put("response", response == null ? null : String.valueOf(response));
            support.save(context, type(), status, exception, botResponse, extra);
        }
        filled.put(Kairon.ACTION_RESPONSE, botResponse);
        return filled;
    }

    private boolean faqDisabled(String bot) {
        Optional<Document> settings = support.botSettings(bot);
        if (settings.isEmpty()) {
            return true;
        }
        Object llm = settings.get().get("llm_settings");
        if (!(llm instanceof Map<?, ?>)) {
            throw new IllegalArgumentException("llm_settings");
        }
        Map<String, Object> map = Maps.map(llm);
        if (!map.containsKey("enable_faq")) {
            throw new IllegalArgumentException("enable_faq");
        }
        return Maps.isEmpty(map.get("enable_faq"));
    }

    private boolean trainingNeeded(String bot, String collection) {
        for (Document document : support.catalog().findByBot("cognition_schema", bot)) {
            if (collection != null && collection.equals(document.get("collection_name"))) {
                Map<String, Object> metadata = Maps.map(document.get("schema_metadata"));
                return Maps.truthy(metadata.get("training_needed"));
            }
        }
        throw new ActionFailure("Cognition schema not found");
    }

    private Map<String, Object> payload(Object spec, ActionContext context) {
        Map<String, Object> request = new LinkedHashMap<>();
        for (Map<String, Object> item : Maps.mapList(spec)) {
            Object value;
            if ("from_slot".equals(item.get("type"))) {
                value = context.tracker.slotValue(Maps.str(item.get("value")));
            } else if ("from_user_message".equals(item.get("type"))) {
                value = context.tracker.userText();
            } else {
                value = item.get("value");
            }
            if ("payload_search".equals(item.get("query_type"))) {
                if (value instanceof String text) {
                    Object parsed = Jsons.readAny(text);
                    if (!(parsed instanceof Map<?, ?>) && !(parsed instanceof java.util.List<?>)) {
                        throw new ActionFailure("Error converting payload to JSON: " + value);
                    }
                    request.put("payload_search", parsed);
                } else {
                    request.put("payload_search", value);
                }
            } else if (!request.containsKey("embedding_search")) {
                request.put("embedding_search", value);
            } else {
                request.put("embedding_search", request.get("embedding_search") + " " + value);
            }
        }
        return request;
    }
}
