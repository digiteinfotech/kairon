package com.kairon.action.support.llm;

import java.util.List;
import java.util.Map;

/**
 * Inputs of processor.py {@code __get_answer}.
 *
 * @param bot                  bot id (URL-quoted in the endpoint)
 * @param endpointLlmType      {@code self.llm_type}: the endpoint's llm_type (openrouter after a swap)
 * @param llmType              the configured {@code llm_type} kwarg, used for the perplexity check
 * @param query                user message
 * @param systemPrompt         system prompt
 * @param context              similarity context
 * @param user                 sender id
 * @param invocation           invocation (rephrase uses {@code {invocation}_rephrase})
 * @param mediaIds             media ids for the main completion
 * @param shouldProcessMedia   should_process_media for the main completion
 * @param queryPrompt          {@code query_prompt.query_prompt}
 * @param useQueryPrompt       {@code query_prompt.use_query_prompt}
 * @param previousBotResponses history messages placed between system and user
 * @param hyperparameters      hyperparameters dict
 * @param instructions         instructions (joined with a newline)
 */
public record AnswerParams(
        String bot,
        String endpointLlmType,
        String llmType,
        Object query,
        Object systemPrompt,
        Object context,
        Object user,
        Object invocation,
        List<?> mediaIds,
        boolean shouldProcessMedia,
        String queryPrompt,
        boolean useQueryPrompt,
        List<Map<String, Object>> previousBotResponses,
        Object hyperparameters,
        Object instructions) {
}
