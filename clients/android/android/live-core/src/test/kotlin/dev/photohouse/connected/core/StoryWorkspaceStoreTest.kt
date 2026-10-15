package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.TestScope
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

@OptIn(ExperimentalCoroutinesApi::class)
class StoryWorkspaceStoreTest {
    private val mutation = UUID.fromString("55555555-5555-4555-8555-555555555555")
    private fun binding(generation: Long = 1) = MemoryCommunityBinding(
        Bearer.from(SessionToken(86400, "a".repeat(43), "Bearer")), "family-a", generation)

    private class DictationApi : PhotoHouseApi {
        override val assistantEnabled = true
        var transcriptText = "ASR words"
        var transcriptions = 0
        var capabilityGate: CompletableDeferred<Unit>? = null
        override suspend fun assistantCapabilities(token: Bearer, library: String): AssistantCapabilities {
            capabilityGate?.let { gate -> withContext(NonCancellable) { gate.await() }; capabilityGate = null }
            return AssistantCapabilities(true, true, true, false, 5)
        }
        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String): AssistantTranscript {
            transcriptions++
            return AssistantTranscript(transcriptText, "en", AssistantRequestReceipt(requestId, "enabled", "succeeded"))
        }
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("member", "+12025550123", emptyList())
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 0, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail = error("unused")
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unused")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unused")
    }

    private fun preview(ids: List<String>, revision: String = "a".repeat(64), evidenceId: String = "caption-101",
                        chunkSize: Int = 4) : ByteArray {
        val items = ids.mapIndexed { index, id ->
            val sourceId = if (index == 0) evidenceId else "caption-$id"
            val evidence = "[{\"id\":\"$sourceId\",\"source\":\"ai\",\"title\":\"\",\"text\":\"A family day.\"}]"
            """{"id":"$id","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/$id/thumbnail?library=family-a","date_hint":null,"evidence":$evidence}"""
        }.joinToString(",")
        val chapters = ids.chunked(chunkSize).mapIndexed { index, group ->
            val assets = group.joinToString(",") { "\"$it\"" }
            val groupEvidence = if (ids.first() == "1") {
                if (index == 0) evidenceId else "caption-${group.first()}"
            } else null
            val evidence = groupEvidence?.let { "[\"$it\"]" } ?: "[]"
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
        val saveProfiles = mutableListOf<Boolean>()
        val updateBodies = mutableListOf<String>()
        val updateTargets = mutableListOf<String>()
        val updateProfiles = mutableListOf<Pair<Boolean, Boolean>>()
        val updateFailures = ArrayDeque<ApiFailure>()
        var updateResponse: ByteArray? = null
        var sourceCapabilityBody = """{"version":1,"source_policy":"chapter_sources_v1","max_sources_per_chapter":12,"needs_review":true}""".toByteArray()
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
        override suspend fun storySourceCapabilities(token: Bearer, library: String) = sourceCapabilityBody
        override suspend fun storyTitles(token: Bearer, library: String, json: String): ByteArray =
            suggestionGates.removeFirst().await()
        override suspend fun storyTitles(token: Bearer, library: String, json: String, sourceReview: Boolean): ByteArray =
            storyTitles(token, library, json)
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray {
            saveBodies += json
            saveFailure?.let { throw it }
            saveResponse?.let { return it }
            throw ApiFailure(FailureKind.OFFLINE)
        }
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String, sourceReview: Boolean): ByteArray {
            saveProfiles += sourceReview
            return createGroupedStory(token, library, json)
        }
        override suspend fun updateGroupedStory(token: Bearer, library: String, storyId: String, json: String,
            sourceReview: Boolean, contributionReferences: Boolean): ByteArray {
            updateBodies += json; updateTargets += storyId; updateProfiles += sourceReview to contributionReferences
            if (updateFailures.isNotEmpty()) throw updateFailures.removeFirst()
            return updateResponse ?: throw ApiFailure(FailureKind.OFFLINE)
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

    private fun savedEditStoryJson(revision: Long = 4, narration: String = "Original saved narration") =
        savedReply(listOf("1")).decodeToString()
            .replace("\"revision\":\"1\"", "\"revision\":\"$revision\"")
            .replace("\"narration\":\"\"", "\"narration\":\"$narration\"")

    private fun savedEditStory(revision: Long = 4, narration: String = "Original saved narration") =
        ProtectedMemoryStoriesWire.detail(savedEditStoryJson(revision, narration).toByteArray(),
            "family-a", "66666666-6666-4666-8666-666666666666", revision)

    private class DraftPersistenceFake : StoryDraftPersistence {
        var stored: StoryDraftRecord? = null
        var failNextWrite = false
        var failNextDelete = false
        var corruptFingerprint: String? = null
        override fun load(scope: StoryDraftScope): StoryDraftRecord? {
            if (corruptFingerprint != null) throw StoryDraftStorageException("fixture corrupt record")
            return stored?.takeIf { it.scope == scope }
        }
        override fun write(record: StoryDraftRecord, expectedRevision: Long?, expectedRecordId: String?): StoryDraftRecord {
            if (failNextWrite) { failNextWrite = false; throw StoryDraftStorageException("fixture write failure") }
            val current = load(record.scope)
            if (expectedRevision == null) require(current == null) else require(current?.revision == expectedRevision && current.recordId == expectedRecordId)
            return record.copy(revision = (expectedRevision ?: 0L) + 1L).also { stored = it }
        }
        override fun delete(scope: StoryDraftScope, expectedRecordId: String, expectedRevision: Long): Boolean {
            if (failNextDelete) { failNextDelete = false; throw StoryDraftStorageException("fixture delete failure") }
            if (stored?.scope != scope || stored?.recordId != expectedRecordId || stored?.revision != expectedRevision) return false
            stored = null
            return true
        }
        override fun unreadableFingerprint(scope: StoryDraftScope) = corruptFingerprint
        override fun deleteUnreadable(scope: StoryDraftScope, expectedFingerprint: String): Boolean {
            if (corruptFingerprint != expectedFingerprint) return false
            corruptFingerprint = null
            return true
        }
        override fun occupiedSlots() = if (stored == null) 0 else 1
    }

    private suspend fun TestScope.readyForEdit(store: StoryWorkspaceStore) {
        assertTrue(store.selectAsset("1"))
        assertTrue(store.preview())
        runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
    }

    @Test fun localOpeningTitleUsesOnlyAuthoredWordsAndDoesNotCallTitleProvider() = runTest {
        var current = binding()
        val api = Fake().apply {
            capabilityBody = """{"version":1,"enabled":false,"max_suggestions":0,"needs_review":true}""".toByteArray()
            previewReplies += preview(listOf("1")).decodeToString()
                .replace("\"narration\":\"\"", "\"narration\":\"Shared memory scaffold.\"").toByteArray()
        }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current })
        readyForEdit(store)
        assertTrue(store.loadTitleCapabilities()); runCurrent()
        assertFalse(store.state.value.titleCapabilities!!.enabled)
        assertNull(store.chapterOpeningTitleCandidate())
        assertEquals("Draft title", store.state.value.title)

        assertTrue(store.editTitle("My custom title"))
        assertTrue(store.editChapterNarration(0, "  Morning at the lake! The walk continued.\nLater notes"))
        val option = requireNotNull(store.chapterOpeningTitleCandidate())
        assertEquals("Morning at the lake!", option.text)
        assertEquals("chapter-1", option.chapterId)
        assertEquals(0, option.chapterIndex)
        assertEquals("My custom title", store.state.value.title)
        assertTrue(store.adoptChapterOpeningTitle(option))
        assertEquals("Morning at the lake!", store.state.value.title)
        assertTrue(store.state.value.dirty)
        assertFalse(store.state.value.reviewed)
        assertTrue(api.saveBodies.isEmpty())
    }

    @Test fun localOpeningTitleParsingHandlesLinesDecimalsPunctuationAndEmoji() = runTest {
        var current = binding(); val store = StoryWorkspaceStore(repo(Fake()) { current }, this, { current })
        readyForEdit(store)
        val cases = listOf(
            "  We saw 2.5 birds. More later" to "We saw 2.5 birds.",
            "First line has no stop\nSecond sentence!" to "First line has no stop",
            "我们到了。后来又下雨了" to "我们到了。",
            "Wait?! Really?" to "Wait?",
            "Family 👨‍👩‍👧‍👦 day. Next" to "Family 👨‍👩‍👧‍👦 day.",
        )
        cases.forEach { (narration, expected) ->
            assertTrue(store.editChapterNarration(0, narration))
            assertEquals(expected, store.chapterOpeningTitleCandidate()?.text)
        }
    }

    @Test fun localOpeningTitleRejectsLongAndUnsafeOpeningLines() = runTest {
        var current = binding(); val store = StoryWorkspaceStore(repo(Fake()) { current }, this, { current })
        readyForEdit(store)
        listOf("x".repeat(81), "a\u0085b.", "a\u2028b.", "a\u202eb.", "\uD800 unsafe.").forEach { narration ->
            assertTrue(store.editChapterNarration(0, narration))
            assertNull(store.chapterOpeningTitleCandidate())
        }
        assertTrue(store.editChapterNarration(0, "\u0009safe-looking after trim."))
        assertNull(store.chapterOpeningTitleCandidate())
    }

    @Test fun localOpeningTitleDoesNotSkipAnOverlongFirstAuthoredChapter() = runTest {
        var current = binding(); val api = Fake()
        api.idsForPreview = listOf("1", "2")
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current })
        assertTrue(store.selectAsset("1")); assertTrue(store.selectAsset("2")); assertTrue(store.preview()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
        assertTrue(store.enableSourceReview()); runCurrent()
        assertTrue(store.splitChapter(0, 1, listOf("1", "2")))
        assertTrue(store.editChapterNarration(0, "x".repeat(81)))
        assertTrue(store.editChapterNarration(1, "A later valid opening."))
        assertNull(store.chapterOpeningTitleCandidate())
    }

    @Test fun localOpeningTitleRejectsStaleTitleNarrationSelectionAccountAndLibrarySnapshots() = runTest {
        var current = binding(); var account: String? = "member-a"
        val api = Fake()
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null,
            currentAccount = { account })
        readyForEdit(store)
        assertTrue(store.editChapterNarration(0, "A clear opening."))

        var stale = requireNotNull(store.chapterOpeningTitleCandidate())
        assertTrue(store.editTitle("A different title"))
        assertFalse(store.adoptChapterOpeningTitle(stale))

        stale = requireNotNull(store.chapterOpeningTitleCandidate())
        assertTrue(store.editChapterNarration(0, "A changed opening."))
        assertFalse(store.adoptChapterOpeningTitle(stale))

        stale = requireNotNull(store.chapterOpeningTitleCandidate())
        account = "member-b"
        assertFalse(store.adoptChapterOpeningTitle(stale))
        account = "member-a"

        stale = requireNotNull(store.chapterOpeningTitleCandidate())
        val observedBinding = current
        current = MemoryCommunityBinding(observedBinding.token, "family-b", observedBinding.generation)
        assertFalse(store.adoptChapterOpeningTitle(stale))

        current = observedBinding
        val selectionStore = StoryWorkspaceStore(repo(Fake()) { current }, this, { current }, dictationApi = null,
            currentAccount = { account })
        readyForEdit(selectionStore)
        assertTrue(selectionStore.editChapterNarration(0, "Another opening."))
        stale = requireNotNull(selectionStore.chapterOpeningTitleCandidate())
        assertTrue(selectionStore.selectAsset("2", discardDraft = true))
        assertFalse(selectionStore.adoptChapterOpeningTitle(stale))
    }

    @Test fun localOpeningTitleRefusesImeAndUnfinishedVoiceCapture() = runTest {
        var current = binding(); val voice = DictationApi()
        val store = StoryWorkspaceStore(repo(Fake()) { current }, this, { current }, dictationApi = voice,
            currentAccount = { "member-a" })
        readyForEdit(store)
        assertTrue(store.editChapterNarration(0, "Our first morning."))
        var option = requireNotNull(store.chapterOpeningTitleCandidate())
        store.composition(true)
        assertFalse(store.adoptChapterOpeningTitle(option))
        store.composition(false)

        assertTrue(store.openChapterDictation(0)); runCurrent()
        val session = requireNotNull(store.chapterDictation.value)
        assertNotNull(session.beginRecording())
        option = requireNotNull(store.chapterOpeningTitleCandidate())
        assertFalse(store.adoptChapterOpeningTitle(option))
        store.closeChapterDictation()
    }

    @Test fun localOpeningTitleCanUseReviewedVoiceWordsAndPersistsAsAuthoredTitle() = runTest {
        var current = binding(); val persistence = DraftPersistenceFake(); val voice = DictationApi()
        voice.transcriptText = "ASR words."
        val store = StoryWorkspaceStore(repo(Fake()) { current }, this, { current }, dictationApi = voice,
            currentAccount = { "member-a" }, localDraftPersistence = persistence)
        readyForEdit(store)
        assertTrue(store.openChapterDictation(0)); runCurrent()
        val session = requireNotNull(store.chapterDictation.value)
        session.beginRecording(); session.stopRecording(wav(1)); runCurrent()
        assertTrue(store.insertChapterTranscript(0, composing = false))
        assertEquals("ASR words.", store.state.value.editableChapters.single().narration)
        val option = requireNotNull(store.chapterOpeningTitleCandidate())
        assertEquals("ASR words.", option.text)
        assertTrue(store.adoptChapterOpeningTitle(option))
        assertEquals("ASR words.", store.state.value.title)
        assertTrue(store.saveLocalDraft())
        assertEquals("ASR words.", persistence.stored?.title)
        assertTrue(persistence.stored?.titleAuthored == true)
        assertEquals("ASR words.", persistence.stored?.chapters?.single()?.narration)
    }

    @Test fun durableDraftResumesAfterProcessLossAndRetriesTheExactFrozenBody() = runTest {
        var current = binding()
        val api = Fake()
        val persistence = DraftPersistenceFake()
        val first = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null, currentAccount = { "member-a" },
            uuidSupplier = { mutation }, localDraftPersistence = persistence)
        readyForEdit(first)
        assertTrue(first.saveLocalDraft())
        assertTrue(first.editTitle("Our park day"))
        assertTrue(first.editChapterNarration(0, "We laughed by the pond."))
        assertEquals("", persistence.stored?.title)

        assertTrue(first.confirmReviewed(true))
        assertTrue(first.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, first.state.value.status)
        val frozenBody = api.saveBodies.single()
        assertEquals(frozenBody, persistence.stored?.pendingSave?.body)

        // Simulate process death, then return a fresh preview with changed generated evidence.
        first.clear()
        api.previewReplies += preview(listOf("1"), revision = "b".repeat(64), evidenceId = "caption-202")
        val resumed = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null, currentAccount = { "member-a" },
            uuidSupplier = { UUID.fromString("88888888-8888-4888-8888-888888888888") }, localDraftPersistence = persistence)
        assertTrue(resumed.inspectLocalDraft())
        assertTrue(resumed.resumeLocalDraft()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, resumed.state.value.status)
        assertEquals("Our park day", resumed.state.value.title)
        assertEquals("We laughed by the pond.", resumed.state.value.editableChapters.single().narration)
        assertFalse(resumed.state.value.reviewed)
        assertTrue(resumed.state.value.sourcesReloaded)
        assertTrue(resumed.retrySave()); runCurrent()
        assertEquals(frozenBody, api.saveBodies.last())
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, resumed.state.value.status)
    }

    @Test fun untouchedGuidedDraftDoesNotRestoreOutlineNarrationAsUserWords() = runTest {
        var current = binding()
        val api = Fake()
        val persistence = DraftPersistenceFake()
        val guide = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null,
            currentAccount = { "member-a" }, localDraftPersistence = persistence)
        assertTrue(guide.startGuide())
        assertTrue(guide.selectAsset("1"))
        assertTrue(guide.continueGuide()); runCurrent()
        assertEquals(StoryGuideStep.WORDS, guide.state.value.guideStep)
        assertTrue(guide.saveLocalDraft())
        guide.clear()

        api.previewReplies += preview(listOf("1")).decodeToString()
            .replace("\"narration\":\"\"", "\"narration\":\"Outline scaffold\"").toByteArray()
        val resumed = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null,
            currentAccount = { "member-a" }, localDraftPersistence = persistence)
        assertTrue(resumed.resumeLocalDraft()); runCurrent()
        assertEquals("", resumed.state.value.editableChapters.single().narration)
    }

    @Test fun unrelatedSavedSlotIsNotCheckpointedByANewCreationWithoutResumeOrReplacement() = runTest {
        var current = binding()
        val api = Fake()
        val persistence = DraftPersistenceFake()
        val original = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null,
            currentAccount = { "member-a" }, localDraftPersistence = persistence)
        readyForEdit(original)
        assertTrue(original.editTitle("Existing saved words"))
        assertTrue(original.saveLocalDraft())
        original.clear()
        val originalRecord = requireNotNull(persistence.stored)

        val freshCreation = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null,
            currentAccount = { "member-a" }, localDraftPersistence = persistence)
        assertTrue(freshCreation.inspectLocalDraft())
        readyForEdit(freshCreation)
        assertTrue(freshCreation.editTitle("A separate new story"))
        assertTrue(freshCreation.confirmReviewed(true))
        assertTrue(freshCreation.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, freshCreation.state.value.status)
        assertEquals(originalRecord.recordId, persistence.stored?.recordId)
        assertEquals(originalRecord.revision, persistence.stored?.revision)
        assertEquals("Existing saved words", persistence.stored?.title)
        assertNull(persistence.stored?.pendingSave)
    }

    @Test fun durableCheckpointFailurePreventsNetworkAndPendingRecoveryCannotBeOverwritten() = runTest {
        var current = binding()
        val api = Fake()
        val persistence = DraftPersistenceFake()
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null, currentAccount = { "member-a" },
            uuidSupplier = { mutation }, localDraftPersistence = persistence)
        readyForEdit(store)
        assertTrue(store.editTitle("Saved words"))
        assertTrue(store.saveLocalDraft())
        persistence.failNextWrite = true
        assertTrue(store.confirmReviewed(true))
        assertFalse(store.save())
        runCurrent()
        assertTrue(api.saveBodies.isEmpty())
        assertNull(persistence.stored?.pendingSave)

        assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        val oldBody = persistence.stored?.pendingSave?.body
        assertNotNull(oldBody)
        store.clear()

        val fresh = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null, currentAccount = { "member-a" },
            localDraftPersistence = persistence)
        assertTrue(fresh.inspectLocalDraft())
        assertTrue(fresh.state.value.localDraftRequiresRecovery)
        assertFalse(fresh.selectAsset("2"))
        assertEquals(oldBody, persistence.stored?.pendingSave?.body)
        assertFalse(fresh.deleteLocalDraft()) // unknown publication cannot be discarded
        assertEquals(oldBody, persistence.stored?.pendingSave?.body)
    }

    @Test fun confirmedPublicationAllowsExplicitCleanupAfterDeleteFailure() = runTest {
        var current = binding()
        val api = Fake()
        val persistence = DraftPersistenceFake()
        val first = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null,
            currentAccount = { "member-a" }, uuidSupplier = { mutation }, localDraftPersistence = persistence)
        readyForEdit(first)
        assertTrue(first.editTitle("Durable title"))
        assertTrue(first.saveLocalDraft())
        assertTrue(first.confirmReviewed(true))
        assertTrue(first.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, first.state.value.status)
        first.clear()

        val resumed = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null,
            currentAccount = { "member-a" }, localDraftPersistence = persistence)
        assertTrue(resumed.inspectLocalDraft())
        assertTrue(resumed.resumeLocalDraft()); runCurrent()
        persistence.failNextDelete = true
        api.saveResponse = savedReply(listOf("1"))
        assertTrue(resumed.retrySave()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVED, resumed.state.value.status)
        assertTrue(resumed.state.value.localDraftError)
        assertNotNull(persistence.stored?.pendingSave)
        assertTrue(resumed.deleteLocalDraft())
        assertNull(persistence.stored)
    }

    @Test fun publicationConfirmationCannotDeleteANewerPendingReplacement() = runTest {
        var current = binding()
        val api = Fake()
        val persistence = DraftPersistenceFake()
        val first = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null,
            currentAccount = { "member-a" }, uuidSupplier = { mutation }, localDraftPersistence = persistence)
        readyForEdit(first)
        assertTrue(first.editTitle("Published words"))
        assertTrue(first.saveLocalDraft())
        assertTrue(first.confirmReviewed(true))
        assertTrue(first.save()); runCurrent()
        first.clear()

        val resumed = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null,
            currentAccount = { "member-a" }, localDraftPersistence = persistence)
        assertTrue(resumed.inspectLocalDraft())
        assertTrue(resumed.resumeLocalDraft()); runCurrent()
        persistence.failNextDelete = true
        api.saveResponse = savedReply(listOf("1"))
        assertTrue(resumed.retrySave()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVED, resumed.state.value.status)

        val oldRecovery = requireNotNull(persistence.stored)
        val replacement = oldRecovery.copy(recordId = "99999999-9999-4999-8999-999999999999",
            revision = oldRecovery.revision + 1, updatedAtEpochMillis = oldRecovery.updatedAtEpochMillis + 1,
            pendingSave = oldRecovery.pendingSave!!.copy(mutationId = "77777777-7777-4777-8777-777777777777"))
        persistence.stored = replacement

        assertFalse(resumed.deleteLocalDraft())
        assertEquals(replacement, persistence.stored)
        assertTrue(resumed.state.value.localDraftRequiresRecovery)
    }

    @Test fun unreadableDraftDeletionRequiresTheFingerprintObservedDuringInspection() = runTest {
        var current = binding()
        val api = Fake()
        val persistence = DraftPersistenceFake().apply { corruptFingerprint = "observed-corrupt-bytes" }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }, dictationApi = null,
            currentAccount = { "member-a" }, localDraftPersistence = persistence)
        assertFalse(store.inspectLocalDraft())
        assertTrue(store.state.value.localDraftCanDeleteUnreadable)
        persistence.corruptFingerprint = "newer-replacement-bytes"
        assertFalse(store.deleteUnreadableLocalDraft())
        assertEquals("newer-replacement-bytes", persistence.corruptFingerprint)

        assertFalse(store.inspectLocalDraft())
        assertTrue(store.deleteUnreadableLocalDraft())
        assertNull(persistence.corruptFingerprint)
    }

    @Test fun selectionCapRejectsTheTwentyFifthWithoutDroppingEarlierChoices() = runTest {
        var current = binding()
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(Fake(), { current }), this, { current })
        (1..24).forEach { assertTrue(store.selectAsset(it.toString())) }
        assertFalse(store.selectAsset("25"))
        assertEquals((1..24).map(Int::toString), store.state.value.selectedAssetIds)
    }

    @Test fun optInEvidenceChoicesClearReviewAndFreezeProfileOnUncertainRetry() = runTest {
        var current = binding(); val api = Fake()
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }) { mutation }
        readyForEdit(store)
        assertTrue(store.enableSourceReview()); runCurrent()
        assertTrue(store.state.value.sourceReviewEnabled)
        assertTrue(store.toggleChapterEvidence(0, "caption-101", false))
        assertTrue(store.state.value.editableChapters.single().evidenceIds.isEmpty())
        assertFalse(store.state.value.reviewed)
        assertTrue(store.confirmReviewed(true)); assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        assertEquals(listOf(true), api.saveProfiles)
        val body = Json.parseToJsonElement(api.saveBodies.single()).jsonObject
        assertEquals("chapter_sources_v1", body["source_policy"]!!.jsonPrimitive.content)
        val chapterJson = body.getValue("chapters").jsonPrimitive.content
        assertTrue(chapterJson.contains("\"evidence_ids\":[]"))
        assertTrue(store.retrySave()); runCurrent()
        assertEquals(listOf(true, true), api.saveProfiles)
        assertEquals(api.saveBodies.first(), api.saveBodies.last())
    }

    @Test fun reviewedNewDraftCanSplitMergeAndRetryManualThreePlusTwoWithoutLosingTextOrSources() = runTest {
        var current = binding(); val titleGate = CompletableDeferred<ByteArray>()
        val api = Fake().apply { idsForPreview = (1..5).map(Int::toString); suggestionGates.add(titleGate) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }) { mutation }
        (1..5).forEach { assertTrue(store.selectAsset(it.toString())) }
        assertTrue(store.preview()); runCurrent()
        val selectionRevision = store.state.value.draft!!.selectionRevision
        assertTrue(store.enableSourceReview()); runCurrent()
        assertTrue(store.state.value.sourceReviewEnabled)
        assertTrue(store.editChapterTitle(0, "Park walk"))
        assertTrue(store.editChapterNarration(0, "First part family words"))
        assertTrue(store.editChapterTitle(1, "Picnic"))
        assertTrue(store.editChapterNarration(1, "Second part family words"))
        assertTrue(store.loadTitleCapabilities()); runCurrent()
        assertTrue(store.suggestTitles()); runCurrent()

        val originalFirstAssets = listOf("1", "2", "3", "4")
        assertFalse(store.splitChapter(0, 2, listOf("wrong")))
        assertTrue(store.splitChapter(0, 3, originalFirstAssets))
        assertEquals(listOf("1", "2", "3", "4", "5"), store.state.value.selectedAssetIds)
        assertEquals(selectionRevision, store.state.value.draft!!.selectionRevision)
        assertEquals(listOf("chapter-1", "chapter-2", "chapter-3"), store.state.value.editableChapters.map { it.id })
        assertEquals(listOf(listOf("1", "2", "3"), listOf("4"), listOf("5")),
            store.state.value.editableChapters.map { it.assetIds })
        assertEquals("Park walk", store.state.value.editableChapters[1].title)
        assertEquals("", store.state.value.editableChapters[1].narration)
        assertEquals("First part family words", store.state.value.editableChapters[0].narration)
        assertEquals("Second part family words", store.state.value.editableChapters[2].narration)
        assertEquals(listOf("caption-101"), store.state.value.editableChapters[0].evidenceIds)
        assertTrue(store.state.value.editableChapters[1].evidenceIds.isEmpty())
        assertTrue(store.state.value.titleCandidates.isEmpty())
        assertFalse(store.state.value.reviewed)
        assertTrue(store.state.value.dirty)

        titleGate.complete(titleReply("Late pre-split title")); runCurrent()
        assertTrue(store.state.value.titleCandidates.isEmpty())
        assertTrue(store.mergeChapterWithNext(0, listOf("1", "2", "3"), listOf("4")))
        assertEquals("Park walk", store.state.value.editableChapters[0].title)
        assertTrue(store.splitChapter(0, 3, listOf("1", "2", "3", "4")))
        assertTrue(store.mergeChapterWithNext(1, listOf("4"), listOf("5")))
        assertEquals(listOf(listOf("1", "2", "3"), listOf("4", "5")),
            store.state.value.editableChapters.map { it.assetIds })
        assertEquals(listOf("chapter-1", "chapter-2"), store.state.value.draft!!.chapters.map { it.id })
        assertEquals("Park walk / Picnic", store.state.value.editableChapters[1].title)
        assertEquals("Second part family words", store.state.value.editableChapters[1].narration)
        assertEquals(listOf("caption-5"), store.state.value.editableChapters[1].evidenceIds)
        assertEquals(store.state.value.editableChapters, store.state.value.draft!!.chapters)

        assertTrue(store.confirmReviewed(true)); assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        val body = Json.parseToJsonElement(api.saveBodies.single()).jsonObject
        val frozenChapters = Json.parseToJsonElement(body.getValue("chapters").jsonPrimitive.content).jsonArray
        assertEquals(listOf(listOf("1", "2", "3"), listOf("4", "5")), frozenChapters.map { chapter ->
            chapter.jsonObject.getValue("asset_ids").jsonArray.map { it.jsonPrimitive.content }
        })
        assertEquals("chapter_sources_v1", body.getValue("source_policy").jsonPrimitive.content)
        assertFalse(store.splitChapter(0, 1, listOf("1", "2", "3")))
        assertTrue(store.retrySave()); runCurrent()
        assertEquals(api.saveBodies.first(), api.saveBodies.last())
    }

    @Test fun regroupRejectsLegacySavedStaleAndOverflowCasesWithoutPartialMutation() = runTest {
        var current = binding()
        val legacy = StoryWorkspaceStore(repo(Fake(), { current }), this, { current })
        (1..4).forEach { assertTrue(legacy.selectAsset(it.toString())) }
        assertTrue(legacy.preview()); runCurrent()
        assertFalse(legacy.splitChapter(0, 2, listOf("1", "2", "3", "4")))

        val api = Fake().apply { idsForPreview = (1..4).map(Int::toString) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current })
        (1..4).forEach { assertTrue(store.selectAsset(it.toString())) }
        assertTrue(store.preview()); runCurrent()
        assertTrue(store.enableSourceReview()); runCurrent()
        assertTrue(store.splitChapter(0, 2, listOf("1", "2", "3", "4")))
        val before = store.state.value.editableChapters
        assertFalse(store.mergeChapterWithNext(0, listOf("1"), listOf("3", "4")))
        assertEquals(before, store.state.value.editableChapters)

        assertTrue(store.editChapterTitle(0, "A".repeat(80)))
        assertTrue(store.editChapterTitle(1, "B".repeat(80)))
        val beforeTitleOverflow = store.state.value.editableChapters
        assertFalse(store.mergeChapterWithNext(0, listOf("1", "2"), listOf("3", "4")))
        assertEquals(beforeTitleOverflow, store.state.value.editableChapters)

        assertTrue(store.editChapterTitle(0, "First"))
        assertTrue(store.editChapterTitle(1, "Second"))
        assertTrue(store.editChapterNarration(0, "x".repeat(3001)))
        assertTrue(store.editChapterNarration(1, "y".repeat(3001)))
        val beforeNarrationOverflow = store.state.value.editableChapters
        assertFalse(store.mergeChapterWithNext(0, listOf("1", "2"), listOf("3", "4")))
        assertEquals(beforeNarrationOverflow, store.state.value.editableChapters)

        val savedJson = savedReply(listOf("1", "2")).decodeToString()
            .replace("\"revision\":\"1\"", "\"revision\":\"4\"")
            .replace("\"version\":1,", "\"version\":1,\"source_policy\":\"chapter_sources_v1\",")
        val saved = ProtectedMemoryStoriesWire.detail(savedJson.toByteArray(), "family-a",
            "66666666-6666-4666-8666-666666666666", 4, sourceReview = true)
        val refs = SavedMemoryStoryContributionReferences(saved.id, saved.libraryId, saved.revision,
            listOf(SavedMemoryChapterContributionReferences("chapter-1", emptyList())))
        val savedStore = StoryWorkspaceStore(repo(Fake(), { current }), this, { current })
        assertTrue(savedStore.seedSavedStoryForEdit(saved, refs))
        assertTrue(savedStore.state.value.sourceReviewEnabled)
        assertFalse(savedStore.splitChapter(0, 1, listOf("1", "2")))
    }

    @Test fun savedStoryEditKeepsSavedLayoutAndCompleteLinksAcrossIdenticalRetry() = runTest {
        var current = binding()
        val api = Fake().apply {
            updateFailures += ApiFailure(FailureKind.OFFLINE)
            updateResponse = savedEditStoryJson(revision = 5, narration = "Edited saved narration").toByteArray()
        }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }, uuidSupplier = { mutation })
        val base = savedEditStory()
        val contributionId = "77777777-7777-4777-8777-777777777777"
        val references = SavedMemoryStoryContributionReferences(base.id, base.libraryId, base.revision,
            listOf(SavedMemoryChapterContributionReferences("chapter-1", listOf(contributionId))))
        assertTrue(store.seedSavedStoryForEdit(base, references))
        assertEquals(listOf("1"), store.state.value.selectedAssetIds)
        assertEquals(listOf("1"), store.state.value.editableChapters.single().assetIds)
        assertEquals("Original saved narration", store.state.value.editableChapters.single().narration)
        assertFalse(store.preview())
        assertFalse(store.selectAsset("2"))
        assertFalse(store.setTheme("trip"))
        assertFalse(store.setLanguage("en"))
        assertTrue(store.editTitle("Edited saved title"))
        assertTrue(store.editChapterNarration(0, "Edited saved narration"))
        assertTrue(store.confirmReviewed(true))
        assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        assertEquals(listOf(base.id), api.updateTargets)
        assertEquals(listOf(false to true), api.updateProfiles)
        val frozen = api.updateBodies.single()
        val body = Json.parseToJsonElement(frozen).jsonObject
        assertEquals("4", body.getValue("revision").jsonPrimitive.content)
        assertEquals(mutation.toString(), body.getValue("mutation_id").jsonPrimitive.content)
        val refs = Json.parseToJsonElement(body.getValue("contribution_refs").jsonPrimitive.content).jsonArray
        assertEquals(listOf(contributionId), refs.single().jsonObject.getValue("contribution_ids").jsonArray.map { it.jsonPrimitive.content })
        assertTrue(store.retrySave()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVED, store.state.value.status)
        assertEquals(2, api.updateBodies.size)
        assertEquals(listOf(frozen, frozen), api.updateBodies)
        assertEquals(listOf(false to true, false to true), api.updateProfiles)
        assertEquals(5L, store.state.value.savedStory?.revision)
        assertEquals("Edited saved title", Json.parseToJsonElement(frozen).jsonObject.getValue("title").jsonPrimitive.content)
    }

    @Test fun savedStoryConflictRetainsUnsavedWordsUntilExplicitFreshReseed() = runTest {
        var current = binding()
        val api = Fake().apply { updateFailures += ApiFailure(FailureKind.HTTP, 409) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current })
        val base = savedEditStory()
        val refs = SavedMemoryStoryContributionReferences(base.id, base.libraryId, base.revision,
            listOf(SavedMemoryChapterContributionReferences("chapter-1", emptyList())))
        assertTrue(store.seedSavedStoryForEdit(base, refs))
        assertTrue(store.editChapterNarration(0, "Unsaved words to keep"))
        assertTrue(store.confirmReviewed(true)); assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.CONFLICT, store.state.value.status)
        assertEquals("Unsaved words to keep", store.state.value.editableChapters.single().narration)
        assertTrue(store.state.value.hasUnfinishedWork)
        val latest = savedEditStory(revision = 5, narration = "Latest server words")
        assertTrue(store.seedSavedStoryForEdit(latest, refs.copy(revision = 5)))
        assertEquals("Latest server words", store.state.value.editableChapters.single().narration)
        assertFalse(store.state.value.reviewed)
        assertFalse(store.state.value.dirty)
        assertEquals(5L, store.state.value.draft?.let { latest.revision })
    }

    @Test fun idempotentUpdateRetryCanReportAConfirmedButNowNewerFamilyVersion() = runTest {
        var current = binding()
        val api = Fake().apply {
            updateResponse = savedEditStoryJson(revision = 6, narration = "Latest family revision").toByteArray()
        }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }, uuidSupplier = { mutation })
        val base = savedEditStory(revision = 4)
        val refs = SavedMemoryStoryContributionReferences(base.id, base.libraryId, base.revision,
            listOf(SavedMemoryChapterContributionReferences("chapter-1", emptyList())))
        assertTrue(store.seedSavedStoryForEdit(base, refs))
        assertTrue(store.editChapterNarration(0, "My previously submitted edits"))
        assertTrue(store.confirmReviewed(true))
        assertTrue(store.save()); runCurrent()

        assertEquals(StoryWorkspaceStoreStatus.SAVED, store.state.value.status)
        assertEquals(6L, store.state.value.savedStory?.revision)
        assertTrue(store.state.value.savedStoryIsNewerThanEditBase)
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

    @Test fun reviewedManualGroupingSurvivesConflictSourceReloadAndFiltersEvidenceByActualAssets() = runTest {
        var current = binding()
        val api = Fake().apply { idsForPreview = (1..5).map(Int::toString); saveFailure = ApiFailure(FailureKind.HTTP, 409) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current }) { mutation }
        (1..5).forEach { assertTrue(store.selectAsset(it.toString())) }
        assertTrue(store.preview()); runCurrent()
        assertTrue(store.enableSourceReview()); runCurrent()
        assertTrue(store.splitChapter(0, 3, listOf("1", "2", "3", "4")))
        assertTrue(store.editTitle("Together again"))
        assertTrue(store.editChapterTitle(0, "Morning walk"))
        assertTrue(store.editChapterNarration(0, "We started together."))
        assertTrue(store.editChapterTitle(1, "At the gate"))
        assertTrue(store.editChapterNarration(1, "We paused there."))
        assertTrue(store.editChapterTitle(2, "Picnic"))
        assertTrue(store.editChapterNarration(2, "We shared lunch."))
        assertTrue(store.confirmReviewed(true)); assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.CONFLICT, store.state.value.status)

        api.saveFailure = null
        api.previewReplies.add(preview((1..5).map(Int::toString), "b".repeat(64), "caption-303"))
        assertTrue(store.reloadPreview()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
        assertEquals("b".repeat(64), store.state.value.draft?.selectionRevision)
        assertEquals("Together again", store.state.value.draft?.title)
        assertEquals(listOf(listOf("1", "2", "3"), listOf("4"), listOf("5")),
            store.state.value.editableChapters.map { it.assetIds })
        assertEquals(listOf("Morning walk", "At the gate", "Picnic"),
            store.state.value.editableChapters.map { it.title })
        assertEquals(listOf("We started together.", "We paused there.", "We shared lunch."),
            store.state.value.editableChapters.map { it.narration })
        assertEquals(emptyList<String>(), store.state.value.editableChapters[0].evidenceIds)
        assertEquals(listOf("caption-5"), store.state.value.editableChapters[2].evidenceIds)
        assertEquals("caption-303", store.state.value.draft?.items?.first()?.evidence?.single()?.id)
        assertEquals(store.state.value.editableChapters, store.state.value.draft?.chapters)
        assertTrue(store.state.value.sourceReviewEnabled)
        assertTrue(store.state.value.sourcesReloaded)
        assertFalse(store.state.value.reviewed)
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

    @Test fun chapterDictationReviewsTranscriptPreservesLatestTypedTextAndKeepsOverflow() = runTest {
        var current = binding()
        val voice = DictationApi()
        val persistence = DraftPersistenceFake()
        val store = StoryWorkspaceStore(repo(Fake()) { current }, this, { current },
            dictationApi = voice, currentAccount = { "member" }, localDraftPersistence = persistence)
        readyForEdit(store)
        assertTrue(store.editChapterNarration(0, "先写下的内容"))
        assertTrue(store.openChapterDictation(0)); runCurrent()
        val session = store.chapterDictation.value!!
        assertEquals(5, session.beginRecording())
        session.stopRecording(wav(1)); runCurrent()
        assertEquals("ASR words", session.state.value.transcript)
        assertTrue(store.editChapterNarration(0, "核对时补充的内容"))
        assertFalse(store.editTitle("Blocked while reviewing"))
        assertFalse(store.confirmReviewed(true))
        assertFalse(store.save())
        assertFalse(store.saveLocalDraft())
        assertFalse(store.insertChapterTranscript(0, composing = true))
        assertEquals("ASR words", session.state.value.transcript)
        assertTrue(store.insertChapterTranscript(0, composing = false))
        assertEquals("核对时补充的内容\n\nASR words", store.state.value.editableChapters.single().narration)
        assertNull(session.state.value.transcript)
        assertTrue(store.saveLocalDraft())
        assertEquals("核对时补充的内容\n\nASR words", persistence.stored?.chapters?.single()?.narration)
        assertNull(store.chapterDictation.value)

        store.closeChapterDictation()
        assertTrue(store.editChapterNarration(0, "字".repeat(2000))) // 6,000 UTF-8 bytes.
        voice.transcriptText = "A"
        assertTrue(store.openChapterDictation(0)); runCurrent()
        val overflowSession = store.chapterDictation.value!!
        overflowSession.beginRecording(); overflowSession.stopRecording(wav(1)); runCurrent()
        assertFalse(store.insertChapterTranscript(0, composing = false))
        assertEquals("字".repeat(2000), store.state.value.editableChapters.single().narration)
        assertEquals("A", overflowSession.state.value.transcript)
        assertTrue(store.hasUnfinishedChapterDictation)
        assertFalse(store.confirmReviewed(true))
        assertFalse(store.save())
        store.closeChapterDictation()
        assertFalse(store.hasUnfinishedChapterDictation)
        assertEquals(2, voice.transcriptions)
    }

    @Test fun chapterDictationCannotOpenDuringUncertainSave() = runTest {
        var current = binding()
        val voice = DictationApi()
        val api = Fake().apply { saveFailure = ApiFailure(FailureKind.OFFLINE) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current },
            dictationApi = voice, currentAccount = { "member" }, uuidSupplier = { mutation })
        readyForEdit(store)
        assertTrue(store.editTitle("Uncertain save")); assertTrue(store.confirmReviewed(true))
        assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        assertFalse(store.openChapterDictation(0))
        assertEquals(0, voice.transcriptions)
    }

    @Test fun openIdleChapterDictationBlocksRegroupAndRemainsOpen() = runTest {
        var current = binding()
        val voice = DictationApi()
        val api = Fake().apply { idsForPreview = (1..5).map(Int::toString) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current },
            dictationApi = voice, currentAccount = { "member" })
        (1..5).forEach { assertTrue(store.selectAsset(it.toString())) }
        assertTrue(store.preview()); runCurrent()
        assertTrue(store.enableSourceReview()); runCurrent()
        assertTrue(store.state.value.sourceReviewEnabled)
        val originalChapters = store.state.value.editableChapters
        assertTrue(store.openChapterDictation(0)); runCurrent()
        val idleSession = store.chapterDictation.value!!
        assertFalse(store.hasUnfinishedChapterDictation)

        assertFalse(store.splitChapter(0, 2, listOf("1", "2", "3", "4")))
        assertFalse(store.mergeChapterWithNext(0, listOf("1", "2", "3", "4"), listOf("5")))
        assertSame(idleSession, store.chapterDictation.value)
        assertEquals(originalChapters, store.state.value.editableChapters)
        assertEquals(0, voice.transcriptions)
        store.closeChapterDictation()
        assertNull(store.chapterDictation.value)
    }

    @Test fun chapterDictationCannotInsertIntoAnotherChapterAndIdleSwitchRebinds() = runTest {
        var current = binding()
        val voice = DictationApi()
        val api = Fake().apply { idsForPreview = (1..5).map(Int::toString) }
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current },
            dictationApi = voice, currentAccount = { "member" })
        (1..5).forEach { assertTrue(store.selectAsset(it.toString())) }
        assertTrue(store.preview()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
        assertEquals(2, store.state.value.editableChapters.size)

        assertTrue(store.openChapterDictation(0)); runCurrent()
        val first = store.chapterDictation.value!!
        first.beginRecording(); first.stopRecording(wav(1)); runCurrent()
        assertEquals("ASR words", first.state.value.transcript)
        assertFalse(store.openChapterDictation(1))
        assertFalse(store.insertChapterTranscript(1, composing = false))
        assertEquals("ASR words", first.state.value.transcript)
        assertEquals("", store.state.value.editableChapters[1].narration)

        store.closeChapterDictation()
        assertTrue(store.openChapterDictation(1)); runCurrent()
        val second = store.chapterDictation.value!!
        assertNotSame(first, second)
        assertFalse("an older pane disposal cannot close the current chapter helper", store.closeChapterDictationIfCurrent(first))
        assertSame(second, store.chapterDictation.value)
        second.beginRecording(); second.stopRecording(wav(1)); runCurrent()
        assertFalse(store.insertChapterTranscript(0, composing = false))
        assertEquals("ASR words", second.state.value.transcript)
        assertTrue(store.insertChapterTranscript(1, composing = false))
        assertEquals("ASR words", store.state.value.editableChapters[1].narration)
        assertEquals("", store.state.value.editableChapters[0].narration)
        store.closeChapterDictation()
    }

    @Test fun changedEditorGenerationDropsLateDictationCapabilityResponse() = runTest {
        var current = binding()
        val gate = CompletableDeferred<Unit>()
        val voice = DictationApi().apply { capabilityGate = gate }
        var denied = 0
        val store = StoryWorkspaceStore(repo(Fake()) { current }, this, { current },
            dictationApi = voice, currentAccount = { "member" }, onDictationDenied = { denied++ })
        readyForEdit(store)
        assertTrue(store.openChapterDictation(0)); runCurrent()
        val oldSession = store.chapterDictation.value!!
        assertTrue(oldSession.state.value.loading)
        current = binding(2)
        assertFalse(store.editChapterNarration(0, "Must be cleared with the old editor"))
        gate.complete(Unit); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SELECTION, store.state.value.status)
        assertNull(store.chapterDictation.value)
        assertEquals(MemoryDictationState(), oldSession.state.value)
        assertEquals(0, denied)
    }

    @Test fun dictatedWordsAreOnlyPersistedByTheSeparateExplicitStorySave() = runTest {
        var current = binding()
        val api = Fake().apply { saveResponse = savedReply(listOf("1")) }
        val voice = DictationApi()
        val store = StoryWorkspaceStore(repo(api) { current }, this, { current },
            dictationApi = voice, currentAccount = { "member" }, uuidSupplier = { mutation })
        readyForEdit(store)
        assertTrue(store.editChapterNarration(0, "Typed first"))
        assertTrue(store.openChapterDictation(0)); runCurrent()
        val session = store.chapterDictation.value!!
        session.beginRecording(); session.stopRecording(wav(1)); runCurrent()
        assertTrue(store.insertChapterTranscript(0, composing = false))
        runCurrent()
        assertTrue(api.saveBodies.isEmpty())
        assertEquals("Typed first\n\nASR words", store.state.value.editableChapters.single().narration)
        assertTrue(store.confirmReviewed(true))
        assertTrue(store.save()); runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVED, store.state.value.status)
        val savedBody = Json.parseToJsonElement(api.saveBodies.single()).jsonObject
        val chapters = Json.parseToJsonElement(savedBody.getValue("chapters").jsonPrimitive.content).jsonArray
        assertEquals("Typed first\n\nASR words", chapters.single().jsonObject.getValue("narration").jsonPrimitive.content)
    }

    private fun wav(seconds: Int): ByteArray {
        val pcmSize = 32_000 * seconds
        return ByteArray(44 + pcmSize).also { out ->
            fun tag(at: Int, text: String) = text.toByteArray(Charsets.US_ASCII).copyInto(out, at)
            fun u16(at: Int, value: Int) { out[at] = value.toByte(); out[at + 1] = (value shr 8).toByte() }
            fun u32(at: Int, value: Int) { repeat(4) { out[at + it] = (value shr (it * 8)).toByte() } }
            tag(0, "RIFF"); u32(4, out.size - 8); tag(8, "WAVE"); tag(12, "fmt ")
            u32(16, 16); u16(20, 1); u16(22, 1); u32(24, 16_000); u32(28, 32_000)
            u16(32, 2); u16(34, 16); tag(36, "data"); u32(40, pcmSize)
        }
    }
}
