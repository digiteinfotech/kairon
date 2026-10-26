package com.kairon.action;

import io.micronaut.context.annotation.Requires;
import io.micronaut.context.event.ApplicationEventListener;
import io.micronaut.runtime.server.event.ServerStartupEvent;
import jakarta.inject.Singleton;

/**
 * Tests bind the server to a random port, so the default own-webhook URL (http://localhost:5055/webhook)
 * would not reach it. When a test leaves {@code kairon.action.action-server-url} at that default, point it
 * at the embedded server so parallel_action children loop back into the server under test.
 */
@Singleton
@Requires(env = "test")
public class OwnWebhookUrl implements ApplicationEventListener<ServerStartupEvent> {

    static final String DEFAULT = "http://localhost:5055/webhook";

    private final ActionSettings settings;

    public OwnWebhookUrl(ActionSettings settings) {
        this.settings = settings;
    }

    @Override
    public void onApplicationEvent(ServerStartupEvent event) {
        if (DEFAULT.equals(settings.getActionServerUrl())) {
            settings.setActionServerUrl("http://127.0.0.1:" + event.getSource().getPort() + "/webhook");
        }
    }
}
