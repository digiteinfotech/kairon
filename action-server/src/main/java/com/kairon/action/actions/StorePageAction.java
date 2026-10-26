package com.kairon.action.actions;

import com.kairon.action.Kairon;
import com.kairon.action.runtime.ActionContext;
import com.kairon.action.runtime.ActionFailure;
import com.kairon.action.runtime.KaironAction;
import com.kairon.action.support.ActionSupport;
import com.kairon.action.support.Maps;
import jakarta.inject.Singleton;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Singleton
public class StorePageAction implements KaironAction {

    private static final Logger LOG = LoggerFactory.getLogger(StorePageAction.class);
    private static final List<String> ACCESS = List.of(
            "/api/bot/.+/customer_data/.*",
            "/api/bot/.+/store_page/metadata",
            "/api/bot/.+/data/collection/.*",
            "/api/bot/.+/store_page/exec/flow"
    );

    private final ActionSupport support;

    public StorePageAction(ActionSupport support) {
        this.support = support;
    }

    @Override
    public String type() {
        return "store_page_action";
    }

    @Override
    public Map<String, Object> execute(ActionContext context) {
        Document config = support.require("store_page_action", context.bot, "name", context.actionName,
                "No StorePageAction found for given action and bot");
        Object pageName = config.containsKey("page_name") ? config.get("page_name") : "";
        Object identifierSlot = config.containsKey("identifier_slot") ? config.get("identifier_slot") : "";
        Object callbackSlot = config.get("callback_identifier");
        Map<String, Object> slots = new LinkedHashMap<>();
        String status = Kairon.SUCCESS;
        String exception = null;
        ActionFailure rethrow = null;
        try {
            Object identifier = context.tracker.slotValue(Maps.str(identifierSlot));
            Object callbackIdentifier = context.tracker.slotValue(Maps.str(callbackSlot));
            if (Maps.isEmpty(identifier)) {
                String slotLabel = identifierSlot == null ? "None" : String.valueOf(identifierSlot);
                String sender = context.tracker.senderId == null ? "None" : context.tracker.senderId;
                throw new ActionFailure("Slot '" + slotLabel + "' is absent or empty for sender " + sender);
            }
            String encrypted = support.tokens().encrypt(String.valueOf(identifier));
            int minutes = expiryMinutes(context.bot);
            Map<String, Object> claims = new LinkedHashMap<>();
            claims.put("sub", context.tracker.senderId);
            claims.put("bot", context.bot);
            String token = support.tokens().storePageToken(claims, minutes, ACCESS);
            slots.put("user_identifier", encrypted);
            slots.put("temp_token", token);
            slots.put("store_page_name", pageName);
            slots.put("callback_identifier", callbackIdentifier);
        } catch (ActionFailure e) {
            exception = ActionFlags.message(e);
            status = Kairon.FAIL;
            rethrow = e;
        } catch (Exception e) {
            exception = ActionFlags.message(e);
            LOG.error("store page action failed", e);
            status = Kairon.FAIL;
        } finally {
            support.save(context, type(), status, exception, null, null);
        }
        if (rethrow != null) {
            throw rethrow;
        }
        return slots;
    }

    /** Python loads BotSettings without a status filter. A missing document is a generic failure. */
    private int expiryMinutes(String bot) {
        Document settings = null;
        for (Document document : support.catalog().findByBot("bot_settings", bot)) {
            settings = document;
            break;
        }
        if (settings == null) {
            throw new IllegalStateException("BotSettings matching query does not exist.");
        }
        Object expiry = settings.get("store_page_token_expiry");
        if (Maps.truthy(expiry) && expiry instanceof Number number) {
            return number.intValue();
        }
        return com.kairon.action.support.Tokens.STORE_PAGE_DEFAULT_EXPIRY;
    }
}
