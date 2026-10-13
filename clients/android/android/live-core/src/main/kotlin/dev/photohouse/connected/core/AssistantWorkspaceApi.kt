package dev.photohouse.connected.core

/** Capabilities for the optional, private, server-owned conversation workspace. */
data class AssistantWorkspaceCapabilities(
    val version: Int,
    val available: Boolean,
    val threads: Boolean,
    val preferences: Boolean,
    val preferencesApplied: Boolean,
    val serverOwnedTurns: Boolean,
    val appliedPreferences: Set<String> = emptySet(),
    val historyPaging: Boolean = false,
    val threadLabels: Boolean = false,
    val replySpeech: Boolean = false,
)

data class AssistantWorkspaceThreadSummary(
    val threadId: String,
    val libraryId: String,
    val createdAt: String,
    val updatedAt: String,
    val expiresAt: String,
    val revision: Long,
    val exchangeCount: Int = 0,
    val label: String? = null,
)

data class AssistantWorkspaceThreadList(val version: Int, val threads: List<AssistantWorkspaceThreadSummary>)
data class AssistantWorkspaceCreatedThread(val version: Int, val thread: AssistantWorkspaceThreadSummary)

data class AssistantWorkspaceCardCount(val type: String, val count: Int, val actionable: Boolean)
data class AssistantWorkspaceExchange(
    val exchangeId: String,
    val revision: Long,
    val createdAt: String,
    val expiresAt: String,
    val inputText: String,
    val reply: String,
    val cards: List<AssistantWorkspaceCardCount>,
    val receiptCount: Int,
    val requestId: String? = null,
)
data class AssistantWorkspaceThreadDetail(
    val version: Int,
    val thread: AssistantWorkspaceThreadSummary,
    val exchanges: List<AssistantWorkspaceExchange>,
    val latestRequestId: String? = null,
    val hasOlderExchanges: Boolean = false,
)

data class AssistantWorkspaceHistoryPage(
    val version: Int,
    val threadId: String,
    val snapshotRevision: Long,
    val beforeRevision: Long,
    val exchanges: List<AssistantWorkspaceExchange>,
    val hasOlderExchanges: Boolean,
    val nextBeforeRevision: Long?,
)

data class AssistantWorkspacePreferences(
    val version: Int,
    val locale: String?,
    val replyLength: String?,
    val voicePace: String?,
    val revision: Long,
)
enum class AssistantWorkspacePreference { LOCALE, REPLY_LENGTH, VOICE_PACE }

enum class AssistantWorkspaceRequestStatus { PENDING, COMPLETED, FAILED, INTERRUPTED }
data class AssistantWorkspaceTurn(
    val version: Int,
    val threadId: String,
    val requestId: String,
    val status: AssistantWorkspaceRequestStatus,
    val revision: Long,
    val recovered: Boolean,
    val error: String?,
    val result: AssistantTurn?,
    /** Validated transport receipt metadata; never read from or written into the JSON body. */
    val receipt: AssistantRequestReceipt? = null,
)
data class AssistantWorkspaceDeletedThread(val threadId: String, val deleted: Boolean)

data class SavedMemoryReaderCapabilities(val version: Int, val available: Boolean)
sealed interface SavedMemoryReaderPayload {
    data class Story(val value: SavedMemoryStory) : SavedMemoryReaderPayload
    data class Memoir(val value: MemoryBook) : SavedMemoryReaderPayload
}
data class AssistantMemoryReaderHandoff(
    val threadId: String, val turnId: String, val completionRevision: Long, val ordinal: Int,
    val card: AssistantSavedMemoryCard, val payload: SavedMemoryReaderPayload,
)

/** Optional protected API. Implementations must remain inert until explicitly enabled. */
interface AssistantWorkspaceApi {
    val assistantWorkspaceEnabled: Boolean get() = false
    suspend fun capabilities(token: Bearer, library: String): AssistantWorkspaceCapabilities = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun listThreads(token: Bearer, library: String): AssistantWorkspaceThreadList = throw ApiFailure(FailureKind.INVALID_INPUT)
    /** Opt-in overload; legacy adapters retain their original unlabelled list behavior. */
    suspend fun listThreads(token: Bearer, library: String, includeLabels: Boolean): AssistantWorkspaceThreadList =
        listThreads(token, library)
    /** Older adapters explicitly report that history paging is unavailable. */
    suspend fun readHistory(token: Bearer, library: String, threadId: String,
                            beforeRevision: Long, snapshotRevision: Long): AssistantWorkspaceHistoryPage =
        throw ApiFailure(FailureKind.HTTP, 503)
    suspend fun createThread(token: Bearer, library: String, clientThreadId: String): AssistantWorkspaceCreatedThread = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun readThread(token: Bearer, library: String, threadId: String): AssistantWorkspaceThreadDetail = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun deleteThread(token: Bearer, library: String, threadId: String, expectedRevision: Long): AssistantWorkspaceDeletedThread = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun preferences(token: Bearer, library: String): AssistantWorkspacePreferences = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun updatePreferences(token: Bearer, library: String, expectedRevision: Long,
                                  updates: Map<AssistantWorkspacePreference, String?>): AssistantWorkspacePreferences =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun resetPreferences(token: Bearer, library: String, expectedRevision: Long): AssistantWorkspacePreferences = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                           expectedRevision: Long, text: String): AssistantWorkspaceTurn = throw ApiFailure(FailureKind.INVALID_INPUT)
    /** Backward-compatible parent correlation overload; old implementations keep their behavior. */
    suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                           expectedRevision: Long, text: String, parentRequestId: String?): AssistantWorkspaceTurn =
        submitTurn(token, library, threadId, requestId, expectedRevision, text)
    /** Opt-in result negotiation; adapters without this overload keep legacy request and response shapes. */
    suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                           expectedRevision: Long, text: String, parentRequestId: String?,
                           acceptSavedMemoryCards: Boolean): AssistantWorkspaceTurn =
        submitTurn(token, library, threadId, requestId, expectedRevision, text, parentRequestId)
    suspend fun getTurn(token: Bearer, library: String, threadId: String, requestId: String): AssistantWorkspaceTurn = throw ApiFailure(FailureKind.INVALID_INPUT)
    /** Synthesizes only the server-owned reply for an exact completed private turn. */
    suspend fun speakTurn(token: Bearer, library: String, threadId: String, turnId: String,
                          expectedRevision: Long, speechRequestId: String): AssistantSpeechResult =
        throw ApiFailure(FailureKind.HTTP, 503)
    /** Optional explicit reader handoff. Legacy adapters conservatively keep this feature unavailable. */
    suspend fun savedMemoryReaderCapabilities(token: Bearer, library: String): SavedMemoryReaderCapabilities =
        SavedMemoryReaderCapabilities(1, false)
    /** Older servers/adapters keep the new search result disabled unless this exact probe is available. */
    suspend fun savedMemoryCardsCapabilities(token: Bearer, library: String): SavedMemoryReaderCapabilities =
        SavedMemoryReaderCapabilities(1, false)
    suspend fun savedMemorySpeechCapabilities(token: Bearer, library: String): SavedMemoryReaderCapabilities =
        SavedMemoryReaderCapabilities(1, false)
    suspend fun savedMemoryReader(
        token: Bearer, library: String, threadId: String, turnId: String, ordinal: Int,
        expectedRevision: Long,
    ): SavedMemoryReaderPayload = throw ApiFailure(FailureKind.HTTP, 503)
}
