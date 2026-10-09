package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryBookNarrativeStoreTest {
    private val bookId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    private val storyOne = "11111111-1111-4111-8111-111111111111"
    private val storyTwo = "22222222-2222-4222-8222-222222222222"
    private val jobId = "99999999-9999-4999-8999-999999999999"
    private val capabilities = """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":true,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}"""

    private fun bearer(seed: Char = 'a') = Bearer.from(SessionToken(86400, seed.toString().repeat(43), "Bearer"))

    private fun children() = listOf(EditorialChild(storyOne, "3"), EditorialChild(storyTwo, "4"))

    private fun makeScope(
        credential: Bearer = bearer(),
        account: String = "account-a",
        bookRevision: Long = 7,
        childRows: List<EditorialChild> = children(),
        scopeId: Long = 12,
        generation: Long = 2,
    ) = MemoryBookNarrativeScope(account, credential, "family-a", generation, bookId,
        bookRevision, childRows, scopeId)

    private fun planJson(
        scope: MemoryBookNarrativeScope,
        editorial: Boolean,
        wholeState: String = "within_limits",
        canEdit: Boolean = true,
    ): ByteArray {
        val sections = scope.children.mapIndexed { index, child ->
            val title = if (index == 0) "Garden" else "Family table"
            """{"position":${index + 1},"id":"${child.storyId}","revision":"${child.revision}","title":"$title","item_count":1,"can_edit":$canEdit,"chapters":[{"id":"chapter-1","title":"${if (index == 0) "Opening" else "Supper"}","item_count":1}],"state":"within_limits","can_draft":$canEdit,"source_count":1,"source_kinds":{"family":1}}"""
        }
        val within = wholeState == "within_limits"
        val whole = if (within) {
            """{"state":"within_limits","can_draft":$canEdit,"source_count":2,"source_kinds":{"family":2}${if (editorial) ",\"context_bytes\":2048" else ""}}"""
        } else {
            """{"state":"smaller_scope_required","can_draft":false,"source_count":null,"source_kinds":null${if (editorial) ",\"context_bytes\":null" else ""}}"""
        }
        return """{"version":1,"target_type":"book","target_id":"${scope.bookId}","revision":"${scope.bookRevision}","can_edit":$canEdit,"kind":"saved_structure_plan","generated":false,"queued":false,"needs_review":true,"story_count":${sections.size},"chapter_count":${sections.size},"item_count":${sections.size},"distinct_item_count":${sections.size},"limits":{"chapters":24,"sources":96,"context_bytes":65536},"whole":$whole,"sections":[${sections.joinToString(",")}]${if (editorial) ",\"context_profile\":\"memoir_editorial_v1\"" else ""}}""".toByteArray()
    }

    private fun proposalJson(ids: List<String>, sourceIds: List<String> = listOf("family-source-1")): String {
        val chapters = ids.mapIndexed { index, id ->
            val citations = sourceIds.joinToString(",") { "\"$it\"" }
            """{"id":"$id","narration":"Suggested memory ${index + 1}","source_ids":[$citations]}"""
        }
        return """{"version":1,"title":"A family memory","chapters":[${chapters.joinToString(",")}],"questions":["Which year was this?"],"needs_review":true}"""
    }

    private fun jobJson(state: String, result: String? = null, id: String = jobId, revision: Long = 7): ByteArray =
        """{"version":1,"id":"$id","kind":"narrative","state":"$state","created_at":1720000000,"updated_at":1720000001,"expires_at":1721000000,"error_code":null,"result":${result ?: "null"},"needs_review":true,"base_revision":"$revision"}""".toByteArray()

    private inner class FakeApi : MemoryCommunityApi {
        var planGate: CompletableDeferred<ByteArray>? = null
        var jobGate: CompletableDeferred<ByteArray>? = null
        var planEditorialChoices = mutableListOf<Boolean>()
        var queueChoices = mutableListOf<Boolean>()
        var requestBodies = mutableListOf<String>()
        var queueCalls = 0
        var getJobCalls = 0
        var cancelCalls = 0
        var nextQueueFailure: ApiFailure? = null
        var nextJobResponse: ByteArray? = null
        var nextCancelResponse: ByteArray? = null

        override suspend fun capabilities(token: Bearer, library: String) = capabilities.toByteArray()

        override suspend fun bookPlan(
            token: Bearer, library: String, bookId: String, editorialContext: Boolean,
        ): ByteArray {
            planEditorialChoices += editorialContext
            return planGate?.await() ?: planJson(currentScopeValue!!, editorialContext)
        }

        override suspend fun queueNarrative(
            token: Bearer, library: String, json: String, editorialContext: Boolean,
        ): ByteArray {
            queueCalls++
            queueChoices += editorialContext
            requestBodies += json
            nextQueueFailure?.let { nextQueueFailure = null; throw it }
            return jobJson("queued")
        }

        override suspend fun getJob(token: Bearer, library: String, jobId: String): ByteArray {
            getJobCalls++
            return jobGate?.await() ?: nextJobResponse ?: jobJson("queued", id = jobId)
        }

        override suspend fun cancelJob(token: Bearer, library: String, jobId: String): ByteArray {
            cancelCalls++
            return nextCancelResponse ?: jobJson("cancelled", id = jobId)
        }
    }

    private var currentScopeValue: MemoryBookNarrativeScope? = null

    private suspend fun setup(
        api: FakeApi,
        scope: kotlinx.coroutines.CoroutineScope,
    ): MemoryBookNarrativeStore {
        val repo = MemoryCommunityRepository(api, {
            currentScopeValue?.let { MemoryCommunityBinding(it.credential, it.library, it.generation) }
        })
        repo.loadCapabilities()
        return MemoryBookNarrativeStore(repo, scope) { currentScopeValue }
    }

    private fun flattenedIds(scope: MemoryBookNarrativeScope): List<String> =
        scope.children.map { "${it.storyId}-chapter-1" }

    @Test fun explicitPlanAndQueueShowMappedReviewWithoutSourceIdentifiers() = runTest {
        currentScopeValue = makeScope()
        val api = FakeApi()
        val store = setup(api, backgroundScope)
        assertFalse(store.state.value.editorialContext)
        assertTrue(store.updateInstructions("Keep the family's uncertainty clear."))
        assertTrue(store.chooseEditorialContext(true))
        assertTrue(store.checkPlan())
        assertEquals(listOf(true), api.planEditorialChoices)
        assertEquals(0, api.queueCalls)
        assertEquals(MemoryBookNarrativeStatus.PLAN_READY, store.state.value.status)
        assertTrue(store.state.value.hasUnfinishedInput)

        assertTrue(store.queue())
        assertEquals(listOf(true), api.queueChoices)
        assertEquals("book", Json.parseToJsonElement(api.requestBodies.single()).jsonObject["target_type"]!!.toString().trim('"'))
        assertEquals(7L, store.state.value.job?.baseRevision)
        assertFalse(store.state.value.hasUnfinishedInput)
        assertNull(store.state.value.proposal)

        api.nextJobResponse = jobJson("ready", proposalJson(flattenedIds(currentScopeValue!!)))
        assertTrue(store.refresh())
        val review = store.state.value.proposal!!
        assertEquals("A family memory", review.title)
        assertEquals(2, review.chapters.size)
        assertEquals(storyOne, review.chapters[0].storyId)
        assertEquals("Garden", review.chapters[0].storyTitle)
        assertEquals("Opening", review.chapters[0].chapterTitle)
        assertEquals(storyTwo, review.chapters[1].storyId)
        assertEquals("Family table", review.chapters[1].storyTitle)
        assertEquals(1, review.chapters[0].citationCount)
        assertFalse(review.toString().contains("family-source-1"))
        assertTrue(review.needsReview)
    }

    @Test fun defaultChoiceKeepsNarrativeQueryOptedOut() = runTest {
        currentScopeValue = makeScope()
        val api = FakeApi()
        val store = setup(api, backgroundScope)
        assertTrue(store.updateInstructions("Use only the current saved stories."))
        assertTrue(store.checkPlan())
        assertTrue(store.queue())
        assertEquals(listOf(false), api.planEditorialChoices)
        assertEquals(listOf(false), api.queueChoices)
        val body = Json.parseToJsonElement(api.requestBodies.single()).jsonObject
        assertEquals(setOf("target_type", "target_id", "revision", "mutation_id", "instructions"), body.keys)
        assertEquals("book", body["target_type"]!!.toString().trim('"'))
        assertEquals("7", body["revision"]!!.toString().trim('"'))
        assertEquals("Use only the current saved stories.", body["instructions"]!!.toString().trim('"'))
        assertEquals(MemoryBookNarrativeForm.EXISTING, store.state.value.form)
    }

    @Test fun formAugmentsQueueInstructionsWithoutReplacingEditableBaseOrRecheckingPlan() = runTest {
        currentScopeValue = makeScope()
        val api = FakeApi()
        val store = setup(api, backgroundScope)
        val base = "Keep the family's original voices and chronology clear."
        assertTrue(store.updateInstructions(base))
        assertTrue(store.checkPlan())
        val savedPlan = store.state.value.plan

        assertTrue(store.chooseForm(MemoryBookNarrativeForm.CHRONICLE))
        assertEquals(base, store.state.value.instructions)
        assertEquals(MemoryBookNarrativeForm.CHRONICLE, store.state.value.form)
        assertSame(savedPlan, store.state.value.plan)
        assertEquals(MemoryBookNarrativeStatus.PLAN_READY, store.state.value.status)
        assertTrue(store.state.value.hasUnfinishedInput)
        assertEquals(1, api.planEditorialChoices.size)
        assertEquals(0, api.queueCalls)

        assertTrue(store.queue())
        val body = Json.parseToJsonElement(api.requestBodies.single()).jsonObject
        assertEquals("$base\n${MemoryBookNarrativeForm.CHRONICLE.instruction}",
            body["instructions"]!!.jsonPrimitive.content)
        assertEquals(base, store.state.value.instructions)
        assertEquals(MemoryBookNarrativeForm.CHRONICLE, store.state.value.form)
        assertFalse(store.state.value.hasUnfinishedInput)
    }

    @Test fun combinedUtf8LimitRejectsFormOrTextWithoutChangingPreviousFormAndText() = runTest {
        currentScopeValue = makeScope()
        val store = setup(FakeApi(), backgroundScope)
        val exactBase = "x".repeat(4096)
        assertTrue(store.updateInstructions(exactBase))
        assertFalse(store.chooseForm(MemoryBookNarrativeForm.CHRONICLE))
        assertEquals(exactBase, store.state.value.instructions)
        assertEquals(MemoryBookNarrativeForm.EXISTING, store.state.value.form)

        assertTrue(store.updateInstructions("Keep this smaller instruction."))
        assertTrue(store.chooseForm(MemoryBookNarrativeForm.ESSAY))
        val retainedText = store.state.value.instructions
        val retainedForm = store.state.value.form
        val formBytes = MemoryBookNarrativeForm.ESSAY.instruction!!.toByteArray(Charsets.UTF_8).size
        val overflow = "字".repeat((4096 - formBytes) / 3 + 1)
        assertFalse(store.updateInstructions(overflow))
        assertEquals(retainedText, store.state.value.instructions)
        assertEquals(retainedForm, store.state.value.form)
        assertTrue(store.state.value.hasUnfinishedInput)

        store.clear()
        assertEquals(MemoryBookNarrativeForm.EXISTING, store.state.value.form)
        assertEquals("", store.state.value.instructions)
        assertFalse(store.state.value.hasUnfinishedInput)
    }

    @Test fun oversizedAndViewOnlyPlansPreserveInstructionsAndNeverQueue() = runTest {
        for ((editorial, state, canEdit, expected) in listOf(
            listOf(true, "smaller_scope_required", true, MemoryBookNarrativeStatus.SMALLER_SCOPE),
            listOf(false, "within_limits", false, MemoryBookNarrativeStatus.VIEW_ONLY),
        )) {
            currentScopeValue = makeScope()
            val api = FakeApi()
            val plan = planJson(currentScopeValue!!, editorial as Boolean, state as String, canEdit as Boolean)
            api.planGate = CompletableDeferred(plan)
            val store = setup(api, backgroundScope)
            assertTrue(store.updateInstructions("Keep this draft instruction."))
            if (editorial as Boolean) assertTrue(store.chooseEditorialContext(true))
            assertTrue(store.checkPlan())
            assertEquals(expected, store.state.value.status)
            assertFalse(store.queue())
            assertEquals(0, api.queueCalls)
            assertEquals("Keep this draft instruction.", store.state.value.instructions)
            assertTrue(store.state.value.hasUnfinishedInput)
        }
    }

    @Test fun offlineRetryReusesExactFrozenRequestAndDoesNotResendAutomatically() = runTest {
        currentScopeValue = makeScope()
        val api = FakeApi().apply { nextQueueFailure = ApiFailure(FailureKind.OFFLINE) }
        val store = setup(api, backgroundScope)
        store.updateInstructions("Mention only details the family can confirm.")
        assertTrue(store.chooseForm(MemoryBookNarrativeForm.ESSAY))
        assertTrue(store.checkPlan())
        assertFalse(store.queue())
        val frozen = store.state.value.pendingRequest!!
        assertEquals("Mention only details the family can confirm.\n${MemoryBookNarrativeForm.ESSAY.instruction}", frozen.instructions)
        assertEquals(MemoryBookNarrativeStatus.RETRY_REQUIRED, store.state.value.status)
        assertEquals(MemoryBookNarrativeFailure.NETWORK, store.state.value.failure)
        assertTrue(store.state.value.hasUnfinishedInput)
        assertEquals(1, api.queueCalls)
        assertEquals(frozen, store.state.value.pendingRequest)
        assertFalse(store.chooseForm(MemoryBookNarrativeForm.LONG_MEMOIR))
        assertEquals(MemoryBookNarrativeForm.ESSAY, store.state.value.form)
        assertTrue(store.retry())
        assertEquals(2, api.queueCalls)
        assertEquals(api.requestBodies.first(), api.requestBodies.last())
        assertEquals(listOf(false, false), api.queueChoices)
        assertNull(store.state.value.pendingRequest)
        assertFalse(store.state.value.hasUnfinishedInput)
    }

    @Test fun conflictDropsFrozenRequestAndNeedsAnExplicitFreshPlan() = runTest {
        currentScopeValue = makeScope()
        val api = FakeApi().apply { nextQueueFailure = ApiFailure(FailureKind.HTTP, 409) }
        val store = setup(api, backgroundScope)
        assertTrue(store.updateInstructions("Keep the family wording tentative."))
        assertTrue(store.chooseForm(MemoryBookNarrativeForm.CHRONICLE))
        assertTrue(store.chooseEditorialContext(true))
        assertTrue(store.checkPlan())

        assertFalse(store.queue())
        assertNull(store.state.value.pendingRequest)
        assertNull(store.state.value.plan)
        assertEquals(MemoryBookNarrativeStatus.DRAFT_STALE, store.state.value.status)
        assertEquals(MemoryBookNarrativeFailure.SCOPE_CHANGED, store.state.value.failure)
        assertEquals("Keep the family wording tentative.", store.state.value.instructions)
        assertEquals(MemoryBookNarrativeForm.CHRONICLE, store.state.value.form)
        assertTrue(store.state.value.editorialContext)
        assertTrue(store.state.value.hasUnfinishedInput)
        assertFalse(store.retry())
        assertFalse(store.queue())
        assertEquals(1, api.queueCalls)

        assertTrue(store.checkPlan())
        assertTrue(store.queue())
        assertEquals(listOf(true, true), api.queueChoices)
        assertEquals(2, api.queueCalls)
    }

    @Test fun tooLargeQueueRejectionDiscardsRetryAndRequiresFreshPlan() = runTest {
        currentScopeValue = makeScope()
        val api = FakeApi().apply { nextQueueFailure = ApiFailure(FailureKind.HTTP, 422) }
        val store = setup(api, backgroundScope)
        assertTrue(store.updateInstructions("Use a shorter scope if needed."))
        assertTrue(store.chooseForm(MemoryBookNarrativeForm.LONG_MEMOIR))
        assertTrue(store.chooseEditorialContext(true))
        assertTrue(store.checkPlan())

        assertFalse(store.queue())
        assertNull(store.state.value.pendingRequest)
        assertNull(store.state.value.plan)
        assertEquals(MemoryBookNarrativeStatus.SMALLER_SCOPE, store.state.value.status)
        assertEquals(MemoryBookNarrativeFailure.TOO_LARGE, store.state.value.failure)
        assertEquals("Use a shorter scope if needed.", store.state.value.instructions)
        assertEquals(MemoryBookNarrativeForm.LONG_MEMOIR, store.state.value.form)
        assertTrue(store.state.value.editorialContext)
        assertTrue(store.state.value.hasUnfinishedInput)
        assertFalse(store.retry())
        assertFalse(store.queue())
        assertEquals(1, api.queueCalls)

        assertTrue(store.checkPlan())
        assertTrue(store.queue())
        assertEquals(listOf(true, true), api.queueChoices)
        assertEquals(2, api.queueCalls)
    }

    @Test fun reviewRejectsWrongMissingAndReorderedFlattenedChapterIds() = runTest {
        val malformed = listOf(
            listOf("${storyTwo}-chapter-1", "${storyOne}-chapter-1"),
            listOf("${storyOne}-chapter-1"),
            listOf("${storyOne}-chapter-1", "unknown-child-chapter-1"),
        )
        for (ids in malformed) {
            currentScopeValue = makeScope()
            val api = FakeApi()
            val store = setup(api, backgroundScope)
            store.updateInstructions("Review the order carefully.")
            assertTrue(store.checkPlan())
            assertTrue(store.queue())
            api.nextJobResponse = jobJson("ready", proposalJson(ids))
            assertFalse(store.refresh())
            assertNull(store.state.value.proposal)
            assertEquals(MemoryBookNarrativeStatus.DRAFT_FAILED, store.state.value.status)
            assertEquals(MemoryBookNarrativeFailure.INVALID_RESPONSE, store.state.value.failure)
        }
    }

    @Test fun latePlanReadIsDroppedOnBookRevisionChildOrAccountChange() = runTest {
        val replacements: List<(MemoryBookNarrativeScope) -> MemoryBookNarrativeScope> = listOf(
            { it.copy(bookRevision = it.bookRevision + 1, scopeId = it.scopeId + 1) },
            { it.copy(children = listOf(it.children[0].copy(revision = "5"), it.children[1]), scopeId = it.scopeId + 1) },
            { it.copy(accountId = "account-b", credential = bearer('b'), generation = it.generation + 1, scopeId = it.scopeId + 1) },
        )
        for (replace in replacements) {
            val original = makeScope()
            currentScopeValue = original
            val api = FakeApi().apply { planGate = CompletableDeferred() }
            val store = setup(api, backgroundScope)
            assertTrue(store.chooseForm(MemoryBookNarrativeForm.LONG_MEMOIR))
            assertTrue(store.state.value.hasUnfinishedInput)
            store.updateInstructions("Still private in this reader.")
            val pendingRead = async { store.checkPlan() }
            runCurrent()
            assertEquals(1, api.planEditorialChoices.size)
            currentScopeValue = replace(original)
            api.planGate!!.complete(planJson(original, editorial = false))
            runCurrent()
            assertTrue(pendingRead.isCancelled)
            assertNull(store.state.value.plan)
            assertNull(store.state.value.pendingRequest)
            assertNull(store.state.value.proposal)
            assertEquals("", store.state.value.instructions)
            assertEquals(MemoryBookNarrativeForm.EXISTING, store.state.value.form)
        }
    }

    @Test fun lateJobResultIsDroppedAfterOrderedChildRevisionChanges() = runTest {
        val original = makeScope()
        currentScopeValue = original
        val api = FakeApi()
        val store = setup(api, backgroundScope)
        assertTrue(store.updateInstructions("Keep the current sources in view."))
        assertTrue(store.checkPlan())
        assertTrue(store.queue())

        api.jobGate = CompletableDeferred()
        val refresh = async { store.refresh() }
        runCurrent()
        assertEquals(1, api.getJobCalls)
        currentScopeValue = original.copy(
            children = listOf(original.children[0], original.children[1].copy(revision = "5")),
            scopeId = original.scopeId + 1,
        )
        api.jobGate!!.complete(jobJson("ready", proposalJson(flattenedIds(original))))
        runCurrent()

        assertTrue(refresh.isCancelled)
        assertNull(store.state.value.proposal)
        assertNull(store.state.value.pendingRequest)
        assertEquals("", store.state.value.instructions)
        assertNull(store.state.value.job)
    }

    @Test fun explicitRefreshStaleResultHasNoReviewProposal() = runTest {
        currentScopeValue = makeScope()
        val api = FakeApi()
        val store = setup(api, backgroundScope)
        assertTrue(store.updateInstructions("Draft only from this saved revision."))
        assertTrue(store.chooseEditorialContext(true))
        assertTrue(store.checkPlan())
        assertTrue(store.queue())
        assertEquals(MemoryBookNarrativeStatus.QUEUED, store.state.value.status)

        api.nextJobResponse = jobJson("stale")
        assertTrue(store.refresh())
        assertEquals(MemoryBookNarrativeStatus.DRAFT_STALE, store.state.value.status)
        assertEquals(MemoryBookNarrativeFailure.SCOPE_CHANGED, store.state.value.failure)
        assertNull(store.state.value.proposal)
        assertNull(store.state.value.pendingRequest)
    }
}
