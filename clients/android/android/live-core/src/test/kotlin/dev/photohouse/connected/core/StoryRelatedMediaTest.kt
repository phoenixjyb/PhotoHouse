package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class StoryRelatedMediaTest {
    private fun binding(generation: Long = 1, library: String = "family-a") = MemoryCommunityBinding(
        Bearer.from(SessionToken(86400, "a".repeat(43), "Bearer")), library, generation)

    private fun item(id: String, takenAt: String = "2026-01-02T23:30:00-05:00", kind: String = "image") =
        """{"id":"$id","kind":"$kind","width":640,"height":480,"duration_sec":${if (kind == "video") "3.5" else "null"},"taken_at":"$takenAt","thumbnail_url":"/assets/$id/thumbnail?library=family-a","match_reason":"same_recorded_capture_day"}"""

    private fun response(
        library: String = "family-a", seeds: String = "\"102\",\"101\"", days: String = "\"2026-01-02\"",
        items: String = item("204"), hasMore: Boolean = false, cursor: String = "null",
    ) = """{"version":1,"library_id":"$library","seed_asset_ids":[$seeds],"recorded_days":[$days],"needs_review":true,"has_more":$hasMore,"next_before_id":$cursor,"items":[$items]}""".toByteArray()

    private inner class Api : StoryWorkspaceApi {
        val requests = mutableListOf<String>()
        val replies = ArrayDeque<ByteArray>()
        var failure: ApiFailure? = null
        var gate: CompletableDeferred<Unit>? = null
        var responseBuffer: ByteArray? = null
        override suspend fun storyPreview(token: Bearer, library: String, json: String) = error("unused")
        override suspend fun storyTitleCapabilities(token: Bearer, library: String) = error("unused")
        override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("unused")
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String) = error("unused")
        override suspend fun relatedStoryMedia(token: Bearer, library: String, json: String): ByteArray {
            requests += json
            gate?.let { withContext(NonCancellable) { it.await() } }
            failure?.let { throw it }
            return replies.removeFirst().also { responseBuffer = it }
        }
    }

    @Test fun decoderAcceptsWrittenOffsetDayAndRejectsForeignScopeMalformedDateAndDuplicateKeys() {
        val page = StoryRelatedMediaWire.decode(response(), "family-a", listOf("102", "101"), null)
        assertEquals("2026-01-02", page.recordedDays.single())
        assertEquals("204", page.items.single().asset.id)
        assertEquals("2026-01-02T23:30:00-05:00", page.items.single().asset.taken_at)
        val acceptedTimeShapes = listOf("2026-01-03", "2026-01-03T12:45", "2026-01-03 12:45:12.123456+0530")
        acceptedTimeShapes.forEach { stamp ->
            assertEquals("204", StoryRelatedMediaWire.decode(response(days = "\"${stamp.take(10)}\"", items = item("204", stamp)), "family-a", listOf("102", "101"), null).items.single().asset.id)
        }
        val malformed = listOf(
            response(library = "family-b"),
            response(seeds = "\"101\",\"102\""),
            response(days = "\"0000-01-01\"", items = item("204", "0000-01-01")),
            response(days = "\"2026-02-30\"", items = item("204", "2026-02-30T12:00:00Z")),
            response(items = item("101")),
            response().decodeToString().replace("\"version\":1", "\"version\":1,\"version\":1").toByteArray(),
            response().decodeToString().replace("\"items\":[", "\"unexpected\":true,\"items\":[").toByteArray(),
            response().decodeToString().replace("2026-01-02T23:30:00-05:00", "2026-01-02T23:30:00+25:00").toByteArray(),
            response().decodeToString().replace("2026-01-02T23:30:00-05:00", "2026-01-02T24:00:00Z").toByteArray(),
            response().decodeToString().replace("\"id\":\"204\"", "\"id\":\"\\ud800\"").toByteArray(),
            ByteArray(256 * 1024 + 1) { if (it == 0) '{'.code.toByte() else ' '.code.toByte() },
            ByteArray(16) { '['.code.toByte() } + "0".toByteArray() + ByteArray(16) { ']'.code.toByte() },
            response(days = "", items = item("204")),
            response(items = (221 downTo 201).joinToString(",") { item(it.toString()) }),
        )
        malformed.forEach { bytes ->
            try { StoryRelatedMediaWire.decode(bytes, "family-a", listOf("102", "101"), null); fail("accepted malformed response") }
            catch (failure: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, failure.kind) }
        }
    }

    @Test fun decoderRequiresExactDescendingCursorProgressionAndBoundedShape() {
        val paged = StoryRelatedMediaWire.decode(response(items = "${item("204")},${item("203", kind = "video")}",
            hasMore = true, cursor = "\"203\""), "family-a", listOf("102", "101"), null)
        assertEquals("203", paged.nextBeforeId)
        val finalPage = StoryRelatedMediaWire.decode(response(items = item("202"), cursor = "null"),
            "family-a", listOf("102", "101"), "203")
        assertFalse(finalPage.hasMore)
        val badPages = listOf(
            response(items = "${item("204")},${item("205")}"),
            response(items = item("204"), hasMore = true, cursor = "\"205\""),
            response(items = item("204"), hasMore = true, cursor = "\"203\"").also { },
        )
        badPages.forEachIndexed { index, bytes ->
            val before = if (index == 2) "203" else null
            try { StoryRelatedMediaWire.decode(bytes, "family-a", listOf("102", "101"), before); fail("accepted invalid page") }
            catch (failure: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, failure.kind) }
        }
    }

    @Test fun repositoryOwnsAndWipesResponseAndPreservesOrderedSeedCursor() = runTest {
        val api = Api().apply { replies.add(response(hasMore = true, cursor = "\"204\"")) }
        val current = binding()
        val repo = StoryWorkspaceRepository(api, { current })
        val page = repo.relatedMedia(listOf("102", "101"), null) { true }
        assertEquals(listOf("102", "101"), page.seedAssetIds)
        assertTrue(api.responseBuffer!!.all { it == 0.toByte() })
        val sent = kotlinx.serialization.json.Json.parseToJsonElement(api.requests.single()).jsonObject
        assertEquals("102,101", sent.getValue("asset_ids").jsonPrimitive.content)
        assertEquals("", sent.getValue("before_id").jsonPrimitive.content)
    }

    @Test fun storeLookupIsExplicitPagedOrderedAndFailurePreservesSelection() = runTest {
        var current = binding()
        val api = Api().apply {
            replies.add(response(hasMore = true, cursor = "\"204\""))
        }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, { current }), this, { current })
        assertTrue(store.selectAsset("102")); assertTrue(store.selectAsset("101"))
        assertTrue(api.requests.isEmpty())
        assertTrue(store.loadRelatedMedia()); runCurrent()
        assertEquals(listOf("102", "101"), store.state.value.selectedAssetIds)
        assertEquals(listOf("204"), store.state.value.relatedCandidates.map { it.asset.id })
        assertTrue(store.state.value.relatedHasMore)
        api.failure = ApiFailure(FailureKind.OFFLINE)
        assertTrue(store.loadRelatedMedia(nextPage = true)); runCurrent()
        assertTrue(store.state.value.relatedFailure)
        assertEquals(listOf("204"), store.state.value.relatedCandidates.map { it.asset.id })
        assertEquals("204", kotlinx.serialization.json.Json.parseToJsonElement(api.requests.last()).jsonObject
            .getValue("before_id").jsonPrimitive.content)
        api.failure = null
        api.replies.add(response(items = item("202")))
        assertTrue(store.retryRelatedMedia()); runCurrent()
        assertEquals(listOf("202"), store.state.value.relatedCandidates.map { it.asset.id })
        assertFalse(store.state.value.relatedFailure)
        assertEquals(listOf("102", "101"), store.state.value.selectedAssetIds)
        assertEquals(StoryWorkspaceStoreStatus.SELECTION, store.state.value.status)
    }

    @Test fun selectionChangeDiscardsLateLookupAndClearsPreviews() = runTest {
        var current = binding()
        val gate = CompletableDeferred<Unit>()
        val api = Api().apply { replies.add(response(seeds = "\"101\"")); this.gate = gate }
        val previewClears = mutableListOf<List<String>>()
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, { current }), this, { current }).also {
            it.observeRelatedCandidates { candidates -> previewClears += candidates.map { candidate -> candidate.asset.id } }
        }
        assertTrue(store.selectAsset("101")); assertTrue(store.loadRelatedMedia()); runCurrent()
        assertTrue(store.selectAsset("102"))
        gate.complete(Unit); runCurrent()
        assertEquals(listOf("101", "102"), store.state.value.selectedAssetIds)
        assertTrue(store.state.value.relatedCandidates.isEmpty())
        assertTrue(previewClears.any { it.isEmpty() })
    }

    @Test fun explicitCandidateInclusionAppendsInOrderAndInvalidatesSuggestions() = runTest {
        val current = binding()
        val api = Api().apply { replies.add(response(seeds = "\"101\"")) }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, { current }), this, { current })
        assertTrue(store.selectAsset("101"))
        assertTrue(store.loadRelatedMedia()); runCurrent()
        assertEquals(listOf("204"), store.state.value.relatedCandidates.map { it.asset.id })
        assertTrue(store.selectAsset("204"))
        assertEquals(listOf("101", "204"), store.state.value.selectedAssetIds)
        assertTrue(store.state.value.relatedCandidates.isEmpty())
        assertFalse(store.state.value.relatedHasMore)
    }

    @Test fun libraryChangeDiscardsLateLookupAndClearsSelection() = runTest {
        var current = binding()
        val gate = CompletableDeferred<Unit>()
        val api = Api().apply { replies.add(response(seeds = "\"101\"")); this.gate = gate }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, { current }), this, { current })
        assertTrue(store.selectAsset("101")); assertTrue(store.loadRelatedMedia()); runCurrent()
        current = binding(library = "family-b")
        gate.complete(Unit); runCurrent()
        assertTrue(store.state.value.selectedAssetIds.isEmpty())
        assertTrue(store.state.value.relatedCandidates.isEmpty())
    }

    @Test fun accountChangeAndMembershipLossDiscardLateLookup() = runTest {
        var current: MemoryCommunityBinding? = binding()
        val gate = CompletableDeferred<Unit>()
        val api = Api().apply { replies.add(response(seeds = "\"101\"")); this.gate = gate }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, { current }), this, { current })
        assertTrue(store.selectAsset("101")); assertTrue(store.loadRelatedMedia()); runCurrent()
        current = binding() // A new token object fences the response even in the same library/generation.
        gate.complete(Unit); runCurrent()
        assertTrue(store.state.value.selectedAssetIds.isEmpty())
        assertTrue(store.state.value.relatedCandidates.isEmpty())

        val secondGate = CompletableDeferred<Unit>()
        val secondApi = Api().apply { replies.add(response(seeds = "\"101\"")); this.gate = secondGate }
        current = binding()
        val secondStore = StoryWorkspaceStore(StoryWorkspaceRepository(secondApi, { current }), this, { current })
        assertTrue(secondStore.selectAsset("101")); assertTrue(secondStore.loadRelatedMedia()); runCurrent()
        current = null // Membership revocation removes the binding.
        secondGate.complete(Unit); runCurrent()
        assertTrue(secondStore.state.value.selectedAssetIds.isEmpty())
        assertTrue(secondStore.state.value.relatedCandidates.isEmpty())
    }

    @Test fun editorCloseFencesLateResponseAndClearsRelatedState() = runTest {
        val current = binding()
        val gate = CompletableDeferred<Unit>()
        val api = Api().apply { replies.add(response(seeds = "\"101\"")); this.gate = gate }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, { current }), this, { current })
        assertTrue(store.selectAsset("101")); assertTrue(store.loadRelatedMedia()); runCurrent()
        assertTrue(store.close(discard = true))
        gate.complete(Unit); runCurrent()
        assertTrue(store.state.value.selectedAssetIds.isEmpty())
        assertTrue(store.state.value.relatedCandidates.isEmpty())
        assertFalse(store.state.value.relatedBusy)
    }

    @Test fun deniedLookupCallsOwnerHandlerAndPreservesFailureStatus() = runTest {
        var denials = 0
        val api = object : StoryWorkspaceApi {
            override suspend fun storyPreview(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun storyTitleCapabilities(token: Bearer, library: String) = error("unused")
            override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun relatedStoryMedia(token: Bearer, library: String, json: String): ByteArray {
                throw ApiFailure(FailureKind.HTTP, 403)
            }
        }
        val current = binding()
        val repo = StoryWorkspaceRepository(api, { current }, onDenied = { denials++ })
        try { repo.relatedMedia(listOf("101"), null) { true }; fail() }
        catch (failure: ApiFailure) { assertEquals(403, failure.status) }
        assertEquals(1, denials)
    }
}
