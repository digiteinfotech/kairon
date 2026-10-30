package com.kairon.action.actions.prompt;

import com.kairon.action.catalog.ActionCatalog;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.TrackerState;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Jsons;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import com.kairon.action.support.Tokens;
import org.bson.Document;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Python ActionPrompt {@code crud} source (kairon/actions/definitions/prompt.py:203-241) over
 * DataProcessor.get_collection_data / prepare_decrypted_data (kairon/shared/data/collection_processor.py).
 */
public final class CrudSource implements PromptParams.ContextSource {

    public static final int DEFAULT_RESULT_LIMIT = 10;

    private final ActionCatalog catalog;
    private final Tokens tokens;
    private final String bot;
    private final TrackerState tracker;

    public CrudSource(ActionCatalog catalog, Tokens tokens, String bot, TrackerState tracker) {
        this.catalog = catalog;
        this.tokens = tokens;
        this.bot = bot;
        this.tracker = tracker;
    }

    @Override
    public String render(Map<String, Object> prompt) {
        Map<String, Object> crudConfig = Maps.map(prompt.get("crud_config"));
        List<Object> collections = crudConfig.containsKey("collections") ? Maps.list(crudConfig.get("collections")) : List.of();
        Object querySource = crudConfig.containsKey("query_source") ? crudConfig.get("query_source") : "value";

        Object query;
        if ("slot".equals(querySource)) {
            Object slotValue = tracker.slotValue(Maps.str(crudConfig.get("query")));
            if (Maps.truthy(slotValue)) {
                if (slotValue instanceof Map<?, ?>) {
                    query = slotValue;
                } else if (slotValue instanceof String text && ActionSupport.pythonJsonError(text) == null) {
                    query = Jsons.readAny(text);
                } else {
                    // json.JSONDecodeError (bad text) or TypeError (non-str slot value)
                    throw new ActionFailure("Invalid JSON format in slot value: " + PyRepr.str(slotValue));
                }
            } else {
                query = new LinkedHashMap<>();
            }
        } else {
            query = crudConfig.containsKey("query") ? crudConfig.get("query") : new LinkedHashMap<>();
            if (query instanceof String text) {
                // no wrapping: str(json.JSONDecodeError) becomes the action exception
                String error = ActionSupport.pythonJsonError(text);
                if (error != null) {
                    throw new ActionFailure(error);
                }
                query = Jsons.readAny(text);
            }
        }

        List<Object> keys = new ArrayList<>();
        List<Object> values = new ArrayList<>();
        if (Maps.truthy(query)) {
            if (!(query instanceof Map<?, ?> dict)) {
                throw new ActionFailure("'" + pyType(query) + "' object has no attribute 'items'");
            }
            dict.forEach((key, value) -> {
                keys.add(key);
                values.add(value);
            });
        }
        int resultLimit = crudConfig.get("result_limit") instanceof Number number ? number.intValue() : DEFAULT_RESULT_LIMIT;

        StringBuilder out = new StringBuilder();
        String name = PyRepr.str(prompt.get("name"));
        for (Object collection : collections) {
            List<Object> dataList = records(Maps.str(collection), keys, values, resultLimit);
            out.append("Collection data for ").append(name).append(":\n").append(PyRepr.str(dataList)).append('\n');
        }
        Object instructions = prompt.get("instructions");
        if (Maps.truthy(instructions)) {
            out.append("Instructions on how to use collection ").append(name).append(":\n")
                    .append(PyRepr.str(instructions)).append("\n\n");
        }
        return out.toString();
    }

    /**
     * DataProcessor.get_collection_data then {@code [rec["data"] for rec in records][:result_limit]}: one
     * {@code filterable_attrs} element match per truthy key/value pair, each record's {@code data} decrypted
     * for its {@code is_secure} keys.
     */
    List<Object> records(String collectionName, List<?> keys, List<?> values, int resultLimit) {
        String name = collectionName.toLowerCase(Locale.ROOT);
        if (keys.size() != values.size()) {
            throw new ActionFailure("Keys and values lists must be of the same length.");
        }
        List<ActionCatalog.AttrFilter> filters = new ArrayList<>();
        for (int i = 0; i < keys.size(); i++) {
            Object key = keys.get(i);
            Object value = values.get(i);
            if (Maps.truthy(key) && Maps.truthy(value)) {
                filters.add(new ActionCatalog.AttrFilter(Maps.str(key), value));
            }
        }
        List<Object> dataList = new ArrayList<>();
        for (Document record : catalog.findCognitionData(bot, name, filters, resultLimit)) {
            if (dataList.size() >= resultLimit) {
                break;
            }
            dataList.add(decrypted(record.get("data"), Maps.list(record.get("is_secure"))));
        }
        return dataList;
    }

    /** DataProcessor.prepare_decrypted_data: Fernet-decrypt values whose key is listed in {@code is_secure}. */
    private Object decrypted(Object data, List<Object> secure) {
        if (!(data instanceof Map<?, ?> map)) {
            return data;
        }
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            Object value = entry.getValue();
            if (secure.contains(entry.getKey())) {
                if (!(value instanceof String text)) {
                    throw new ActionFailure("'" + pyType(value) + "' object has no attribute 'encode'");
                }
                value = tokens.decrypt(text);
            }
            out.put(String.valueOf(entry.getKey()), value);
        }
        return out;
    }

    private static String pyType(Object value) {
        if (value == null) {
            return "NoneType";
        }
        if (value instanceof Boolean) {
            return "bool";
        }
        if (value instanceof Double || value instanceof Float) {
            return "float";
        }
        if (value instanceof Number) {
            return "int";
        }
        if (value instanceof String) {
            return "str";
        }
        if (value instanceof Map<?, ?>) {
            return "dict";
        }
        if (value instanceof List<?>) {
            return "list";
        }
        return value.getClass().getSimpleName();
    }
}
