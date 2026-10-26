package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.runtime.RequestIds;
import com.kairon.action.server.ActionProcessor;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Jsons;
import com.kairon.action.support.Maps;
import jakarta.inject.Provider;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * Children run in-process. An HTTP call back into this Netty server deadlocks,
 * and Provider breaks the factory to processor cycle.
 */
@Singleton
public class ParallelAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(ParallelAction.class);

    private final ActionSupport support;
    private final Provider<ActionProcessor> processor;

    public ParallelAction(ActionSupport support, Provider<ActionProcessor> processor) {
        this.support = support;
        this.processor = processor;
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
        String status = Kairon.SUCCESS;
        String exception = null;
        Object botResponse = null;
        try {
            Document config = support.require("parallel_action_config", context.bot, "name", context.actionName,
                    "No parallel action found for given action and bot");
            if (!config.containsKey("actions") || !config.containsKey("dispatch_response_text")
                    || !config.containsKey("response_text")) {
                throw new IllegalArgumentException("parallel config");
            }
            dispatch = Maps.truthy(config.get("dispatch_response_text"));
            responseText = config.get("response_text");
            logId = insertStub();
            List<Object> results = runChildren(context, config.get("actions"), logId);
            extractSlots(results, filled);
        } catch (Exception e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            exception = ActionFlags.message(e);
            LOG.error("parallel action failed", e);
            status = Kairon.FAIL;
            support.failureMail(context.bot, context.actionName, context.tracker.text(), exception);
        } finally {
            if (dispatch) {
                if (Maps.truthy(responseText)) {
                    ActionFlags.utterText(context.dispatcher, responseText);
                }
                filled.put(Kairon.ACTION_RESPONSE, responseText);
                botResponse = responseText;
            }
            if (logId == null) {
                logId = insertStub();
            }
            Document log = new Document();
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

    private Object insertStub() {
        Document stub = new Document();
        stub.put("request_id", RequestIds.get());
        return support.catalog().insert(Kairon.LOGS, stub).get("_id");
    }

    private List<Object> runChildren(ActionContext context, Object names, Object logId) throws InterruptedException {
        String parentRequest = RequestIds.get();
        List<Callable<Object>> tasks = new ArrayList<>();
        for (Object name : Maps.list(names)) {
            String child = String.valueOf(name);
            tasks.add(() -> childCall(context, child, logId, parentRequest));
        }
        List<Object> results = new ArrayList<>();
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

    private Object childCall(ActionContext context, String name, Object logId, String requestId) {
        RequestIds.set(requestId);
        try {
            Map<String, Object> copy = Jsons.readMap(Jsons.write(context.actionCall));
            copy.put("next_action", name);
            Map<String, Object> trigger = new LinkedHashMap<>();
            trigger.put("trigger_name", context.actionName);
            trigger.put("trigger_type", "parallel_action");
            trigger.put("trigger_id", logId == null ? "" : String.valueOf(logId));
            copy.put("trigger_info", trigger);
            return processor.get().handle(copy);
        } catch (Exception e) {
            return e;
        } finally {
            RequestIds.clear();
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
