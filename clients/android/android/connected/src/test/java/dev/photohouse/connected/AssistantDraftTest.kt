package dev.photohouse.connected

import org.junit.Assert.*
import org.junit.Test

class AssistantDraftTest {
    @Test fun insertionPreservesTypedWordsAndTranscript() {
        assertEquals("我的问题\n这是转写", assistantDraftWithTranscript("我的问题", "这是转写"))
        assertEquals("  My draft  \n  recognized words  ", assistantDraftWithTranscript("  My draft  ", "  recognized words  "))
        assertEquals("recognized words", assistantDraftWithTranscript(" ", "recognized words"))
    }
    @Test fun oversizedInsertionKeepsBothInputsAvailable() {
        val draft = "D".repeat(500)
        val recognized = "R".repeat(20)
        assertNull(assistantDraftWithTranscript(draft, recognized))
        assertEquals(500, draft.length)
        assertEquals(20, recognized.length)
        assertNull(assistantDraftWithTranscript("", "R".repeat(513)))
        assertNull(assistantDraftWithTranscript("draft", " "))
    }
    @Test fun limitCountsUnicodeCodepoints() {
        assertTrue(assistantDraftWithinLimits("x".repeat(512)))
        assertFalse(assistantDraftWithinLimits("x".repeat(513)))
    }
    @Test fun insertionAlsoHonorsUtf8ByteLimitAtExactMixedBoundaries() {
        val chinese = "中".repeat(341)
        val mixedAt1024Bytes = chinese + "a"
        assertEquals(1024, mixedAt1024Bytes.toByteArray(Charsets.UTF_8).size)
        assertEquals(mixedAt1024Bytes, assistantDraftWithTranscript("", mixedAt1024Bytes))
        assertTrue(assistantDraftWithinLimits(mixedAt1024Bytes)) // 342 codepoints, 1024 bytes
        assertFalse(assistantDraftWithinLimits("中".repeat(342))) // 1026 bytes, still below 512 codepoints

        // The raw 1023-byte transcript fits alone. A one-byte draft plus the
        // inserted newline would exceed the request's 1024-byte wire cap.
        assertEquals(1023, chinese.toByteArray(Charsets.UTF_8).size)
        assertEquals(chinese, assistantDraftWithTranscript("", chinese))
        assertNull(assistantDraftWithTranscript("a", chinese))
        assertNull(assistantDraftWithTranscript("", mixedAt1024Bytes + "b"))
    }
    @Test fun emojiBoundaryUsesBothCodepointsAndUtf8Bytes() {
        val face = String(Character.toChars(0x1f642))
        val atByteLimit = face.repeat(256)
        assertEquals(1024, atByteLimit.toByteArray(Charsets.UTF_8).size)
        assertEquals(atByteLimit, assistantDraftWithTranscript("", atByteLimit))
        assertNull(assistantDraftWithTranscript("", face.repeat(257)))
        assertNull(assistantDraftWithTranscript(face, atByteLimit))
    }
}
