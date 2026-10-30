package com.kairon.action.parity;

import com.kairon.action.ActionSettings;

import java.util.ArrayList;
import java.util.List;
import java.util.function.BiConsumer;
import java.util.function.Function;

/**
 * Points the settings-driven upstream endpoints (evaluator, pyscript, events, live agent, simple agent, voice call,
 * llm, vector, web search) at a replay's stubs.
 * <p>
 * A Python recording calls these services at the URLs of the Python test configuration
 * ({@code tests/testing_data/system.yaml} defaults, listed in {@link #ENDPOINTS}), not at the port's test
 * configuration. During a replay each setting is set to that recorded URL, mapped through the stubs:
 * <ul>
 *   <li>a recorded {@code http://} origin becomes its stub origin ({@link UpstreamStubs#httpOrigins()});</li>
 *   <li>an {@code https://} URL is kept, and the port's https rewrite sends it to the shared https stub;</li>
 *   <li>a URL whose http origin was never recorded is pointed at the https stub, which answers 599 and reports
 *   the call as unexpected instead of letting it reach a real host;</li>
 *   <li>a setting the Python configuration leaves unset stays unset (blank).</li>
 * </ul>
 * A Python default can be overridden per setting with the system property {@code kairon.parity.endpoint.<name>}
 * (for nodes that monkeypatch {@code Utility.environment}). {@link Saved#restore()} puts the previous values back.
 */
final class ReplayEndpoints {

    static final String OVERRIDE_PREFIX = "kairon.parity.endpoint.";

    /** One settings-driven endpoint: its name, Python recording default ("" when unset there) and accessors. */
    record Endpoint(String name, String pythonDefault, Function<ActionSettings, String> getter,
                    BiConsumer<ActionSettings, String> setter) {

        String recorded() {
            return System.getProperty(OVERRIDE_PREFIX + name, pythonDefault);
        }
    }

    static final List<Endpoint> ENDPOINTS = List.of(
            new Endpoint("evaluator", "http://localhost:8080/format", ActionSettings::getEvaluatorUrl, ActionSettings::setEvaluatorUrl),
            new Endpoint("pyscript", "http://localhost:8080/evaluate", ActionSettings::getPyscriptUrl, ActionSettings::setPyscriptUrl),
            new Endpoint("events", "http://localhost:5001", ActionSettings::getEventsServerUrl, ActionSettings::setEventsServerUrl),
            new Endpoint("live-agent", "http://localhost:8000/api/v1", ActionSettings::getLiveAgentUrl, ActionSettings::setLiveAgentUrl),
            new Endpoint("simple-agent", "", ActionSettings::getSimpleAgentUrl, ActionSettings::setSimpleAgentUrl),
            new Endpoint("voice-call", "", ActionSettings::getVoiceCallUrl, ActionSettings::setVoiceCallUrl),
            new Endpoint("llm", "http://localhost", ActionSettings::getLlmServerUrl, ActionSettings::setLlmServerUrl),
            new Endpoint("vector", "http://localhost:6333", ActionSettings::getVectorDb, ActionSettings::setVectorDb),
            new Endpoint("web-search", "", ActionSettings::getWebSearchUrl, ActionSettings::setWebSearchUrl));

    private ReplayEndpoints() {
    }

    /** Previous setting values, restored after the replay. */
    record Saved(ActionSettings settings, List<String> values) {
        void restore() {
            for (int i = 0; i < ENDPOINTS.size(); i++) {
                ENDPOINTS.get(i).setter().accept(settings, values.get(i));
            }
        }
    }

    static Saved apply(ActionSettings settings, UpstreamStubs stubs) {
        List<String> previous = new ArrayList<>();
        for (Endpoint endpoint : ENDPOINTS) {
            previous.add(endpoint.getter().apply(settings));
            endpoint.setter().accept(settings, target(endpoint.recorded(), stubs));
        }
        return new Saved(settings, previous);
    }

    /**
     * Where a setting points during a replay. A blank recorded value stays blank, as the service was not
     * configured for the Python node either.
     */
    static String target(String recorded, UpstreamStubs stubs) {
        if (recorded == null || recorded.isBlank()) {
            return "";
        }
        String origin = UpstreamStubs.originOf(recorded);
        String rest = origin == null ? recorded : recorded.substring(origin.length());
        if (origin != null) {
            String stub = stubs.httpOrigins().get(origin);
            if (stub != null) {
                return stub + rest;
            }
            if (origin.startsWith("https://")) {
                return recorded;
            }
        }
        return stubs.httpsBase() + (rest.startsWith("/") || rest.isEmpty() ? rest : "/" + rest);
    }
}
