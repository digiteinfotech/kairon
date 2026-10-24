use serde_json::{Map, Value};

use crate::pyfmt::py_truthy;

pub const NLU_FALLBACK: &str = "nlu_fallback";
pub const USER_MSG_ENTITY: &str = "kairon_user_msg";

#[derive(Clone, Debug)]
pub struct Tracker {
    pub sender_id: String,
    pub slots: Map<String, Value>,
    pub latest_message: Value,
    pub events: Vec<Value>,
    pub followup_action: Option<String>,
    pub latest_action_name: Option<String>,
}

impl Tracker {
    pub fn from_value(value: &Value) -> Self {
        let obj = value.as_object();
        let slots = obj
            .and_then(|map| map.get("slots"))
            .and_then(|slots| slots.as_object())
            .cloned()
            .unwrap_or_default();
        let latest_message = obj
            .and_then(|map| map.get("latest_message"))
            .cloned()
            .filter(|msg| msg.is_object())
            .unwrap_or_else(|| Value::Object(Map::new()));
        let events = obj
            .and_then(|map| map.get("events"))
            .and_then(|events| events.as_array())
            .cloned()
            .unwrap_or_default();
        Self {
            sender_id: obj
                .and_then(|map| map.get("sender_id"))
                .and_then(|id| id.as_str())
                .unwrap_or("")
                .to_string(),
            slots,
            latest_message,
            events,
            followup_action: obj
                .and_then(|map| map.get("followup_action"))
                .and_then(|v| v.as_str())
                .map(str::to_string),
            latest_action_name: obj
                .and_then(|map| map.get("latest_action_name"))
                .and_then(|v| v.as_str())
                .map(str::to_string),
        }
    }

    pub fn get_slot(&self, name: &str) -> Value {
        self.slots.get(name).cloned().unwrap_or(Value::Null)
    }

    pub fn current_slots(&self) -> Map<String, Value> {
        self.slots.clone()
    }

    pub fn user_text(&self) -> Option<String> {
        self.latest_message
            .get("text")
            .and_then(|text| text.as_str())
            .map(str::to_string)
    }

    pub fn intent(&self, skip_fallback: bool) -> Option<String> {
        let ranking = self.latest_message.get("intent_ranking")?.as_array()?;
        if ranking.is_empty() {
            return None;
        }
        let highest = ranking[0].get("name")?.as_str()?;
        if skip_fallback && highest == NLU_FALLBACK {
            if ranking.len() >= 2 {
                return ranking[1].get("name").and_then(|n| n.as_str()).map(str::to_string);
            }
            return None;
        }
        Some(highest.to_string())
    }

    /// First entity value whose type matches and whose group and role are both absent.
    pub fn latest_entity(&self, entity_type: &str) -> Option<String> {
        let entities = self.latest_message.get("entities")?.as_array()?;
        for entity in entities {
            let kind = entity.get("entity").and_then(|v| v.as_str());
            if kind != Some(entity_type) {
                continue;
            }
            if !field_is_none(entity, "group") || !field_is_none(entity, "role") {
                continue;
            }
            if let Some(value) = entity.get("value").and_then(|v| v.as_str()) {
                return Some(value.to_string());
            }
        }
        None
    }

    /// Latest user event's `input_channel`, walking events from the end.
    pub fn latest_input_channel(&self) -> Option<String> {
        for event in self.events.iter().rev() {
            if event.get("event").and_then(|v| v.as_str()) == Some("user") {
                return event
                    .get("input_channel")
                    .and_then(|v| v.as_str())
                    .map(str::to_string);
            }
        }
        None
    }

    pub fn followup_or(&self, action: &str) -> String {
        if let Some(name) = &self.followup_action {
            if !name.is_empty() {
                return name.clone();
            }
        }
        if let Some(name) = &self.latest_action_name {
            if !name.is_empty() {
                return name.clone();
            }
        }
        action.to_string()
    }
}

#[derive(Clone, Debug, Default)]
pub struct Dispatcher {
    pub messages: Vec<Value>,
}

impl Dispatcher {
    pub fn utter(
        &mut self,
        text: Option<Value>,
        buttons: Option<Value>,
        elements: Option<Value>,
        custom: Option<Value>,
        response: Option<Value>,
        image: Option<Value>,
        attachment: Option<Value>,
    ) {
        let message = serde_json::json!({
            "text": text.unwrap_or(Value::Null),
            "buttons": or_empty_list(buttons),
            "elements": or_empty_list(elements),
            "custom": custom.filter(py_truthy).unwrap_or_else(|| serde_json::json!({})),
            "template": response.clone().unwrap_or(Value::Null),
            "response": response.unwrap_or(Value::Null),
            "image": image.unwrap_or(Value::Null),
            "attachment": attachment.unwrap_or(Value::Null),
        });
        self.messages.push(message);
    }

    pub fn utter_text(&mut self, text: Value) {
        self.utter(Some(text), None, None, None, None, None, None);
    }

    pub fn utter_response(&mut self, name: &str) {
        self.utter(
            None,
            None,
            None,
            None,
            Some(Value::String(name.to_string())),
            None,
            None,
        );
    }

    pub fn utter_custom_json(&mut self, custom: Value) {
        self.utter(None, None, None, Some(custom), None, None, None);
    }

    pub fn utter_buttons(&mut self, text: Value, buttons: Value) {
        self.utter(Some(text), Some(buttons), None, None, None, None, None);
    }

    /// `utter_message(**mapping)`. `template` is ignored; `response` fills both fields.
    pub fn utter_mapping(&mut self, mapping: &Value) {
        let obj = mapping.as_object();
        let get = |key: &str| obj.and_then(|map| map.get(key)).cloned();
        self.utter(
            get("text"),
            get("buttons"),
            get("elements"),
            get("json_message"),
            get("response"),
            get("image"),
            get("attachment"),
        );
        if let Some(map) = obj {
            if let Some(Value::Object(dest)) = self.messages.last_mut() {
                for (key, value) in map {
                    if !matches!(
                        key.as_str(),
                        "text"
                            | "image"
                            | "json_message"
                            | "template"
                            | "response"
                            | "attachment"
                            | "buttons"
                            | "elements"
                    ) {
                        dest.insert(key.clone(), value.clone());
                    }
                }
            }
        }
    }
}

fn field_is_none(entity: &Value, key: &str) -> bool {
    matches!(entity.get(key), None | Some(Value::Null))
}

fn or_empty_list(value: Option<Value>) -> Value {
    match value {
        None | Some(Value::Null) => serde_json::json!([]),
        Some(Value::Array(items)) if items.is_empty() => serde_json::json!([]),
        Some(Value::Bool(false)) => serde_json::json!([]),
        Some(other) if !py_truthy(&other) => serde_json::json!([]),
        Some(other) => other,
    }
}

pub fn slot_events(slots: &Map<String, Value>) -> Vec<Value> {
    slots
        .iter()
        .map(|(name, value)| {
            serde_json::json!({
                "event": "slot",
                "timestamp": null,
                "name": name,
                "value": value,
            })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn intent_skips_only_fallback() {
        let tracker = Tracker::from_value(&json!({
            "sender_id": "s",
            "slots": {},
            "latest_message": {
                "intent_ranking": [{"name": "nlu_fallback"}, {"name": "greet"}]
            },
            "events": []
        }));
        assert_eq!(tracker.intent(true).as_deref(), Some("greet"));
        assert_eq!(tracker.intent(false).as_deref(), Some("nlu_fallback"));
    }

    #[test]
    fn sole_fallback_is_none_when_skipped() {
        let tracker = Tracker::from_value(&json!({
            "latest_message": {"intent_ranking": [{"name": "nlu_fallback"}]}
        }));
        assert_eq!(tracker.intent(true), None);
    }

    #[test]
    fn entity_requires_empty_group_and_role() {
        let tracker = Tracker::from_value(&json!({
            "latest_message": {
                "entities": [
                    {"entity": "kairon_user_msg", "value": "skip", "group": "g", "role": null},
                    {"entity": "kairon_user_msg", "value": "keep"}
                ]
            }
        }));
        assert_eq!(tracker.latest_entity(USER_MSG_ENTITY).as_deref(), Some("keep"));
    }

    #[test]
    fn input_channel_is_latest_user_event() {
        let tracker = Tracker::from_value(&json!({
            "latest_message": {"input_channel": "nope"},
            "events": [
                {"event": "user", "input_channel": "telegram", "text": "a"},
                {"event": "bot", "text": "b"},
                {"event": "user", "input_channel": "whatsapp", "text": "c"}
            ]
        }));
        assert_eq!(tracker.latest_input_channel().as_deref(), Some("whatsapp"));
    }

    #[test]
    fn utter_response_sets_template_from_response() {
        let mut dispatcher = Dispatcher::default();
        dispatcher.utter_response("utter_default");
        assert_eq!(dispatcher.messages[0]["template"], "utter_default");
        assert_eq!(dispatcher.messages[0]["response"], "utter_default");
        assert!(dispatcher.messages[0]["text"].is_null());
        assert_eq!(dispatcher.messages[0]["buttons"], json!([]));
        assert_eq!(dispatcher.messages[0]["custom"], json!({}));
    }
}
