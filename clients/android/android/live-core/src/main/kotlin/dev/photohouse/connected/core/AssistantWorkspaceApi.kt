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
)

data class AssistantWorkspaceThreadSummary(
    val threadId: String,
    val libraryId: String,
    val createdAt: String,
    val updatedAt: String,
    val expiresAt: String,
    val revision: Long,
    val exchangeCount: Int = 0,
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
)
data class AssistantWorkspaceDeletedThread(val threadId: String, val deleted: Boolean)

/** Optional protected API. Implementations must remain inert until explicitly enabled. */
interface AssistantWorkspaceApi {
    val assistantWorkspaceEnabled: Boolean get() = false
    suspend fun capabilities(token: Bearer, library: String): AssistantWorkspaceCapabilities = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun listThreads(token: Bearer, library: String): AssistantWorkspaceThreadList = throw ApiFailure(FailureKind.INVALID_INPUT)
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
    suspend fun getTurn(token: Bearer, library: String, threadId: String, requestId: String): AssistantWorkspaceTurn = throw ApiFailure(FailureKind.INVALID_INPUT)
}
