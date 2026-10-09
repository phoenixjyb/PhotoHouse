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
        val face = String(Character.toChars(0x1f642))
        assertEquals(face.repeat(512), assistantDraftWithTranscript("", face.repeat(512)))
        assertNull(assistantDraftWithTranscript(face.repeat(500), face.repeat(12)))
        assertEquals(512, assistantDraftWithTranscript(face.repeat(500), face.repeat(11))!!.codePointCount(0, 1023))
    }
}
