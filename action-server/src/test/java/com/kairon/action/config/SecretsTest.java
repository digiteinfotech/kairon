package com.kairon.action.config;

import com.kairon.action.ActionSettings;
import com.kairon.action.SecretsValidator;
import io.micronaut.context.ApplicationContext;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-034: cavekit-config-and-deploy.md R2 c1-c6, no shipped secrets and fail-fast startup. */
class SecretsTest {

    private static final Path PORT = Path.of("").toAbsolutePath();
    private static final Path SYSTEM_YAML = PORT.resolve("../system.yaml").normalize();
    private static final Path APPLICATION_YML = PORT.resolve("src/main/resources/application.yml");
    private static final List<String> SECRETS = List.of("FERNET_KEY", "SECRET_KEY", "ASYNC_CALLBACK_AES_KEY", "ASYNC_CALLBACK_AES_IV");
    private static final Set<String> SKIPPED_DIRS = Set.of("build", ".gradle", ".idea", "out", "bin");

    private static Map<String, Object> allSecrets() {
        Map<String, Object> properties = new LinkedHashMap<>();
        for (String name : SECRETS) {
            properties.put(name, "test-" + name.toLowerCase());
        }
        return properties;
    }

    /** c2-c5: each secret, when missing, stops startup with an error naming it. */
    @ParameterizedTest
    @ValueSource(strings = {"FERNET_KEY", "SECRET_KEY", "ASYNC_CALLBACK_AES_KEY", "ASYNC_CALLBACK_AES_IV"})
    void startupFailsNamingTheMissingSecret(String missing) {
        Map<String, Object> properties = allSecrets();
        properties.put(missing, "");
        Throwable error = assertThrows(Throwable.class,
                () -> ApplicationContext.builder().deduceEnvironment(false).properties(properties).start().close());
        String messages = chain(error);
        assertTrue(messages.contains(missing), messages);
        for (String other : SECRETS) {
            if (!other.equals(missing)) {
                assertFalse(messages.contains(other), other + " is set and must not be reported: " + messages);
            }
        }
    }

    @Test
    void startupSucceedsWithAllSecrets() {
        assertDoesNotThrow(() -> ApplicationContext.builder().deduceEnvironment(false).properties(allSecrets()).start().close());
    }

    @Test
    void validatorNamesEveryMissingSecret() {
        ActionSettings settings = new ActionSettings();
        Throwable error = assertThrows(RuntimeException.class, () -> SecretsValidator.validate(settings));
        for (String name : SECRETS) {
            assertTrue(error.getMessage().contains(name), error.getMessage());
        }
    }

    /** c1: the packaged config binds each secret to its env var with an empty default. */
    @Test
    void packagedConfigHasNoSecretValues() throws IOException {
        String application = Files.readString(APPLICATION_YML, StandardCharsets.UTF_8);
        for (String name : SECRETS) {
            Matcher m = Pattern.compile("\\$\\{" + name + "(?::([^}]*))?}").matcher(application);
            assertTrue(m.find(), name + " is not bound in application.yml");
            assertEquals("", m.group(1) == null ? "" : m.group(1).trim(), name + " must have no default");
        }
        ActionSettings defaults = new ActionSettings();
        assertEquals("", defaults.getFernetKey());
        assertEquals("", defaults.getJwtSecret());
        assertEquals("", defaults.getAsyncCallbackAesKey());
        assertEquals("", defaults.getAsyncCallbackAesIv());
    }

    /** c6: no default secret from the Python system.yaml appears anywhere in the port's tree. Values are read at runtime. */
    @Test
    void pythonDefaultSecretsAppearNowhereInThePort() throws IOException {
        String system = Files.readString(SYSTEM_YAML, StandardCharsets.UTF_8);
        List<String> needles = new ArrayList<>();
        for (String name : SECRETS) {
            Matcher m = Pattern.compile("\\$\\{" + name + ":([^}\\n]*)}").matcher(system);
            assertTrue(m.find(), name + " has no default in system.yaml; the scan would prove nothing");
            String value = m.group(1).trim();
            if (value.length() >= 2 && (value.startsWith("\"") || value.startsWith("'")) && value.charAt(value.length() - 1) == value.charAt(0)) {
                value = value.substring(1, value.length() - 1);
            }
            assertTrue(value.length() >= 8, name + " default too short to scan for meaningfully");
            needles.add(value);
        }
        List<String> hits = new ArrayList<>();
        int[] scanned = {0};
        try (Stream<Path> files = Files.walk(PORT)) {
            files.filter(Files::isRegularFile)
                    .filter(path -> PORT.relativize(path).getNameCount() == 1
                            || !SKIPPED_DIRS.contains(PORT.relativize(path).getName(0).toString()))
                    .forEach(path -> {
                        try {
                            String text = new String(Files.readAllBytes(path), StandardCharsets.ISO_8859_1);
                            scanned[0]++;
                            for (int i = 0; i < needles.size(); i++) {
                                if (text.contains(needles.get(i))) {
                                    hits.add(SECRETS.get(i) + " default found in " + PORT.relativize(path));
                                }
                            }
                        } catch (IOException e) {
                            throw new RuntimeException(e);
                        }
                    });
        }
        assertTrue(scanned[0] > 50, "scan saw only " + scanned[0] + " files");
        assertTrue(hits.isEmpty(), String.join("\n", hits));
    }

    private static String chain(Throwable error) {
        StringBuilder out = new StringBuilder();
        for (Throwable t = error; t != null; t = t.getCause()) {
            out.append(t.getMessage()).append('\n');
        }
        return out.toString();
    }
}
