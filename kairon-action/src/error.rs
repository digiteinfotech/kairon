use thiserror::Error;

/// Failures raised while running an action.
///
/// `Failure` is swallowed by the processor (HTTP 200, empty events, FAIL log).
/// `Rejected` and `NotFound` map to HTTP 400 only when they escape `process_actions`.
/// Kairon actions raise them inside the processor catch, so the 400 path is unused
/// for normal execution and kept so the webhook matches the Python server.
#[derive(Debug, Error)]
pub enum ActionError {
    #[error("{0}")]
    Failure(String),
    #[error("{message}")]
    Rejected { message: String, action_name: String },
    #[error("{message}")]
    NotFound { message: String, action_name: String },
}

impl ActionError {
    pub fn failure(message: impl Into<String>) -> Self {
        Self::Failure(message.into())
    }
}
