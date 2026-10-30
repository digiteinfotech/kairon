package com.kairon.action.actions;

import com.kairon.action.ActionSettings;
import com.kairon.action.Kairon;
import com.kairon.action.catalog.MemoryActionCatalog;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.Dispatcher;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.runtime.TrackerState;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.LlmHttp;
import com.kairon.action.support.Tokens;
import com.kairon.action.support.llm.CognitionSchemas;
import com.kairon.action.support.llm.LlmClient;
import com.kairon.action.support.llm.LlmProcessor;
import com.kairon.action.support.llm.LlmSecrets;
import com.kairon.action.support.llm.QdrantClient;
import com.kairon.action.support.llm.SimilarityContext;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-104: FAQ gate before config load, Python bot_settings defaults, active-config lookup (prompt-db R1 c1-c5). */
class PromptDatabaseGateTest {

    private static final String BOT = "bot-1";

    /** Records every findActive call so a test can assert the config was (or was not) read. */
    static final class SpyCatalog extends MemoryActionCatalog {
        final List<List<String>> configReads = new ArrayList<>();

        @Override
        public Optional<Document> findActive(String collection, String bot, String nameField, String value) {
            configReads.add(List.of(collection, bot, nameField, value));
            return super.findActive(collection, bot, nameField, value);
        }
    }

    SpyCatalog catalog;
    ActionSupport support;
    DatabaseAction database;
    PromptAction prompt;

    @BeforeEach
    void setUp() {
        ActionSettings settings = new ActionSettings();
        settings.setFernetKey("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=");
        catalog = new SpyCatalog();
        Tokens tokens = new Tokens(settings);
        support = new ActionSupport(catalog, settings, tokens, null);
        LlmSecrets secrets = new LlmSecrets(catalog, tokens);
        CognitionSchemas schemas = new CognitionSchemas(catalog, secrets);
        HttpCaller http = new HttpCaller(settings);
        LlmClient llm = new LlmClient(new LlmHttp(http, settings), settings, schemas);
        QdrantClient qdrant = new QdrantClient(http, settings, llm);
        database = new DatabaseAction(support, secrets, schemas, qdrant);
        prompt = new PromptAction(support, secrets, schemas, new LlmProcessor(llm, new SimilarityContext(qdrant)));
    }

    private KaironAction action(String type) {
        return "prompt_action".equals(type) ? prompt : database;
    }

    private Document run(String type, String name) {
        Map<String, Object> tracker = new LinkedHashMap<>();
        tracker.put("sender_id", "user-1");
        tracker.put("slots", new LinkedHashMap<>());
        tracker.put("latest_message", Map.of("text", "hello"));
        tracker.put("events", List.of());
        ActionContext context = new ActionContext(BOT, name, TrackerState.from(tracker), new Dispatcher(), Map.of(), Map.of());
        action(type).execute(context);
        List<Document> logs = catalog.all(Kairon.LOGS);
        assertEquals(1, logs.size());
        return logs.get(0);
    }

    private void assertFaqDisabled(String type) {
        Document log = run(type, "act");
        assertEquals(Kairon.FAIL, log.get("status"));
        assertEquals(Kairon.FAQ_DISABLED, log.get("exception"));
        assertTrue(catalog.configReads.isEmpty(), "config must not be read: " + catalog.configReads);
    }

    @ParameterizedTest
    @ValueSource(strings = {"prompt_action", "database_action"})
    void faqFalseFailsBeforeConfigRead(String type) {
        catalog.put("bot_settings", new Document("bot", BOT).append("status", true)
                .append("llm_settings", new Document("enable_faq", false)));
        catalog.put(type, new Document("bot", BOT).append("name", "act").append("status", true));
        assertFaqDisabled(type);
    }

    @ParameterizedTest
    @ValueSource(strings = {"prompt_action", "database_action"})
    void missingBotSettingsUsesPythonDefaults(String type) {
        catalog.put(type, new Document("bot", BOT).append("name", "act").append("status", true));
        assertFaqDisabled(type);
    }

    @ParameterizedTest
    @ValueSource(strings = {"prompt_action", "database_action"})
    void inactiveBotSettingsUsesPythonDefaults(String type) {
        catalog.put("bot_settings", new Document("bot", BOT).append("status", false)
                .append("llm_settings", new Document("enable_faq", true)));
        assertFaqDisabled(type);
    }

    @ParameterizedTest
    @ValueSource(strings = {"prompt_action", "database_action"})
    void missingLlmSettingsUsesPythonDefaults(String type) {
        catalog.put("bot_settings", new Document("bot", BOT).append("status", true));
        assertFaqDisabled(type);
    }

    @ParameterizedTest
    @ValueSource(strings = {"prompt_action", "database_action"})
    void missingEnableFaqUsesPythonDefaults(String type) {
        catalog.put("bot_settings", new Document("bot", BOT).append("status", true)
                .append("llm_settings", new Document("provider", "openai")));
        assertFaqDisabled(type);
    }

    @ParameterizedTest
    @ValueSource(strings = {"prompt_action", "database_action"})
    void configReadByBotNameAndActiveStatus(String type) {
        catalog.put("bot_settings", new Document("bot", BOT).append("status", true)
                .append("llm_settings", new Document("enable_faq", true)));
        // only an inactive config exists: status: true filter must skip it
        catalog.put(type, new Document("bot", BOT).append("name", "act").append("status", false));
        Document log = run(type, "act");
        assertEquals(List.of(List.of(type, BOT, "name", "act")), catalog.configReads);
        assertEquals(Kairon.FAIL, log.get("status"));
        String expected = "prompt_action".equals(type)
                ? "No action found for given bot and name"
                : "No Vector action found for given action and bot";
        assertEquals(expected, log.get("exception"));
    }
}
