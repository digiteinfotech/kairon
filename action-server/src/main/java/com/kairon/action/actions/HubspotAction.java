package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Singleton
public class HubspotAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(HubspotAction.class);

    private final ActionSupport support;

    public HubspotAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "hubspot_forms_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("hubspot_forms_action", context.bot, "name", context.actionName,
                "No Hubspot forms action found for given action and bot");
        Object botResponse = config.get("response");
        String status = Kairon.SUCCESS;
        String exception = null;
        Object httpResponse = null;
        Map<String, Object> request = null;
        try {
            String url = "https://api.hsforms.com/submissions/v3/integration/submit/"
                    + config.get("portal_id") + "/" + config.get("form_guid");
            Map<String, Object> trackerData = support.context(context.tracker, false);
            // Python prepare_hubspot_form_request iterates action_config.get("fields"); None is
            // TypeError: 'NoneType' object is not iterable.
            if (config.get("fields") == null) {
                throw new ActionFailure("'NoneType' object is not iterable");
            }
            List<Map<String, Object>> fields = new ArrayList<>();
            for (Map<String, Object> field : Maps.mapList(config.get("fields"))) {
                ActionSupport.Prepared prepared = support.prepareRequest(trackerData, List.of(field), context.bot);
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("name", field.get("key"));
                item.put("value", prepared.body().get(Maps.str(field.get("key"))));
                fields.add(item);
            }
            request = new LinkedHashMap<>();
            request.put("fields", fields);
            httpResponse = support.http().executeStrict("POST", url, Map.of("Content-Type", "application/json"), request, "json");
        } catch (Exception e) {
            LOG.error("hubspot action failed", e);
            exception = ActionFlags.message(e);
            status = Kairon.FAIL;
            botResponse = Kairon.FAILED;
            support.failureMail(context, e);
        } finally {
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("request_params", request);
            extra.put("api_response", Maps.truthy(httpResponse) ? PyRepr.str(httpResponse) : null);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        ActionFlags.utterText(context.dispatcher, botResponse);
        return ActionFlags.response(botResponse);
    }
}
