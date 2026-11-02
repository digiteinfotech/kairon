package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.support.Maps;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

/**
 * Python's {@code Model.objects(...).get().to_mongo().to_dict()} with {@code _id} popped, for the prompt and
 * database action configs (kairon/shared/actions/data_objects.py). mongoengine loads a missing or null field as
 * its default, then {@code to_mongo()} writes declared fields in declaration order and omits None values (except
 * {@code null=True} fields). Undeclared stored keys (Python would reject them) are kept after the declared ones.
 */
final class ConfigViews {

    private ConfigViews() {}

    /** Python DEFAULT_LLM; the PromptAction.llm_type default. */
    static final String DEFAULT_LLM = "openai";

    /** PromptAction declared fields in order; {@code hyperparameters} default is computed lazily. */
    static Document prompt(Document raw, Supplier<Map<String, Object>> defaultHyperparameters) {
        View view = new View(raw);
        view.plain("name");
        view.withDefault("num_bot_responses", 5);
        view.withDefault("failure_message", Kairon.DEFAULT_FALLBACK);
        view.embedded("user_question", ConfigViews::userQuestion, true);
        view.plain("bot");
        view.plain("user");
        view.withDefault("timestamp", new Date());
        view.withDefault("llm_type", DEFAULT_LLM);
        view.seen.add("hyperparameters");
        Object hyperparameters = view.in.get("hyperparameters");
        view.out.put("hyperparameters", hyperparameters != null ? hyperparameters : defaultHyperparameters.get());
        view.list("llm_prompts", ConfigViews::llmPrompt);
        view.list("instructions", item -> item);
        view.list("set_slots", ConfigViews::setSlot);
        view.withDefault("dispatch_response", true);
        view.withDefault("process_media", false);
        view.withDefault("status", true);
        return view.finish();
    }

    /** HttpActionConfig declared fields in order. */
    static Document http(Document raw) {
        View view = new View(raw);
        view.plain("action_name");
        view.plain("http_url");
        view.plain("request_method");
        view.withDefault("content_type", "json");
        view.list("params_list", ConfigViews::httpParam);
        view.plain("dynamic_params");
        view.list("headers", ConfigViews::httpParam);
        view.embedded("response", ConfigViews::httpResponse, true);
        view.list("set_slots", ConfigViews::setSlot);
        view.plain("bot");
        view.plain("user");
        view.withDefault("timestamp", new Date());
        view.withDefault("status", true);
        return view.finish();
    }

    /** HttpActionRequestBody: key omitted when None, value "", parameter_type value, encrypt False. */
    private static Object httpParam(Object raw) {
        if (!(raw instanceof Map<?, ?>)) {
            return raw;
        }
        View view = new View(raw);
        view.plain("key");
        view.withDefault("value", "");
        view.withDefault("parameter_type", "value");
        view.withDefault("encrypt", false);
        return view.finish();
    }

    /** DatabaseAction declared fields in order. */
    static Document database(Document raw) {
        View view = new View(raw);
        view.plain("name");
        view.plain("collection");
        view.list("payload", ConfigViews::dbQuery);
        view.embedded("response", ConfigViews::httpResponse, true);
        view.list("set_slots", ConfigViews::setSlot);
        view.withDefault("db_type", "qdrant");
        view.withDefault("failure_response", Kairon.FAILED_DOT);
        view.plain("bot");
        view.plain("user");
        view.withDefault("timestamp", new Date());
        view.withDefault("status", true);
        return view.finish();
    }

    /** HttpActionResponse: value (None omitted), dispatch True, evaluation_type expression, dispatch_type text. */
    static Document httpResponse(Object raw) {
        View view = new View(raw);
        view.plain("value");
        view.withDefault("dispatch", true);
        view.withDefault("evaluation_type", "expression");
        view.withDefault("dispatch_type", "text");
        return view.finish();
    }

    private static Document userQuestion(Object raw) {
        View view = new View(raw);
        view.withDefault("type", "from_user_message");
        view.plain("value");
        return view.finish();
    }

    private static Object setSlot(Object raw) {
        if (!(raw instanceof Map<?, ?>)) {
            return raw;
        }
        View view = new View(raw);
        view.plain("name");
        view.plain("value");
        view.withDefault("evaluation_type", "expression");
        return view.finish();
    }

    private static Object dbQuery(Object raw) {
        if (!(raw instanceof Map<?, ?>)) {
            return raw;
        }
        View view = new View(raw);
        view.plain("type");
        view.plain("value");
        view.plain("query_type");
        return view.finish();
    }

    private static Object llmPrompt(Object raw) {
        if (!(raw instanceof Map<?, ?>)) {
            return raw;
        }
        View view = new View(raw);
        view.plain("name");
        view.embedded("hyperparameters", ConfigViews::promptHyperparameter, false);
        view.plain("data");
        view.plain("instructions");
        view.plain("type");
        view.withDefault("source", "static");
        view.withDefault("is_enabled", true);
        view.embedded("crud_config", ConfigViews::crudConfig, false);
        return view.finish();
    }

    private static Document promptHyperparameter(Object raw) {
        View view = new View(raw);
        view.withDefault("top_results", 10);
        view.withDefault("similarity_threshold", 0.70);
        return view.finish();
    }

    private static Document crudConfig(Object raw) {
        View view = new View(raw);
        view.withDefault("collections", new ArrayList<>());
        view.withDefault("query", new Document());
        view.withDefault("result_limit", 10);
        // StringField(null=True): to_mongo keeps an unset value as None
        view.out.put("query_source", view.in.get("query_source"));
        view.seen.add("query_source");
        return view.finish();
    }

    /** Builds one document view: declared keys in call order, then leftover stored keys except {@code _id}. */
    private static final class View {
        final Map<String, Object> in;
        final Document out = new Document();
        final List<String> seen = new ArrayList<>();

        View(Object raw) {
            this.in = raw instanceof Map<?, ?> ? new LinkedHashMap<>(Maps.map(raw)) : new LinkedHashMap<>();
        }

        void plain(String key) {
            seen.add(key);
            Object value = in.get(key);
            if (value != null) {
                out.put(key, value);
            }
        }

        void withDefault(String key, Object fallback) {
            seen.add(key);
            Object value = in.get(key);
            out.put(key, value != null ? value : fallback);
        }

        void embedded(String key, java.util.function.Function<Object, Document> view, boolean hasDefault) {
            seen.add(key);
            Object value = in.get(key);
            if (value instanceof Map<?, ?>) {
                out.put(key, view.apply(value));
            } else if (value == null && hasDefault) {
                out.put(key, view.apply(null));
            } else if (value != null) {
                out.put(key, value);
            }
        }

        void list(String key, java.util.function.Function<Object, Object> item) {
            seen.add(key);
            Object value = in.get(key);
            if (value instanceof List<?> items) {
                List<Object> mapped = new ArrayList<>();
                for (Object element : items) {
                    mapped.add(item.apply(element));
                }
                out.put(key, mapped);
            } else {
                out.put(key, value != null ? value : new ArrayList<>());
            }
        }

        Document finish() {
            in.forEach((key, value) -> {
                if (!seen.contains(key) && !"_id".equals(key)) {
                    out.put(key, value);
                }
            });
            return out;
        }
    }
}
