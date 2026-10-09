package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class StoryWorkspaceRepositoryTest {
    private val example = javaClass.classLoader!!.getResourceAsStream("story-workspace-contract/examples.json")!!.use {
        Json.parseToJsonElement(it.readBytes().toString(Charsets.UTF_8)).jsonObject
    }
    private fun token() = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private inner class Fake : StoryWorkspaceApi {
        val sent = mutableListOf<String>()
        var error: ApiFailure? = null
        var after: (() -> Unit)? = null
        var buffer: ByteArray? = null
        private fun response(key: String): ByteArray {
            after?.invoke(); error?.let { throw it }
            return example.getValue(key).toString().toByteArray().also { buffer = it }
        }
        override suspend fun storyPreview(token: Bearer, library: String, json: String) = response("preview")
        override suspend fun storyTitleCapabilities(token: Bearer, library: String) = response("title_capabilities_off")
        override suspend fun storyTitles(token: Bearer, library: String, json: String) = response("titles")
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray {
            sent += json; return response("created")
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
    @Test fun pendingSaveCannotBeRetriedInAnotherLibraryOrGeneration() = runBlocking {
        val fake = Fake(); var binding: MemoryCommunityBinding? = MemoryCommunityBinding(token(), "family-a", 1)
        val repo = StoryWorkspaceRepository(fake, { binding })
        val draft = repo.preview(listOf("102", "101"), "trip", "zh", "") { true }
        val pending = repo.freeze(draft, draft.title, draft.chapters, "22222222-2222-4222-8222-222222222222", true) { true }
        binding = binding!!.copy(generation = 2)
        try { repo.save(pending) { true }; fail() } catch (_: CancellationException) { }
        assertTrue(fake.sent.isEmpty())
    }
}
