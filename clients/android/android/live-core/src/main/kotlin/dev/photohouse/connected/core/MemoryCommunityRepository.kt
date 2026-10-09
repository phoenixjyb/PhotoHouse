package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import java.util.UUID

/** The current protected identity/library binding supplied by the owning session store. */
data class MemoryCommunityBinding(val token: Bearer, val libraryId: String, val generation: Long)

/**
 * Narrow v1 transport seam. Implementations must use authenticated HTTPS, no redirects, and enforce
 * [MemoryCommunityResponseLimits.JSON_BYTES] for JSON and [MemoryCommunityResponseLimits.WAV_BYTES]
 * for WAV while reading the response stream (before constructing a complete body buffer).
 */
interface MemoryCommunityApi {
    suspend fun capabilities(token: Bearer, library: String): ByteArray = unsupported()
    suspend fun listContributions(token: Bearer, library: String, storyId: String, page: Int): ByteArray = unsupported()
    suspend fun getContribution(token: Bearer, library: String, storyId: String, contributionId: String): ByteArray = unsupported()
    suspend fun createTextContribution(token: Bearer, library: String, storyId: String, json: String): ByteArray = unsupported()
    suspend fun createAudioContribution(token: Bearer, library: String, storyId: String,
                                        metadataBase64: String, wav: ByteArray): ByteArray = unsupported()
    suspend fun contributionAudio(token: Bearer, library: String, storyId: String, contributionId: String): ByteArray = unsupported()
    suspend fun reviewContribution(token: Bearer, library: String, storyId: String, contributionId: String,
                                   json: String): ByteArray = unsupported()
    suspend fun deleteContribution(token: Bearer, library: String, storyId: String, contributionId: String): ByteArray = unsupported()
    suspend fun listBooks(token: Bearer, library: String, page: Int): ByteArray = unsupported()
    suspend fun getBook(token: Bearer, library: String, bookId: String): ByteArray = unsupported()
    suspend fun saveBook(token: Bearer, library: String, bookId: String?, json: String): ByteArray = unsupported()
    suspend fun startConversation(token: Bearer, library: String, json: String): ByteArray = unsupported()
    suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String): ByteArray = unsupported()
    /** Optional metadata route; older fakes and adapters continue to provide the legacy response. */
    suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String): ByteArray =
        listConversations(token, library, targetType, targetId)
    suspend fun conversationTurns(token: Bearer, library: String, conversationId: String, page: Int): ByteArray = unsupported()
    suspend fun conversationTurnsWithReplyContext(token: Bearer, library: String, conversationId: String, page: Int): ByteArray =
        conversationTurns(token, library, conversationId, page)
    suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String): ByteArray = unsupported()
    /** Old adapters keep their exact request path; unsupported adapters fail closed on opt-in. */
    suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String,
                         editorialContext: Boolean): ByteArray =
        if (editorialContext) unsupported() else sendTurn(token, library, conversationId, json)
    suspend fun closeConversation(token: Bearer, library: String, conversationId: String): ByteArray = unsupported()
    suspend fun queueNarrative(token: Bearer, library: String, json: String): ByteArray = unsupported()
    /** Old adapters keep their exact request path; unsupported adapters fail closed on opt-in. */
    suspend fun queueNarrative(token: Bearer, library: String, json: String,
                               editorialContext: Boolean): ByteArray =
        if (editorialContext) unsupported() else queueNarrative(token, library, json)
    suspend fun bookPlan(token: Bearer, library: String, bookId: String): ByteArray = unsupported()
    /** New opt-in remains explicit even for adapters which only implement the legacy overload. */
    suspend fun bookPlan(token: Bearer, library: String, bookId: String,
                         editorialContext: Boolean): ByteArray =
        if (editorialContext) unsupported() else bookPlan(token, library, bookId)
    suspend fun getJob(token: Bearer, library: String, jobId: String): ByteArray = unsupported()
    suspend fun cancelJob(token: Bearer, library: String, jobId: String): ByteArray = unsupported()

    private fun unsupported(): Nothing = throw ApiFailure(FailureKind.INVALID_INPUT)
}

/**
 * Ephemeral, scope-bound coordinator for protected memory endpoints. It stores no drafts,
 * transcripts, WAVs, pages or job results; the owner can keep returned values in its transient UI.
 * Every network result is dropped if the session/library generation changed while awaiting it.
 */
class MemoryCommunityRepository(
    private val api: MemoryCommunityApi,
    private val currentBinding: () -> MemoryCommunityBinding?,
    private val onDenied: () -> Unit = {},
) {
    private data class BindingKey(val token: Bearer, val library: String, val generation: Long)
    private data class CapabilityCache(val key: BindingKey, val value: MemoryCommunityCapabilities)
    @Volatile private var capabilityCache: CapabilityCache? = null

    private fun binding(): MemoryCommunityBinding {
        val value = currentBinding() ?: throw CancellationException("Protected scope ended")
        require(PhoneDiscoveryWire.validLibrary(value.libraryId) && value.generation >= 0)
        return value
    }

    private fun current(expected: MemoryCommunityBinding) {
        val actual = currentBinding()
        if (actual == null || actual.token !== expected.token || actual.libraryId != expected.libraryId ||
            actual.generation != expected.generation) throw CancellationException("Protected scope changed")
    }

    /** Response bytes are private-data buffers owned by this repository and are wiped after parsing. */
    private suspend fun <T> parseOwned(response: suspend () -> ByteArray, parse: (ByteArray) -> T): T {
        val bytes = response()
        try { return parse(bytes) } finally { bytes.fill(0) }
    }

    private suspend fun <T> withBinding(
        currentRequest: (() -> Boolean)? = null,
        block: suspend (MemoryCommunityBinding) -> T,
    ): T {
        val expected = binding()
        return try {
            val result = block(expected)
            try {
                current(expected)
            } catch (e: CancellationException) {
                when (result) {
                    is ProtectedAnnotationAudio -> result.close()
                    is ByteArray -> result.fill(0)
                }
                throw e
            }
            result
        } catch (e: CancellationException) {
            throw e
        } catch (e: ApiFailure) {
            if (e.status in setOf(401, 403) && runCatching { current(expected) }.isSuccess) {
                if (currentRequest == null) onDenied()
                else if (runCatching(currentRequest).getOrDefault(false)) {
                    // A current reader owns its denial handling; let it route the failure
                    // through the existing protected readFailure path.
                } else throw CancellationException("Protected reader request changed")
            }
            throw e
        } catch (_: IllegalArgumentException) {
            throw ApiFailure(FailureKind.INVALID_INPUT)
        } catch (_: Exception) {
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        }
    }

    suspend fun loadCapabilities(): MemoryCommunityCapabilities = withBinding { scope ->
        val value = parseOwned({ api.capabilities(scope.token, scope.libraryId) }, ProtectedMemoryCommunityWire::capabilities)
        current(scope)
        capabilityCache = CapabilityCache(BindingKey(scope.token, scope.libraryId, scope.generation), value)
        value
    }

    fun clear() { capabilityCache = null }

    private fun capabilities(scope: MemoryCommunityBinding, feature: Feature): MemoryCommunityCapabilities {
        val cache = capabilityCache
        if (cache?.key != BindingKey(scope.token, scope.libraryId, scope.generation)) throw ApiFailure(FailureKind.INVALID_INPUT)
        val found = cache.value
        if (!found.enabled || feature == Feature.CONTRIBUTIONS && !found.contributionsEnabled ||
            feature == Feature.GENERATION && !found.generationEnabled) throw ApiFailure(FailureKind.HTTP, 503)
        return found
    }
    private enum class Feature { COLLABORATION, CONTRIBUTIONS, GENERATION }

    suspend fun contributions(storyId: String, page: Int = 1): MemoryContributionPage = withBinding { s ->
        capabilities(s, Feature.CONTRIBUTIONS)
        requireUuid(storyId); require(page in 1..100000)
        parseOwned({ api.listContributions(s.token, s.libraryId, storyId, page) }) { ProtectedMemoryCommunityWire.contributionPage(it, storyId, page) }
    }

    suspend fun contribution(storyId: String, contributionId: String): MemoryContributionDetail = withBinding { s ->
        capabilities(s, Feature.CONTRIBUTIONS)
        requireUuid(storyId); requireUuid(contributionId)
        parseOwned({ api.getContribution(s.token, s.libraryId, storyId, contributionId) }) {
            ProtectedMemoryCommunityWire.contributionDetail(it, storyId, contributionId)
        }
    }

    suspend fun submitText(storyId: String, submission: MemoryContributionRequest): MemoryContributionReceipt = withBinding { s ->
        capabilities(s, Feature.CONTRIBUTIONS)
        requireUuid(storyId)
        val body = ProtectedMemoryCommunityWire.textRequest(submission)
        parseOwned({ api.createTextContribution(s.token, s.libraryId, storyId, body) }) {
            ProtectedMemoryCommunityWire.contributionReceipt(it, storyId).also { receipt -> verifyReceipt(receipt, submission, null) }
        }
    }

    /** Takes ownership of [wav], validates and sends a private copy, then wipes both owned buffers. */
    suspend fun submitAudio(storyId: String, submission: MemoryContributionRequest, wav: ByteArray): MemoryContributionReceipt {
        val owned = try { wav.copyOf() } finally { wav.fill(0) }
        try {
            return withBinding { s ->
                val caps = capabilities(s, Feature.CONTRIBUTIONS)
                requireUuid(storyId)
                require(ProtectedMemoryCommunityWire.validWav(owned, caps.maxAudioSeconds))
                val metadata = ProtectedMemoryCommunityWire.audioMetadata(submission, caps)
                val digest = java.security.MessageDigest.getInstance("SHA-256").digest(owned)
                    .joinToString("") { "%02x".format(it) }
                parseOwned({ api.createAudioContribution(s.token, s.libraryId, storyId, metadata, owned) }) { ProtectedMemoryCommunityWire.contributionReceipt(it, storyId) }
                    .also { verifyReceipt(it, submission, digest) }
            }
        } finally {
            owned.fill(0)
        }
    }

    /** Audio is returned in a wipe-on-close holder, never in a persistent cache. */
    suspend fun contributionAudio(storyId: String, contributionId: String): ProtectedAnnotationAudio = withBinding { s ->
        val caps = capabilities(s, Feature.CONTRIBUTIONS)
        requireUuid(storyId); requireUuid(contributionId)
        val response = api.contributionAudio(s.token, s.libraryId, storyId, contributionId)
        try {
            require(ProtectedMemoryCommunityWire.validWav(response, caps.maxAudioSeconds))
            ProtectedAnnotationAudio(response.copyOf())
        } finally {
            response.fill(0)
        }
    }

    suspend fun reviewContribution(storyId: String, contributionId: String, accepted: Boolean,
                                   revision: Long): MemoryContributionReceipt = withBinding { s ->
        capabilities(s, Feature.CONTRIBUTIONS)
        requireUuid(storyId); requireUuid(contributionId)
        val body = ProtectedMemoryCommunityWire.reviewRequest(accepted, revision)
        parseOwned({ api.reviewContribution(s.token, s.libraryId, storyId, contributionId, body) }) { ProtectedMemoryCommunityWire.contributionReceipt(it, storyId) }
    }

    suspend fun deleteContribution(storyId: String, contributionId: String): Unit = withBinding { s ->
        capabilities(s, Feature.CONTRIBUTIONS)
        requireUuid(storyId); requireUuid(contributionId)
        parseOwned({ api.deleteContribution(s.token, s.libraryId, storyId, contributionId) }) { ProtectedMemoryCommunityWire.deleted(it, contributionId) }
    }

    suspend fun books(page: Int = 1): MemoryBookPage = withBinding { s ->
        capabilities(s, Feature.COLLABORATION); require(page in 1..100000)
        parseOwned({ api.listBooks(s.token, s.libraryId, page) }) { ProtectedMemoryCommunityWire.bookPage(it, s.libraryId, page) }
    }

    suspend fun book(bookId: String, expectedRevision: Long = 1): MemoryBook = withBinding { s ->
        capabilities(s, Feature.COLLABORATION); requireUuid(bookId); require(expectedRevision > 0)
        parseOwned({ api.getBook(s.token, s.libraryId, bookId) }) { ProtectedMemoryCommunityWire.bookDetail(it, bookId, expectedRevision) }
    }

    /** Retries must pass the original mutation object unchanged; each revision is an explicit CAS. */
    suspend fun saveBook(bookId: String?, mutation: MemoryBookMutation): MemoryBook = withBinding { s ->
        capabilities(s, Feature.COLLABORATION)
        if (bookId != null) requireUuid(bookId)
        require((bookId == null) == (mutation.revision == 0L))
        val body = ProtectedMemoryCommunityWire.bookRequest(mutation)
        parseOwned({ api.saveBook(s.token, s.libraryId, bookId, body) }) { ProtectedMemoryCommunityWire.bookDetail(it,
            bookId, if (bookId == null) 1 else mutation.revision + 1) }
    }

    suspend fun startConversation(conversationRequest: MemoryConversationRequest): MemoryConversation = withBinding { s ->
        capabilities(s, Feature.GENERATION)
        require(conversationRequest.targetType in setOf("story", "book")); requireUuid(conversationRequest.targetId); requireUuid(conversationRequest.id)
        val json = ProtectedMemoryCommunityWire.conversationRequest(conversationRequest)
        parseOwned({ api.startConversation(s.token, s.libraryId, json) }) { ProtectedMemoryCommunityWire.conversation(it, conversationRequest) }
    }

    suspend fun conversations(
        targetType: String,
        targetId: String,
        withPreview: Boolean = false,
        currentRequest: (() -> Boolean)? = null,
    ): MemoryConversationPage = withBinding(currentRequest) { s ->
        capabilities(s, Feature.COLLABORATION); require(targetType in setOf("story", "book")); requireUuid(targetId)
        currentCoroutineContext().ensureActive()
        if (currentRequest != null && !runCatching(currentRequest).getOrDefault(false)) {
            throw CancellationException("Conversation reader changed")
        }
        current(s)
        val response = if (!withPreview) {
            api.listConversations(s.token, s.libraryId, targetType, targetId)
        } else try {
            api.listConversationsWithPreview(s.token, s.libraryId, targetType, targetId)
        } catch (failure: ApiFailure) {
            if (failure.status != 400 || currentRequest == null) throw failure
            currentCoroutineContext().ensureActive()
            if (!runCatching(currentRequest).getOrDefault(false)) throw CancellationException("Conversation reader changed")
            // Both the bound account/library generation and the originating reader must still own this fallback.
            current(s)
            if (!runCatching(currentRequest).getOrDefault(false)) throw CancellationException("Conversation reader changed")
            api.listConversations(s.token, s.libraryId, targetType, targetId)
        }
        parseOwned({ response }, ProtectedMemoryCommunityWire::conversations)
    }

    suspend fun turns(
        conversationId: String, page: Int = 1, replyContext: Boolean = false,
        currentRequest: (() -> Boolean)? = null,
    ): MemoryTurnPage = withBinding(currentRequest) { s ->
        capabilities(s, Feature.COLLABORATION); requireUuid(conversationId); require(page in 1..100000)
        currentCoroutineContext().ensureActive()
        if (currentRequest != null && !runCatching(currentRequest).getOrDefault(false)) {
            throw CancellationException("Conversation reader changed")
        }
        current(s)
        parseOwned({
            if (replyContext) api.conversationTurnsWithReplyContext(s.token, s.libraryId, conversationId, page)
            else api.conversationTurns(s.token, s.libraryId, conversationId, page)
        }) { ProtectedMemoryCommunityWire.turns(it, conversationId, page) }
    }

    suspend fun sendTurn(conversationId: String, turn: MemoryTurnRequest): MemoryJob = withBinding { s ->
        capabilities(s, Feature.GENERATION); requireUuid(conversationId)
        parseOwned({ api.sendTurn(s.token, s.libraryId, conversationId,
            ProtectedMemoryCommunityWire.turnRequest(turn), turn.editorialContext) }, ProtectedMemoryCommunityWire::job)
    }

    suspend fun closeConversation(conversationId: String) = withBinding { s ->
        capabilities(s, Feature.COLLABORATION); requireUuid(conversationId)
        parseOwned({ api.closeConversation(s.token, s.libraryId, conversationId) }, ProtectedMemoryCommunityWire::deletedConversation)
    }

    suspend fun queueNarrative(narrativeRequest: MemoryNarrativeRequest): MemoryJob = withBinding { s ->
        capabilities(s, Feature.GENERATION)
        require(!narrativeRequest.editorialContext || narrativeRequest.targetType == "book")
        val json = ProtectedMemoryCommunityWire.narrativeRequest(narrativeRequest)
        parseOwned({ api.queueNarrative(s.token, s.libraryId, json,
            narrativeRequest.editorialContext) }, ProtectedMemoryCommunityWire::job)
    }

    /** Read-only saved structure plan, bound to the caller's current book revision and scope. */
    suspend fun bookPlan(
        bookId: String,
        expectedRevision: Long,
        editorialContext: Boolean = false,
        currentRequest: (() -> Boolean)? = null,
    ): MemoryBookPlan = withBinding(currentRequest) { s ->
        capabilities(s, Feature.COLLABORATION)
        requireUuid(bookId); require(expectedRevision > 0)
        if (currentRequest != null && !runCatching(currentRequest).getOrDefault(false))
            throw CancellationException("Book plan request changed")
        parseOwned({
            val bytes = api.bookPlan(s.token, s.libraryId, bookId, editorialContext)
            if (currentRequest != null && !runCatching(currentRequest).getOrDefault(false)) {
                bytes.fill(0)
                throw CancellationException("Book plan request changed")
            }
            bytes
        }) { MemoryBookPlanWire.decode(it, bookId, expectedRevision, editorialContext) }
    }

    /** Reader-scoped recovery keeps a stale denial from invalidating the wider library. */
    suspend fun job(jobId: String, currentRequest: (() -> Boolean)? = null): MemoryJob = withBinding(currentRequest) { s ->
        capabilities(s, Feature.COLLABORATION); requireUuid(jobId)
        parseOwned({ api.getJob(s.token, s.libraryId, jobId) }) { ProtectedMemoryCommunityWire.job(it, jobId) }
    }

    suspend fun cancelJob(jobId: String): MemoryJob = withBinding { s ->
        capabilities(s, Feature.COLLABORATION); requireUuid(jobId)
        parseOwned({ api.cancelJob(s.token, s.libraryId, jobId) }) { ProtectedMemoryCommunityWire.job(it, jobId) }
    }

    private fun requireUuid(value: String) {
        require(runCatching { UUID.fromString(value).toString() == value }.getOrDefault(false))
    }

    private fun verifyReceipt(receipt: MemoryContributionReceipt, request: MemoryContributionRequest, sha256: String?) {
        val item = receipt.contribution
        val expectedText = if (request.kind == "text") request.text else null
        if (item.kind != request.kind || item.language != request.language || item.byline != request.byline ||
            item.processingConsent != request.consent || item.chapterId != request.chapterId ||
            item.baseStoryRevision != request.revision || item.text != expectedText ||
            sha256 != null && item.sha256 != sha256) throw ApiFailure(FailureKind.INVALID_RESPONSE)
    }

}
