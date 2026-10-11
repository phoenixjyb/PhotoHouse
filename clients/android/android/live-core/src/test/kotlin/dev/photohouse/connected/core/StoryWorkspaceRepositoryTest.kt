package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class StoryWorkspaceRepositoryTest {
    private data class UpdateCall(val id: String, val json: String, val sourceReview: Boolean, val contributionReferences: Boolean)
    private val example = javaClass.classLoader!!.getResourceAsStream("story-workspace-contract/examples.json")!!.use {
        Json.parseToJsonElement(it.readBytes().toString(Charsets.UTF_8)).jsonObject
    }
    private fun token() = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private inner class Fake : StoryWorkspaceApi {
        val sent = mutableListOf<String>()
        val updates = mutableListOf<UpdateCall>()
        var error: ApiFailure? = null
        var after: (() -> Unit)? = null
        var buffer: ByteArray? = null
        private fun response(key: String): ByteArray {
            after?.invoke(); error?.let { throw it }
            return example.getValue(key).toString().toByteArray().also { buffer = it }
        }
        override suspend fun storyPreview(token: Bearer, library: String, json: String) = response("preview")
        override suspend fun storyTitleCapabilities(token: Bearer, library: String) = response("title_capabilities_off")
        override suspend fun storySourceCapabilities(token: Bearer, library: String): ByteArray {
            after?.invoke(); error?.let { throw it }
            return """{"version":1,"source_policy":"chapter_sources_v1","max_sources_per_chapter":12,"needs_review":true}""".toByteArray().also { buffer = it }
        }
        override suspend fun storyTitles(token: Bearer, library: String, json: String) = response("titles")
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray {
            sent += json; return response("created")
        }
        override suspend fun updateGroupedStory(
            token: Bearer, library: String, storyId: String, json: String,
            sourceReview: Boolean, contributionReferences: Boolean,
        ): ByteArray {
            updates += UpdateCall(storyId, json, sourceReview, contributionReferences)
            after?.invoke(); error?.let { throw it }
            val result = example.getValue("created").jsonObject.toMutableMap()
            result["revision"] = JsonPrimitive("5")
            if (sourceReview) result["source_policy"] = JsonPrimitive(ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1)
            return JsonObject(result).toString().toByteArray().also { buffer = it }
        }
    }
    @Test fun responseBuffersAreWipedAndExplicitReviewFreezesExactRetryBody() = runBlocking {
        val fake = Fake(); val binding = MemoryCommunityBinding(token(), "family-a", 1)
        val repo = StoryWorkspaceRepository(fake, { binding })
        val draft = repo.preview(listOf("102", "101"), "trip", "zh", "") { true }
        assertTrue(fake.buffer!!.all { it == 0.toByte() })
        try { repo.freeze(draft, draft.title, draft.chapters, "22222222-2222-4222-8222-222222222222", false) { true }; fail() }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
        val chapters = draft.chapters.toMutableList()
        val pending = repo.freeze(draft, draft.title, chapters, "22222222-2222-4222-8222-222222222222", true) { true }
        chapters.clear()
        assertFalse(pending.toString().contains(draft.title))
        fake.error = ApiFailure(FailureKind.OFFLINE)
        try { repo.save(pending) { true }; fail() } catch (_: ApiFailure) { }
        fake.error = null
        val saved = repo.save(pending) { true }
        assertEquals(1L, saved.revision)
        assertEquals(2, fake.sent.size)
        assertEquals(fake.sent[0], fake.sent[1])
        assertTrue(fake.buffer!!.all { it == 0.toByte() })
    }
    @Test fun staleSuccessAndStaleDenialCannotEnterNewSession() = runBlocking {
        val fake = Fake(); var binding: MemoryCommunityBinding? = MemoryCommunityBinding(token(), "family-a", 1)
        var denied = 0; val repo = StoryWorkspaceRepository(fake, { binding }, { denied++ })
        fake.after = { binding = MemoryCommunityBinding(token(), "family-a", 2) }
        try { repo.preview(listOf("102", "101"), "trip", "zh", "") { true }; fail() }
        catch (_: CancellationException) { }
        assertTrue(fake.buffer!!.all { it == 0.toByte() })
        fake.error = ApiFailure(FailureKind.HTTP, 401)
        try { repo.titleCapabilities { true }; fail() } catch (_: CancellationException) { }
        assertEquals(0, denied)
        fake.after = null
        try { repo.titleCapabilities { true }; fail() } catch (_: ApiFailure) { }
        assertEquals(1, denied)
    }
    @Test fun unknownOptionalCapabilityIsUnavailableWithoutAuthDenial() = runBlocking {
        val fake = Fake(); val binding = MemoryCommunityBinding(token(), "family-a", 1)
        var denied = 0
        val repo = StoryWorkspaceRepository(fake, { binding }, { denied++ })
        fake.error = ApiFailure(FailureKind.HTTP, 404)
        assertNull(repo.sourceCapabilities { true })
        assertEquals(0, denied)
        fake.error = ApiFailure(FailureKind.HTTP, 403)
        try { repo.sourceCapabilities { true }; fail() } catch (_: ApiFailure) { }
        assertEquals(1, denied)
        fake.error = ApiFailure(FailureKind.HTTP, 401)
        try { repo.sourceCapabilities { true }; fail() } catch (_: ApiFailure) { }
        assertEquals(2, denied)
    }
    @Test fun pendingSaveCannotBeRetriedInAnotherLibraryOrGeneration() = runBlocking {
        val fake = Fake(); var binding: MemoryCommunityBinding? = MemoryCommunityBinding(token(), "family-a", 1)
        val repo = StoryWorkspaceRepository(fake, { binding })
        val draft = repo.preview(listOf("102", "101"), "trip", "zh", "") { true }
        val pending = repo.freeze(draft, draft.title, draft.chapters, "22222222-2222-4222-8222-222222222222", true) { true }
        binding = binding!!.copy(generation = 2)
        try { repo.save(pending) { true }; fail() } catch (_: CancellationException) { }
        assertTrue(fake.sent.isEmpty())
    }

    @Test fun fullUpdateFreezesProfileRevisionAndCompleteLinksAcrossRetry() = runBlocking {
        val fake = Fake(); val binding = MemoryCommunityBinding(token(), "family-a", 1)
        val repo = StoryWorkspaceRepository(fake, { binding })
        val initial = ProtectedMemoryStoriesWire.decode(example.getValue("created").toString().toByteArray(),
            "family-a", listOf("102", "101")).copy(revision = 4,
            sourcePolicy = ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1)
        val contributionIds = mutableListOf("44444444-4444-4444-8444-444444444444")
        val referenceGroups = mutableListOf(SavedMemoryChapterContributionReferences("chapter-1", contributionIds))
        val references = SavedMemoryStoryContributionReferences(initial.id, initial.libraryId, initial.revision, referenceGroups)
        val edits = initial.chapters.map { it.copy(narration = "Changed family words") }
        val pending = repo.freezeUpdate(initial, references, "Edited title", edits,
            "22222222-2222-4222-8222-222222222222", reviewed = true, sourceReview = true,
            sourcePolicy = ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1) { true }
        contributionIds.clear(); referenceGroups.clear()
        assertEquals(initial.id, pending.targetStoryId)
        assertEquals(4L, pending.baseRevision)
        assertTrue(pending.sourceReview)
        assertTrue(pending.contributionReferences)
        val frozenBody = pending.body
        val body = Json.parseToJsonElement(frozenBody).jsonObject
        assertEquals("4", body.getValue("revision").jsonPrimitive.content)
        assertEquals("Edited title", body.getValue("title").jsonPrimitive.content)
        assertEquals("chapter_sources_v1", body.getValue("source_policy").jsonPrimitive.content)
        assertTrue(body.getValue("chapters").jsonPrimitive.content.contains("Changed family words"))
        assertEquals("[{\"chapter_id\":\"chapter-1\",\"contribution_ids\":[\"44444444-4444-4444-8444-444444444444\"]}]",
            body.getValue("contribution_refs").jsonPrimitive.content)

        fake.error = ApiFailure(FailureKind.OFFLINE)
        try { repo.save(pending) { true }; fail() } catch (_: ApiFailure) { }
        fake.error = null
        val updated = repo.save(pending) { true }
        assertEquals(initial.id, updated.id)
        assertEquals(5L, updated.revision)
        assertEquals(2, fake.updates.size)
        assertEquals(fake.updates.first(), fake.updates.last())
        assertEquals(initial.id, fake.updates.first().id)
        assertTrue(fake.buffer!!.all { it == 0.toByte() })
    }

    @Test fun updateFreezeRejectsWrongStoryRevisionLinksOrUnreviewedInput() {
        val initial = ProtectedMemoryStoriesWire.decode(example.getValue("created").toString().toByteArray(),
            "family-a", listOf("102", "101")).copy(revision = 4,
            sourcePolicy = ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1)
        val refs = SavedMemoryStoryContributionReferences(initial.id, initial.libraryId, 4,
            listOf(SavedMemoryChapterContributionReferences("chapter-1", emptyList())))
        val binding = MemoryCommunityBinding(token(), "family-a", 1)
        val repo = StoryWorkspaceRepository(Fake(), { binding })
        fun freeze(story: SavedMemoryStory = initial, references: SavedMemoryStoryContributionReferences = refs,
                   reviewed: Boolean = true) = repo.freezeUpdate(story, references, "Edited title", story.chapters,
            "22222222-2222-4222-8222-222222222222", reviewed, true,
            ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1) { true }
        try { freeze(references = refs.copy(revision = 3)); fail() } catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
        try { freeze(story = initial.copy(revision = Long.MAX_VALUE),
            references = refs.copy(revision = Long.MAX_VALUE)); fail() }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
        try { freeze(story = initial.copy(canEdit = false)); fail() } catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
        try { freeze(reviewed = false); fail() } catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
    }
}
