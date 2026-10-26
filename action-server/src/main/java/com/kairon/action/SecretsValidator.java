package com.kairon.action;

import io.micronaut.context.annotation.Context;
import io.micronaut.context.exceptions.ConfigurationException;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Fails startup when a required secret is unset. The packaged application.yml gives these no default
 * (cavekit-config-and-deploy.md R2), so each must come from the environment. Eagerly created via {@link Context}.
 */
@Context
public class SecretsValidator {

    /** Env var name (as in the Python system.yaml) to the setting it fills. */
    static final Map<String, Function<ActionSettings, String>> REQUIRED = required();

    public SecretsValidator(ActionSettings settings) {
        validate(settings);
    }

    /** Throws naming every missing secret by its env var name. */
    public static void validate(ActionSettings settings) {
        List<String> missing = new ArrayList<>();
        REQUIRED.forEach((env, getter) -> {
            String value = getter.apply(settings);
            if (value == null || value.isBlank()) {
                missing.add(env);
            }
        });
        if (!missing.isEmpty()) {
            throw new ConfigurationException("Missing required secret" + (missing.size() > 1 ? "s" : "") + ": "
                    + String.join(", ", missing) + ". Set " + (missing.size() > 1 ? "them" : "it")
                    + " in the environment; the packaged config has no default.");
        }
    }

    private static Map<String, Function<ActionSettings, String>> required() {
        Map<String, Function<ActionSettings, String>> map = new LinkedHashMap<>();
        map.put("FERNET_KEY", ActionSettings::getFernetKey);
        map.put("SECRET_KEY", ActionSettings::getJwtSecret);
        map.put("ASYNC_CALLBACK_AES_KEY", ActionSettings::getAsyncCallbackAesKey);
        map.put("ASYNC_CALLBACK_AES_IV", ActionSettings::getAsyncCallbackAesIv);
        return java.util.Collections.unmodifiableMap(map);
    }
}
