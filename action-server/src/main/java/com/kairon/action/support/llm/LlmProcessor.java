package com.kairon.action.support.llm;

import com.kairon.action.support.PyRepr;
import jakarta.inject.Inject;
import jakarta.inject.Singleton;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * processor.py {@code LLMProcessor.predict}: query embedding ({@link LlmClient#embed}), similarity context
 * ({@link SimilarityContext#attach}), then the answer ({@link LlmClient#answer}, optional rephrase + main completion).
 *
 * <p>LLM logs: the caller owns the list ({@code self.__logs}). Each completion appends its
 * {@code {messages, raw_completion_response, type, hyperparameters}} entry as soon as it returns, in call order
 * ({@code rephrase_query} then {@code answer_query}). On failure one {@code {"error": "<stage> <exc>"}} entry is
 * appended after whatever completion entries were already written, so a rephrase that succeeded before a failing
 * main completion is logged as {@code [rephrase_query, error]} (same as Python).
 */
@Singleton
public class LlmProcessor {

    private static final Logger LOG = LoggerFactory.getLogger(LlmProcessor.class);

    static final String EMBEDDING_STAGE = "Creating a new embedding for the provided query.";
    static final String COMPLETION_STAGE = "Retrieving chat completion for the provided query.";

    /**
     * {@code (response, elapsed_time)} of predict.
     *
     * @param response       success {@code {content, similarity_context, litellm_call_id}} or failure
     *                       {@code {is_failure: true, exception, content: null}} (insertion ordered)
     * @param elapsedSeconds wall-clock seconds of the whole prediction (embedding, search and completion)
     */
    public record Prediction(Map<String, Object> response, double elapsedSeconds) {

        public boolean isFailure() {
            return Boolean.TRUE.equals(response.get("is_failure"));
        }

        public Object content() {
            return response.get("content");
        }

        /** {@code str(e)} of the failure; null on success. */
        public Object exception() {
            return response.get("exception");
        }

        /** {@code litellm_call_id} (null on failure). */
        public Object callId() {
            return response.get("litellm_call_id");
        }
    }

    private final LlmClient llm;
    private final SimilarityContext similarity;

    @Inject
    public LlmProcessor(LlmClient llm, SimilarityContext similarity) {
        this.llm = llm;
        this.similarity = similarity;
    }

    /**
     * processor.py {@code predict}.
     *
     * @param params            answer inputs; {@code params.context()} is the {@code context_prompt} that the similarity
     *                          blocks are appended to, {@code params.query()} the embedded user message and
     *                          {@code params.endpointLlmType()} the llm_type of both endpoints
     * @param collection        first similarity collection (embedding kwargs, schema lookup)
     * @param similarityPrompts similarity sources ({@code similarity_prompt}), searched concurrently
     * @param embeddingSecret   embedding secret ({@code api_key} sent in the embedding kwargs; never logged)
     * @param logs              LLM log list completions and the failure entry are appended to
     */
    public Prediction predict(AnswerParams params, String collection, List<?> similarityPrompts,
                              Map<String, String> embeddingSecret, List<Map<String, Object>> logs) {
        long start = System.nanoTime();
        boolean embeddingCreated = false;
        Map<String, Object> response = new LinkedHashMap<>();
        try {
            Object embedding = llm.embed(params.bot(), params.endpointLlmType(), PyRepr.str(params.query()),
                    params.user(), params.invocation(), collection, embeddingSecret);
            embeddingCreated = true;
            String context = similarity.attach(params.bot(), params.context(), similarityPrompts,
                    embedding instanceof List<?> vector ? vector : null);
            LlmClient.Answer answer = llm.answer(withContext(params, context), logs);
            response.put("content", answer.content());
            response.put("similarity_context", context);
            response.put("litellm_call_id", answer.callId());
        } catch (RuntimeException e) {
            // Only the exception text is logged: messages carry status phrases / error texts, never secrets.
            LOG.error("LLM prediction failed for bot {}: {}", params.bot(), e.toString());
            String exception = e.getMessage() == null ? "" : e.getMessage();
            String stage = embeddingCreated ? COMPLETION_STAGE : EMBEDDING_STAGE;
            Map<String, Object> error = new LinkedHashMap<>();
            error.put("error", stage + " " + exception);
            logs.add(error);
            response.clear();
            response.put("is_failure", true);
            response.put("exception", exception);
            response.put("content", null);
        }
        double elapsed = (System.nanoTime() - start) / 1_000_000_000.0;
        return new Prediction(response, elapsed);
    }

    private static AnswerParams withContext(AnswerParams p, String context) {
        return new AnswerParams(p.bot(), p.endpointLlmType(), p.llmType(), p.query(), p.systemPrompt(), context,
                p.user(), p.invocation(), p.mediaIds(), p.shouldProcessMedia(), p.queryPrompt(), p.useQueryPrompt(),
                p.previousBotResponses(), p.hyperparameters(), p.instructions());
    }
}
