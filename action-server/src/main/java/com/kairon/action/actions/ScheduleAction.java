package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * schedule_action (kairon/actions/definitions/schedule.py). The job is submitted through the events server
 * scheduling endpoint (POST /api/events/schedule/action), which is the single writer of the scheduler job
 * store; the port never writes a job document itself. A successful submission is followed by one
 * GET /api/events/dispatch/{job_id}.
 */
@Singleton
public class ScheduleAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(ScheduleAction.class);
    private static final DateTimeFormatter SPACE = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final DateTimeFormatter MINUTE = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");
    private static final DateTimeFormatter SPACE_FRACTION = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSSSSS");
    private static final DateTimeFormatter DATE_TIME = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");
    static final String SCHEDULE_PATH = "/api/events/schedule/action";
    static final String DISPATCH_PATH = "/api/events/dispatch/";

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
        Object dataLog = new LinkedHashMap<>();
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
            Map<String, Object> trackerData = support.context(context.tracker, true, context.bot);
            Object resolved = support.one(trackerData, config.get("schedule_time"), context.bot);
            scheduleTime = resolved;
            ActionSupport.Prepared prepared = support.prepareRequestWithBot(trackerData, config.get("params_list"), context.bot);
            dataLog = prepared.log();
            String kind = Maps.str(config.get("schedule_action_type"));
            if ("pyscript".equals(kind)) {
                Document callback = support.callbackConfig(context.bot, Maps.str(scheduleAction));
                executionInfo = Maps.of("pyscript_code", callback.get("pyscript_code"), "type", "pyscript");
            } else if ("flow".equals(kind)) {
                executionInfo = Maps.of("flow", scheduleAction, "type", "flow");
            } else {
                throw new ActionFailure("unsupported schedule action type");
            }
            String runAt = runAt(resolved);
            String base = eventsServer();
            String id = support.tokens().uuid7Hex();
            Map<String, Object> request = new LinkedHashMap<>();
            request.put("job_id", id);
            request.put("run_at", runAt);
            request.put("timezone", timezone == null ? "" : String.valueOf(timezone));
            request.put("schedule_action_type", kind);
            request.put("schedule_action", scheduleAction);
            request.put("bot", context.bot);
            request.put("user", context.tracker.senderId);
            request.put("data", prepared.body());
            submit(base, request);
            dispatchJob(base, id);
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("schedule action failed", e);
            status = Kairon.FAIL;
            botResponse = Kairon.SORRY;
            support.failureMail(context, e);
        } finally {
            if (dispatch) {
                context.dispatcher.text(botResponse == null ? null : String.valueOf(botResponse));
            }
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("messages", new ArrayList<String>());
            extra.put("schedule_action", scheduleAction);
            extra.put("schedule_time", scheduleTime);
            extra.put("timezone", timezone);
            extra.put("execution_info", executionInfo);
            extra.put("data", dataLog);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        return Map.of();
    }

    private String eventsServer() {
        String base = support.settings().getEventsServerUrl();
        if (base == null || base.isBlank()) {
            throw new ActionFailure("events server url is not configured");
        }
        return base.endsWith("/") ? base.substring(0, base.length() - 1) : base;
    }

    /**
     * Exactly one POST. Failed when the HTTP status is not 200 or the envelope's success is not true
     * (the events server reports rejections as HTTP 200 {success: false, error_code: 422, message}).
     */
    private void submit(String base, Map<String, Object> request) {
        HttpCaller.Exchange exchange = support.http().exchange("POST", base + SCHEDULE_PATH, Map.of(), request, null);
        Object body = exchange.body();
        boolean accepted = exchange.status() == 200 && body instanceof Map<?, ?> envelope
                && Boolean.TRUE.equals(envelope.get("success"));
        if (!accepted) {
            String reason;
            if (exchange.error() != null) {
                reason = exchange.error();
            } else if (body instanceof Map<?, ?> envelope && envelope.get("message") != null) {
                reason = String.valueOf(envelope.get("message"));
            } else {
                reason = String.valueOf(body);
            }
            throw new ActionFailure("Failed to schedule action: " + reason);
        }
    }

    private void dispatchJob(String base, String id) {
        HttpCaller.Exchange exchange = support.http().exchange("GET", base + DISPATCH_PATH + id, Map.of(), null, null);
        if (exchange.status() != 200) {
            throw new ActionFailure(String.valueOf(exchange.body()));
        }
    }

    /**
     * dateutil.parser.parse(schedule_time).isoformat(): naive values stay naive (the zone travels separately
     * in `timezone`), offset values keep their offset ("+HH:MM", UTC as "+00:00"), microseconds only when non-zero.
     */
    static String runAt(Object value) {
        if (value == null) {
            throw new ActionFailure("Invalid schedule time: null");
        }
        String text = String.valueOf(value).trim();
        try {
            OffsetDateTime parsed = OffsetDateTime.parse(text);
            return isoformat(parsed.toLocalDateTime()) + offset(parsed.getOffset());
        } catch (RuntimeException ignored) {
            // try a naive date-time
        }
        for (DateTimeFormatter format : new DateTimeFormatter[]{DateTimeFormatter.ISO_LOCAL_DATE_TIME, SPACE, SPACE_FRACTION, MINUTE}) {
            try {
                return isoformat(LocalDateTime.parse(text, format));
            } catch (RuntimeException ignored) {
                // try the next format
            }
        }
        try {
            return isoformat(LocalDate.parse(text).atStartOfDay());
        } catch (RuntimeException ignored) {
            throw new ActionFailure("Invalid schedule time: " + text);
        }
    }

    private static String isoformat(LocalDateTime value) {
        String text = DATE_TIME.format(value);
        int micros = value.getNano() / 1000;
        return micros == 0 ? text : text + String.format(".%06d", micros);
    }

    private static String offset(ZoneOffset offset) {
        int seconds = offset.getTotalSeconds();
        String sign = seconds < 0 ? "-" : "+";
        seconds = Math.abs(seconds);
        String text = String.format("%s%02d:%02d", sign, seconds / 3600, (seconds % 3600) / 60);
        return seconds % 60 == 0 ? text : text + String.format(":%02d", seconds % 60);
    }
}
