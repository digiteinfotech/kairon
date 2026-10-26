package com.kairon.action;

import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.runtime.TrackerState;
import jakarta.inject.Singleton;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Test-only action type {@code test_probe}: records the executing thread and tracker, utters one message,
 * then fails when the slot {@code probe_fail} is true.
 */
@Singleton
public class ProbeAction implements KaironAction {

    static final String TYPE = "test_probe";

    volatile Thread lastThread;
    volatile TrackerState lastTracker;
    volatile int executions;

    @Override
    public String type() {
        return TYPE;
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        lastThread = Thread.currentThread();
        lastTracker = context.tracker;
        executions++;
        context.dispatcher.text("uttered before failure");
        if (Boolean.TRUE.equals(context.tracker.slotValue("probe_fail"))) {
            throw new IllegalStateException("probe failure");
        }
        Map<String, Object> slots = new LinkedHashMap<>();
        slots.put("probe_sender", context.tracker.senderId);
        return slots;
    }

    void reset() {
        lastThread = null;
        lastTracker = null;
        executions = 0;
    }
}
