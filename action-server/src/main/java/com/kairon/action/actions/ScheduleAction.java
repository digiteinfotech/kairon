package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Jsons;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.Map;

@Singleton
public class ScheduleAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(ScheduleAction.class);
    private static final DateTimeFormatter SPACE = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final DateTimeFormatter MINUTE = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    private final ActionSupport support;

    public ScheduleAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "schedule_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        boolean dispatch = true;
        Object botResponse = null;
        String status = Kairon.SUCCESS;
        String exception = null;
        Object scheduleAction = null;
        Object scheduleTime = null;
        Object timezone = null;
        Object executionInfo = null;
        Object dataLog = null;
        try {
            Document config = support.require("schedule_action", context.bot, "name", context.actionName,
                    "No Schedule action found for given action and bot");
            dispatch = ActionFlags.enabled(config, "dispatch_bot_response");
            botResponse = config.get("response_text");
            if (!config.containsKey("schedule_action") || !config.containsKey("timezone")
                    || !config.containsKey("schedule_time") || !config.containsKey("params_list")
                    || !config.containsKey("schedule_action_type")) {
                throw new IllegalArgumentException("schedule config");
            }
            scheduleAction = config.get("schedule_action");
            timezone = config.get("timezone");
            Map<String, Object> trackerData = support.context(context.tracker, true);
            trackerData.put("bot", context.bot);
            Object resolved = support.one(trackerData, config.get("schedule_time"), context.bot);
            scheduleTime = resolved;
            ActionSupport.Prepared prepared = support.prepareRequestWithBot(trackerData, config.get("params_list"), context.bot);
            dataLog = prepared.log();
            String kind = Maps.str(config.get("schedule_action_type"));
            Instant when = parseWhen(resolved, Maps.str(timezone));
            String id = support.tokens().uuid7Hex();
            Map<String, Object> data;
            String taskType;
            if ("pyscript".equals(kind)) {
                Document callback = support.callbackConfig(context.bot, Maps.str(scheduleAction));
                Map<String, Object> predefined = new LinkedHashMap<>(prepared.body());
                predefined.put("event", id);
                data = new LinkedHashMap<>();
                data.put("source_code", callback.get("pyscript_code"));
                data.put("predefined_objects", predefined);
                executionInfo = Maps.of("pyscript_code", callback.get("pyscript_code"), "type", "pyscript");
                taskType = "Action";
            } else if ("flow".equals(kind)) {
                data = new LinkedHashMap<>();
                data.put("slot_data", Jsons.pythonDumps(prepared.body()));
                data.put("flow_name", scheduleAction);
                data.put("bot", context.bot);
                data.put("user", context.tracker.senderId);
                executionInfo = Maps.of("flow", scheduleAction, "type", "flow");
                taskType = "Event";
            } else {
                throw new ActionFailure("unsupported schedule action type");
            }
            Document job = new Document();
            job.put("_id", id);
            job.put("id", id);
            job.put("name", "execute_task");
            job.put("misfire_grace_time", 7200);
            job.put("coalesce", true);
            job.put("max_instances", 1);
            job.put("date_time", when.toString());
            job.put("timezone", timezone);
            job.put("data", data);
            job.put("task_type", taskType);
            support.catalog().insert("scheduler_jobs", job);
            dispatchJob(id);
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("schedule action failed", e);
            status = Kairon.FAIL;
            botResponse = Kairon.SORRY;
            support.failureMail(context.bot, context.actionName, context.tracker.text(), exception);
        } finally {
            if (dispatch) {
                context.dispatcher.text(botResponse == null ? null : String.valueOf(botResponse));
            }
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("schedule_action", scheduleAction);
            extra.put("schedule_time", scheduleTime);
            extra.put("timezone", timezone);
            extra.put("execution_info", executionInfo);
            extra.put("data", dataLog);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        return Map.of();
    }

    private void dispatchJob(String id) {
        String base = support.settings().getEventsServerUrl();
        if (base == null || base.isBlank()) {
            throw new ActionFailure("events server url is not configured");
        }
        if (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        HttpCaller.Exchange exchange = support.http().exchange("GET", base + "/api/events/dispatch/" + id, Map.of(), null, null);
        if (exchange.status() != 200) {
            throw new ActionFailure(String.valueOf(exchange.body()));
        }
    }

    private static Instant parseWhen(Object value, String timezone) {
        if (value == null) {
            throw new ActionFailure("Invalid schedule time: null");
        }
        String text = String.valueOf(value).trim();
        try {
            return Instant.parse(text);
        } catch (RuntimeException ignored) {
            // try the next format
        }
        try {
            return OffsetDateTime.parse(text).toInstant();
        } catch (RuntimeException ignored) {
            // try a local date in the configured zone
        }
        ZoneId zone = ZoneId.of(timezone == null || timezone.isBlank() ? "UTC" : timezone);
        for (DateTimeFormatter format : new DateTimeFormatter[]{DateTimeFormatter.ISO_LOCAL_DATE_TIME, SPACE, MINUTE}) {
            try {
                return LocalDateTime.parse(text, format).atZone(zone).toInstant();
            } catch (RuntimeException ignored) {
                // try the next format
            }
        }
        throw new ActionFailure("Invalid schedule time: " + text);
    }
}
