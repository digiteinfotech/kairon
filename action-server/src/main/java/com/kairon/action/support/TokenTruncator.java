package com.kairon.action.support;

import com.knuddels.jtokkit.Encodings;
import com.knuddels.jtokkit.api.Encoding;
import com.knuddels.jtokkit.api.EncodingType;
import com.knuddels.jtokkit.api.IntArrayList;

/**
 * LLMProcessor.truncate_text: {@code tokenizer.decode(tokenizer.encode(text)[:8191])} on {@code cl100k_base}.
 * The token list is sliced as-is (no UTF-8 boundary smoothing), so a cut through a multi-token character
 * decodes to U+FFFD like tiktoken's {@code errors="replace"}. Text containing special tokens such as
 * {@code <|endoftext|>} is rejected, as tiktoken's default {@code disallowed_special="all"} does.
 */
public final class TokenTruncator {

    /** LLMProcessor.EMBEDDING_CTX_LENGTH. */
    public static final int EMBEDDING_CTX_LENGTH = 8191;

    private static final Encoding CL100K_BASE =
            Encodings.newDefaultEncodingRegistry().getEncoding(EncodingType.CL100K_BASE);

    private TokenTruncator() {
    }

    public static String truncate(String text, int maxTokens) {
        IntArrayList tokens = CL100K_BASE.encode(text);
        if (tokens.size() <= maxTokens) {
            return CL100K_BASE.decode(tokens);
        }
        IntArrayList kept = new IntArrayList(maxTokens);
        for (int i = 0; i < maxTokens; i++) {
            kept.add(tokens.get(i));
        }
        return CL100K_BASE.decode(kept);
    }
}
