package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.HttpCaller;
import com.kairon.action.support.Maps;
import com.kairon.action.support.PyRepr;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;

@Singleton
public class RazorpayAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(RazorpayAction.class);
    private static final String URL = "https://api.razorpay.com/v1/payment_links/";

    private final ActionSupport support;

    public RazorpayAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "razorpay_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("razorpay_action", context.bot, "name", context.actionName,
                "No Razorpay action found for given action and bot");
        Object botResponse = null;
        Object httpResponse = null;
        Map<String, Object> body = new LinkedHashMap<>();
        Object amountRaw = null;
        String status = Kairon.SUCCESS;
        String exception = null;
        try {
            Map<String, Object> trackerData = support.context(context.tracker, false);
            Object apiKey = support.one(trackerData, config.get("api_key"), context.bot);
            Object apiSecret = support.one(trackerData, config.get("api_secret"), context.bot);
            amountRaw = support.one(trackerData, config.get("amount"), context.bot);
            if (Maps.isEmpty(amountRaw)) {
                throw new ActionFailure("amount must be a whole number! Got " + PyRepr.str(amountRaw) + ".");
            }
            long amount = whole(amountRaw);
            Object currency = support.one(trackerData, config.get("currency"), context.bot);
            Object username = support.one(trackerData, config.get("username"), context.bot);
            Object email = support.one(trackerData, config.get("email"), context.bot);
            Object contact = support.one(trackerData, config.get("contact"), context.bot);
            ActionSupport.Prepared notes = support.prepareRequest(trackerData, config.get("notes"), context.bot);
            Map<String, Object> customer = new LinkedHashMap<>();
            customer.put("username", username);
            customer.put("email", email);
            customer.put("contact", contact);
            Map<String, Object> noteBody = new LinkedHashMap<>(notes.body());
            noteBody.put("bot", context.bot);
            body.put("amount", amount);
            body.put("currency", currency);
            body.put("customer", customer);
            body.put("notes", noteBody);
            Map<String, String> headers = Map.of(
                    "Authorization", HttpCaller.basic(Maps.str(apiKey), Maps.str(apiSecret)),
                    "Content-Type", "application/json");
            httpResponse = support.http().executeStrict("POST", URL, headers, body, "json");
            // Python http_response["short_url"]: missing key is KeyError("'short_url'"), FAIL + mail.
            Map<String, Object> payload = Maps.map(httpResponse);
            if (!(httpResponse instanceof Map<?, ?>) || !payload.containsKey("short_url")) {
                throw new ActionFailure("'short_url'");
            }
            botResponse = payload.get("short_url");
        } catch (NumberFormatException e) {
            LOG.error("razorpay amount", e);
            exception = "amount must be a whole number! Got " + PyRepr.str(amountRaw) + ".";
            status = Kairon.FAIL;
            botResponse = Kairon.FAILED;
        } catch (Exception e) {
            LOG.error("razorpay action failed", e);
            exception = e instanceof ActionFailure && e.getMessage() != null && e.getMessage().startsWith("amount must")
                    ? e.getMessage()
                    : ActionFlags.message(e);
            status = Kairon.FAIL;
            botResponse = Kairon.FAILED;
            support.failureMail(context, e);
        } finally {
            Map<String, Object> extra = new LinkedHashMap<>();
            extra.put("api_response", httpResponse == null ? null : String.valueOf(httpResponse));
            extra.put("request", body);
            support.save(context, type(), status, exception, botResponse, extra);
        }
        ActionFlags.utterText(context.dispatcher, botResponse);
        return ActionFlags.response(botResponse);
    }

    /** Python int() truncates numbers and rejects decimal strings. */
    static long whole(Object amount) {
        if (amount instanceof Number number) {
            return number.longValue();
        }
        String text = String.valueOf(amount).trim();
        if (text.indexOf('.') >= 0 || text.indexOf('e') >= 0 || text.indexOf('E') >= 0) {
            throw new NumberFormatException(text);
        }
        return Long.parseLong(text);
    }
}
