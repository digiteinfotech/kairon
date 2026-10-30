package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.actions.database.DbPayload;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

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
        List<Object> messages = new ArrayList<>();
        Map<String, Object> filled = new LinkedHashMap<>();
        try {
            FaqGate.require(support, context.bot);
            config = support.require("database_action", context.bot, "name", context.actionName,
                    "No Vector action found for given action and bot");
            Map<String, Object> responseConfig = Maps.map(config.get("response"));
            if (!responseConfig.containsKey("dispatch")) {
                throw new IllegalArgumentException("dispatch");
            }
            dispatch = Maps.truthy(responseConfig.get("dispatch"));
            failure = Maps.str(config.get("failure_response"));
            String collection = Maps.str(config.get("collection"));
            if (!"qdrant".equals(config.get("db_type"))) {
                throw new ActionFailure("Database not yet implemented!");
            }
            boolean trainingNeeded = trainingNeeded(context.bot, collection);
            requestBody = DbPayload.build(config.get("payload"), context.tracker);
            messages.add(requestBody);
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
            ActionSupport.Composed composed = support.composeLogged(responseConfig, responseContext);
            botResponse = composed.result();
            messages.add(composed.log());
            ActionSupport.SlotFill slotFill = support.fillSlotsLogged(config.get("set_slots"), responseContext);
            messages.addAll(slotFill.log());
            filled.putAll(slotFill.values());
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("database action failed", e);
            status = Kairon.FAIL;
            botResponse = failure;
            support.failureMail(context, e);
        } finally {
            if (dispatch) {
                ActionFlags.utterText(context.dispatcher, botResponse);
            }
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("config", config);
            extra.put("payload", Maps.isEmpty(requestBody) ? null : PyRepr.str(requestBody));
            extra.put("response", Maps.isEmpty(response) ? null : PyRepr.str(response));
            extra.put("messages", messages);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        filled.put(Kairon.ACTION_RESPONSE, botResponse);
        return filled;
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
}
