package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.runtime.RequestIds;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Jsons;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * Port of kairon/actions/definitions/custom_parallel_actions.py. Each child action is a POST of the
 * original request (next_action and trigger_info replaced) to this server's own webhook URL
 * ({@code action.url} / ACTION_SERVER_URL) carrying the parent's X-Kairon-Request-ID. The webhook runs
 * on the blocking (virtual thread) executor, so the loopback call does not tie up the Netty event loop.
 * Child utterances are discarded; only child slot events are merged, last write wins in child order.
 */
@Singleton
public class ParallelAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(ParallelAction.class);

    private final ActionSupport support;

    public ParallelAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "parallel_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Map<String, Object> filled = new LinkedHashMap<>();
        boolean dispatch = false;
        Object responseText = null;
        Object logId = null;
        Date created = null;
        String status = Kairon.SUCCESS;
        String exception = null;
        Object botResponse = null;
        try {
            Document config = support.require("parallel_action_config", context.bot, "name", context.actionName,
                    "No parallel action found for given action and bot");
            Object actions = ActionFlags.require(config, "actions");
            ActionFlags.require(config, "dispatch_response_text");
            ActionFlags.require(config, "response_text");
            if (actions == null) {
                throw new ActionFailure("'NoneType' object is not iterable");
            }
            dispatch = Maps.truthy(config.get("dispatch_response_text"));
            responseText = config.get("response_text");
            created = new Date();
            logId = insertPreRecord(created);
            List<Object> results = runChildren(context, actions, logId);
            extractSlots(results, filled);
            context.succeeded(null);
        } catch (Exception e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            exception = ActionFlags.message(e);
            LOG.error("parallel action failed", e);
            status = Kairon.FAIL;
            support.failureMail(context, e);
        } finally {
            if (dispatch) {
                if (Maps.truthy(responseText)) {
                    ActionFlags.utterText(context.dispatcher, responseText);
                }
                filled.put(Kairon.ACTION_RESPONSE, responseText);
                botResponse = responseText;
            }
            if (logId == null) {
                created = new Date();
                logId = insertPreRecord(created);
            }
            Document log = new Document();
            // mongoengine keeps the timestamp default set when Python first saved the pre-created record.
            log.put("timestamp", created);
            log.put("type", type());
            log.put("intent", context.tracker.intent());
            log.put("action", context.actionName);
            log.put("sender", context.tracker.senderId);
            log.put("exception", exception);
            log.put("bot_response", botResponse == null ? null : String.valueOf(botResponse));
            log.put("bot", context.bot);
            log.put("status", status);
            log.put("user_msg", context.tracker.text());
            log.put("request_id", RequestIds.get());
            Document trigger = new Document();
            trigger.put("trigger_name", context.trigger("trigger_name", ""));
            trigger.put("trigger_type", context.trigger("trigger_type", "implicit"));
            trigger.put("trigger_id", context.trigger("trigger_id", ""));
            log.put("trigger_info", trigger);
            support.catalog().replace(Kairon.LOGS, logId, log);
        }
        return filled;
    }

    /**
     * Python {@code ActionServerLogs(request_id=get_request_id()).save()}: mongoengine stores the field
     * defaults (timestamp, status, trigger_info) plus request_id, in declaration order. Its _id is the trigger_id.
     */
    private Object insertPreRecord(Date created) {
        Document record = new Document("_id", new ObjectId());
        record.put("timestamp", created);
        record.put("status", Kairon.SUCCESS);
        Document trigger = new Document();
        trigger.put("trigger_name", "");
        trigger.put("trigger_type", "implicit");
        trigger.put("trigger_id", "");
        record.put("trigger_info", trigger);
        String requestId = RequestIds.get();
        if (requestId != null) {
            record.put("request_id", requestId);
        }
        return support.catalog().insert(Kairon.LOGS, record).get("_id");
    }

    private List<Object> runChildren(ActionContext context, Object names, Object logId) throws InterruptedException {
        String parentRequest = RequestIds.get();
        String url = support.settings().getActionServerUrl();
        List<Callable<Object>> tasks = new ArrayList<>();
        for (Object name : Maps.list(names)) {
            String child = String.valueOf(name);
            tasks.add(() -> childCall(context, url, child, logId, parentRequest));
        }
        List<Object> results = new ArrayList<>();
        // asyncio.gather(..., return_exceptions=True): every child runs, errors become results.
        try (ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor()) {
            for (Future<Object> future : pool.invokeAll(tasks)) {
                try {
                    results.add(future.get());
                } catch (Exception e) {
                    results.add(e);
                }
            }
        }
        return results;
    }

    private Object childCall(ActionContext context, String url, String name, Object logId, String requestId) {
        try {
            Map<String, Object> body = Jsons.readMap(Jsons.write(context.actionCall));
            body.put("next_action", name);
            Map<String, Object> trigger = new LinkedHashMap<>();
            trigger.put("trigger_name", context.actionName);
            trigger.put("trigger_type", "parallel_action");
            trigger.put("trigger_id", String.valueOf(logId));
            body.put("trigger_info", trigger);
            Map<String, Object> headers = new LinkedHashMap<>();
            if (requestId != null && !requestId.isEmpty()) {
                headers.put(Kairon.REQUEST_ID, requestId);
            }
            HttpCaller.Exchange exchange = support.http().exchange("POST", url, headers, body, "json");
            if (exchange.transportFailed()) {
                LOG.warn("parallel_action child {} could not reach {}", name, url);
            }
            return exchange.body();
        } catch (Exception e) {
            LOG.warn("parallel_action child {} failed", name, e);
            return e;
        }
    }

    private static void extractSlots(List<Object> results, Map<String, Object> filled) {
        for (Object body : results) {
            if (!(body instanceof Map<?, ?> map) || !map.containsKey("events")) {
                continue;
            }
            for (Object event : Maps.list(map.get("events"))) {
                if (!(event instanceof Map<?, ?> raw)) {
                    continue;
                }
                Map<String, Object> slot = Maps.map(raw);
                if ("slot".equals(slot.get("event")) && raw.containsKey("name") && raw.containsKey("value")) {
                    filled.put(String.valueOf(slot.get("name")), raw.get("value"));
                }
            }
        }
    }
}
