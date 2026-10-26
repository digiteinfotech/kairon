package com.kairon.action;

public final class Kairon {

    public static final String ACTION_RESPONSE = "kairon_action_response";
    public static final String USER_MSG = "kairon_user_msg";
    public static final String LLM_CALL_ID = "llm_call_id";
    public static final String REQUEST_ID = "X-Kairon-Request-ID";
    public static final String TIMESTAMP = "X-TimeStamp";
    public static final String FAQ_DISABLED = "Faq feature is disabled for the bot! Please contact support.";
    public static final String DEFAULT_FALLBACK = "I'm sorry, I didn't quite understand that. Could you rephrase?";
    public static final String UTTER_DEFAULT = "utter_default";
    public static final String FAILED = "I have failed to process your request";
    public static final String FAILED_DOT = "I have failed to process your request.";
    public static final String SORRY = "Sorry, I am unable to process your request at the moment.";
    public static final String JIRA_FAIL = "I have failed to create issue for you";
    public static final String LEAD_FAIL = "I have failed to create lead for you";
    public static final String CALL_OK = "I'm placing a call to you now.";
    public static final String CALL_FAIL = "I have failed to place the call";
    public static final String LOGS = "action_server_logs";
    public static final String SUCCESS = "Success";
    public static final String FAIL = "Failed";

    private Kairon() {}
}
