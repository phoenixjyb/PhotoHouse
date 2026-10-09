package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.TestScope
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

@OptIn(ExperimentalCoroutinesApi::class)
class StoryWorkspaceStoreTest {
    private val mutation = UUID.fromString("55555555-5555-4555-8555-555555555555")
    private fun binding(generation: Long = 1) = MemoryCommunityBinding(
        Bearer.from(SessionToken(86400, "a".repeat(43), "Bearer")), "family-a", generation)

    private fun preview(ids: List<String>, revision: String = "a".repeat(64), evidenceId: String = "caption-101",
                        chunkSize: Int = 4) : ByteArray {
        val items = ids.mapIndexed { index, id ->
            val evidence = if (index == 0) "[{\"id\":\"$evidenceId\",\"source\":\"ai\",\"title\":\"\",\"text\":\"A family day.\"}]" else "[]"
            """{"id":"$id","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/$id/thumbnail?library=family-a","date_hint":null,"evidence":$evidence}"""
        }.joinToString(",")
        val chapters = ids.chunked(chunkSize).mapIndexed { index, group ->
            val assets = group.joinToString(",") { "\"$it\"" }
            val evidence = if (index == 0 && ids.first() == "1") "[\"$evidenceId\"]" else "[]"
            """{"id":"chapter-${index + 1}","title":"Chapter ${index + 1}","narration":"","asset_ids":[$assets],"evidence_ids":$evidence}"""
        }.joinToString(",")
        return """{"version":1,"library_id":"family-a","selection_revision":"$revision","state":"draft","saved":false,"title":"Draft title","theme":"everyday","language":"zh","generator":"evidence_outline","needs_review":true,"items":[$items],"chapters":[$chapters],"questions":[]}""".toByteArray()
    }

    private inner class Fake : StoryWorkspaceApi {
        var previewGate: CompletableDeferred<Unit>? = null
        val suggestionGates = ArrayDeque<CompletableDeferred<ByteArray>>()
        var capabilityBody = """{"version":1,"enabled":true,"max_suggestions":3,"needs_review":true}""".toByteArray()
        var saveFailure: ApiFailure? = null
        var saveResponse: ByteArray? = null
        val saveBodies = mutableListOf<String>()
        var idsForPreview = listOf("1")
        val previewReplies = ArrayDeque<ByteArray>()
        val previewFailures = ArrayDeque<ApiFailure>()
        override suspend fun storyPreview(token: Bearer, library: String, json: String): ByteArray {
            previewGate?.await()
            if (previewFailures.isNotEmpty()) throw previewFailures.removeFirst()
            if (previewReplies.isNotEmpty()) return previewReplies.removeFirst()
            return preview(idsForPreview)
        }
        override suspend fun storyTitleCapabilities(token: Bearer, library: String) = capabilityBody
        override suspend fun storyTitles(token: Bearer, library: String, json: String): ByteArray =
            suggestionGates.removeFirst().await()
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray {
            saveBodies += json
            saveFailure?.let { throw it }
            saveResponse?.let { return it }
            throw ApiFailure(FailureKind.OFFLINE)
        }
    }

    private fun repo(api: Fake, current: () -> MemoryCommunityBinding?) = StoryWorkspaceRepository(api, current)
    private fun titleReply(text: String) = """{"version":1,"selection_revision":"${"a".repeat(64)}","titles":[{"text":"$text","source_ids":["caption-101"]}],"needs_review":true}""".toByteArray()

    private fun savedReply(ids: List<String>) = preview(ids).decodeToString()
        .replace("\"state\":\"draft\",\"saved\":false", "\"created_at\":1,\"updated_at\":2,\"can_edit\":true,\"state\":\"draft\",\"saved\":true")
        .replace("\"generator\":\"evidence_outline\"", "\"generator\":\"family_edited_outline\"")
        .replace("\"id\":\"1\"", "\"id\":\"1\"")
        .replace("\"version\":1,", "\"version\":1,\"id\":\"66666666-6666-4666-8666-666666666666\",\"revision\":\"1\",")
        .toByteArray()

    private suspend fun TestScope.readyForEdit(store: StoryWorkspaceStore) {
        assertTrue(store.selectAsset("1"))
        assertTrue(store.preview())
        runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
    }

    @Test fun selectionCapRejectsTheTwentyFifthWithoutDroppingEarlierChoices() = runTest {
        var current = binding()
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(Fake(), { current }), this, { current })
        (1..24).forEach { assertTrue(store.selectAsset(it.toString())) }
        assertFalse(store.selectAsset("25"))
        assertEquals((1..24).map(Int::toString), store.state.value.selectedAssetIds)
    }

    @Test fun changedBindingDiscardsLatePreviewAndClearsTheOldSelection() = runTest {
        var current = binding()
        val api = Fake().apply { previewGate = CompletableDeferred() }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current })
        assertTrue(store.selectAsset("1")); assertTrue(store.preview()); runCurrent()
        current = binding(2)
        api.previewGate!!.complete(Unit); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SELECTION, store.state.value.status)
        assertNull(store.state.value.draft)
        assertTrue(store.state.value.selectedAssetIds.isEmpty())
    }

    @Test fun reviewIsClearedByEditsAndImeAndInvalidInputBlocksSave() = runTest {
        var current = binding(); val api = Fake()
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }) { mutation }
        readyForEdit(store)
        assertTrue(store.confirmReviewed(true))
        assertTrue(store.editTitle("Reviewed title"))
        assertFalse(store.state.value.reviewed)
        store.composition(true)
        assertFalse(store.confirmReviewed(true)); assertFalse(store.save())
        store.composition(false)
        assertTrue(store.editTitle("\u0000"))
        assertTrue(store.state.value.invalidInput)
        assertFalse(store.confirmReviewed(true)); assertFalse(store.save())
        assertTrue(store.editTitle("Valid title"))
        assertFalse(store.state.value.invalidInput)
        assertTrue(store.confirmReviewed(true))
        assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
    }

    @Test fun changingSelectionOrThemeRequiresExplicitDraftDiscard() = runTest {
        var current = binding(); val store = StoryWorkspaceStore(repo(Fake()) { current }, this, { current })
        readyForEdit(store)
        assertTrue(store.editTitle("Keep this draft"))
        assertFalse(store.selectAsset("2"))
        assertFalse(store.setTheme("trip"))
        assertEquals("Keep this draft", store.state.value.title)
        assertEquals("everyday", store.state.value.theme)
        assertNotNull(store.state.value.draft)
        assertTrue(store.setTheme("trip", discardDraft = true))
        assertNull(store.state.value.draft)
        assertEquals(StoryWorkspaceStoreStatus.SELECTION, store.state.value.status)
    }

    @Test fun uncertainRetryReusesTheFrozenBodyAndBlocksEditsUntilExplicitDiscard() = runTest {
        var current = binding(); val api = Fake().apply { saveFailure = ApiFailure(FailureKind.OFFLINE) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }) { mutation }
        readyForEdit(store)
        assertTrue(store.editTitle("Frozen title")); assertTrue(store.confirmReviewed(true))
        assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        assertFalse(store.editTitle("Replacement")); assertFalse(store.preview()); assertFalse(store.close())
        assertTrue(store.retrySave()); runCurrent()
        assertEquals(2, api.saveBodies.size)
        assertEquals(api.saveBodies[0], api.saveBodies[1])
        assertTrue(api.saveBodies[0].contains("\"mutation_id\":\"$mutation\""))
        assertTrue(store.state.value.hasPendingSave)
        assertTrue(store.close(discard = true))
        assertEquals(StoryWorkspaceStoreStatus.SELECTION, store.state.value.status)
    }

    @Test fun saveKeepsTheValidatedSavedStoryForTheReader() = runTest {
        var current = binding(); val api = Fake().apply { saveResponse = savedReply(listOf("1")) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }) { mutation }
        readyForEdit(store)
        assertTrue(store.editTitle("Family title")); assertTrue(store.confirmReviewed(true))
        assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVED, store.state.value.status)
        assertEquals("66666666-6666-4666-8666-666666666666", store.state.value.savedStory?.id)
        assertFalse(store.state.value.hasUnfinishedWork)
    }

    @Test fun lateTitleSuggestionIsDroppedAfterManualEditAndOutOfOrderResponses() = runTest {
        var current = binding()
        val first = CompletableDeferred<ByteArray>()
        val second = CompletableDeferred<ByteArray>()
        val api = Fake().apply { suggestionGates.add(first); suggestionGates.add(second) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current })
        readyForEdit(store)
        assertTrue(store.loadTitleCapabilities()); runCurrent()
        assertTrue(store.suggestTitles()); runCurrent()
        assertTrue(store.suggestTitles()); runCurrent()
        second.complete(titleReply("Second response")); runCurrent()
        first.complete(titleReply("Late first response")); runCurrent()
        assertEquals(listOf("Second response"), store.state.value.titleCandidates.map { it.text })
        val late = CompletableDeferred<ByteArray>()
        api.suggestionGates.add(late)
        assertTrue(store.suggestTitles()); runCurrent()
        assertTrue(store.editTitle("Manual title"))
        late.complete(titleReply("Should be dropped")); runCurrent()
        assertEquals("Manual title", store.state.value.title)
        assertTrue(store.state.value.titleCandidates.isEmpty())

        val chapterLate = CompletableDeferred<ByteArray>()
        api.suggestionGates.add(chapterLate)
        assertTrue(store.suggestTitles()); runCurrent()
        assertTrue(store.editChapterNarration(0, "Edited narration"))
        chapterLate.complete(titleReply("Stale after chapter edit")); runCurrent()
        assertEquals("Edited narration", store.state.value.editableChapters.single().narration)
        assertTrue(store.state.value.titleCandidates.isEmpty())
    }

    @Test fun clearFencesLateDeniedResponseFromANewBinding() = runTest {
        var current = binding()
        val gate = CompletableDeferred<Unit>()
        val api = object : StoryWorkspaceApi {
            var previews = 0
            override suspend fun storyPreview(token: Bearer, library: String, json: String): ByteArray {
                previews++
                if (previews == 1) {
                    withContext(NonCancellable) { gate.await() }
                    throw ApiFailure(FailureKind.HTTP, 401)
                }
                return preview(listOf("2"))
            }
            override suspend fun storyTitleCapabilities(token: Bearer, library: String) = error("unused")
            override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String) = error("unused")
        }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, { current }), this, { current })
        assertTrue(store.selectAsset("1")); assertTrue(store.preview()); runCurrent()
        store.clear(); current = binding(2)
        assertTrue(store.selectAsset("2")); assertTrue(store.preview()); runCurrent()
        gate.complete(Unit); runCurrent()
        assertEquals(listOf("2"), store.state.value.selectedAssetIds)
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
    }

    @Test fun reloadPreservesManualProseAndUsesFreshEvidenceWithoutSaving() = runTest {
        var current = binding()
        val api = Fake().apply { saveFailure = ApiFailure(FailureKind.HTTP, 409) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }) { mutation }
        readyForEdit(store)
        assertTrue(store.editTitle("My edited title"))
        assertTrue(store.editChapterTitle(0, "My chapter"))
        assertTrue(store.editChapterNarration(0, "The family kept walking."))
        assertTrue(store.confirmReviewed(true))
        assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.CONFLICT, store.state.value.status)

        api.saveFailure = null
        api.previewReplies.add(preview(listOf("1"), "b".repeat(64), "caption-202"))
        assertTrue(store.reloadPreview()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
        assertEquals("My edited title", store.state.value.title)
        assertEquals("My edited title", store.state.value.draft?.title)
        assertEquals("My chapter", store.state.value.editableChapters.single().title)
        assertEquals("The family kept walking.", store.state.value.editableChapters.single().narration)
        assertEquals("b".repeat(64), store.state.value.draft?.selectionRevision)
        assertEquals("caption-202", store.state.value.draft?.items?.single()?.evidence?.single()?.id)
        assertEquals(listOf("caption-202"), store.state.value.draft?.chapters?.single()?.evidenceIds)
        assertTrue(store.state.value.sourcesReloaded)
        assertFalse(store.state.value.reviewed)
        assertTrue(api.saveBodies.size == 1)
    }

    @Test fun changedGroupingRejectsReloadAndRetainsOldDraftAndProse() = runTest {
        var current = binding()
        val api = Fake().apply { idsForPreview = (1..5).map(Int::toString); saveFailure = ApiFailure(FailureKind.HTTP, 409) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }) { mutation }
        (1..5).forEach { assertTrue(store.selectAsset(it.toString())) }
        assertTrue(store.preview()); runCurrent()
        assertTrue(store.editTitle("Retain this title"))
        assertTrue(store.editChapterNarration(0, "Retain this narration"))
        assertTrue(store.confirmReviewed(true)); assertTrue(store.save()); runCurrent()
        val oldRevision = store.state.value.draft?.selectionRevision
        api.saveFailure = null
        api.previewReplies.add(preview((1..5).map(Int::toString), "c".repeat(64), "caption-303", chunkSize = 3))
        assertTrue(store.reloadPreview()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.UNAVAILABLE, store.state.value.status)
        assertEquals(oldRevision, store.state.value.draft?.selectionRevision)
        assertEquals("Retain this title", store.state.value.title)
        assertEquals("Retain this narration", store.state.value.editableChapters.first().narration)
        assertFalse(store.state.value.sourcesReloaded)
        assertEquals(1, api.saveBodies.size)
    }

    @Test fun lateReloadAfterScopeClearCannotRestoreOldDraft() = runTest {
        var current = binding()
        val gate = CompletableDeferred<Unit>()
        val api = object : StoryWorkspaceApi {
            var previews = 0
            override suspend fun storyPreview(token: Bearer, library: String, json: String): ByteArray {
                previews++
                return when (previews) {
                    1 -> preview(listOf("1"))
                    2 -> {
                        withContext(NonCancellable) { gate.await() }
                        preview(listOf("1"), "d".repeat(64), "caption-404")
                    }
                    else -> preview(listOf("2"), "e".repeat(64), "caption-505")
                }
            }
            override suspend fun storyTitleCapabilities(token: Bearer, library: String) = error("unused")
            override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String) = throw ApiFailure(FailureKind.HTTP, 409)
        }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, { current }), this, { current }) { mutation }
        assertTrue(store.selectAsset("1")); assertTrue(store.preview()); runCurrent()
        assertTrue(store.editTitle("Old prose")); assertTrue(store.confirmReviewed(true)); assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.CONFLICT, store.state.value.status)
        assertTrue(store.reloadPreview()); runCurrent()
        store.clear(); current = binding(2)
        assertTrue(store.selectAsset("2")); assertTrue(store.preview()); runCurrent()
        gate.complete(Unit); runCurrent()
        assertEquals(listOf("2"), store.state.value.selectedAssetIds)
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
        assertEquals("Draft title", store.state.value.title)
        assertFalse(store.state.value.sourcesReloaded)
    }

    @Test fun retryPreviewRecoversInitialUnavailableSelection() = runTest {
        var current = binding()
        val api = Fake().apply { previewFailures.add(ApiFailure(FailureKind.OFFLINE)) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current })
        assertTrue(store.selectAsset("1")); assertTrue(store.preview()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.UNAVAILABLE, store.state.value.status)
        assertEquals(listOf("1"), store.state.value.selectedAssetIds)
        assertNull(store.state.value.draft)
        assertTrue(store.retryPreview()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
        assertNotNull(store.state.value.draft)
        assertFalse(store.state.value.sourcesReloaded)
    }

    @Test fun pendingSaveStateCannotReloadSourcesOrRetryInitialPreview() = runTest {
        var current = binding()
        val api = Fake().apply { saveFailure = ApiFailure(FailureKind.OFFLINE) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }) { mutation }
        readyForEdit(store)
        assertTrue(store.editTitle("Uncertain prose")); assertTrue(store.confirmReviewed(true))
        assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        assertTrue(store.state.value.hasPendingSave)
        assertFalse(store.reloadPreview())
        assertFalse(store.retryPreview())
        assertEquals(1, api.saveBodies.size)
    }
}
