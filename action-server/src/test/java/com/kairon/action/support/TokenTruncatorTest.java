package com.kairon.action.support;

import com.knuddels.jtokkit.Encodings;
import com.knuddels.jtokkit.api.Encoding;
import com.knuddels.jtokkit.api.EncodingType;
import com.knuddels.jtokkit.api.IntArrayList;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** T-102, llm-vector-clients R1 c5 (truncation half): LLMProcessor.truncate_text on cl100k_base, 8191 tokens. */
class TokenTruncatorTest {

    private static final Encoding CL100K = Encodings.newDefaultEncodingRegistry().getEncoding(EncodingType.CL100K_BASE);

    @Test
    void usesCl100kBase() {
        // tiktoken.get_encoding("cl100k_base").encode("hello world") == [15339, 1917]
        IntArrayList tokens = CL100K.encode("hello world");
        assertEquals(2, tokens.size());
        assertEquals(15339, tokens.get(0));
        assertEquals(1917, tokens.get(1));
        assertEquals(8191, TokenTruncator.EMBEDDING_CTX_LENGTH);
    }

    @Test
    void nineThousandTokenInputKeepsExactlyFirst8191Tokens() {
        String text = "hello world ".repeat(4499) + "hello world";
        IntArrayList all = CL100K.encode(text);
        assertEquals(9000, all.size(), "precondition: 9000-token input");

        String truncated = TokenTruncator.truncate(text, TokenTruncator.EMBEDDING_CTX_LENGTH);

        IntArrayList kept = CL100K.encode(truncated);
        assertEquals(8191, kept.size());
        for (int i = 0; i < kept.size(); i++) {
            assertEquals(all.get(i), kept.get(i), "token " + i);
        }
        assertTrue(text.startsWith(truncated));
    }

    @Test
    void shortInputUnchanged() {
        String text = "What is the refund policy for orders placed in Pune? ₹ 500 – ok 👍";
        assertEquals(text, TokenTruncator.truncate(text, TokenTruncator.EMBEDDING_CTX_LENGTH));
        assertEquals("", TokenTruncator.truncate("", TokenTruncator.EMBEDDING_CTX_LENGTH));
    }

    @Test
    void exactlyAtLimitUnchanged() {
        String text = "hello world ".repeat(4095) + "hello";
        assertEquals(8191, CL100K.encode(text).size());
        assertEquals(text, TokenTruncator.truncate(text, 8191));
    }

    @Test
    void cutInsideMultiTokenCharacterDecodesLikePythonReplace() {
        // tiktoken decode uses errors="replace": a cut through a multi-byte character yields U+FFFD
        String text = "👍";
        IntArrayList tokens = CL100K.encode(text);
        assertTrue(tokens.size() > 1, "precondition: emoji spans several tokens");
        assertEquals("�", TokenTruncator.truncate(text, 1));
    }
}
