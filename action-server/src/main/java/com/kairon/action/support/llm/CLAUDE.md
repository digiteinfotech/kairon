# support/llm

Real LLM-server and Qdrant clients for prompt_action and database_action (no adapter).

Implements:
- cavekit-llm-vector-clients.md R1 (embed), R2 (complete/answer), R3 (LlmHttp transport, in support/), R4 (similarity search), R5 (vector query), R6 (LlmSecrets), R7 (CognitionSchemas), R8 (LlmProcessor log capture)

Build tasks: T-100..T-122 (build-site-llm-prompt-db.md). Never log LlmSecrets maps or api_key values.
