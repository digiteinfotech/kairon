package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.actions.database.DbPayload;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import com.kairon.action.support.llm.CognitionSchemas;
import com.kairon.action.support.llm.LlmSecrets;
import com.kairon.action.support.llm.QdrantClient;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * database.py {@code ActionDatabase.execute}: FAQ gate, config, db_type, Qdrant/LLMProcessor setup (llm_type
 * {@code openai} = DEFAULT_LLM, its secret doubles as the embedding secret), cognition schema, openrouter swap when
 * {@code training_needed} is false, payload, point query (embedding via the LLM server), compose, set_slots.
 */
@Singleton
public class DatabaseAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(DatabaseAction.class);

    private final ActionSupport support;
    private final LlmSecrets secrets;
    private final CognitionSchemas schemas;
    private final QdrantClient qdrant;

    public DatabaseAction(ActionSupport support, LlmSecrets secrets, CognitionSchemas schemas, QdrantClient qdrant) {
        this.support = support;
        this.secrets = secrets;
        this.schemas = schemas;
        this.qdrant = qdrant;
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
            // retrieve_config: to_mongo() view (defaults applied, _id popped)
            config = ConfigViews.database(support.require("database_action", context.bot, "name",
                    context.actionName, "No Vector action found for given action and bot"));
            Map<String, Object> responseConfig = Maps.map(config.get("response"));
            dispatch = Maps.truthy(responseConfig.get("dispatch"));
            failure = Maps.str(config.get("failure_response"));
            ActionFlags.require(config, "collection");
            String collection = Maps.str(config.get("collection"));
            if (!"qdrant".equals(config.get("db_type"))) {
                throw new ActionFailure("Database not yet implemented!");
            }
            // Qdrant(...) builds LLMProcessor(bot, DEFAULT_LLM): openai secret loaded here; for openai the
            // embedding secret is that same secret (LlmSecrets.embeddingSecret).
            String llmType = LlmSecrets.DEFAULT_LLM;
            Map<String, String> embeddingSecret = secrets.embeddingSecret(context.bot, llmType);
            CognitionSchemas.Schema schema = schemas.forAction(context.bot, collection);
            if (CognitionSchemas.databaseSwapsToOpenrouter(schema)) {
                llmType = CognitionSchemas.OPENROUTER;
                embeddingSecret = secrets.secret(context.bot, CognitionSchemas.OPENROUTER);
            }
            requestBody = DbPayload.build(config.get("payload"), context.tracker);
            messages.add(requestBody);
            response = qdrant.query(context.bot, collection, requestBody, llmType, embeddingSecret,
                    context.tracker.senderId);
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
            // ActionServerLogs(..., user_msg=...) keyword order: user_msg after response.
            extra.put("user_msg", context.tracker.text());
            // bot_response=str(bot_response) if bot_response else None: a falsy value is a declared None (omitted).
            support.save(context, type(), status, exception, Maps.truthy(botResponse) ? botResponse : null, extra);
        }
        filled.put(Kairon.ACTION_RESPONSE, botResponse);
        return filled;
    }
}
