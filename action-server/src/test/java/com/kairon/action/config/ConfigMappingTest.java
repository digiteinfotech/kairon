package com.kairon.action.config;

import com.kairon.action.ActionSettings;
import com.kairon.action.catalog.MongoFactory;
import io.micronaut.context.ApplicationContext;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** cavekit-config-and-deploy.md R1: Python env var names and defaults, and the CONFIG.md mapping table. */
class ConfigMappingTest {

    private static final Path PORT = Path.of("").toAbsolutePath();
    private static final Path SYSTEM_YAML = PORT.resolve("../system.yaml").normalize();
    /** Python reads the SMTP sender and subject keys from email.yaml (Utility.email_conf). */
    private static final Path EMAIL_YAML = PORT.resolve("../email.yaml").normalize();
    private static final Path APPLICATION_YML = PORT.resolve("src/main/resources/application.yml");
    private static final Path CONFIG_MD = PORT.resolve("CONFIG.md");

    /** Every env var the in-scope actions need (R1 c3), with the Python default (null = secret or none). */
    private static final Map<String, String> REQUIRED = new LinkedHashMap<>();

    static {
        REQUIRED.put("DATABASE_URL", "mongodb://localhost:27017/conversations");
        REQUIRED.put("ACTION_SERVER_REQUEST_TIMEOUT", "60");
        REQUIRED.put("ACTION_SERVER_URL", "http://localhost:5055/webhook");
        REQUIRED.put("TRIGGER_MAIN_PYSCRIPT_URL", "http://localhost:5059/main_pyscript/execute-python");
        REQUIRED.put("EXPRESSION_EVALUATOR_ENDPOINT", "http://192.168.100.109:8085/evaluate");
        REQUIRED.put("EVENT_SERVER_ENDPOINT", "http://localhost:5056");
        REQUIRED.put("ASYNC_CALLBACK_ACTION_SERVER_URL", "http://localhost:5059/callback");
        REQUIRED.put("LIVE_AGENT_SERVER_URL", "http://localhost:8000/api/v1");
        REQUIRED.put("LIVE_AGENT_AUTH_TOKEN", null);
        REQUIRED.put("SIMPLE_AGENT_URL", null);
        REQUIRED.put("WEB_SEARCH_URL", null);
        REQUIRED.put("KAIRON_SUPPORT_MAIL", "kairon@digite.com");
        REQUIRED.put("ALLOWED_ORIGIN", "[\"*\"]");
        REQUIRED.put("FERNET_KEY", null);
        REQUIRED.put("SECRET_KEY", null);
        REQUIRED.put("ASYNC_CALLBACK_AES_KEY", null);
        REQUIRED.put("ASYNC_CALLBACK_AES_IV", null);
        REQUIRED.put("SECRET_UNMASKED_CHAR_COUNT", "2");
        REQUIRED.put("FRONTEND_URL", "http://localhost:3000");
        REQUIRED.put("EMAIL_SENDER_SERVICE", "changeit");
        REQUIRED.put("EMAIL_SENDER_PORT", "587");
        REQUIRED.put("EMAIL_SENDER_EMAIL", "changeit@changeit.com");
        REQUIRED.put("EMAIL_SENDER_PASSWORD", null);
        REQUIRED.put("EMAIL_SENDER_USERID", null);
        REQUIRED.put("EMAIL_TEMPLATES_ACTION_FAILURE", "kAIron Action Failure - BOT_NAME");
        REQUIRED.put("LLM_SERVER_URL", "http://localhost");
        REQUIRED.put("LLM_REQUEST_TIMEOUT", "30");
        REQUIRED.put("VECTOR_DB", "http://localhost:6333");
        REQUIRED.put("VECTOR_DB_KEY", null);
    }

    record Row(String pythonKey, String env, String property, String defaultCell) {
    }

    @Test
    void everyMappedEnvVarMatchesSystemYamlAndApplicationYml() throws IOException {
        String system = pythonYaml();
        String application = read(APPLICATION_YML);
        List<Row> rows = table();
        assertFalse(rows.isEmpty());
        for (Row row : rows) {
            if (row.env().isEmpty()) {
                continue;
            }
            String pythonDefault = placeholderDefault(system, row.env());
            assertTrue(pythonDefault != null, row.env() + " is not a system.yaml or email.yaml env var");
            String portDefault = placeholderDefault(application, row.env());
            assertTrue(portDefault != null, row.env() + " is not bound in application.yml");
            String cell = row.defaultCell();
            if (cell.equals("secret")) {
                assertFalse(pythonDefault.isEmpty(), row.env());
                assertEquals("", portDefault, row.env() + " must not ship a default secret");
            } else if (cell.equals("none")) {
                assertEquals("", pythonDefault, row.env());
                assertEquals("", portDefault, row.env());
            } else if (cell.startsWith("deviation:")) {
                assertEquals("", portDefault, row.env());
            } else {
                String expected = unquote(cell);
                assertEquals(expected, pythonDefault, row.env() + " default differs from system.yaml");
                assertEquals(expected, portDefault, row.env() + " default differs in application.yml");
            }
        }
    }

    @Test
    void tableCoversEveryRequiredKey() throws IOException {
        Map<String, Row> byEnv = new LinkedHashMap<>();
        for (Row row : table()) {
            byEnv.put(row.env(), row);
        }
        String system = pythonYaml();
        for (Map.Entry<String, String> required : REQUIRED.entrySet()) {
            assertTrue(byEnv.containsKey(required.getKey()), required.getKey() + " missing from CONFIG.md");
            if (required.getValue() != null) {
                assertEquals(required.getValue(), placeholderDefault(system, required.getKey()), required.getKey());
            }
        }
        assertTrue(table().stream().anyMatch(r -> r.pythonKey().equals("security.algorithm")));
        assertTrue(table().stream().anyMatch(r -> r.pythonKey().equals("live_agent.enable")));
    }

    @Test
    void defaultsResolveWithoutEnv() {
        // Secrets have no default and SecretsValidator refuses to start without them (T-034).
        Map<String, Object> secrets = Map.of("FERNET_KEY", "f", "SECRET_KEY", "s",
                "ASYNC_CALLBACK_AES_KEY", "k", "ASYNC_CALLBACK_AES_IV", "i");
        try (ApplicationContext context = ApplicationContext.builder().deduceEnvironment(false).properties(secrets).start()) {
            ActionSettings settings = context.getBean(ActionSettings.class);
            if (System.getenv("ACTION_SERVER_REQUEST_TIMEOUT") == null) {
                assertEquals(60, settings.getRequestTimeout());
            }
            if (System.getenv("EVENT_SERVER_ENDPOINT") == null) {
                assertEquals("http://localhost:5056", settings.getEventsServerUrl());
            }
            if (System.getenv("TRIGGER_MAIN_PYSCRIPT_URL") == null) {
                assertEquals("http://localhost:5059/main_pyscript/execute-python", settings.getPyscriptUrl());
            }
            if (System.getenv("SECRET_UNMASKED_CHAR_COUNT") == null) {
                assertEquals(2, settings.getUnmaskedCharCount());
            }
            if (System.getenv("ALLOWED_ORIGIN") == null) {
                assertEquals(List.of("*"), settings.corsOrigins());
            }
            assertEquals("HS256", settings.getJwtAlgorithm());
            assertTrue(settings.isLiveAgentEnabled());
            if (System.getenv("ACTION_SERVER_URL") == null) {
                assertEquals("http://localhost:5055/webhook", settings.getActionServerUrl());
            }
            if (System.getenv("EXPRESSION_EVALUATOR_ENDPOINT") == null) {
                assertEquals("http://192.168.100.109:8085/evaluate", settings.getEvaluatorUrl());
            }
            if (System.getenv("EMAIL_SENDER_PORT") == null) {
                assertEquals(587, context.getProperty("email.sender.port", Integer.class).orElseThrow());
            }
            if (System.getenv("EMAIL_SENDER_SERVICE") == null) {
                assertEquals("changeit", context.getProperty("email.sender.service", String.class).orElseThrow());
            }
            if (System.getenv("EMAIL_SENDER_EMAIL") == null) {
                assertEquals("changeit@changeit.com", context.getProperty("email.sender.email", String.class).orElseThrow());
            }
            if (System.getenv("EMAIL_SENDER_PASSWORD") == null) {
                assertEquals("", context.getProperty("email.sender.password", String.class).orElse(""));
            }
            if (System.getenv("EMAIL_TEMPLATES_ACTION_FAILURE") == null) {
                assertEquals("kAIron Action Failure - BOT_NAME",
                        context.getProperty("email.templates.action.failure", String.class).orElseThrow());
            }
            if (System.getenv("DATABASE_URL") == null) {
                assertEquals("mongodb://localhost:27017/conversations", context.getProperty("mongodb.uri", String.class).orElseThrow());
            }
        }
    }

    @Test
    void pythonEnvNamesOverrideSettings() {
        Map<String, Object> env = new LinkedHashMap<>();
        env.put("ACTION_SERVER_REQUEST_TIMEOUT", "33");
        env.put("DATABASE_URL", "mongodb://db.test:27017");
        env.put("FERNET_KEY", "fernet-from-env");
        env.put("SECRET_KEY", "secret-from-env");
        env.put("ASYNC_CALLBACK_AES_KEY", "aes-key-from-env");
        env.put("ASYNC_CALLBACK_AES_IV", "aes-iv-from-env");
        env.put("TRIGGER_MAIN_PYSCRIPT_URL", "http://pyscript.test/run");
        env.put("EXPRESSION_EVALUATOR_ENDPOINT", "http://eval.test/evaluate");
        env.put("EVENT_SERVER_ENDPOINT", "http://events.test");
        env.put("ASYNC_CALLBACK_ACTION_SERVER_URL", "http://callback.test/callback");
        env.put("LIVE_AGENT_SERVER_URL", "http://live.test/api/v1");
        env.put("LIVE_AGENT_AUTH_TOKEN", "live-token-from-env");
        env.put("SIMPLE_AGENT_URL", "http://agent.test");
        env.put("KAIRON_VOICE_CALL_URL", "http://voice.test");
        env.put("WEB_SEARCH_URL", "http://search.test");
        env.put("KAIRON_SUPPORT_MAIL", "support@test");
        env.put("ALLOWED_ORIGIN", "[\"https://a.test\", \"https://b.test\"]");
        env.put("SECRET_UNMASKED_CHAR_COUNT", "3");
        env.put("SECRET_UNMASKED_CHAR_STRATEGY", "from_left");
        env.put("ACTION_SERVER_URL", "http://self.test/webhook");
        env.put("FRONTEND_URL", "http://front.test");
        env.put("EMAIL_SENDER_SERVICE", "smtp.test");
        env.put("EMAIL_SENDER_PORT", "2525");
        env.put("EMAIL_SENDER_EMAIL", "bot@test");
        env.put("EMAIL_SENDER_PASSWORD", "smtp-password-from-env");
        env.put("EMAIL_SENDER_USERID", "smtp-user");
        env.put("EMAIL_TEMPLATES_ACTION_FAILURE", "Failure in BOT_NAME");
        try (ApplicationContext context = ApplicationContext.builder().deduceEnvironment(false).properties(env).start()) {
            ActionSettings settings = context.getBean(ActionSettings.class);
            assertEquals(33, settings.getRequestTimeout());
            assertEquals("fernet-from-env", settings.getFernetKey());
            assertEquals("secret-from-env", settings.getJwtSecret());
            assertEquals("aes-key-from-env", settings.getAsyncCallbackAesKey());
            assertEquals("aes-iv-from-env", settings.getAsyncCallbackAesIv());
            assertEquals("http://pyscript.test/run", settings.getPyscriptUrl());
            assertEquals("http://eval.test/evaluate", settings.getEvaluatorUrl());
            assertEquals("http://events.test", settings.getEventsServerUrl());
            assertEquals("http://callback.test/callback", settings.getCallbackBaseUrl());
            assertEquals("http://live.test/api/v1", settings.getLiveAgentUrl());
            assertEquals("live-token-from-env", settings.getLiveAgentToken());
            assertEquals("http://agent.test", settings.getSimpleAgentUrl());
            assertEquals("http://voice.test", settings.getVoiceCallUrl());
            assertEquals("http://search.test", settings.getWebSearchUrl());
            assertEquals("support@test", settings.getSupportMail());
            assertEquals(List.of("https://a.test", "https://b.test"), settings.corsOrigins());
            assertEquals(3, settings.getUnmaskedCharCount());
            assertEquals("from_left", settings.getUnmaskedCharStrategy());
            assertEquals("http://self.test/webhook", settings.getActionServerUrl());
            assertEquals("http://front.test", settings.getFrontendUrl());
            assertEquals("smtp.test", context.getProperty("email.sender.service", String.class).orElseThrow());
            assertEquals(2525, context.getProperty("email.sender.port", Integer.class).orElseThrow());
            assertEquals("bot@test", context.getProperty("email.sender.email", String.class).orElseThrow());
            assertEquals("smtp-password-from-env", context.getProperty("email.sender.password", String.class).orElseThrow());
            assertEquals("smtp-user", context.getProperty("email.sender.userid", String.class).orElseThrow());
            assertEquals("Failure in BOT_NAME", context.getProperty("email.templates.action.failure", String.class).orElseThrow());
            String uri = context.getProperty("mongodb.uri", String.class).orElseThrow();
            assertEquals("mongodb://db.test:27017", uri);
            assertEquals("kairon", MongoFactory.databaseName(uri));
        }
    }

    /** cavekit-config-and-deploy R1 / cavekit-prompt-database-actions R7: llm.* and vector.* keys. */
    @Test
    void llmAndVectorKeysDefaultWithoutEnv() {
        Map<String, Object> secrets = Map.of("FERNET_KEY", "f", "SECRET_KEY", "s",
                "ASYNC_CALLBACK_AES_KEY", "k", "ASYNC_CALLBACK_AES_IV", "i");
        try (ApplicationContext context = ApplicationContext.builder().deduceEnvironment(false).properties(secrets).start()) {
            ActionSettings settings = context.getBean(ActionSettings.class);
            if (System.getenv("LLM_SERVER_URL") == null) {
                assertEquals("http://localhost", settings.getLlmServerUrl());
            }
            if (System.getenv("LLM_REQUEST_TIMEOUT") == null) {
                assertEquals(30, settings.getLlmRequestTimeout());
            }
            if (System.getenv("VECTOR_DB") == null) {
                assertEquals("http://localhost:6333", settings.getVectorDb());
            }
            if (System.getenv("VECTOR_DB_KEY") == null) {
                assertNull(settings.getVectorKey());
            }
            if (System.getenv("ACTION_SERVER_REQUEST_TIMEOUT") == null) {
                assertEquals(60, settings.getRequestTimeout());
            }
        }
        ActionSettings plain = new ActionSettings();
        assertEquals("http://localhost", plain.getLlmServerUrl());
        assertEquals(30, plain.getLlmRequestTimeout());
        assertEquals("http://localhost:6333", plain.getVectorDb());
        assertNull(plain.getVectorKey());
    }

    @Test
    void llmAndVectorKeysFollowPythonEnvNames() {
        Map<String, Object> env = new LinkedHashMap<>();
        env.put("FERNET_KEY", "f");
        env.put("SECRET_KEY", "s");
        env.put("ASYNC_CALLBACK_AES_KEY", "k");
        env.put("ASYNC_CALLBACK_AES_IV", "i");
        env.put("LLM_SERVER_URL", "http://llm.test:8000");
        env.put("LLM_REQUEST_TIMEOUT", "45");
        env.put("VECTOR_DB", "http://qdrant.test:6333");
        env.put("VECTOR_DB_KEY", "qdrant-key-from-env");
        env.put("ACTION_SERVER_REQUEST_TIMEOUT", "21");
        try (ApplicationContext context = ApplicationContext.builder().deduceEnvironment(false).properties(env).start()) {
            ActionSettings settings = context.getBean(ActionSettings.class);
            assertEquals("http://llm.test:8000", settings.getLlmServerUrl());
            assertEquals(45, settings.getLlmRequestTimeout());
            assertEquals("http://qdrant.test:6333", settings.getVectorDb());
            assertEquals("qdrant-key-from-env", settings.getVectorKey());
            assertEquals(21, settings.getRequestTimeout());
        }
    }

    /** cavekit-prompt-database-actions R7: llm.* / vector.* rows name the bound property; no "deferred" wording. */
    @Test
    void llmAndVectorRowsMatchApplicationYml() throws IOException {
        Map<String, Row> byKey = new LinkedHashMap<>();
        for (Row row : table()) {
            byKey.put(row.pythonKey(), row);
        }
        Map<String, String[]> expected = new LinkedHashMap<>();
        expected.put("llm.url", new String[] {"LLM_SERVER_URL", "kairon.action.llm-server-url", "`http://localhost`"});
        expected.put("llm.request_timeout", new String[] {"LLM_REQUEST_TIMEOUT", "kairon.action.llm-request-timeout", "`30`"});
        expected.put("vector.db", new String[] {"VECTOR_DB", "kairon.action.vector-db", "`http://localhost:6333`"});
        expected.put("vector.key", new String[] {"VECTOR_DB_KEY", "kairon.action.vector-key", "none"});
        String application = read(APPLICATION_YML);
        for (Map.Entry<String, String[]> e : expected.entrySet()) {
            Row row = byKey.get(e.getKey());
            assertTrue(row != null, e.getKey() + " missing from CONFIG.md");
            assertEquals(e.getValue()[0], row.env(), e.getKey());
            assertEquals(e.getValue()[1], row.property(), e.getKey());
            assertEquals(e.getValue()[2], row.defaultCell(), e.getKey());
            String leaf = row.property().substring("kairon.action.".length());
            assertTrue(Pattern.compile("(?m)^\\s+" + Pattern.quote(leaf) + ": \\$\\{" + Pattern.quote(row.env()) + "[:}]")
                    .matcher(application).find(), row.property() + " not bound to " + row.env() + " in application.yml");
        }
        assertTrue(read(CONFIG_MD).contains("database_action point query is bounded by `action.request_timeout`"));
        String config = read(CONFIG_MD).toLowerCase(java.util.Locale.ROOT);
        assertFalse(config.contains("deferred"), "CONFIG.md still describes actions as deferred");
        assertFalse(config.contains("keeps them off") || config.contains("keeps it off"));
    }

    @Test
    void databaseNameFromUrlElseKairon() {
        assertEquals("kairon", MongoFactory.databaseName("mongodb://localhost:27017"));
        assertEquals("kairon", MongoFactory.databaseName("mongodb://localhost:27017/"));
        assertEquals("kairon", MongoFactory.databaseName("mongodb://u:p@h1:27017,h2:27017/?replicaSet=rs"));
        assertEquals("conversations", MongoFactory.databaseName("mongodb://localhost:27017/conversations"));
    }

    @Test
    void corsOriginAcceptsCommaSeparated() {
        ActionSettings settings = new ActionSettings();
        settings.setCorsOrigin("https://a.test, https://b.test");
        assertEquals(List.of("https://a.test", "https://b.test"), settings.corsOrigins());
    }

    /** system.yaml followed by email.yaml; env var names are unique across both. */
    private static String pythonYaml() throws IOException {
        return read(SYSTEM_YAML) + "\n" + read(EMAIL_YAML);
    }

    private static List<Row> table() throws IOException {
        List<Row> rows = new ArrayList<>();
        boolean inTable = false;
        for (String line : read(CONFIG_MD).split("\n")) {
            if (line.startsWith("## Python key to port key")) {
                inTable = true;
                continue;
            }
            if (inTable && line.startsWith("## ")) {
                break;
            }
            if (!inTable || !line.startsWith("| `")) {
                continue;
            }
            String[] cells = line.split("\\|");
            rows.add(new Row(unquote(cells[1]), cells[2].trim().equals("-") ? "" : unquote(cells[2]),
                    unquote(cells[3]), cells[4].trim()));
        }
        return rows;
    }

    /** Default of {@code ${NAME:default}} in a yaml file, "" for {@code ${NAME}} or {@code ${NAME:}}, null if absent. */
    private static String placeholderDefault(String yaml, String name) {
        Matcher m = Pattern.compile("\\$\\{" + Pattern.quote(name) + "(?::([^}]*))?}").matcher(yaml);
        if (!m.find()) {
            return null;
        }
        String value = m.group(1) == null ? "" : m.group(1).trim();
        if (value.length() >= 2 && value.startsWith("`") && value.endsWith("`")) {
            value = value.substring(1, value.length() - 1);
        }
        if (value.length() >= 2 && value.startsWith("\"") && value.endsWith("\"") && !value.startsWith("[")) {
            value = value.substring(1, value.length() - 1);
        }
        return value;
    }

    private static String unquote(String cell) {
        String value = cell.trim();
        if (value.length() >= 2 && value.startsWith("`") && value.endsWith("`")) {
            value = value.substring(1, value.length() - 1);
        }
        return value;
    }

    private static String read(Path path) throws IOException {
        return Files.readString(path, StandardCharsets.UTF_8);
    }
}
