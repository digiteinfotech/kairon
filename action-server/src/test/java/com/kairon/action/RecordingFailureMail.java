package com.kairon.action;

import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.support.FailureMail;
import com.kairon.action.support.SmtpMailer;
import io.micronaut.context.annotation.Replaces;
import jakarta.inject.Singleton;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

/** Test stand-in for {@link FailureMail}: records each triggered failure mail instead of sending it. */
@Singleton
@Replaces(FailureMail.class)
public class RecordingFailureMail extends FailureMail {

    public record Call(String bot, String action, Map<String, Object> slots, Object userText, String stackTrace) {}

    public static final List<Call> CALLS = new CopyOnWriteArrayList<>();

    public RecordingFailureMail(ActionCatalog catalog, ActionSettings settings, SmtpMailer mailer) {
        super(catalog, settings, mailer, "127.0.0.1", 1, "noreply@kairon.test", "", "", null);
    }

    @Override
    public void trigger(String bot, String action, Map<String, Object> slotValues, Object userText, String stackTrace) {
        CALLS.add(new Call(bot, action, slotValues, userText, stackTrace));
    }
}
