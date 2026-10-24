use serde_json::{json, Map, Value};

use super::{intent_of, save_log, text_of};
use crate::context::{note_failure_mail, py_log_str, trigger_info, ExecCtx};
use crate::error::ActionError;

pub async fn execute(ctx: &mut ExecCtx) -> Result<Map<String, Value>, ActionError> {
    let mut status = "Success".to_string();
    let mut exception = Value::Null;
    if let Err(err) = utter_disconnect(ctx) {
        exception = Value::String(err.to_string());
        status = "Failed".to_string();
        note_failure_mail(&ctx.bot, &ctx.action, ctx.tracker.user_text().as_deref());
    }
    let doc = json!({
        "type": "kairon_voice_disconnect",
        "intent": intent_of(&ctx.tracker, false),
        "action": ctx.action,
        "sender": ctx.tracker.sender_id,
        "bot": ctx.bot,
        "exception": exception,
        "bot_response": py_log_str(&json!({"disconnect": true})),
        "status": status,
        "user_msg": text_of(&ctx.tracker),
        "trigger_info": trigger_info(&ctx.action_call),
        "request_id": ctx.request_id,
    });
    save_log(ctx.store.as_ref(), doc).await?;
    Ok(Map::new())
}

fn utter_disconnect(ctx: &mut ExecCtx) -> Result<(), ActionError> {
    ctx.dispatcher
        .utter_custom_json(json!({"disconnect": true}));
    Ok(())
}
