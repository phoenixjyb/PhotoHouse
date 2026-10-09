package dev.photohouse.connected.core

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

@OptIn(ExperimentalCoroutinesApi::class)
class ProtectedStoryEditingTest {
    private val story = ProtectedStory("123e4567-e89b-12d3-a456-426614174001", "42", "Old", "Old text", "en", "Mom", "account", 3, 1, 2, true, true)

    @Test fun reviewFreezesBodyAndRetryReusesExactMutation() = runTest {
        val attempts = mutableListOf<StoryMutation>()
        var fail = true
        val store = ProtectedStoryEditorStore(this, "42", story, { mutation ->
            attempts += mutation
            if (fail) { fail = false; throw ApiFailure(FailureKind.OFFLINE) }
            story.copy(text = mutation.draft.text, revision = 4)
        }, { story }, {}, {})
        store.updateText("Reviewed memory")
        store.updateByline("")
        assertTrue(store.beginReview())
        val mutation = store.state.value.mutation!!
        store.updateText("must be ignored while reviewed")
        assertEquals("Reviewed memory", store.state.value.mutation!!.draft.text)
        store.confirmSave(); advanceUntilIdle()
        assertEquals(StoryEditorPhase.UNCERTAIN, store.state.value.phase)
        store.retryUncertain(); advanceUntilIdle()
        assertEquals(StoryEditorPhase.SAVED, store.state.value.phase)
        assertEquals(2, attempts.size)
        assertEquals(mutation.mutationId, attempts[1].mutationId)
        assertEquals(mutation.draft, attempts[1].draft)
        assertEquals("", attempts[1].draft.byline)
    }

    @Test fun creationUsesOnlyValidBoundedDefaultAndEditsKeepTheirExactByline() = runTest {
        fun newEditor(default: String?) = ProtectedStoryEditorStore(
            this, "42", null, { error("unused") }, { null }, {}, {}, defaultByline = default)

        assertEquals("Family Name", newEditor("Family Name").state.value.draft.byline)
        for (invalid in listOf(null, "   ", "\t\n", "x".repeat(257), "bad\u0000name", "bad\u007fname", "\uD800")) {
            val editor = newEditor(invalid)
            assertEquals("", editor.state.value.draft.byline)
            editor.updateText("valid memory")
            assertTrue("default should not block saving: $invalid", editor.beginReview())
        }
        assertEquals("😀".repeat(64), newEditor("😀".repeat(64)).state.value.draft.byline)
        assertEquals("", newEditor("😀".repeat(65)).state.value.draft.byline)

        val blankExisting = story.copy(byline = "")
        val edit = ProtectedStoryEditorStore(this, "42", blankExisting,
            { blankExisting }, { blankExisting }, {}, {}, defaultByline = "Ignored name")
        assertEquals("", edit.state.value.draft.byline)
        edit.updateByline("Edited byline")
        edit.updateText("edited memory")
        assertTrue(edit.beginReview())
        assertEquals("Edited byline", edit.state.value.mutation!!.draft.byline)
    }

    @Test fun conflictRequiresReloadAndExplicitLatestRevisionBeforeReview() = runTest {
        var current = story
        val store = ProtectedStoryEditorStore(this, "42", story, { throw ApiFailure(FailureKind.HTTP, 409) }, { current }, {}, {})
        store.updateText("My edit"); store.updateByline("My chosen byline")
        assertTrue(store.beginReview()); store.confirmSave(); advanceUntilIdle()
        assertEquals(StoryEditorPhase.CONFLICT, store.state.value.phase)
        store.useLatestRevision(); assertEquals(StoryEditorPhase.CONFLICT, store.state.value.phase)
        current = story.copy(revision = 4, text = "Other edit")
        store.reloadCurrent(); advanceUntilIdle()
        assertEquals(StoryEditorPhase.CONFLICT, store.state.value.phase)
        store.useLatestRevision()
        assertEquals(StoryEditorPhase.REVIEW, store.state.value.phase)
        assertEquals(4L, store.state.value.mutation!!.revision)
        assertEquals("My edit", store.state.value.mutation!!.draft.text)
        assertEquals("My chosen byline", store.state.value.mutation!!.draft.byline)
    }

    @Test fun validationDenialAndCloseDiscardLateResult() = runTest {
        val gate = CompletableDeferred<ProtectedStory>()
        var denied = 0
        val store = ProtectedStoryEditorStore(this, "42", null, { gate.await() }, { null }, {}, { denied++ })
        store.updateText("\uD800")
        assertFalse(store.beginReview())
        store.updateText("Valid memory")
        assertTrue(store.beginReview()); store.confirmSave();
        store.close(); gate.complete(story); advanceUntilIdle()
        assertEquals(StoryEditorPhase.CLOSED, store.state.value.phase)
        assertEquals(0, denied)

        val deniedStore = ProtectedStoryEditorStore(this, "42", null, { throw ApiFailure(FailureKind.HTTP, 403) }, { null }, {}, { denied++ })
        deniedStore.updateText("Valid memory"); assertTrue(deniedStore.beginReview()); deniedStore.confirmSave(); advanceUntilIdle()
        assertEquals(StoryEditorPhase.DENIED, deniedStore.state.value.phase)
        assertEquals(1, denied)
    }

    @Test fun limitsAreByteSafeAndMutationStartsWithStableUuid() = runTest {
        val store = ProtectedStoryEditorStore(this, "42", null, { error("unused") }, { null }, {}, {})
        store.updateText("😀".repeat(16384) + "x")
        assertFalse(store.beginReview())
        store.updateText("ok"); assertTrue(store.beginReview())
        assertEquals(36, store.state.value.mutation!!.mutationId.toString().length)
        assertEquals(UUID::class.java, store.state.value.mutation!!.mutationId.javaClass)
    }
    @Test fun cooldownTlsAndMalformedRepliesKeepTheExactMutation() = runTest {
        for (error in listOf(ApiFailure(FailureKind.TLS), ApiFailure(FailureKind.INVALID_RESPONSE), ApiFailure(FailureKind.HTTP, 503, 5000))) {
            val attempts = mutableListOf<StoryMutation>()
            val store = ProtectedStoryEditorStore(this, "42", story,
                { attempts += it; throw error }, { story }, {}, {}, now = { testScheduler.currentTime })
            store.updateText("my words"); store.beginReview(); store.confirmSave(); advanceUntilIdle()
            assertEquals(StoryEditorPhase.UNCERTAIN, store.state.value.phase)
            val frozen = store.state.value.mutation
            store.updateText("cannot change")
            assertEquals(frozen, store.state.value.mutation)
            store.retryUncertain(); advanceUntilIdle()
            if (error.retryAfterMillis > 0) {
                assertEquals(1, attempts.size)
                testScheduler.advanceTimeBy(5000)
                store.retryUncertain(); advanceUntilIdle()
            }
            assertEquals(2, attempts.size); assertEquals(attempts[0], attempts[1])
            store.dismissUncertain(); assertEquals(StoryEditorPhase.CLOSED, store.state.value.phase)
            assertTrue(store.state.value.draft.text.isEmpty())
        }
    }
    @Test fun conflictRequiresFreshEditableRevisionAndCreatesNewMutation() = runTest {
        var latest: ProtectedStory? = story.copy(revision = 4, canEdit = false)
        var reloadError: Exception? = null
        var denied = false
        val store = ProtectedStoryEditorStore(this, "42", story,
            { throw ApiFailure(FailureKind.HTTP, 409) }, { reloadError?.let { throw it }; latest }, {}, { denied = true })
        store.updateText("my draft"); store.beginReview()
        val original = store.state.value.mutation!!
        store.confirmSave(); advanceUntilIdle()
        store.reloadCurrent(); advanceUntilIdle(); store.useLatestRevision()
        assertEquals(StoryEditorPhase.CONFLICT, store.state.value.phase)
        latest = story.copy(revision = 4)
        store.reloadCurrent(); advanceUntilIdle(); store.useLatestRevision()
        assertEquals(StoryEditorPhase.REVIEW, store.state.value.phase)
        assertNotEquals(original.mutationId, store.state.value.mutation!!.mutationId)
        assertEquals(4L, store.state.value.mutation!!.revision)
        store.confirmSave(); advanceUntilIdle()
        reloadError = ApiFailure(FailureKind.HTTP, 401)
        store.reloadCurrent(); advanceUntilIdle()
        assertTrue(denied); assertTrue(store.state.value.draft.text.isEmpty())
    }

}
