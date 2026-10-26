package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import jakarta.inject.Singleton;

import java.util.Map;

@Singleton
public class VoiceDisconnectAction implements KaironAction {

    private final ActionSupport support;

    public VoiceDisconnectAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "kairon_voice_disconnect";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            context.dispatcher.custom(Map.of("disconnect", true));
        } catch (Exception e) {
            exception = e.getMessage();
            status = Kairon.FAIL;
            support.failureMail(context, e);
        } finally {
            support.save(context, type(), status, exception, Map.of("disconnect", true), null);
        }
        return Map.of();
    }
}
