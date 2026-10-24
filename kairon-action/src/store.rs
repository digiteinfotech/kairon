use std::collections::HashMap;
use std::sync::Mutex;

use async_trait::async_trait;
use bson::{doc, Bson, Document};
use futures_util::TryStreamExt;
use mongodb::Client;
use serde_json::{Map, Value};

use crate::config::Config;
use crate::error::ActionError;
use crate::pyfmt::json_number_equal;

#[async_trait]
pub trait ActionStore: Send + Sync {
    async fn find_one(&self, collection: &str, filter: &Value) -> Result<Option<Value>, ActionError>;
    async fn find_many(
        &self,
        collection: &str,
        filter: &Value,
        limit: Option<i64>,
        sort_desc: Option<&str>,
    ) -> Result<Vec<Value>, ActionError>;
    async fn insert_one(&self, collection: &str, document: Value) -> Result<(), ActionError>;
    async fn update_one(
        &self,
        collection: &str,
        filter: &Value,
        update: &Value,
    ) -> Result<(), ActionError>;
    async fn text_search(
        &self,
        collection: &str,
        query: &str,
        extra: &Value,
        limit: i64,
    ) -> Result<Vec<Value>, ActionError>;
}

pub struct MemoryStore {
    docs: Mutex<HashMap<String, Vec<Value>>>,
}

impl MemoryStore {
    pub fn new() -> Self {
        Self {
            docs: Mutex::new(HashMap::new()),
        }
    }

    pub fn collection(&self, name: &str) -> Vec<Value> {
        let guard = self.docs.lock().unwrap_or_else(|err| err.into_inner());
        guard.get(name).cloned().unwrap_or_default()
    }
}

impl Default for MemoryStore {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl ActionStore for MemoryStore {
    async fn find_one(&self, collection: &str, filter: &Value) -> Result<Option<Value>, ActionError> {
        let docs = self.find_many(collection, filter, Some(1), None).await?;
        Ok(docs.into_iter().next())
    }

    async fn find_many(
        &self,
        collection: &str,
        filter: &Value,
        limit: Option<i64>,
        sort_desc: Option<&str>,
    ) -> Result<Vec<Value>, ActionError> {
        let guard = self.docs.lock().unwrap_or_else(|err| err.into_inner());
        let mut matched: Vec<Value> = guard
            .get(collection)
            .map(|docs| docs.iter().filter(|doc| matches_filter(doc, filter)).cloned().collect())
            .unwrap_or_default();
        if let Some(field) = sort_desc {
            matched.sort_by(|left, right| cmp_desc(left.get(field), right.get(field)));
        }
        if let Some(limit) = limit {
            if limit >= 0 {
                matched.truncate(limit as usize);
            }
        }
        Ok(matched)
    }

    async fn insert_one(&self, collection: &str, document: Value) -> Result<(), ActionError> {
        let mut guard = self.docs.lock().unwrap_or_else(|err| err.into_inner());
        guard.entry(collection.to_string()).or_default().push(document);
        Ok(())
    }

    async fn update_one(
        &self,
        collection: &str,
        filter: &Value,
        update: &Value,
    ) -> Result<(), ActionError> {
        let set = update.get("$set").cloned().unwrap_or_else(|| update.clone());
        let Some(set) = set.as_object().cloned() else {
            return Ok(());
        };
        let mut guard = self.docs.lock().unwrap_or_else(|err| err.into_inner());
        if let Some(docs) = guard.get_mut(collection) {
            if let Some(doc) = docs.iter_mut().find(|doc| matches_filter(doc, filter)) {
                if let Some(obj) = doc.as_object_mut() {
                    for (key, value) in set {
                        obj.insert(key, value);
                    }
                }
            }
        }
        Ok(())
    }

    async fn text_search(
        &self,
        collection: &str,
        query: &str,
        extra: &Value,
        limit: i64,
    ) -> Result<Vec<Value>, ActionError> {
        let guard = self.docs.lock().unwrap_or_else(|err| err.into_inner());
        let needle = query.to_lowercase();
        let mut matched: Vec<Value> = guard
            .get(collection)
            .map(|docs| {
                docs.iter()
                    .filter(|doc| matches_filter(doc, extra))
                    .filter(|doc| {
                        doc.get("text")
                            .and_then(|text| text.as_str())
                            .map(|text| text.to_lowercase().contains(&needle))
                            .unwrap_or(false)
                    })
                    .cloned()
                    .collect()
            })
            .unwrap_or_default();
        if limit >= 0 {
            matched.truncate(limit as usize);
        }
        Ok(matched)
    }
}

pub struct MongoActionStore {
    client: Client,
    db_name: String,
}

impl MongoActionStore {
    pub async fn connect(config: &Config) -> Result<Self, ActionError> {
        let client = Client::with_uri_str(&config.database_url)
            .await
            .map_err(|err| ActionError::failure(format!("mongo connect: {err}")))?;
        Ok(Self {
            client,
            db_name: config.database_name.clone(),
        })
    }

    pub async fn ping(&self) -> Result<(), ActionError> {
        self.client
            .database("admin")
            .run_command(doc! {"ping": 1})
            .await
            .map_err(|err| ActionError::failure(format!("mongo ping: {err}")))?;
        Ok(())
    }

    fn collection(&self, name: &str) -> mongodb::Collection<Document> {
        self.client.database(&self.db_name).collection(name)
    }
}

#[async_trait]
impl ActionStore for MongoActionStore {
    async fn find_one(&self, collection: &str, filter: &Value) -> Result<Option<Value>, ActionError> {
        let filter = to_doc(filter)?;
        let found = self
            .collection(collection)
            .find_one(filter)
            .await
            .map_err(|err| ActionError::failure(err.to_string()))?;
        Ok(found.map(doc_to_value))
    }

    async fn find_many(
        &self,
        collection: &str,
        filter: &Value,
        limit: Option<i64>,
        sort_desc: Option<&str>,
    ) -> Result<Vec<Value>, ActionError> {
        let filter = to_doc(filter)?;
        let coll = self.collection(collection);
        let mut find = coll.find(filter);
        if let Some(field) = sort_desc {
            find = find.sort(doc! { field: -1 });
        }
        if let Some(limit) = limit {
            find = find.limit(limit);
        }
        let cursor = find
            .await
            .map_err(|err| ActionError::failure(err.to_string()))?;
        let docs: Vec<Document> = cursor
            .try_collect()
            .await
            .map_err(|err| ActionError::failure(err.to_string()))?;
        Ok(docs.into_iter().map(doc_to_value).collect())
    }

    async fn insert_one(&self, collection: &str, mut document: Value) -> Result<(), ActionError> {
        if collection == "action_server_logs" {
            if let Some(obj) = document.as_object_mut() {
                obj.remove("timestamp");
            }
        }
        let mut doc = to_doc(&document)?;
        if collection == "action_server_logs" {
            doc.insert("timestamp", Bson::DateTime(bson::DateTime::now()));
        }
        self.collection(collection)
            .insert_one(doc)
            .await
            .map_err(|err| ActionError::failure(err.to_string()))?;
        Ok(())
    }

    async fn update_one(
        &self,
        collection: &str,
        filter: &Value,
        update: &Value,
    ) -> Result<(), ActionError> {
        self.collection(collection)
            .update_one(to_doc(filter)?, to_doc(update)?)
            .await
            .map_err(|err| ActionError::failure(err.to_string()))?;
        Ok(())
    }

    async fn text_search(
        &self,
        collection: &str,
        query: &str,
        extra: &Value,
        limit: i64,
    ) -> Result<Vec<Value>, ActionError> {
        let mut filter = to_doc(extra)?;
        filter.insert("$text", doc! { "$search": query });
        let coll = self.collection(collection);
        match coll.find(filter).limit(limit).await {
            Ok(cursor) => {
                let docs: Vec<Document> = cursor
                    .try_collect()
                    .await
                    .map_err(|err| ActionError::failure(err.to_string()))?;
                Ok(docs.into_iter().map(doc_to_value).collect())
            }
            Err(err) => {
                tracing::warn!("$text search failed ({err}); falling back to a regex on text");
                let mut fallback = to_doc(extra)?;
                fallback.insert(
                    "text",
                    doc! { "$regex": regex::escape(query), "$options": "i" },
                );
                let cursor = coll
                    .find(fallback)
                    .limit(limit)
                    .await
                    .map_err(|err| ActionError::failure(err.to_string()))?;
                let docs: Vec<Document> = cursor
                    .try_collect()
                    .await
                    .map_err(|err| ActionError::failure(err.to_string()))?;
                Ok(docs.into_iter().map(doc_to_value).collect())
            }
        }
    }
}

fn to_doc(value: &Value) -> Result<Document, ActionError> {
    bson::to_document(value).map_err(|err| ActionError::failure(err.to_string()))
}

fn doc_to_value(mut document: Document) -> Value {
    document.remove("_id");
    bson::from_document(document).unwrap_or_else(|_| Value::Object(Map::new()))
}

fn matches_filter(doc: &Value, filter: &Value) -> bool {
    let Some(filter) = filter.as_object() else {
        return true;
    };
    if filter.is_empty() {
        return true;
    }
    if let Some(parts) = filter.get("$and").and_then(|v| v.as_array()) {
        return parts.iter().all(|part| matches_filter(doc, part));
    }
    filter.iter().all(|(key, expected)| {
        if key == "$text" {
            let query = expected
                .get("$search")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_lowercase();
            return doc
                .get("text")
                .and_then(|v| v.as_str())
                .map(|text| text.to_lowercase().contains(&query))
                .unwrap_or(false);
        }
        let actual = doc.get(key);
        match expected {
            Value::Object(ops) if ops.contains_key("$regex") => {
                let pattern = ops.get("$regex").and_then(|v| v.as_str()).unwrap_or("");
                let options = ops.get("$options").and_then(|v| v.as_str()).unwrap_or("");
                let mut builder = regex::RegexBuilder::new(pattern);
                if options.contains('i') {
                    builder.case_insensitive(true);
                }
                let Ok(re) = builder.build() else {
                    return false;
                };
                actual
                    .and_then(|v| v.as_str())
                    .map(|text| re.is_match(text))
                    .unwrap_or(false)
            }
            other => actual.map(|value| json_number_equal(value, other)).unwrap_or(false),
        }
    })
}

fn cmp_desc(left: Option<&Value>, right: Option<&Value>) -> std::cmp::Ordering {
    match (left, right) {
        (None, None) => std::cmp::Ordering::Equal,
        (None, Some(_)) => std::cmp::Ordering::Greater,
        (Some(_), None) => std::cmp::Ordering::Less,
        (Some(a), Some(b)) => match (a.as_f64(), b.as_f64()) {
            (Some(x), Some(y)) => y.partial_cmp(&x).unwrap_or(std::cmp::Ordering::Equal),
            _ => b.to_string().cmp(&a.to_string()),
        },
    }
}
