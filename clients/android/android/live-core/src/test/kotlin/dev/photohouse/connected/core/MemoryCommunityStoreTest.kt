package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryCommunityStoreTest {
    private val storyId = "11111111-1111-1111-1111-111111111111"
    private val contributionId = "33333333-3333-3333-3333-333333333333"
    private val authorId = "22222222-2222-2222-2222-222222222222"
    private val conversationId = "44444444-4444-4444-4444-444444444444"
    private val secondConversationId = "99999999-9999-9999-9999-999999999999"
    private val jobId = "55555555-5555-5555-5555-555555555555"
    private val bookId = "66666666-6666-6666-6666-666666666666"
    private val secondStoryId = "77777777-7777-7777-7777-777777777777"
    private val summary = SavedMemoryStorySummary(storyId, "Garden", "everyday", "zh", 3, "1", 1, 1, 10, false)
    private val photo = Asset("1", "image", 10, 10, null, null, "/assets/1/thumbnail?library=family")
    private fun photoAsset(id: String) = photo.copy(id = id, thumbnail_url = "/assets/$id/thumbnail?library=family")
    private fun savedStory() = SavedMemoryStory(storyId, "family", 3, 1, 10, false, "a".repeat(64), "Garden", "everyday", "zh",
        listOf(MemoryStoryAsset(photo, emptyList())),
        listOf(SavedMemoryStoryChapter("chapter-1", "Morning", "A walk in the garden.", listOf("1"), emptyList())), emptyList())

    private inner class StoryApi : PhotoHouseApi {
        var storyCanEdit = true
        var voiceEnabled = false
        var voiceCapabilityReads = 0
        var instructionTranscriptions = 0
        var instructionTranscript = "保留每位家人的声音，不确定的年份先询问。"
        val instructionAudioBuffers = mutableListOf<ByteArray>()
        val childReads = mutableListOf<String>()
        var mediaGate: CompletableDeferred<Unit>? = null
        var lateMediaBytes: ByteArray? = null
        var thumbnailFixture: ByteArray? = null
        var thumbnailFailure: ApiFailure? = null
        var tenFrameStory = false
        var availableLibraries = listOf("family")
        var membershipRevision = 1L
        var accountId = "account"
        var savedStoryListReads = 0
        var storyRevision = 3L
        var storyChapterIds = listOf("chapter-1")
        var deniedChildId: String? = null
        var childReadGateId: String? = null
        var childReadGate: CompletableDeferred<Unit>? = null
        var childReadGateEntered = CompletableDeferred<Unit>()
        var denyChildInsideReadGate = false
        var childReadFailure: ApiFailure? = null
        var childReadException: Exception? = null
        var contributionDetailGate: CompletableDeferred<Unit>? = null
        var contributionDetailGateEntered = CompletableDeferred<Unit>()
        val thumbnailReads = mutableListOf<String>()
        val heroReads = mutableListOf<String>()
        var originalReads = 0
        override val protectedNativeV2Enabled = true
        override val assistantEnabled get() = voiceEnabled
        override suspend fun assistantCapabilities(token: Bearer, library: String): AssistantCapabilities {
            voiceCapabilityReads++
            return AssistantCapabilities(true, true, true, false, 30)
        }
        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String): AssistantTranscript {
            instructionTranscriptions++
            instructionAudioBuffers += wav
            return AssistantTranscript(instructionTranscript, "zh", AssistantRequestReceipt(requestId, "enabled", "succeeded"))
        }
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session(accountId, "+12025550123", availableLibraries.map {
            Membership(it, "approved", "owner", membershipRevision, null, 0, true)
        })
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 8, 1, false, listOf(photo))
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, photo)
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray {
            thumbnailReads += asset.id
            val failure = thumbnailFailure
            mediaGate?.let { withContext(NonCancellable) { it.await(); failure?.let { throw it } } }
            failure?.let { throw it }
            return (thumbnailFixture?.copyOf() ?: byteArrayOf(9, 8, 7)).also { lateMediaBytes = it }
        }
        override suspend fun detailPreview(token: Bearer, library: String, asset: Asset): ByteArray? {
            heroReads += asset.id
            return byteArrayOf(9, 8, 7)
        }
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 1, byteArrayOf(1))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray {
            originalReads++
            return byteArrayOf(1)
        }
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int): SavedMemoryStoryPage {
            savedStoryListReads++
            return SavedMemoryStoryPage(library, page, 8, false, false, listOf(summary))
        }
        override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
            childReads += storyId
            if (storyId == childReadGateId) {
                childReadGateEntered.complete(Unit)
                childReadGate?.let { gate -> withContext(NonCancellable) {
                    gate.await()
                    if (denyChildInsideReadGate && storyId == deniedChildId) throw ApiFailure(FailureKind.HTTP, 403)
                    childReadFailure?.let { childReadFailure = null; throw it }
                    childReadException?.let { childReadException = null; throw it }
                } }
            }
            childReadFailure?.let { childReadFailure = null; throw it }
            if (storyId == deniedChildId) throw ApiFailure(FailureKind.HTTP, 403)
            val base = savedStory().copy(id = storyId, revision = storyRevision, canEdit = storyCanEdit)
            val withChapters = base.copy(chapters = storyChapterIds.mapIndexed { index, id ->
                SavedMemoryStoryChapter(id, if (index == 0) "Morning" else "Afternoon", "A walk in the garden.", listOf("1"), emptyList())
            })
            if (!tenFrameStory) return withChapters
            val ids = (1..10).map(Int::toString)
            return withChapters.copy(items = ids.map { MemoryStoryAsset(photoAsset(it), emptyList()) },
                chapters = withChapters.chapters.map { it.copy(assetIds = ids) })
        }
        override suspend fun savedMemoryContributionDetail(
            token: Bearer, library: String, storyId: String, contributionId: String,
        ): MemoryContributionDetail {
            contributionDetailGateEntered.complete(Unit)
            contributionDetailGate?.let { withContext(NonCancellable) { it.await() } }
            return MemoryContributionDetail(
                MemoryContributionReceipt(MemoryContribution(contributionId, storyId, "member", "text", "en", "Member",
                    "a".repeat(64), null, "chapter-1", storyRevision, "accepted", 1, "Family words", true), false, false),
                null,
            )
        }
    }

    private inner class CommunityApi : MemoryCommunityApi, MemoryBookEditorialApi {
        var capFailure: ApiFailure? = null
        var capabilitiesEnabled = true
        var contributionsEnabled = true
        var chatTurnText: String? = null
        var chatTurnReplySourceIds: List<String>? = null
        var chatTurnReplyQuestions: List<String>? = null
        var contributionGate: CompletableDeferred<Unit>? = null
        var textGate: CompletableDeferred<Unit>? = null
        var listReads = 0
        val contributionPages = mutableListOf<Int>()
        val turnPages = mutableListOf<Int>()
        var sentBodies = mutableListOf<String>()
        var conversationReads = 0
        val turnConversationIds = mutableListOf<String>()
        var conversationGate: CompletableDeferred<Unit>? = null
        var turnGate: CompletableDeferred<Unit>? = null
        var conversationFailure: ApiFailure? = null
        var turnFailure: ApiFailure? = null
        var conversationStartFailure: ApiFailure? = null
        var conversationStartGate: CompletableDeferred<Unit>? = null
        var hideNewestStartedConversation = false
        var chatTurnFailure: ApiFailure? = null
        val startedConversationIds = mutableListOf<String>()
        var chatTurnPosts = 0
        var existingConversation = false
        var extraConversationIds = emptyList<String>()
        var existingActiveTurn = false
        var activeTurnSequence = 1
        var activeJobKind = "chat"
        var activeJobBaseRevision = "1"
        var jobGate: CompletableDeferred<Unit>? = null
        var jobFailure: ApiFailure? = null
        var beforeJobFailure: (() -> Unit)? = null
        var startedPosts = 0
        var jobReads = 0
        var cancelJobReads = 0
        var failNextJob = false
        var startedConversationId: String? = null
        val startedTargets = mutableListOf<Pair<String, String>>()
        val turnMutationIds = mutableListOf<String>()
        var failNextBookTurn = false
        var narrativeWrites = 0
        var bookOrder = listOf(storyId, secondStoryId)
        var bookRevision = "1"
        var bookChildRevisions = mutableMapOf(storyId to "3", secondStoryId to "3")
        var bookItemCount = 1
        var bookReads = 0
        var bookPageReads = 0
        val bookPageRequests = mutableListOf<Int>()
        var bookCanCreate = true
        var bookSaveCalls = 0
        var createdBookJson: String? = null
        val bookSaveBodies = mutableListOf<String>()
        var bookFailure: ApiFailure? = null
        var bookGate: CompletableDeferred<Unit>? = null
        var denyBookAfterGate = false
        var planGate: CompletableDeferred<Unit>? = null
        var planFailure: ApiFailure? = null
        var planReads = 0
        var planCanDraft = false
        var narrativeRequest: JsonObject? = null
        val narrativeEditorialChoices = mutableListOf<Boolean>()
        val turnEditorialChoices = mutableListOf<Boolean>()
        val callOrder = mutableListOf<String>()
        private fun bookJson(): String {
            val entries = bookOrder.joinToString(prefix = "[", postfix = "]") { id ->
                "{\"id\":\"" + id + "\",\"title\":\"" + (if (id == storyId) "Garden" else "Picnic") +
                    "\",\"revision\":\"" + (bookChildRevisions[id] ?: "3") + "\",\"item_count\":" +
                    (if (id == storyId) bookItemCount else 1) + ",\"cover_asset_id\":\"1\"}"
            }
            return "{\"version\":1,\"type\":\"memoir\",\"id\":\"" + bookId +
                "\",\"revision\":\"" + bookRevision + "\",\"can_edit\":true,\"title\":\"Garden memories\"," +
                "\"introduction\":\"A family collection.\",\"language\":\"en\",\"stories\":" + entries + "}"
        }
        override suspend fun capabilities(token: Bearer, library: String): ByteArray {
            callOrder += "capabilities"
            capFailure?.let { throw it }
            return """{"version":1,"enabled":$capabilitiesEnabled,"contributions_enabled":$contributionsEnabled,"generation_enabled":$capabilitiesEnabled,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()
        }
        override suspend fun listBooks(token: Bearer, library: String, page: Int): ByteArray {
            callOrder += "books"
            bookPageReads++
            bookPageRequests += page
            return ("{\"version\":1,\"library_id\":\"" + library + "\",\"page\":" + page +
                ",\"page_size\":8,\"has_more\":false,\"can_create\":" + bookCanCreate + ",\"items\":[" + bookJson() + "]}").toByteArray()
        }
        override suspend fun getBook(token: Bearer, library: String, bookId: String): ByteArray {
            callOrder += "book"
            bookFailure?.let { throw it }
            val pendingReadGate = bookGate
            pendingReadGate?.let { withContext(NonCancellable) { it.await() } }
            if (pendingReadGate != null && denyBookAfterGate) throw ApiFailure(FailureKind.HTTP, 403)
            bookReads++
            return if (bookId == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
                createdBookJson?.toByteArray() ?: error("missing synthetic created book")
            else bookJson().toByteArray()
        }
        override suspend fun saveBook(token: Bearer, library: String, bookId: String?, json: String): ByteArray {
            bookSaveCalls++
            bookSaveBodies += json
            check(bookId == null)
            val request = Json.parseToJsonElement(json).jsonObject
            val ids = request.getValue("story_ids").jsonPrimitive.content.split(',')
            val stories = ids.joinToString(",") { id ->
                "{\"id\":\"$id\",\"title\":\"Garden\",\"revision\":\"${bookChildRevisions[id] ?: "3"}\",\"item_count\":1,\"cover_asset_id\":\"1\"}"
            }
            createdBookJson = """{"version":1,"type":"memoir","id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","revision":"1","can_edit":true,"title":${request.getValue("title")},"introduction":${request.getValue("introduction")},"language":${request.getValue("language")},"stories":[$stories]}"""
            return createdBookJson!!.toByteArray()
        }
        override suspend fun getBookEditorial(token: Bearer, library: String, bookId: String): ByteArray {
            val children = bookOrder.joinToString(prefix = "[", postfix = "]") { id ->
                "{\"story_id\":\"$id\",\"revision\":\"${bookChildRevisions[id] ?: "3"}\"}"
            }
            val transitions = bookOrder.zipWithNext().joinToString(prefix = "[", postfix = "]") { (left, right) ->
                "{\"left_story_id\":\"$left\",\"right_story_id\":\"$right\",\"text\":\"\",\"source_refs\":[]}"
            }
            return ("{\"version\":1,\"id\":\"$bookId\",\"revision\":\"$bookRevision\",\"children\":$children," +
                "\"state\":\"current\",\"introduction_source_refs\":[],\"transitions\":$transitions}").toByteArray()
        }
        override suspend fun saveBookEditorial(token: Bearer, library: String, bookId: String, json: String): ByteArray =
            getBookEditorial(token, library, bookId)
        override suspend fun getBookEditorialSourceReferences(
            token: Bearer, library: String, storyId: String, revision: Long,
        ): SavedMemoryStoryContributionReferences = SavedMemoryStoryContributionReferences(
            storyId, library, revision, listOf(SavedMemoryChapterContributionReferences("chapter-1", listOf(contributionId))))
        override suspend fun bookPlan(token: Bearer, library: String, bookId: String, editorialContext: Boolean): ByteArray {
            planReads++
            planGate?.let { withContext(NonCancellable) { it.await() } }
            planFailure?.let { throw it }
            val sections = bookOrder.mapIndexed { index, id ->
                """{"position":${index + 1},"id":"$id","revision":"3","title":"Saved story","item_count":1,"can_edit":$planCanDraft,"chapters":[{"id":"chapter-1","title":"Morning","item_count":1}],"state":"within_limits","can_draft":$planCanDraft,"source_count":1,"source_kinds":{"editorial":1}}"""
            }
            val profile = if (editorialContext) ",\"context_profile\":\"memoir_editorial_v1\"" else ""
            val contextBytes = if (editorialContext) ",\"context_bytes\":3000" else ""
            return """{"version":1,"target_type":"book","target_id":"$bookId","revision":"$bookRevision","can_edit":$planCanDraft,"kind":"saved_structure_plan","generated":false,"queued":false,"needs_review":true,"story_count":${sections.size},"chapter_count":${sections.size},"item_count":${sections.size},"distinct_item_count":1,"limits":{"chapters":24,"sources":96,"context_bytes":65536},"whole":{"state":"within_limits","can_draft":$planCanDraft,"source_count":${sections.size},"source_kinds":{"editorial":${sections.size}}${contextBytes}},"sections":[${sections.joinToString(",")}]${profile}}""".toByteArray()
        }
        override suspend fun listContributions(token: Bearer, library: String, storyId: String, page: Int): ByteArray {
            listReads++
            contributionPages += page
            contributionGate?.let { withContext(NonCancellable) { it.await() } }
            return """{"version":1,"story_id":"$storyId","page":$page,"page_size":16,"has_more":${page == 1},"can_review":true,"can_delete":true,"items":[]}""".toByteArray()
        }
        override suspend fun createTextContribution(token: Bearer, library: String, storyId: String, json: String): ByteArray {
            sentBodies += json
            textGate?.let { it.await() }
            val r = Json.parseToJsonElement(json).jsonObject
            val text = r.getValue("text").jsonPrimitive.content
            val lang = r.getValue("language").jsonPrimitive.content
            val byline = r.getValue("byline").jsonPrimitive.content
            val chapter = r.getValue("chapter_id").jsonPrimitive.content.takeIf { it.isNotEmpty() }
            val consent = r.getValue("consent").jsonPrimitive.content == "1"
            return """{"version":1,"id":"$contributionId","story_id":"$storyId","author_id":"$authorId","kind":"text","language":"$lang","byline":"$byline","sha256":"${"a".repeat(64)}","duration_ms":null,"chapter_id":${chapter?.let { "\"$it\"" } ?: "null"},"base_story_revision":"${r.getValue("revision").jsonPrimitive.content}","state":"pending","created_at":10,"text":${JsonPrimitive(text)},"processing_consent":$consent,"can_review":true,"can_delete":true}""".toByteArray()
        }
        override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
            conversationReads++
            conversationFailure?.let { throw it }
            val gate = conversationGate; conversationGate = null
            gate?.let { withContext(NonCancellable) { it.await() } }
            val ids = ((if (existingConversation) listOf(conversationId) + extraConversationIds else emptyList()) + startedConversationIds)
                .distinct().filterNot { hideNewestStartedConversation && it == startedConversationIds.lastOrNull() }
            val items = ids.mapIndexed { index, id ->
                """{"id":"$id","created_at":${10 + index},"expires_at":999}"""
            }
            return """{"version":1,"items":[${items.joinToString(",")}]}""".toByteArray()
        }
        override suspend fun startConversation(token: Bearer, library: String, json: String): ByteArray {
            startedPosts++
            val request = Json.parseToJsonElement(json).jsonObject
            startedConversationId = request.getValue("id").jsonPrimitive.content
            val type = request.getValue("target_type").jsonPrimitive.content
            val target = request.getValue("target_id").jsonPrimitive.content
            startedTargets += type to target
            startedConversationIds += startedConversationId!!
            val gate = conversationStartGate; conversationStartGate = null
            gate?.let { withContext(NonCancellable) { it.await() } }
            conversationStartFailure?.let { conversationStartFailure = null; throw it }
            return """{"version":1,"id":"$startedConversationId","target_type":"$type","target_id":"$target","expires_at":999}""".toByteArray()
        }
        override suspend fun conversationTurns(token: Bearer, library: String, conversationId: String, page: Int): ByteArray {
            turnConversationIds += conversationId
            turnPages += page
            val gate = turnGate; turnGate = null
            val failure = turnFailure; turnFailure = null
            gate?.let { withContext(NonCancellable) { it.await() } }
            failure?.let { throw it }
            val item = when {
                existingActiveTurn -> """{"id":"$jobId","sequence":$activeTurnSequence,"input_text":"Continue","reply_text":null,"reply_kind":null,"job_id":"$jobId","state":"queued"}"""
                chatTurnText != null -> {
                    val context = if (chatTurnReplySourceIds != null && chatTurnReplyQuestions != null) {
                        ",\"reply_source_ids\":" + JsonArray(chatTurnReplySourceIds!!.map { JsonPrimitive(it) }) +
                            ",\"reply_questions\":" + JsonArray(chatTurnReplyQuestions!!.map { JsonPrimitive(it) })
                    } else ""
                    """{"id":"88888888-8888-4888-8888-888888888888","sequence":1,"input_text":${JsonPrimitive(chatTurnText)} ,"reply_text":"assistant reply must not be seeded","reply_kind":"answer","job_id":null,"state":"ready"$context}"""
                }
                else -> ""
            }
            return """{"version":1,"id":"$conversationId","expires_at":999,"page":$page,"has_more":${page == 1},"items":[$item]}""".toByteArray()
        }
        override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String): ByteArray {
            sentBodies += json
            chatTurnPosts++
            val body = Json.parseToJsonElement(json).jsonObject
            turnMutationIds += body.getValue("mutation_id").jsonPrimitive.content
            chatTurnFailure?.let { chatTurnFailure = null; throw it }
            if (failNextBookTurn) { failNextBookTurn = false; throw ApiFailure(FailureKind.OFFLINE) }
            return """{"version":1,"id":"$jobId","kind":"chat","state":"queued","created_at":10,"updated_at":10,"expires_at":999,"error_code":null,"result":null,"needs_review":true,"base_revision":"3"}""".toByteArray()
        }
        override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String, editorialContext: Boolean): ByteArray {
            turnEditorialChoices += editorialContext
            return sendTurn(token, library, conversationId, json)
        }
        fun narrativeResponse() =
            """{"version":1,"id":"$jobId","kind":"narrative","state":"ready","created_at":10,"updated_at":10,"expires_at":999,"error_code":null,"result":{"version":1,"title":"Garden draft","chapters":[{"id":"chapter-1","narration":"A draft.","source_ids":[]}],"questions":[],"needs_review":true},"needs_review":true,"base_revision":"3"}""".toByteArray()
        override suspend fun queueNarrative(token: Bearer, library: String, json: String): ByteArray {
            narrativeWrites++
            narrativeRequest = Json.parseToJsonElement(json).jsonObject
            if (narrativeRequest?.get("target_type")?.jsonPrimitive?.content == "book") {
                val chapters = bookOrder.joinToString(",") { story ->
                    """{"id":"$story-chapter-1","narration":"Connected family account.","source_ids":[]}"""
                }
                return """{"version":1,"id":"$jobId","kind":"narrative","state":"ready","created_at":10,"updated_at":10,"expires_at":999,"error_code":null,"result":{"version":1,"title":"Family memoir draft","chapters":[$chapters],"questions":["Who remembers the year?"],"needs_review":true},"needs_review":true,"base_revision":"$bookRevision"}""".toByteArray()
            }
            return narrativeResponse()
        }
        override suspend fun queueNarrative(token: Bearer, library: String, json: String, editorialContext: Boolean): ByteArray {
            narrativeEditorialChoices += editorialContext
            return queueNarrative(token, library, json)
        }
        override suspend fun getJob(token: Bearer, library: String, jobId: String): ByteArray {
            jobReads++
            val gate = jobGate; jobGate = null
            gate?.let { withContext(NonCancellable) { it.await() } }
            beforeJobFailure?.let { beforeJobFailure = null; it() }
            jobFailure?.let { jobFailure = null; throw it }
            if (failNextJob) { failNextJob = false; throw ApiFailure(FailureKind.OFFLINE) }
            return """{"version":1,"id":"$jobId","kind":"$activeJobKind","state":"running","created_at":10,"updated_at":10,"expires_at":999,"error_code":null,"result":null,"needs_review":true,"base_revision":"$activeJobBaseRevision"}""".toByteArray()
        }
        override suspend fun cancelJob(token: Bearer, library: String, jobId: String): ByteArray {
            cancelJobReads++
            return """{"version":1,"id":"$jobId","kind":"chat","state":"cancelled","created_at":10,"updated_at":10,"expires_at":999,"error_code":null,"result":null,"needs_review":true,"base_revision":"$activeJobBaseRevision"}""".toByteArray()
        }
    }

    private class ReaderPositionMemoryStore : MemoryBookReaderPositionPersistence {
        private val rows = linkedMapOf<String, List<MemoryBookReaderPosition>>()
        val clearedAccounts = mutableListOf<String>()
        var failLoad = false
        var failSave = false
        override fun load(accountId: String): List<MemoryBookReaderPosition> {
            if (failLoad) error("synthetic persistence failure")
            return rows[accountId].orEmpty().toList()
        }
        override fun save(accountId: String, position: MemoryBookReaderPosition) {
            if (failSave) error("synthetic persistence failure")
            rows[accountId] = MemoryBookReaderPositions.upsert(accountId, load(accountId), position)
        }
        override fun remove(accountId: String, libraryId: String, bookId: String) {
            rows[accountId] = MemoryBookReaderPositions.without(accountId, load(accountId), libraryId, bookId)
        }
        override fun clear(accountId: String) { clearedAccounts += accountId; rows.remove(accountId) }
        fun seed(position: MemoryBookReaderPosition) { save(position.accountId, position) }
    }

    private fun TestScope.newStore(
        api: StoryApi,
        community: CommunityApi?,
        enabled: Boolean = community != null,
        readerPositionPersistence: MemoryBookReaderPositionPersistence? = null,
    ) = ConnectedStore(api, backgroundScope, memoryCommunityApi = community, memoryCommunityEnabled = enabled,
        now = { testScheduler.currentTime }, memoryBookReaderPositionPersistence = readerPositionPersistence)
    private fun TestScope.openStory(store: ConnectedStore) {
        store.authenticate("+12025550123", "synthetic-password")
        runCurrent()
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(summary); runCurrent()
        assertEquals(storyId, store.state.value.savedMemoryStories?.detail?.id)
    }
    private fun TestScope.openBookReader(store: ConnectedStore) {
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        assertEquals(storyId, store.state.value.memoryBooks?.story?.id)
    }

    private fun instructionWav(): ByteArray = ByteArray(32044).also { bytes ->
        fun tag(at: Int, text: String) = text.toByteArray(Charsets.US_ASCII).copyInto(bytes, at)
        fun u16(at: Int, value: Int) { bytes[at] = value.toByte(); bytes[at + 1] = (value shr 8).toByte() }
        fun u32(at: Int, value: Int) { repeat(4) { bytes[at + it] = (value shr (it * 8)).toByte() } }
        tag(0, "RIFF"); u32(4, 32036); tag(8, "WAVE"); tag(12, "fmt ")
        u32(16, 16); u16(20, 1); u16(22, 1); u32(24, 16000); u32(28, 32000)
        u16(32, 2); u16(34, 16); tag(36, "data"); u32(40, 32000)
    }

    @Test fun wholeMemoirVoiceInstructionsWaitForReviewInsertionAndExplicitRequest() = runTest {
        val api = StoryApi().apply { voiceEnabled = true }
        val community = CommunityApi().apply { planCanDraft = true }
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent(); store.openMemoryBook(bookId); runCurrent()
        assertNull(store.state.value.memoryBooks?.story)
        assertEquals(0, api.voiceCapabilityReads)
        assertTrue(store.updateMemoryBookNarrativeInstructions("按时间顺序。"))
        assertTrue(store.openMemoryBookNarrativeDictation()); runCurrent()
        val voice = store.memoryBookNarrativeDictationState.value!!
        assertEquals(1, api.voiceCapabilityReads)
        assertEquals(0, api.instructionTranscriptions)
        assertEquals(30, voice.beginRecording())
        store.checkMemoryBookNarrativePlan(); runCurrent()
        assertEquals(0, community.planReads)
        voice.stopRecording(instructionWav()); runCurrent()
        assertEquals(api.instructionTranscript, voice.state.value.transcript)
        assertEquals("按时间顺序。", store.memoryBookNarrativeState.value.instructions)
        assertEquals(0, community.narrativeWrites)
        voice.updateTranscript("请保留不同家人的讲述。")
        assertTrue(store.insertMemoryBookNarrativeDictation())
        assertEquals("按时间顺序。\n请保留不同家人的讲述。", store.memoryBookNarrativeState.value.instructions)
        assertNull(voice.state.value.transcript)
        assertTrue(api.instructionAudioBuffers.single().all { it == 0.toByte() })
        assertEquals(0, community.narrativeWrites)
        store.checkMemoryBookNarrativePlan(); runCurrent()
        store.requestMemoryBookNarrative(); runCurrent()
        assertEquals(1, community.narrativeWrites)
        assertEquals("按时间顺序。\n请保留不同家人的讲述。", community.narrativeRequest!!["instructions"]!!.jsonPrimitive.content)
    }

    @Test fun staleMemoirDictationCallbacksCannotCloseOrInsertIntoReplacementHelper() = runTest {
        val api = StoryApi().apply { voiceEnabled = true }
        val store = newStore(api, CommunityApi())
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent(); store.openMemoryBook(bookId); runCurrent()
        assertTrue(store.updateMemoryBookNarrativeInstructions("Keep family voices distinct."))

        assertTrue(store.openMemoryBookNarrativeDictation()); runCurrent()
        val helperA = store.memoryBookNarrativeDictationState.value!!
        helperA.beginRecording(); helperA.stopRecording(instructionWav()); runCurrent()
        helperA.updateTranscript("An earlier reviewed transcript.")
        assertEquals("An earlier reviewed transcript.", helperA.state.value.transcript)

        assertTrue(store.clearMemoryBookNarrativeDictation(helperA))
        api.instructionTranscript = "The current transcript belongs to the replacement helper."
        assertTrue(store.openMemoryBookNarrativeDictation()); runCurrent()
        val helperB = store.memoryBookNarrativeDictationState.value!!
        assertNotSame(helperA, helperB)
        helperB.beginRecording(); helperB.stopRecording(instructionWav()); runCurrent()
        helperB.updateTranscript("The current transcript belongs to the replacement helper.")

        assertFalse(store.clearMemoryBookNarrativeDictation(helperA))
        assertFalse(store.insertMemoryBookNarrativeDictation(helperA))
        assertSame(helperB, store.memoryBookNarrativeDictationState.value)
        assertEquals("The current transcript belongs to the replacement helper.", helperB.state.value.transcript)
        assertEquals("Keep family voices distinct.", store.memoryBookNarrativeState.value.instructions)

        assertTrue(store.insertMemoryBookNarrativeDictation(helperB))
        assertEquals("Keep family voices distinct.\nThe current transcript belongs to the replacement helper.",
            store.memoryBookNarrativeState.value.instructions)
        assertNull(helperB.state.value.transcript)
    }

    @Test fun oversizedInstructionInsertionKeepsTranscriptAndReaderCloseClearsIt() = runTest {
        val api = StoryApi().apply { voiceEnabled = true }
        val community = CommunityApi().apply { planCanDraft = true }
        val store = newStore(api, community)
        openBookReader(store)
        assertTrue(store.updateMemoryBookNarrativeInstructions("x".repeat(4090)))
        assertTrue(store.openMemoryBookNarrativeDictation()); runCurrent()
        val voice = store.memoryBookNarrativeDictationState.value!!
        voice.beginRecording(); voice.stopRecording(instructionWav()); runCurrent()
        assertFalse(store.insertMemoryBookNarrativeDictation())
        assertEquals(api.instructionTranscript, voice.state.value.transcript)
        assertEquals("x".repeat(4090), store.memoryBookNarrativeState.value.instructions)
        store.requestMemoryBookNarrative(); runCurrent()
        assertEquals(0, community.narrativeWrites)
        store.closeMemoryBooks()
        assertNull(store.memoryBookNarrativeDictationState.value)
        assertEquals(MemoryDictationState(), voice.state.value)
        assertEquals("", store.memoryBookNarrativeState.value.instructions)
    }

    @Test fun wholeMemoirChecksBeforeQueueAndReviewsWithoutChangingSavedStories() = runTest {
        val api = StoryApi()
        val community = CommunityApi().apply { planCanDraft = true }
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertNull("whole memoir works before opening a child", store.state.value.memoryBooks?.story)
        assertTrue(store.updateMemoryBookNarrativeInstructions("Keep the different family voices."))
        store.requestMemoryBookNarrative(); runCurrent()
        assertEquals("a plan is required", 0, community.narrativeWrites)
        store.checkMemoryBookNarrativePlan(); runCurrent()
        assertEquals(MemoryBookNarrativeStatus.PLAN_READY, store.memoryBookNarrativeState.value.status)
        assertEquals(1, community.planReads)
        assertEquals(0, community.narrativeWrites)
        store.chooseMemoryBookNarrativeEditorialContext(true)
        assertNull("changing context needs another plan", store.memoryBookNarrativeState.value.plan)
        store.checkMemoryBookNarrativePlan(); runCurrent()
        store.requestMemoryBookNarrative(); runCurrent()
        val draft = store.memoryBookNarrativeState.value
        assertEquals(MemoryBookNarrativeStatus.REVIEW_READY, draft.status)
        assertEquals(listOf(storyId, secondStoryId), draft.proposal!!.chapters.map { it.storyId })
        assertEquals(listOf(true), community.narrativeEditorialChoices)
        assertEquals("book", community.narrativeRequest!!.getValue("target_type").jsonPrimitive.content)
        assertEquals(bookId, community.narrativeRequest!!.getValue("target_id").jsonPrimitive.content)
        assertEquals("1", community.narrativeRequest!!.getValue("revision").jsonPrimitive.content)
        store.loadMemoryBookStory(1); runCurrent()
        assertEquals("A walk in the garden.", store.state.value.memoryBooks?.story?.chapters?.single()?.narration)
        assertEquals(draft.proposal, store.memoryBookNarrativeState.value.proposal)
        store.closeMemoryBooks()
        assertNull(store.memoryBookNarrativeState.value.proposal)
        assertEquals("", store.memoryBookNarrativeState.value.instructions)
    }

    @Test fun lateWholeMemoirPlanCannotPopulateAReopenedReader() = runTest {
        val community = CommunityApi().apply { planCanDraft = true; planGate = CompletableDeferred() }
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        store.updateMemoryBookNarrativeInstructions("An unfinished family account.")
        store.checkMemoryBookNarrativePlan(); runCurrent()
        assertTrue(store.memoryBookNarrativeState.value.busy)
        store.closeMemoryBooks()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        community.planGate!!.complete(Unit); runCurrent()
        assertNull(store.memoryBookNarrativeState.value.plan)
        assertEquals("", store.memoryBookNarrativeState.value.instructions)
        assertEquals(0, community.narrativeWrites)
    }

    @Test fun storyFollowupOnlyFillsCurrentBlankDraftAndWaitsForExplicitSend() = runTest {
        val question = "那天后来发生了什么？"
        val api = CommunityApi().apply {
            existingConversation = true
            chatTurnText = "那天在花园里散步。"
            chatTurnReplySourceIds = listOf("editorial-$storyId-chapter-1")
            chatTurnReplyQuestions = listOf(question)
        }
        val store = newStore(StoryApi(), api)
        openStory(store)
        store.selectMemoryCommunityTab(1)
        val reader = store.state.value.savedMemoryStories!!.community!!
        val turn = reader.turns!!.items.single()
        val generation = store.state.value.generation
        val sentBefore = api.sentBodies.size

        assertEquals(MemoryChatFollowupResult.STALE, store.chooseMemoryChatFollowup(
            "account", generation, "other-library", reader.readerScopeId, storyId, 3,
            conversationId, 1, turn.id, question))
        assertEquals(MemoryChatFollowupResult.SELECTED, store.chooseMemoryChatFollowup(
            "account", generation, "family", reader.readerScopeId, storyId, 3,
            conversationId, 1, turn.id, question))
        var chat = store.state.value.savedMemoryStories!!.community!!
        assertEquals(question, chat.chatDraft)
        assertEquals(question, chat.threadDrafts[conversationId])
        assertEquals(1, chat.chatDraftFocusRequestId)
        assertEquals(sentBefore, api.sentBodies.size)

        assertEquals(MemoryChatFollowupResult.BLOCKED, store.chooseMemoryChatFollowup(
            "account", generation, "family", reader.readerScopeId, storyId, 3,
            conversationId, 1, turn.id, question))
        store.sendMemoryChat(); runCurrent()
        chat = store.state.value.savedMemoryStories!!.community!!
        assertEquals(sentBefore + 1, api.sentBodies.size)
        assertEquals(question, Json.parseToJsonElement(api.sentBodies.last()).jsonObject
            .getValue("text").jsonPrimitive.content)
        assertEquals(MemoryChatFollowupResult.BLOCKED, store.chooseMemoryChatFollowup(
            "account", generation, "family", reader.readerScopeId, storyId, 3,
            conversationId, 1, turn.id, question))
        assertEquals("queued", chat.job?.state)

        store.closeSavedMemoryStoryDetail()
        assertEquals(MemoryChatFollowupResult.STALE, store.chooseMemoryChatFollowup(
            "account", generation, "family", reader.readerScopeId, storyId, 3,
            conversationId, 1, turn.id, question))
    }

    @Test fun storyFollowupIsBlockedDuringVoiceCapture() = runTest {
        val question = "后来呢？"
        val api = CommunityApi().apply {
            existingConversation = true
            chatTurnText = "花园里的故事。"
            chatTurnReplySourceIds = emptyList()
            chatTurnReplyQuestions = listOf(question)
        }
        val storyApi = StoryApi().apply { voiceEnabled = true }
        val store = newStore(storyApi, api)
        openStory(store)
        store.selectMemoryCommunityTab(1)
        val reader = store.state.value.savedMemoryStories!!.community!!
        val turn = reader.turns!!.items.single()
        val dictation = store.memoryCommunityDictation()!!
        dictation.loadCapabilities(); runCurrent()
        assertNotNull(dictation.beginRecording())
        assertEquals(MemoryChatFollowupResult.BLOCKED, store.chooseMemoryChatFollowup(
            "account", store.state.value.generation, "family", reader.readerScopeId, storyId, 3,
            conversationId, 1, turn.id, question))
        dictation.cancel()
        assertTrue(api.sentBodies.isEmpty())
    }

    @Test fun memoirFollowupIsReaderScopedAndWaitsForExplicitSend() = runTest {
        val question = "谁还记得那次野餐？"
        val api = CommunityApi().apply {
            existingConversation = true
            chatTurnText = "我们在花园里吃了午饭。"
            chatTurnReplySourceIds = listOf("editorial-book-$bookId")
            chatTurnReplyQuestions = listOf(question)
        }
        val store = newStore(StoryApi(), api)
        openBookReader(store)
        val reading = store.state.value.memoryBooks!!
        val chat = reading.companion!!
        val turn = chat.turns!!.items.single()
        val generation = store.state.value.generation
        val sentBefore = api.sentBodies.size
        assertEquals(MemoryChatFollowupResult.STALE, store.chooseMemoryBookChatFollowup(
            "account", generation, "family", reading.readerScopeId + 1, bookId, 1,
            storyId, 3, conversationId, 1, turn.id, question))
        assertEquals(MemoryChatFollowupResult.SELECTED, store.chooseMemoryBookChatFollowup(
            "account", generation, "family", reading.readerScopeId, bookId, 1,
            storyId, 3, conversationId, 1, turn.id, question))
        var selected = store.state.value.memoryBooks!!.companion!!
        assertEquals(question, selected.draft)
        assertEquals(question, selected.threadDrafts[conversationId])
        assertEquals(1, selected.chatDraftFocusRequestId)
        assertEquals(sentBefore, api.sentBodies.size)
        assertEquals(MemoryChatFollowupResult.BLOCKED, store.chooseMemoryBookChatFollowup(
            "account", generation, "family", reading.readerScopeId, bookId, 1,
            storyId, 3, conversationId, 1, turn.id, question))

        store.sendMemoryBookChat(); runCurrent()
        selected = store.state.value.memoryBooks!!.companion!!
        assertEquals(sentBefore + 1, api.sentBodies.size)
        assertEquals(question, Json.parseToJsonElement(api.sentBodies.last()).jsonObject
            .getValue("text").jsonPrimitive.content)
        assertEquals("queued", selected.job?.state)
        assertEquals(MemoryChatFollowupResult.BLOCKED, store.chooseMemoryBookChatFollowup(
            "account", generation, "family", reading.readerScopeId, bookId, 1,
            storyId, 3, conversationId, 1, turn.id, question))

        store.closeMemoryBook()
        assertEquals(MemoryChatFollowupResult.STALE, store.chooseMemoryBookChatFollowup(
            "account", generation, "family", reading.readerScopeId, bookId, 1,
            storyId, 3, conversationId, 1, turn.id, question))
    }

    @Test fun currentChapterQuestionOnlyEditsTheSelectedThreadUntilExplicitSend() = runTest {
        val community = CommunityApi().apply { existingConversation = true }
        val api = StoryApi()
        val store = newStore(api, community)
        openBookReader(store)
        val context = store.memoryBookChapterDiscussionContext()!!
        val reads = community.callOrder.toList()
        val childReads = api.childReads.toList()
        assertEquals("Morning", context.chapterTitle)
        assertEquals(MemoryChatFollowupResult.SELECTED, store.chooseMemoryBookChapterDiscussion(context, true))
        val chat = store.state.value.memoryBooks!!.companion!!
        assertTrue(chat.draft.contains("《Garden》的第 1 篇章“Morning”"))
        assertTrue(chat.draft.contains("不要编造经历或对白"))
        assertFalse(chat.draft.contains("A walk in the garden."))
        assertEquals(chat.draft, chat.threadDrafts[conversationId])
        assertEquals(1, chat.chatDraftFocusRequestId)
        assertEquals(reads, community.callOrder)
        assertEquals(childReads, api.childReads)
        assertEquals(0, community.startedPosts)
        assertTrue(community.sentBodies.isEmpty())
        store.sendMemoryBookChat(); runCurrent()
        assertEquals(chat.draft, Json.parseToJsonElement(community.sentBodies.single()).jsonObject
            .getValue("text").jsonPrimitive.content)
    }

    @Test fun chapterQuestionRejectsChangedChapterAndForgedSnapshot() = runTest {
        val community = CommunityApi().apply { existingConversation = true }
        val store = newStore(StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }, community)
        openBookReader(store)
        val first = store.memoryBookChapterDiscussionContext()!!
        assertEquals(MemoryChatFollowupResult.STALE,
            store.chooseMemoryBookChapterDiscussion(first.copy(chapterTitle = "Invented"), true))
        assertEquals(MemoryChatFollowupResult.STALE,
            store.chooseMemoryBookChapterDiscussion(first.copy(accountId = "another-account"), true))
        store.loadMemoryBookChapter(1); runCurrent()
        assertEquals(MemoryChatFollowupResult.STALE, store.chooseMemoryBookChapterDiscussion(first, true))
        val second = store.memoryBookChapterDiscussionContext()!!
        assertEquals("chapter-2", second.chapterId)
        assertEquals(MemoryChatFollowupResult.SELECTED, store.chooseMemoryBookChapterDiscussion(second, false))
        assertTrue(store.state.value.memoryBooks!!.companion!!.draft.contains("chapter 2: “Afternoon”"))
        assertTrue(community.sentBodies.isEmpty())
        store.closeMemoryBook()
        assertNull(store.memoryBookChapterDiscussionContext())
        assertEquals(MemoryChatFollowupResult.STALE, store.chooseMemoryBookChapterDiscussion(second, false))
    }

    @Test fun chapterQuestionPreservesTypedInputAndUncertainSend() = runTest {
        val community = CommunityApi().apply { existingConversation = true }
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        val context = store.memoryBookChapterDiscussionContext()!!
        val draft = "我还没说完这段回忆"
        store.updateMemoryBookChatDraft(draft)
        assertEquals(MemoryChatFollowupResult.BLOCKED, store.chooseMemoryBookChapterDiscussion(context, true))
        assertEquals(draft, store.state.value.memoryBooks!!.companion!!.draft)
        community.failNextBookTurn = true
        store.sendMemoryBookChat(); runCurrent()
        assertNotNull(store.state.value.memoryBooks!!.companion!!.pendingTurn)
        val sent = community.sentBodies.toList()
        assertEquals(MemoryChatFollowupResult.BLOCKED, store.chooseMemoryBookChapterDiscussion(context, true))
        assertEquals(sent, community.sentBodies)
        assertEquals(draft, store.state.value.memoryBooks!!.companion!!.pendingTurn!!.text)
    }

    @Test fun chapterQuestionNeedsLoadedThreadAndRejectsRunningTurn() = runTest {
        val noThread = newStore(StoryApi(), CommunityApi())
        openBookReader(noThread)
        assertNull(noThread.memoryBookChapterDiscussionContext())
        val community = CommunityApi().apply { existingConversation = true; existingActiveTurn = true }
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        val context = store.memoryBookChapterDiscussionContext()!!
        assertEquals(MemoryChatFollowupResult.BLOCKED, store.chooseMemoryBookChapterDiscussion(context, true))
        assertEquals("", store.state.value.memoryBooks!!.companion!!.draft)
        assertTrue(community.sentBodies.isEmpty())
    }

    @Test fun chapterQuestionPreservesAnUnreviewedVoiceTranscript() = runTest {
        val community = CommunityApi().apply { existingConversation = true }
        val store = newStore(StoryApi().apply { voiceEnabled = true }, community)
        openBookReader(store)
        val context = store.memoryBookChapterDiscussionContext()!!
        val dictation = store.memoryBookChatDictation()!!
        dictation.loadCapabilities(); runCurrent()
        assertNotNull(dictation.beginRecording())
        dictation.stopRecording(instructionWav()); runCurrent()
        assertNotNull(dictation.state.value.transcript)
        assertEquals(MemoryChatFollowupResult.BLOCKED, store.chooseMemoryBookChapterDiscussion(context, true))
        assertNotNull(dictation.state.value.transcript)
        assertEquals("", store.state.value.memoryBooks!!.companion!!.draft)
        assertTrue(community.sentBodies.isEmpty())
    }

    @Test fun bookShelfNegotiatesCapabilitiesThenReadsChildrenInCurrentOrder() = runTest {
        val community = CommunityApi()
        val api = StoryApi()
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        assertEquals(listOf("capabilities", "books"), community.callOrder)
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        assertEquals(listOf(storyId), api.childReads)
        store.loadMemoryBookStory(1); runCurrent()
        assertEquals(listOf(storyId, secondStoryId), api.childReads)
        assertEquals(3, community.bookReads)
        assertEquals(secondStoryId, store.state.value.memoryBooks?.story?.id)
        assertEquals(1, store.state.value.memoryBooks?.storyIndex)
    }

    @Test fun memoirEditorialChoiceChecksWithoutSendingThenFreezesTheSameRetry() = runTest {
        val community = CommunityApi().apply { existingConversation = true }
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        store.updateMemoryBookChatDraft("把这段开篇和家人的讲述联系起来")
        assertEquals(MemoryBookChatEditorialContext.BASIC, store.state.value.memoryBooks?.companion?.editorialContext)
        assertEquals(0, community.planReads)
        store.chooseMemoryBookChatEditorialContext(true); runCurrent()
        assertEquals(1, community.planReads)
        assertEquals(MemoryBookChatEditorialContext.READY, store.state.value.memoryBooks?.companion?.editorialContext)
        assertEquals("把这段开篇和家人的讲述联系起来", store.state.value.memoryBooks?.companion?.draft)
        assertTrue(community.turnEditorialChoices.isEmpty())
        community.failNextBookTurn = true
        store.sendMemoryBookChat(); runCurrent()
        val pending = store.state.value.memoryBooks?.companion?.pendingTurn!!
        assertTrue(pending.editorialContext)
        store.chooseMemoryBookChatEditorialContext(false); runCurrent()
        assertEquals(pending, store.state.value.memoryBooks?.companion?.pendingTurn)
        assertEquals(MemoryBookChatEditorialContext.READY, store.state.value.memoryBooks?.companion?.editorialContext)
        store.retryMemoryBookChatTurn(); runCurrent()
        assertEquals(listOf(true, true), community.turnEditorialChoices)
        assertEquals(listOf(pending.mutationId, pending.mutationId), community.turnMutationIds)
        assertEquals(community.sentBodies.first(), community.sentBodies.last())
    }

    @Test fun memoirEditorialPreflightRejectsWithoutDowngradingOrLosingDraft() = runTest {
        for ((status, expected) in listOf(503 to MemoryBookChatEditorialContext.UNAVAILABLE,
                409 to MemoryBookChatEditorialContext.CHANGED, 422 to MemoryBookChatEditorialContext.SMALLER_SCOPE)) {
            val community = CommunityApi().apply { existingConversation = true; planFailure = ApiFailure(FailureKind.HTTP, status) }
            val store = newStore(StoryApi(), community)
            openBookReader(store)
            store.updateMemoryBookChatDraft("尚未发送的家人回忆")
            store.chooseMemoryBookChatEditorialContext(true); runCurrent()
            assertEquals(expected, store.state.value.memoryBooks?.companion?.editorialContext)
            store.sendMemoryBookChat(); runCurrent()
            assertTrue(community.turnEditorialChoices.isEmpty())
            assertEquals("尚未发送的家人回忆", store.state.value.memoryBooks?.companion?.draft)
            store.chooseMemoryBookChatEditorialContext(false)
            store.sendMemoryBookChat(); runCurrent()
            assertEquals(listOf(false), community.turnEditorialChoices)
            store.closeMemoryBooks()
        }
    }

    @Test fun deferredMemoirPlanBlocksSendingAndCannotChooseAReopenedReader() = runTest {
        val gate = CompletableDeferred<Unit>()
        val community = CommunityApi().apply { existingConversation = true; planGate = gate }
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        store.updateMemoryBookChatDraft("检查期间的草稿")
        store.chooseMemoryBookChatEditorialContext(true); runCurrent()
        assertEquals(MemoryBookChatEditorialContext.CHECKING, store.state.value.memoryBooks?.companion?.editorialContext)
        store.sendMemoryBookChat(); runCurrent()
        assertTrue(community.turnEditorialChoices.isEmpty())
        store.closeMemoryBook()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        gate.complete(Unit); runCurrent()
        assertEquals(MemoryBookChatEditorialContext.BASIC, store.state.value.memoryBooks?.companion?.editorialContext)
        assertFalse(store.state.value.memoryBooks?.companion?.busy ?: true)
    }

    @Test fun memoirConversationAndDraftSurviveEssayNavigationAndRetryUsesSameMutation() = runTest {
        val community = CommunityApi()
        val api = StoryApi()
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        assertEquals(bookId, store.state.value.memoryBooks?.companion?.bookId)
        store.queueMemoryBookConversation(); runCurrent()
        assertEquals(listOf("book" to bookId), community.startedTargets)
        store.updateMemoryBookChatDraft("继续聊花园")
        community.failNextBookTurn = true
        store.sendMemoryBookChat(); runCurrent()
        val pending = store.state.value.memoryBooks?.companion?.pendingTurn
        assertNotNull(pending)
        val postsBeforeBlockedNewChat = community.startedPosts
        store.queueMemoryBookConversation(); runCurrent()
        assertEquals(postsBeforeBlockedNewChat, community.startedPosts)
        assertEquals(pending, store.state.value.memoryBooks?.companion?.pendingTurn)
        store.updateMemoryBookChatDraft("下一条未发送草稿")
        store.loadMemoryBookStory(1); runCurrent()
        assertEquals("下一条未发送草稿", store.state.value.memoryBooks?.companion?.draft)
        assertEquals(pending, store.state.value.memoryBooks?.companion?.pendingTurn)
        store.retryMemoryBookChatTurn(); runCurrent()
        assertEquals(2, community.turnMutationIds.size)
        assertEquals(community.turnMutationIds.first(), community.turnMutationIds.last())
        assertEquals("queued", store.state.value.memoryBooks?.companion?.job?.state)
        store.closeMemoryBook()
        assertNull(store.state.value.memoryBooks?.companion)
    }

    @Test fun closingReaderWhileConversationListIsDeferredCannotPublishLateBookState() = runTest {
        val gate = CompletableDeferred<Unit>()
        val community = CommunityApi().apply { conversationGate = gate }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertEquals(1, community.conversationReads)
        store.closeMemoryBook()
        gate.complete(Unit)
        runCurrent()
        assertNull(store.state.value.memoryBooks?.selectedBook)
        assertNull(store.state.value.memoryBooks?.companion)
    }

    @Test fun closeBeforeChatCoroutineDispatchPreventsConversationPost() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        store.queueMemoryBookConversation()
        store.closeMemoryBook()
        runCurrent()
        assertEquals(0, community.startedPosts)
        assertNull(store.state.value.memoryBooks?.companion)
    }

    @Test fun deniedConversationReadCannotRepopulateInvalidatedReader() = runTest {
        val community = CommunityApi().apply { conversationFailure = ApiFailure(FailureKind.HTTP, 403) }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertNull(store.state.value.memoryBooks)
        runCurrent()
        assertNull(store.state.value.memoryBooks)
    }

    @Test fun deferredTurnsAfterLogoutCannotRestoreMemoirConversation() = runTest {
        val gate = CompletableDeferred<Unit>()
        val community = CommunityApi().apply {
            existingConversation = true
            turnGate = gate
        }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertEquals(1, community.turnPages.size)
        store.logout(); runCurrent()
        gate.complete(Unit)
        runCurrent()
        assertNull(store.state.value.memoryBooks)
        assertNull(store.state.value.session)
    }

    @Test fun deniedFreshStoryTurnsClearRememberedSelectionAndRequireFreshReader() = runTest {
        for (status in listOf(401, 403)) {
            val api = StoryApi()
            val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
            val store = newStore(api, community)
            openStory(store)
            store.selectMemoryConversation(secondConversationId); runCurrent()
            store.closeSavedMemoryStoryDetail()
            community.turnFailure = ApiFailure(FailureKind.HTTP, status)

            store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()

            assertNull(store.state.value.savedMemoryStories)
            if (store.state.value.covered) store.foreground()
            else if (store.state.value.library == null) store.selectLibrary("family")
            runCurrent()
            store.openSavedMemoryStories(); runCurrent()
            store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()
            val chat = store.state.value.savedMemoryStories!!.community!!
            assertEquals(conversationId, chat.conversationId)
            assertFalse("HTTP $status must not restore the invalidated hint", chat.conversationRestored)
            assertEquals("", chat.chatDraft)
            assertTrue(community.sentBodies.isEmpty())
            assertEquals(0, community.startedPosts)
        }
    }

    @Test fun deniedFreshMemoirTurnsClearRememberedSelectionAndRequireFreshReader() = runTest {
        val api = StoryApi()
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(api, community)
        openBookReader(store)
        store.selectMemoryBookConversation(secondConversationId); runCurrent()
        store.closeMemoryBook()
        community.turnFailure = ApiFailure(FailureKind.HTTP, 403)

        store.openMemoryBook(bookId); runCurrent()

        assertTrue("HTTP 403 must cover the protected reader", store.state.value.covered)
        assertNull(store.state.value.memoryBooks)
        store.foreground(); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        val chat = store.state.value.memoryBooks!!.companion!!
        assertEquals(conversationId, chat.conversationId)
        assertFalse(chat.conversationRestored)
        assertEquals("", chat.draft)
        assertTrue(community.sentBodies.isEmpty())
        assertEquals(0, community.startedPosts)
    }

    @Test fun staleStoryTurnDenialCannotClearTheReopenedRestoredReader() = runTest {
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.selectMemoryConversation(secondConversationId); runCurrent()
        store.closeSavedMemoryStoryDetail()

        val staleGate = CompletableDeferred<Unit>()
        community.turnGate = staleGate
        community.turnFailure = ApiFailure(FailureKind.HTTP, 403)
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()
        assertEquals(secondConversationId, community.turnConversationIds.last())
        store.closeSavedMemoryStoryDetail()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()
        assertEquals(secondConversationId, store.state.value.savedMemoryStories?.community?.conversationId)
        assertTrue(store.state.value.savedMemoryStories?.community?.conversationRestored == true)

        staleGate.complete(Unit); runCurrent()

        assertFalse(store.state.value.covered)
        assertEquals(storyId, store.state.value.savedMemoryStories?.detail?.id)
        val chat = store.state.value.savedMemoryStories!!.community!!
        assertEquals(secondConversationId, chat.conversationId)
        assertTrue(chat.conversationRestored)
        assertTrue(community.sentBodies.isEmpty())
        assertEquals(0, community.startedPosts)
    }

    @Test fun staleMemoirTurnDenialCannotClearTheReopenedRestoredReader() = runTest {
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        store.selectMemoryBookConversation(secondConversationId); runCurrent()
        store.closeMemoryBook()

        val staleGate = CompletableDeferred<Unit>()
        community.turnGate = staleGate
        community.turnFailure = ApiFailure(FailureKind.HTTP, 401)
        store.openMemoryBook(bookId); runCurrent()
        assertEquals(secondConversationId, community.turnConversationIds.last())
        store.closeMemoryBook()
        store.openMemoryBook(bookId); runCurrent()
        assertEquals(secondConversationId, store.state.value.memoryBooks?.companion?.conversationId)
        assertTrue(store.state.value.memoryBooks?.companion?.conversationRestored == true)

        staleGate.complete(Unit); runCurrent()

        assertFalse(store.state.value.covered)
        assertEquals(bookId, store.state.value.memoryBooks?.selectedBook?.id)
        val chat = store.state.value.memoryBooks!!.companion!!
        assertEquals(secondConversationId, chat.conversationId)
        assertTrue(chat.conversationRestored)
        assertTrue(community.sentBodies.isEmpty())
        assertEquals(0, community.startedPosts)
    }

    @Test fun deferredOldRevisionCannotOverwriteReopenedMemoirAndLibraryChangeDropsLateResult() = runTest {
        val firstGate = CompletableDeferred<Unit>()
        val community = CommunityApi().apply { conversationGate = firstGate }
        val api = StoryApi().apply { availableLibraries = listOf("family", "other") }
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.closeMemoryBook()
        community.bookRevision = "2"
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertEquals(2L, store.state.value.memoryBooks?.selectedBook?.revision)
        assertEquals(2L, store.state.value.memoryBooks?.companion?.bookRevision)
        firstGate.complete(Unit)
        runCurrent()
        assertEquals(2L, store.state.value.memoryBooks?.selectedBook?.revision)
        assertEquals(2L, store.state.value.memoryBooks?.companion?.bookRevision)

        val libraryGate = CompletableDeferred<Unit>()
        community.conversationGate = libraryGate
        store.closeMemoryBook()
        store.openMemoryBook(bookId); runCurrent()
        store.selectLibrary("other"); runCurrent()
        libraryGate.complete(Unit)
        runCurrent()
        assertEquals("other", store.state.value.library)
        assertNull(store.state.value.memoryBooks)
    }

    @Test fun deferredTurnsAfterReaderCloseAndReopenDoNotReplaceNewRevision() = runTest {
        val oldTurnsGate = CompletableDeferred<Unit>()
        val community = CommunityApi().apply {
            existingConversation = true
            turnGate = oldTurnsGate
        }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.closeMemoryBook()
        oldTurnsGate.complete(Unit)
        runCurrent()
        assertNull(store.state.value.memoryBooks?.selectedBook)
        store.openMemoryBooks(); runCurrent()
        community.existingConversation = false
        store.openMemoryBook(bookId); runCurrent()
        assertEquals(1L, store.state.value.memoryBooks?.selectedBook?.revision)
        assertNull(store.state.value.memoryBooks?.companion?.conversationId)
    }

    @Test fun pendingTurnFreezesConversationIdentity() = runTest {
        val community = CommunityApi().apply { existingConversation = true }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        store.updateMemoryBookChatDraft("same conversation retry")
        community.failNextBookTurn = true
        store.sendMemoryBookChat(); runCurrent()
        val frozen = store.state.value.memoryBooks?.companion?.pendingTurn
        assertNotNull(frozen)
        val postsBeforeNewChat = community.startedPosts
        store.queueMemoryBookConversation(); runCurrent()
        store.selectMemoryBookConversation("99999999-9999-9999-9999-999999999999"); runCurrent()
        assertEquals(postsBeforeNewChat, community.startedPosts)
        assertEquals(frozen, store.state.value.memoryBooks?.companion?.pendingTurn)
        assertEquals(conversationId, store.state.value.memoryBooks?.companion?.pendingTurnConversationId)
    }

    @Test fun composerDraftsStayWithEachStoryAndMemoirConversationAndNewThreadStartsBlank() = runTest {
        val community = CommunityApi().apply {
            existingConversation = true
            extraConversationIds = listOf(secondConversationId)
        }
        val api = StoryApi()
        val store = newStore(api, community)
        openStory(store)
        store.updateMemoryChatDraft("story draft one")
        store.selectMemoryConversation(secondConversationId); runCurrent()
        assertEquals("", store.state.value.savedMemoryStories?.community?.chatDraft)
        store.updateMemoryChatDraft("story draft two")
        store.selectMemoryConversation(conversationId); runCurrent()
        assertEquals("story draft one", store.state.value.savedMemoryStories?.community?.chatDraft)
        store.selectMemoryConversation(secondConversationId); runCurrent()
        assertEquals("story draft two", store.state.value.savedMemoryStories?.community?.chatDraft)

        val bookStore = newStore(StoryApi(), community)
        bookStore.authenticate("+12025550123", "synthetic-password"); runCurrent()
        bookStore.openMemoryBooks(); runCurrent()
        bookStore.openMemoryBook(bookId); runCurrent()
        bookStore.loadMemoryBookStory(0); runCurrent()
        bookStore.updateMemoryBookChatDraft("memoir draft one")
        bookStore.selectMemoryBookConversation(secondConversationId); runCurrent()
        assertEquals("", bookStore.state.value.memoryBooks?.companion?.draft)
        bookStore.updateMemoryBookChatDraft("memoir draft two")
        bookStore.selectMemoryBookConversation(conversationId); runCurrent()
        assertEquals("memoir draft one", bookStore.state.value.memoryBooks?.companion?.draft)
        bookStore.queueMemoryBookConversation(); runCurrent()
        assertEquals("", bookStore.state.value.memoryBooks?.companion?.draft)
        bookStore.selectMemoryBookConversation(conversationId); runCurrent()
        assertEquals("memoir draft one", bookStore.state.value.memoryBooks?.companion?.draft)
        bookStore.closeMemoryBook()
        bookStore.openMemoryBook(bookId); runCurrent()
        bookStore.loadMemoryBookStory(0); runCurrent()
        assertEquals(emptyMap<String, String>(), bookStore.state.value.memoryBooks?.companion?.threadDrafts)
        assertEquals("", bookStore.state.value.memoryBooks?.companion?.draft)
    }

    @Test fun delayedStoryAndMemoirThreadChangesKeepLateDraftEditsOnTheirOriginThread() = runTest {
        val community = CommunityApi().apply {
            existingConversation = true
            extraConversationIds = listOf(secondConversationId)
        }
        val storyStore = newStore(StoryApi(), community)
        openStory(storyStore)
        storyStore.updateMemoryChatDraft("story before switch")
        val storySelectGate = CompletableDeferred<Unit>()
        community.turnGate = storySelectGate
        storyStore.selectMemoryConversation(secondConversationId); runCurrent()
        assertTrue(storyStore.state.value.savedMemoryStories?.community?.busy == true)
        storyStore.updateMemoryChatDraft("story edited during switch")
        storySelectGate.complete(Unit); runCurrent()
        var storyChat = storyStore.state.value.savedMemoryStories!!.community!!
        assertEquals(secondConversationId, storyChat.conversationId)
        assertEquals("", storyChat.chatDraft)
        assertEquals("story edited during switch", storyChat.threadDrafts[conversationId])
        storyStore.selectMemoryConversation(conversationId); runCurrent()
        assertEquals("story edited during switch", storyStore.state.value.savedMemoryStories?.community?.chatDraft)

        storyStore.updateMemoryChatDraft("story before creation")
        val storyCreateGate = CompletableDeferred<Unit>()
        community.turnGate = storyCreateGate
        storyStore.startMemoryConversation(); runCurrent()
        storyStore.updateMemoryChatDraft("story edited during creation")
        storyCreateGate.complete(Unit); runCurrent()
        storyChat = storyStore.state.value.savedMemoryStories!!.community!!
        val newStoryConversation = storyChat.conversationId!!
        assertNotEquals(conversationId, newStoryConversation)
        assertEquals("", storyChat.chatDraft)
        assertEquals("story edited during creation", storyChat.threadDrafts[conversationId])
        storyStore.selectMemoryConversation(conversationId); runCurrent()
        assertEquals("story edited during creation", storyStore.state.value.savedMemoryStories?.community?.chatDraft)

        val bookStore = newStore(StoryApi(), community)
        bookStore.authenticate("+12025550123", "synthetic-password"); runCurrent()
        bookStore.openMemoryBooks(); runCurrent()
        bookStore.openMemoryBook(bookId); runCurrent()
        bookStore.loadMemoryBookStory(0); runCurrent()
        bookStore.updateMemoryBookChatDraft("memoir before switch")
        val bookSelectGate = CompletableDeferred<Unit>()
        community.turnGate = bookSelectGate
        bookStore.selectMemoryBookConversation(secondConversationId); runCurrent()
        assertTrue(bookStore.state.value.memoryBooks?.companion?.busy == true)
        bookStore.updateMemoryBookChatDraft("memoir edited during switch")
        bookSelectGate.complete(Unit); runCurrent()
        var bookChat = bookStore.state.value.memoryBooks?.companion!!
        assertEquals(secondConversationId, bookChat.conversationId)
        assertEquals("", bookChat.draft)
        assertEquals("memoir edited during switch", bookChat.threadDrafts[conversationId])
        bookStore.selectMemoryBookConversation(conversationId); runCurrent()
        assertEquals("memoir edited during switch", bookStore.state.value.memoryBooks?.companion?.draft)

        bookStore.updateMemoryBookChatDraft("memoir before creation")
        val bookCreateGate = CompletableDeferred<Unit>()
        community.turnGate = bookCreateGate
        bookStore.queueMemoryBookConversation(); runCurrent()
        bookStore.updateMemoryBookChatDraft("memoir edited during creation")
        bookCreateGate.complete(Unit); runCurrent()
        bookChat = bookStore.state.value.memoryBooks?.companion!!
        val newBookConversation = bookChat.conversationId!!
        assertNotEquals(conversationId, newBookConversation)
        assertEquals("", bookChat.draft)
        assertEquals("memoir edited during creation", bookChat.threadDrafts[conversationId])
        bookStore.selectMemoryBookConversation(conversationId); runCurrent()
        assertEquals("memoir edited during creation", bookStore.state.value.memoryBooks?.companion?.draft)
    }

    @Test fun selectedStoryChatTurnSeedsReviewWithoutPostingAndKeepsConsentExplicit() = runTest {
        val words = "我记得湖边那天，爸爸带了红色的毯子。"
        val community = CommunityApi().apply { existingConversation = true; chatTurnText = words }
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.selectMemoryCommunityTab(1)
        val current = store.state.value.savedMemoryStories!!.community!!
        val turn = current.turns!!.items.single()
        val startsBefore = community.startedPosts
        val bodiesBefore = community.sentBodies.size

        assertEquals(MemoryChatTurnSeedResult.SEEDED, store.keepMemoryChatTurnAsContribution(
            "family", storyId, 3, store.state.value.generation, current.readerScopeId, conversationId, turn.id))
        val review = store.state.value.savedMemoryStories!!.community!!
        assertEquals(0, review.tab)
        assertEquals(words, review.contributionDraft)
        assertFalse(review.contributionConsent)
        assertFalse(review.audioConsent)
        assertTrue(review.chatTurnContributionSeeded)
        assertTrue(review.contributionWholeStory)
        store.updateMemoryContributionWholeStory(false)
        assertTrue(store.state.value.savedMemoryStories!!.community!!.contributionWholeStory)
        assertEquals(1, review.contributionFocusRequestId)
        assertEquals(startsBefore, community.startedPosts)
        assertEquals(bodiesBefore, community.sentBodies.size)

        store.updateMemoryContributionConsent(textConsent = true)
        store.submitMemoryText(words, "zh", "家人", consent = true)
        runCurrent()
        val sent = Json.parseToJsonElement(community.sentBodies.single()).jsonObject
        assertEquals(words, sent.getValue("text").jsonPrimitive.content)
        assertEquals("", sent.getValue("byline").jsonPrimitive.content)
        assertEquals("", sent.getValue("chapter_id").jsonPrimitive.content)
        assertEquals("1", sent.getValue("consent").jsonPrimitive.content)
        assertFalse(store.state.value.savedMemoryStories?.community?.chatTurnContributionSeeded ?: true)
    }

    @Test fun selectedStoryChatTurnImportBlocksExistingDraftConsentAudioAndChatWork() = runTest {
        val community = CommunityApi().apply { existingConversation = true; chatTurnText = "Only the user's words" }
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.selectMemoryCommunityTab(1)
        val reader = store.state.value.savedMemoryStories!!.community!!
        val turnId = reader.turns!!.items.single().id
        fun transfer() = store.keepMemoryChatTurnAsContribution(
            "family", storyId, 3, store.state.value.generation, reader.readerScopeId, conversationId, turnId)

        store.updateMemoryContributionDraft("existing contribution draft")
        assertEquals(MemoryChatTurnSeedResult.BLOCKED, transfer())
        assertEquals("existing contribution draft", store.state.value.savedMemoryStories?.community?.contributionDraft)
        store.updateMemoryContributionDraft("")
        store.updateMemoryContributionConsent(textConsent = true)
        assertEquals(MemoryChatTurnSeedResult.BLOCKED, transfer())
        assertTrue(store.state.value.savedMemoryStories?.community?.contributionConsent == true)
        store.updateMemoryContributionConsent(textConsent = false, audioConsent = true)
        assertEquals(MemoryChatTurnSeedResult.BLOCKED, transfer())
        assertTrue(store.state.value.savedMemoryStories?.community?.audioConsent == true)
        store.updateMemoryContributionConsent(audioConsent = false)
        val audioScopeGeneration = store.state.value.generation
        store.setMemoryContributionAudioBusy("family", storyId, 3, audioScopeGeneration, reader.readerScopeId, "capture-one", true)
        store.selectMemoryCommunityTab(0)
        assertEquals(1, store.state.value.savedMemoryStories?.community?.tab)
        assertEquals(MemoryChatTurnSeedResult.BLOCKED, transfer())
        store.setMemoryContributionAudioBusy("family", storyId, 3, audioScopeGeneration, reader.readerScopeId, "capture-one", false)
        store.updateMemoryChatDraft("unsent message")
        assertEquals(MemoryChatTurnSeedResult.BLOCKED, transfer())
        assertEquals("unsent message", store.state.value.savedMemoryStories?.community?.chatDraft)
        store.updateMemoryChatDraft("")

        community.failNextBookTurn = true
        store.updateMemoryChatDraft("frozen retry words")
        store.sendMemoryChat(); runCurrent()
        val pending = store.state.value.savedMemoryStories?.community?.pendingTurn
        assertNotNull(pending)
        assertEquals(MemoryChatTurnSeedResult.BLOCKED, transfer())
        assertEquals(pending, store.state.value.savedMemoryStories?.community?.pendingTurn)
        assertEquals("", store.state.value.savedMemoryStories?.community?.contributionDraft)
    }

    @Test fun chatTurnImportRejectsActiveJobsMissingCapabilityMemoirAndStaleScope() = runTest {
        val active = CommunityApi().apply { existingConversation = true; existingActiveTurn = true }
        val activeStore = newStore(StoryApi(), active)
        openStory(activeStore)
        activeStore.selectMemoryCommunityTab(1)
        val activeReader = activeStore.state.value.savedMemoryStories!!.community!!
        val activeTurnId = activeReader.turns!!.items.single().id
        assertEquals(MemoryChatTurnSeedResult.BLOCKED, activeStore.keepMemoryChatTurnAsContribution(
            "family", storyId, 3, activeStore.state.value.generation, activeReader.readerScopeId, conversationId, activeTurnId))
        assertEquals("", activeStore.state.value.savedMemoryStories?.community?.contributionDraft)

        val disabled = CommunityApi().apply { existingConversation = true; chatTurnText = "story words"; contributionsEnabled = false }
        val disabledStore = newStore(StoryApi(), disabled)
        openStory(disabledStore)
        disabledStore.selectMemoryCommunityTab(1)
        val disabledReader = disabledStore.state.value.savedMemoryStories!!.community!!
        val disabledTurnId = disabledReader.turns!!.items.single().id
        assertEquals(MemoryChatTurnSeedResult.BLOCKED, disabledStore.keepMemoryChatTurnAsContribution(
            "family", storyId, 3, disabledStore.state.value.generation, disabledReader.readerScopeId, conversationId, disabledTurnId))

        val memoirOnly = newStore(StoryApi(), CommunityApi().apply { existingConversation = true })
        memoirOnly.authenticate("+12025550123", "synthetic-password"); runCurrent()
        memoirOnly.openMemoryBooks(); runCurrent()
        memoirOnly.openMemoryBook(bookId); runCurrent()
        assertEquals(MemoryChatTurnSeedResult.STALE, memoirOnly.keepMemoryChatTurnAsContribution(
            "family", storyId, 3, memoirOnly.state.value.generation, 0, conversationId, "88888888-8888-4888-8888-888888888888"))

        val scoped = CommunityApi().apply { existingConversation = true; chatTurnText = "story words" }
        val scopedStore = newStore(StoryApi(), scoped)
        openStory(scopedStore)
        scopedStore.selectMemoryCommunityTab(1)
        val scopedReader = scopedStore.state.value.savedMemoryStories!!.community!!
        val scopedTurnId = scopedReader.turns!!.items.single().id
        assertEquals(MemoryChatTurnSeedResult.STALE, scopedStore.keepMemoryChatTurnAsContribution(
            "another-library", storyId, 3, scopedStore.state.value.generation, scopedReader.readerScopeId, conversationId, scopedTurnId))
        scopedStore.closeSavedMemoryStoryDetail()
        assertEquals(MemoryChatTurnSeedResult.STALE, scopedStore.keepMemoryChatTurnAsContribution(
            "family", storyId, 3, scopedStore.state.value.generation, scopedReader.readerScopeId, conversationId, scopedTurnId))
    }

    @Test fun staleRecorderDisposalCannotClearReopenedOrReauthenticatedStoryCapture() = runTest {
        val store = newStore(StoryApi(), CommunityApi().apply {
            existingConversation = true
            chatTurnText = "current story words"
        })
        openStory(store)
        val oldGeneration = store.state.value.generation
        val oldReader = store.state.value.savedMemoryStories!!.community!!
        val oldConversationId = oldReader.conversationId!!
        val oldTurnId = oldReader.turns!!.items.single().id
        store.setMemoryContributionAudioBusy("family", storyId, 3, oldGeneration, oldReader.readerScopeId, "old-recorder", true)
        assertTrue(store.state.value.savedMemoryStories?.community?.contributionAudioBusy == true)

        store.closeSavedMemoryStoryDetail()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.single()); runCurrent()
        val reopenedGeneration = store.state.value.generation
        assertEquals(oldGeneration, reopenedGeneration)
        val reopenedReader = store.state.value.savedMemoryStories?.community!!
        assertNotEquals(oldReader.readerScopeId, reopenedReader.readerScopeId)
        store.selectMemoryCommunityTab(1)
        assertEquals(oldConversationId, reopenedReader.conversationId)
        assertEquals(oldTurnId, reopenedReader.turns?.items?.single()?.id)
        assertEquals(MemoryChatTurnSeedResult.STALE, store.keepMemoryChatTurnAsContribution(
            "family", storyId, 3, reopenedGeneration, oldReader.readerScopeId, oldConversationId, oldTurnId))
        assertEquals("", store.state.value.savedMemoryStories?.community?.contributionDraft)
        // Both callback edges from the old recorder are inert even before the new instance claims activity.
        store.setMemoryContributionAudioBusy("family", storyId, 3, oldGeneration, oldReader.readerScopeId, "old-recorder", true)
        store.setMemoryContributionAudioBusy("family", storyId, 3, oldGeneration, oldReader.readerScopeId, "old-recorder", false)
        assertFalse(store.state.value.savedMemoryStories?.community?.contributionAudioBusy ?: true)
        store.selectMemoryCommunityTab(0)
        store.setMemoryContributionAudioBusy("family", storyId, 3, reopenedGeneration, reopenedReader.readerScopeId, "new-recorder", true)
        store.setMemoryContributionAudioBusy("family", storyId, 3, oldGeneration, oldReader.readerScopeId, "old-recorder", false)
        val reopened = store.state.value.savedMemoryStories?.community!!
        assertTrue(reopened.contributionAudioBusy)
        assertEquals("new-recorder", reopened.contributionAudioActivityId)
        store.setMemoryContributionAudioBusy("family", storyId, 3, reopenedGeneration, reopenedReader.readerScopeId, "new-recorder", false)
        assertFalse(store.state.value.savedMemoryStories?.community?.contributionAudioBusy ?: true)

        store.logout(); runCurrent()
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.single()); runCurrent()
        val newAccountGeneration = store.state.value.generation
        assertTrue(newAccountGeneration > oldGeneration)
        store.selectMemoryCommunityTab(1)
        val currentReader = store.state.value.savedMemoryStories?.community!!
        val currentTurnId = currentReader.turns?.items?.single()?.id
        assertNotNull(currentTurnId)
        assertEquals(MemoryChatTurnSeedResult.STALE, store.keepMemoryChatTurnAsContribution(
            "family", storyId, 3, oldGeneration, currentReader.readerScopeId, conversationId, currentTurnId!!))
        assertEquals("", store.state.value.savedMemoryStories?.community?.contributionDraft)
        store.setMemoryContributionAudioBusy("family", storyId, 3, oldGeneration, currentReader.readerScopeId, "old-recorder", false)
        assertFalse(store.state.value.savedMemoryStories?.community?.contributionAudioBusy ?: true)
    }

    @Test fun queuedActiveConversationBlocksThreadSelectionAndCreation() = runTest {
        val community = CommunityApi().apply {
            existingConversation = true
            existingActiveTurn = true
            extraConversationIds = listOf(secondConversationId)
        }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertEquals(conversationId, store.state.value.memoryBooks?.companion?.conversationId)
        assertEquals(jobId, store.state.value.memoryBooks?.companion?.job?.id)
        store.selectMemoryBookConversation(secondConversationId); runCurrent()
        store.queueMemoryBookConversation(); runCurrent()
        assertEquals(conversationId, store.state.value.memoryBooks?.companion?.conversationId)
        assertEquals(0, community.startedPosts)
    }

    @Test fun queuedTurnRemainsRefreshableWhenInitialJobFetchFails() = runTest {
        val community = CommunityApi().apply {
            existingConversation = true
            existingActiveTurn = true
            failNextJob = true
        }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertNull(store.state.value.memoryBooks?.companion?.job)
        assertTrue(store.state.value.memoryBooks?.companion?.turns?.items?.any { it.state == "queued" } == true)
        store.loadMemoryBookStory(0); runCurrent()
        store.refreshMemoryBookChat(); runCurrent()
        assertEquals("running", store.state.value.memoryBooks?.companion?.job?.state)
        assertEquals(2, community.jobReads)
    }

    @Test fun acceptedStoryAndMemoirChatsRecoverFromFreshHistoryAfterBackgroundWithoutRemoteCancel() = runTest {
        val storyApi = CommunityApi().apply {
            existingConversation = true
            existingActiveTurn = true
            activeTurnSequence = 35
            activeJobBaseRevision = "3"
        }
        val storyStore = newStore(StoryApi(), storyApi)
        openStory(storyStore)
        val acceptedStory = storyStore.state.value.savedMemoryStories?.community!!
        assertEquals(jobId, acceptedStory.job?.id)
        assertEquals("queued", acceptedStory.turns?.items?.single()?.state)
        val storyTurnReadsBeforeBackground = storyApi.turnPages.size

        storyStore.background()
        storyStore.foreground(); runCurrent()
        storyStore.openSavedMemoryStories(); runCurrent()
        storyStore.openSavedMemoryStory(summary); runCurrent()
        val recoveredStory = storyStore.state.value.savedMemoryStories?.community!!
        assertEquals(jobId, recoveredStory.job?.id)
        assertEquals(35, recoveredStory.turns?.items?.single()?.sequence)
        assertEquals("queued", recoveredStory.turns?.items?.single()?.state)
        assertTrue(storyApi.turnPages.size > storyTurnReadsBeforeBackground)
        assertEquals(0, storyApi.cancelJobReads)
        assertTrue(storyApi.sentBodies.isEmpty())

        val bookApi = CommunityApi().apply {
            existingConversation = true
            existingActiveTurn = true
            activeTurnSequence = 36
            activeJobBaseRevision = "1"
        }
        val bookStore = newStore(StoryApi(), bookApi)
        bookStore.authenticate("+12025550123", "synthetic-password"); runCurrent()
        bookStore.openMemoryBooks(); runCurrent()
        bookStore.openMemoryBook(bookId); runCurrent()
        val acceptedBook = bookStore.state.value.memoryBooks?.companion!!
        assertEquals(jobId, acceptedBook.job?.id)
        assertEquals("queued", acceptedBook.turns?.items?.single()?.state)
        val bookTurnReadsBeforeBackground = bookApi.turnPages.size

        bookStore.background()
        bookStore.foreground(); runCurrent()
        bookStore.openMemoryBooks(); runCurrent()
        bookStore.openMemoryBook(bookId); runCurrent()
        val recoveredBook = bookStore.state.value.memoryBooks?.companion!!
        assertEquals(jobId, recoveredBook.job?.id)
        assertEquals(36, recoveredBook.turns?.items?.single()?.sequence)
        assertEquals("queued", recoveredBook.turns?.items?.single()?.state)
        assertTrue(bookApi.turnPages.size > bookTurnReadsBeforeBackground)
        assertEquals(0, bookApi.cancelJobReads)
        assertTrue(bookApi.sentBodies.isEmpty())
    }

    @Test fun storyOpeningRecoversNewestPendingTurnAndRetryRefreshPreservesDraftAfterJobLookupFailure() = runTest {
        val community = CommunityApi().apply {
            existingConversation = true
            existingActiveTurn = true
            activeTurnSequence = 35
            activeJobBaseRevision = "3"
            failNextJob = true
        }
        val store = newStore(StoryApi(), community)
        openStory(store); runCurrent()
        val initial = store.state.value.savedMemoryStories?.community!!
        assertEquals(35, initial.turns?.items?.single()?.sequence)
        assertNull("failed exact-job GET leaves visible history available", initial.job)
        store.updateMemoryChatDraft("保留在当前对话的草稿")
        store.refreshMemoryChat(); runCurrent()
        val refreshed = store.state.value.savedMemoryStories?.community!!
        assertEquals("保留在当前对话的草稿", refreshed.chatDraft)
        assertEquals(jobId, refreshed.job?.id)
        assertEquals(35, refreshed.turns?.items?.single()?.sequence)
        store.sendMemoryChat()
        runCurrent()
        assertTrue("pending turn is recovered without sending a new turn", community.sentBodies.isEmpty())
    }

    @Test fun storyRejectsRecoveredJobsWithWrongKindOrBaseRevision() = runTest {
        for ((kind, revision) in listOf("narrative" to "3", "chat" to "2")) {
            val community = CommunityApi().apply {
                existingConversation = true
                existingActiveTurn = true
                activeTurnSequence = 35
                activeJobKind = kind
                activeJobBaseRevision = revision
            }
            val store = newStore(StoryApi(), community)
            openStory(store); runCurrent()
            val chat = store.state.value.savedMemoryStories?.community!!
            assertEquals(35, chat.turns?.items?.single()?.sequence)
            assertNull("$kind/$revision job must not be adopted", chat.job)
            store.updateMemoryChatDraft("still blocked")
            store.sendMemoryChat(); runCurrent()
            assertTrue(community.sentBodies.isEmpty())
        }
    }

    @Test fun memoirOpeningRejectsPendingJobsWithWrongKindOrBookRevision() = runTest {
        for ((kind, revision) in listOf("narrative" to "1", "chat" to "2")) {
            val community = CommunityApi().apply {
                existingConversation = true
                existingActiveTurn = true
                activeJobKind = kind
                activeJobBaseRevision = revision
            }
            val store = newStore(StoryApi(), community)
            store.authenticate("+12025550123", "synthetic-password"); runCurrent()
            store.openMemoryBooks(); runCurrent()
            store.openMemoryBook(bookId); runCurrent()
            val chat = store.state.value.memoryBooks?.companion!!
            assertTrue(chat.turns?.items?.single()?.state == "queued")
            assertNull("$kind/$revision job must not be adopted", chat.job)
        }
    }

    @Test fun latePendingJobLookupCannotRestoreClosedStoryConversation() = runTest {
        val gate = CompletableDeferred<Unit>()
        val community = CommunityApi().apply {
            existingConversation = true
            existingActiveTurn = true
            activeJobBaseRevision = "3"
            jobGate = gate
        }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(summary); runCurrent()
        assertEquals(1, community.jobReads)
        store.closeSavedMemoryStoryDetail()
        gate.complete(Unit); runCurrent()
        assertNull(store.state.value.savedMemoryStories?.detail)
        assertNull("late job response must not resurrect chat state", store.state.value.savedMemoryStories?.community)
    }

    @Test fun currentStoryPendingJobDenialUsesProtectedReadFailureHandling() = runTest {
        val community = CommunityApi().apply {
            existingConversation = true
            existingActiveTurn = true
            activeJobBaseRevision = "3"
            jobFailure = ApiFailure(FailureKind.HTTP, 403)
        }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(summary); runCurrent()
        assertEquals(1, community.jobReads)
        assertFalse("current job denial follows readFailure, not repository-wide invalidation", store.state.value.covered)
        assertNull(store.state.value.savedMemoryStories)
        assertEquals(Message.CLOSED, store.state.value.problem?.message)
    }

    @Test fun currentMemoirChatRefreshJobDenialUsesProtectedReadFailureHandling() = runTest {
        val community = CommunityApi().apply {
            existingConversation = true
            existingActiveTurn = true
            jobFailure = null
        }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        community.jobFailure = ApiFailure(FailureKind.HTTP, 403)
        store.refreshMemoryBookChat(); runCurrent()
        assertEquals(2, community.jobReads)
        assertFalse("current job denial follows readFailure, not repository-wide invalidation", store.state.value.covered)
        assertFalse("the retained memoir reader must not remain visually busy", store.state.value.memoryBooks?.companion?.busy ?: true)
        assertEquals(Message.CLOSED, store.state.value.problem?.message)
    }

    @Test fun staleBookPendingJobDenialIsDiscardedAfterReaderCloses() = runTest {
        lateinit var store: ConnectedStore
        val community = CommunityApi().apply {
            existingConversation = true
            existingActiveTurn = true
            jobFailure = ApiFailure(FailureKind.HTTP, 403)
            beforeJobFailure = { store.closeMemoryBook() }
        }
        store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertEquals(1, community.jobReads)
        assertNull("stale protected denial must be observed and discarded", community.jobFailure)
        assertFalse(store.state.value.covered)
        assertNull(store.state.value.memoryBooks?.selectedBook)
        assertNull(store.state.value.problem)
    }

    @Test fun repeatedSendWhileChatRequestIsBusyCannotReplaceFrozenTurnOrDraft() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        store.queueMemoryBookConversation()
        val pendingConversation = store.state.value.memoryBooks?.companion?.pendingConversation
        assertNotNull(pendingConversation)
        store.queueMemoryBookConversation()
        assertEquals(pendingConversation, store.state.value.memoryBooks?.companion?.pendingConversation)
        runCurrent()
        assertEquals(1, community.startedPosts)
        val activeConversationId = store.state.value.memoryBooks?.companion?.conversationId
        assertNotNull(activeConversationId)
        store.updateMemoryBookChatDraft("first request")
        community.failNextBookTurn = true
        store.sendMemoryBookChat()
        val pending = store.state.value.memoryBooks?.companion?.pendingTurn
        assertNotNull(pending)
        assertTrue(store.state.value.memoryBooks?.companion?.busy == true)
        store.updateMemoryBookChatDraft("editable while request is active")
        store.sendMemoryBookChat()
        runCurrent()
        assertEquals(pending, store.state.value.memoryBooks?.companion?.pendingTurn)
        assertEquals(activeConversationId, store.state.value.memoryBooks?.companion?.pendingTurnConversationId)
        assertEquals("editable while request is active", store.state.value.memoryBooks?.companion?.draft)
        assertEquals(1, community.sentBodies.size)
    }

    @Test fun reorderedBookEntryFailsClosedBeforeChildRequest() = runTest {
        val community = CommunityApi()
        val api = StoryApi()
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        community.bookOrder = listOf(secondStoryId, storyId)
        store.loadMemoryBookStory(0); runCurrent()
        assertTrue(store.state.value.memoryBooks?.readerUnavailable == true)
        assertTrue(api.childReads.isEmpty())
    }

    @Test fun parentBook403UsesExistingSessionInvalidation() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        community.bookFailure = ApiFailure(FailureKind.HTTP, 403)
        store.openMemoryBook(bookId); runCurrent()
        assertTrue(store.state.value.covered)
        assertNull(store.state.value.memoryBooks)
    }

    @Test fun delayedParentDenialDoesNotInvalidateReplacementReaderInSameLibrary() = runTest {
        val community = CommunityApi().apply { denyBookAfterGate = true }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        val gate = CompletableDeferred<Unit>()
        community.bookGate = gate
        store.openMemoryBook(bookId); runCurrent()
        assertTrue(store.state.value.memoryBooks!!.readerBusy)
        store.closeMemoryBook()
        community.bookGate = null
        store.openMemoryBook(bookId); runCurrent()
        val current = store.state.value.memoryBooks!!
        val generation = store.state.value.generation
        assertEquals(bookId, current.selectedBook?.id)
        assertFalse(current.readerBusy)
        gate.complete(Unit); runCurrent()
        assertFalse(store.state.value.covered)
        assertEquals(generation, store.state.value.generation)
        assertEquals(current, store.state.value.memoryBooks)
        assertEquals(1, community.bookReads)
    }

    @Test fun delayedChildParentDenialDoesNotInvalidateReplacementReader() = runTest {
        val community = CommunityApi().apply { denyBookAfterGate = true }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        val gate = CompletableDeferred<Unit>()
        community.bookGate = gate
        store.loadMemoryBookStory(0); runCurrent()
        assertTrue(store.state.value.memoryBooks!!.readerBusy)
        store.closeMemoryBook()
        community.bookGate = null
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        val replacement = store.state.value.memoryBooks!!
        val generation = store.state.value.generation
        assertEquals(storyId, replacement.story?.id)
        assertFalse(replacement.readerBusy)
        gate.complete(Unit); runCurrent()
        assertFalse(store.state.value.covered)
        assertEquals(generation, store.state.value.generation)
        assertEquals(replacement, store.state.value.memoryBooks)
    }

    @Test fun lateBookResponseCannotRestoreShelfAfterClose() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        val gate = CompletableDeferred<Unit>()
        community.bookGate = gate
        store.openMemoryBook(bookId); runCurrent()
        store.closeMemoryBooks()
        gate.complete(Unit); runCurrent()
        assertNull(store.state.value.memoryBooks)
    }

    @Test fun disabledCapabilityStopsBeforeBookListAndBackgroundDropsLateParent() = runTest {
        val community = CommunityApi().apply { capabilitiesEnabled = false }
        val api = StoryApi()
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        assertEquals(listOf("capabilities"), community.callOrder)
        assertNull(store.state.value.memoryBooks?.result)

        community.capabilitiesEnabled = true
        community.callOrder.clear()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        community.bookGate = CompletableDeferred()
        store.loadMemoryBookStory(0); runCurrent()
        store.background()
        community.bookGate?.complete(Unit); runCurrent()
        assertTrue(store.state.value.covered)
        assertNull(store.state.value.memoryBooks)
        assertTrue(api.childReads.isEmpty())
    }

    @Test fun lateChapterThumbnailIsWipedAfterReaderCloses() = runTest {
        val community = CommunityApi()
        val api = StoryApi()
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        val gate = CompletableDeferred<Unit>()
        api.mediaGate = gate
        store.loadMemoryBookStory(0); runCurrent()
        assertTrue(store.state.value.memoryBooks?.framesBusy == true)
        store.closeMemoryBook()
        gate.complete(Unit); runCurrent()
        assertArrayEquals(byteArrayOf(0, 0, 0), api.lateMediaBytes)
        assertNull(store.state.value.memoryBooks?.story)
        assertTrue(store.state.value.memoryBooks?.frames?.isEmpty() == true)
    }

    @Test fun chapterFramePagesKeepLaterAssetsSelectable() = runTest {
        val community = CommunityApi()
        community.bookItemCount = 10
        val api = StoryApi().apply { tenFrameStory = true }
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        api.thumbnailReads.clear()
        store.loadMemoryBookStory(0); runCurrent()
        assertEquals((1..8).map(Int::toString).toSet(), store.state.value.memoryBooks?.frames?.keys)
        assertTrue("Initial frame page overfetched: ${api.thumbnailReads}", api.thumbnailReads.size <= 9)
        store.loadMemoryBookFramePage(1); runCurrent()
        assertEquals(setOf("9", "10"), store.state.value.memoryBooks?.frames?.keys)
        assertEquals(listOf("9", "10"), api.thumbnailReads.takeLast(2))
        assertEquals("9", store.state.value.memoryBooks?.selectedAssetId)
        store.selectMemoryBookAsset("10"); runCurrent()
        assertEquals("10", store.state.value.memoryBooks?.selectedAssetId)
        assertEquals("10", store.state.value.memoryBooks?.heroAssetId)
    }

    @Test fun memoirResumeSurvivesReaderAndShelfCloseThenRefetchesParentAndChild() = runTest {
        val community = CommunityApi()
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        store.loadMemoryBookChapter(1); runCurrent()
        store.closeMemoryBook()
        assertEquals("chapter-2", store.state.value.memoryBooks?.resumePosition?.chapterId)
        store.closeMemoryBooks()

        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertEquals("chapter-2", store.state.value.memoryBooks?.resumePosition?.chapterId)
        val parentReadsBeforeResume = community.bookReads
        val childReadsBeforeResume = api.childReads.size
        store.resumeMemoryBookReading(); runCurrent()
        assertEquals(parentReadsBeforeResume + 1, community.bookReads)
        assertEquals(childReadsBeforeResume + 1, api.childReads.size)
        assertEquals(1, store.state.value.memoryBooks?.selectedChapter)
        assertEquals("chapter-2", store.state.value.memoryBooks?.story?.chapters?.get(store.state.value.memoryBooks!!.selectedChapter)?.id)
    }

    @Test fun memoirResumeWithRemovedChapterRestartsAtFirstChapter() = runTest {
        val community = CommunityApi()
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        store.loadMemoryBookChapter(1); runCurrent()
        store.closeMemoryBook(); store.closeMemoryBooks()

        api.storyChapterIds = listOf("chapter-1")
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertNotNull(store.state.value.memoryBooks?.resumePosition)
        store.resumeMemoryBookReading(); runCurrent()
        assertEquals(0, store.state.value.memoryBooks?.selectedChapter)
        assertEquals("chapter-1", store.state.value.memoryBooks?.story?.chapters?.get(0)?.id)
    }

    @Test fun memoirResumeRevalidatesFullParentOrderBeforeChildAndBackgroundClearsHint() = runTest {
        val community = CommunityApi()
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        store.loadMemoryBookChapter(1); runCurrent()
        store.closeMemoryBook()
        store.openMemoryBook(bookId); runCurrent()
        assertNotNull(store.state.value.memoryBooks?.resumePosition)
        val childReadsBeforeResume = api.childReads.size
        community.bookOrder = listOf(secondStoryId, storyId)
        store.resumeMemoryBookReading(); runCurrent()
        assertTrue(store.state.value.memoryBooks?.readerUnavailable == true)
        assertEquals(childReadsBeforeResume, api.childReads.size)
        assertNull(store.state.value.memoryBooks?.resumePosition)

        store.closeMemoryBooks()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        store.closeMemoryBook()
        store.openMemoryBook(bookId); runCurrent()
        assertNotNull(store.state.value.memoryBooks?.resumePosition)
        store.background()
        store.foreground(); runCurrent()
        assertFalse(store.state.value.covered)
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        assertNull(store.state.value.memoryBooks?.resumePosition)
    }

    @Test fun durableMemoirResumeOffersAfterFreshChildCheckAndReturnsToExactAssetPage() = runTest {
        val community = CommunityApi().apply { bookItemCount = 10 }
        val api = StoryApi().apply { tenFrameStory = true }
        val positions = ReaderPositionMemoryStore()
        val firstProcess = newStore(api, community, readerPositionPersistence = positions)
        firstProcess.authenticate("+12025550123", "synthetic-password"); runCurrent()
        firstProcess.openMemoryBooks(); runCurrent()
        firstProcess.openMemoryBook(bookId); runCurrent()
        firstProcess.loadMemoryBookStory(0); runCurrent()
        firstProcess.loadMemoryBookFramePage(1); runCurrent()
        firstProcess.selectMemoryBookAsset("10")
        assertEquals("10", positions.load("account").single().assetId)
        firstProcess.background()
        assertEquals("backgrounding must retain durable locations", "10", positions.load("account").single().assetId)

        // A new store simulates process recreation; it must derive the offer from persistence.
        val store = newStore(api, community, readerPositionPersistence = positions)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        val childReadsBeforeOpen = api.childReads.size
        val thumbnailReadsBeforeOpen = api.thumbnailReads.size
        store.openMemoryBook(bookId); runCurrent()

        val offer = store.state.value.memoryBooks?.resumePosition
        assertNotNull(offer)
        assertEquals("account", offer?.accountId)
        assertEquals("family", offer?.libraryId)
        assertEquals(bookId, offer?.bookId)
        assertEquals(1L, offer?.bookRevision)
        assertEquals("10", offer?.assetId)
        assertEquals(childReadsBeforeOpen + 1, api.childReads.size)
        assertEquals("validating the offer must not load thumbnails", thumbnailReadsBeforeOpen, api.thumbnailReads.size)
        assertEquals(0, api.originalReads)

        val parentReads = community.bookReads
        val childReads = api.childReads.size
        assertTrue(store.resumeMemoryBookReading(offer!!))
        runCurrent()
        val reading = store.state.value.memoryBooks!!
        assertEquals(parentReads + 1, community.bookReads)
        assertEquals(childReads + 1, api.childReads.size)
        assertEquals(0, reading.selectedChapter)
        assertEquals(1, reading.framePage)
        assertEquals("10", reading.selectedAssetId)
        assertEquals("10", reading.heroAssetId)
        assertEquals("10", api.heroReads.last())
        assertNull(reading.resumePosition)
        assertEquals(0, api.originalReads)
    }

    @Test fun durableOfferWithMissingExactMomentIsRemovedWithoutGuessingAReplacement() = runTest {
        val community = CommunityApi()
        val api = StoryApi()
        val positions = ReaderPositionMemoryStore()
        positions.seed(MemoryBookReaderPosition("account", "family", bookId, 1, storyId, 3, "chapter-1", "99"))
        val store = newStore(api, community, readerPositionPersistence = positions)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        val thumbnailsBeforeOfferValidation = api.thumbnailReads.size
        store.openMemoryBook(bookId); runCurrent()
        assertNull(store.state.value.memoryBooks?.resumePosition)
        assertTrue(positions.load("account").isEmpty())
        assertEquals(thumbnailsBeforeOfferValidation, api.thumbnailReads.size)
        assertEquals(0, api.originalReads)
        assertFalse(store.state.value.memoryBooks!!.readerUnavailable)
    }

    @Test fun definitiveFreshChildFailureRemovesStalePointerButTransientFailureRetainsIt() = runTest {
        val community = CommunityApi()
        val positions = ReaderPositionMemoryStore()
        positions.seed(MemoryBookReaderPosition("account", "family", bookId, 1, storyId, 3, "chapter-1", "1"))
        val definitiveApi = StoryApi().apply { childReadFailure = ApiFailure(FailureKind.HTTP, 409) }
        val definitiveStore = newStore(definitiveApi, community, readerPositionPersistence = positions)
        definitiveStore.authenticate("+12025550123", "synthetic-password"); runCurrent()
        definitiveStore.openMemoryBooks(); runCurrent()
        definitiveStore.openMemoryBook(bookId); runCurrent()
        assertNull(definitiveStore.state.value.memoryBooks?.resumePosition)
        assertTrue("a definite child conflict invalidates the location", positions.load("account").isEmpty())

        positions.seed(MemoryBookReaderPosition("account", "family", bookId, 1, storyId, 3, "chapter-1", "1"))
        val transientApi = StoryApi().apply { childReadFailure = ApiFailure(FailureKind.HTTP, 503) }
        val transientStore = newStore(transientApi, community, readerPositionPersistence = positions)
        transientStore.authenticate("+12025550123", "synthetic-password"); runCurrent()
        transientStore.openMemoryBooks(); runCurrent()
        transientStore.openMemoryBook(bookId); runCurrent()
        assertNull(transientStore.state.value.memoryBooks?.resumePosition)
        assertEquals("transient failure keeps the stored pointer for a later fresh check", "1", positions.load("account").single().assetId)
    }

    @Test fun startOverRemovesOnlyTheBookPointerAndAutomaticFirstChapterLoadDoesNotRecreateIt() = runTest {
        val community = CommunityApi().apply { bookItemCount = 10 }
        val api = StoryApi().apply { tenFrameStory = true; storyChapterIds = listOf("chapter-1", "chapter-2") }
        val positions = ReaderPositionMemoryStore()
        positions.seed(MemoryBookReaderPosition("account", "family", bookId, 1, storyId, 3, "chapter-2", "10"))
        val store = newStore(api, community, readerPositionPersistence = positions)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        val expected = store.state.value.memoryBooks!!.resumePosition!!
        assertTrue(store.startMemoryBookReadingOver(expected))
        runCurrent()
        val reading = store.state.value.memoryBooks!!
        assertEquals(0, reading.selectedChapter)
        assertEquals(0, reading.framePage)
        assertEquals("1", reading.selectedAssetId)
        assertTrue(positions.load("account").isEmpty())
        assertNull(reading.resumePosition)
        assertEquals(0, api.originalReads)
    }

    @Test fun unfinishedBookCompanionDraftBlocksResumeAndStartOverWithoutReads() = runTest {
        val community = CommunityApi()
        val api = StoryApi()
        val positions = ReaderPositionMemoryStore()
        positions.seed(MemoryBookReaderPosition("account", "family", bookId, 1, storyId, 3, "chapter-1", "1"))
        val store = newStore(api, community, readerPositionPersistence = positions)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        val reading = store.state.value.memoryBooks!!
        val expected = reading.resumePosition!!
        assertTrue(store.updateMemoryBookChatDraft("Unsent family question"))
        val parents = community.bookReads
        val children = api.childReads.size
        assertFalse(store.resumeMemoryBookReading(expected))
        assertFalse(store.startMemoryBookReadingOver(expected))
        runCurrent()
        assertEquals(parents, community.bookReads)
        assertEquals(children, api.childReads.size)
        assertEquals(expected, store.state.value.memoryBooks?.resumePosition)
        assertEquals("Unsent family question", store.state.value.memoryBooks?.companion?.draft)
    }

    @Test fun speechAdvanceMovesWithinSameStoryValidatesDestinationAndBookmarksChapter() = runTest {
        val community = CommunityApi()
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val positions = ReaderPositionMemoryStore()
        val store = newStore(api, community, readerPositionPersistence = positions)
        openBookReader(store)

        val scope = store.captureMemoryBookSpeechAdvance() ?: error("first chapter should have a next chapter")
        assertEquals("account", scope.accountId)
        assertEquals("family", scope.libraryId)
        assertEquals(bookId, scope.bookId)
        assertEquals(listOf(MemoryBookSpeechChildRevision(storyId, 3), MemoryBookSpeechChildRevision(secondStoryId, 3)),
            scope.orderedChildren)
        assertTrue(store.isCurrentMemoryBookSpeechAdvance(scope))
        assertTrue(store.advanceMemoryBookSpeech(scope))
        runCurrent()

        val reading = store.state.value.memoryBooks!!
        assertEquals(storyId, reading.story?.id)
        assertEquals(1, reading.selectedChapter)
        assertEquals("chapter-2", reading.story?.chapters?.get(reading.selectedChapter)?.id)
        assertFalse("the source-phase one-shot is stale after advancing", store.isCurrentMemoryBookSpeechAdvance(scope))
        assertTrue("the same frozen scope authorizes the expected destination render", store.isCurrentMemoryBookSpeechDestination(scope))
        assertEquals("chapter-2", positions.load("account").single().chapterId)
        assertEquals(0, api.originalReads)
    }

    @Test fun speechAdvanceIsUnavailableForLastChapterAndNeverCrossesToNextStory() = runTest {
        val community = CommunityApi()
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val store = newStore(api, community)
        openBookReader(store)
        val first = store.captureMemoryBookSpeechAdvance()!!
        store.loadMemoryBookChapter(1); runCurrent()
        assertNull("last chapter has no same-story destination", store.captureMemoryBookSpeechAdvance())
        assertTrue("the target remains the captured chapter when the reader navigates there manually", store.isCurrentMemoryBookSpeechDestination(first))
        assertFalse(store.advanceMemoryBookSpeech(first))
        assertEquals(storyId, store.state.value.memoryBooks?.story?.id)

        store.loadMemoryBookStory(1); runCurrent()
        assertEquals(secondStoryId, store.state.value.memoryBooks?.story?.id)
        assertFalse("a captured target can never follow into the next child story", store.isCurrentMemoryBookSpeechDestination(first))
    }

    @Test fun speechAdvanceRejectsTamperedAdjacentChapterIdsBeforeMutationInBothPhases() = runTest {
        val community = CommunityApi()
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2", "chapter-3") }
        val positions = ReaderPositionMemoryStore()
        val store = newStore(api, community, readerPositionPersistence = positions)
        openBookReader(store)
        val scope = store.captureMemoryBookSpeechAdvance()!!
        val wrongFrom = scope.copy(fromChapterId = "chapter-9")
        val wrongNext = scope.copy(nextChapterId = "chapter-3")
        val thumbnailsBefore = api.thumbnailReads.toList()
        val heroesBefore = api.heroReads.toList()
        val positionBefore = positions.load("account").single()

        assertFalse(store.isCurrentMemoryBookSpeechAdvance(wrongFrom))
        assertFalse(store.isCurrentMemoryBookSpeechAdvance(wrongNext))
        assertFalse(store.advanceMemoryBookSpeech(wrongFrom))
        assertFalse(store.advanceMemoryBookSpeech(wrongNext))
        assertEquals(0, store.state.value.memoryBooks?.selectedChapter)
        assertEquals(thumbnailsBefore, api.thumbnailReads)
        assertEquals(heroesBefore, api.heroReads)
        assertEquals(positionBefore, positions.load("account").single())

        assertTrue(store.advanceMemoryBookSpeech(scope))
        runCurrent()
        val thumbnailsAfterAdvance = api.thumbnailReads.toList()
        val heroesAfterAdvance = api.heroReads.toList()
        val positionAfterAdvance = positions.load("account").single()
        assertEquals("chapter-2", positionAfterAdvance.chapterId)
        assertFalse(store.isCurrentMemoryBookSpeechDestination(wrongFrom))
        assertFalse(store.isCurrentMemoryBookSpeechDestination(wrongNext))
        assertEquals(1, store.state.value.memoryBooks?.selectedChapter)
        assertEquals(thumbnailsAfterAdvance, api.thumbnailReads)
        assertEquals(heroesAfterAdvance, api.heroReads)
        assertEquals(positionAfterAdvance, positions.load("account").single())
    }

    @Test fun speechAdvanceCaptureAndUseRejectLateAccountReaderStoryAndChapterScopes() = runTest {
        val chapterApi = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val chapterStore = newStore(chapterApi, CommunityApi())
        openBookReader(chapterStore)
        val chapterScope = chapterStore.captureMemoryBookSpeechAdvance()!!
        chapterStore.loadMemoryBookChapter(1); runCurrent()
        assertFalse(chapterStore.isCurrentMemoryBookSpeechAdvance(chapterScope))
        assertFalse(chapterStore.advanceMemoryBookSpeech(chapterScope))

        val storyApi = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val storyStore = newStore(storyApi, CommunityApi())
        openBookReader(storyStore)
        val storyScope = storyStore.captureMemoryBookSpeechAdvance()!!
        storyStore.loadMemoryBookStory(1); runCurrent()
        assertFalse(storyStore.isCurrentMemoryBookSpeechAdvance(storyScope))
        assertFalse(storyStore.isCurrentMemoryBookSpeechDestination(storyScope))

        val accountApi = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val accountStore = newStore(accountApi, CommunityApi())
        openBookReader(accountStore)
        val accountScope = accountStore.captureMemoryBookSpeechAdvance()!!
        accountStore.logout(); runCurrent()
        assertFalse(accountStore.isCurrentMemoryBookSpeechAdvance(accountScope))
        assertFalse(accountStore.advanceMemoryBookSpeech(accountScope))
    }

    @Test fun memoirRenderedStoryCallbackIsRejectedAfterReaderStoryScopeChanges() = runTest {
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val community = CommunityApi()
        val positions = ReaderPositionMemoryStore()
        val store = newStore(api, community, readerPositionPersistence = positions)
        openBookReader(store)
        val rendered = store.captureMemoryBookReaderNavigation()!!
        assertEquals(storyId, rendered.storyId)

        store.loadMemoryBookStory(1); runCurrent()
        assertEquals(secondStoryId, store.state.value.memoryBooks?.story?.id)
        val childReads = api.childReads.toList()
        val thumbnailReads = api.thumbnailReads.toList()
        val heroReads = api.heroReads.toList()
        val savedPositions = positions.load("account")

        assertFalse(store.isCurrentMemoryBookReaderNavigation(rendered))
        assertFalse(store.loadMemoryBookStory(rendered, 0))
        assertEquals(secondStoryId, store.state.value.memoryBooks?.story?.id)
        assertEquals(childReads, api.childReads)
        assertEquals(thumbnailReads, api.thumbnailReads)
        assertEquals(heroReads, api.heroReads)
        assertEquals(savedPositions, positions.load("account"))
    }

    @Test fun memoirGuardedStoryChapterPageAndFrameActionsAcceptCurrentScopeAndSaveMoment() = runTest {
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2"); tenFrameStory = true }
        val community = CommunityApi().apply { bookItemCount = 10 }
        val positions = ReaderPositionMemoryStore()
        val store = newStore(api, community, readerPositionPersistence = positions)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()

        val tocScope = store.captureMemoryBookReaderNavigation()!!
        assertNull(tocScope.storyId)
        assertTrue(store.loadMemoryBookStory(tocScope, 0))
        runCurrent()
        assertEquals(storyId, store.state.value.memoryBooks?.story?.id)

        val chapterScope = store.captureMemoryBookReaderNavigation()!!
        assertTrue(store.loadMemoryBookChapter(chapterScope, 1))
        runCurrent()
        assertEquals(1, store.state.value.memoryBooks?.selectedChapter)
        assertEquals("chapter-2", positions.load("account").single().chapterId)

        val pageScope = store.captureMemoryBookReaderNavigation()!!
        assertTrue(store.loadMemoryBookFramePage(pageScope, 1))
        runCurrent()
        assertEquals(1, store.state.value.memoryBooks?.framePage)
        assertEquals("9", store.state.value.memoryBooks?.selectedAssetId)

        val frameScope = store.captureMemoryBookReaderNavigation()!!
        assertTrue(store.selectMemoryBookAsset(frameScope, "10"))
        runCurrent()
        assertEquals("10", store.state.value.memoryBooks?.selectedAssetId)
        assertEquals("10", positions.load("account").single().assetId)
        assertEquals("10", api.heroReads.last())
    }

    @Test fun memoirRenderedChapterAndFrameCallbacksAreRejectedAfterChapterOrPageChanges() = runTest {
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2"); tenFrameStory = true }
        val community = CommunityApi().apply { bookItemCount = 10 }
        val positions = ReaderPositionMemoryStore()
        val store = newStore(api, community, readerPositionPersistence = positions)
        openBookReader(store)
        val beforeChapter = store.captureMemoryBookReaderNavigation()!!
        store.loadMemoryBookChapter(1); runCurrent()
        assertEquals(1, store.state.value.memoryBooks?.selectedChapter)
        val chapterReads = api.thumbnailReads.toList()
        val chapterHeroes = api.heroReads.toList()
        val chapterPosition = positions.load("account")
        assertFalse(store.loadMemoryBookChapter(beforeChapter, 0))
        assertEquals(1, store.state.value.memoryBooks?.selectedChapter)
        assertEquals(chapterReads, api.thumbnailReads)
        assertEquals(chapterHeroes, api.heroReads)
        assertEquals(chapterPosition, positions.load("account"))

        store.loadMemoryBookFramePage(1); runCurrent()
        assertEquals(1, store.state.value.memoryBooks?.framePage)
        val beforePage = store.captureMemoryBookReaderNavigation()!!
        store.loadMemoryBookFramePage(0); runCurrent()
        val pageReads = api.thumbnailReads.toList()
        val pageHeroes = api.heroReads.toList()
        val pagePosition = positions.load("account")
        assertFalse(store.loadMemoryBookFramePage(beforePage, 1))
        assertFalse(store.selectMemoryBookAsset(beforePage, "10"))
        assertEquals(0, store.state.value.memoryBooks?.framePage)
        assertEquals(pageReads, api.thumbnailReads)
        assertEquals(pageHeroes, api.heroReads)
        assertEquals(pagePosition, positions.load("account"))
    }

    @Test fun memoirNavigationScopeRejectsReplacementAccountAndReaderBeforeAnyRead() = runTest {
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val community = CommunityApi()
        val store = newStore(api, community)
        openBookReader(store)
        val oldAccountScope = store.captureMemoryBookReaderNavigation()!!
        val oldChildReads = api.childReads.toList()

        store.closeMemoryBook()
        runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(1); runCurrent()
        val replacementChildReads = api.childReads.toList()
        val replacementBookReads = community.bookReads
        val replacementStory = store.state.value.memoryBooks?.story?.id
        assertFalse(store.loadMemoryBookStory(oldAccountScope, 0))
        assertEquals(replacementStory, store.state.value.memoryBooks?.story?.id)
        assertEquals(replacementChildReads, api.childReads)
        assertEquals(replacementBookReads, community.bookReads)
        assertTrue(replacementChildReads.size > oldChildReads.size)

        val oldReaderScope = store.captureMemoryBookReaderNavigation()!!
        store.logout(); runCurrent()
        api.accountId = "replacement-account"
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        val currentChildReads = api.childReads.toList()
        val currentReaderStory = store.state.value.memoryBooks?.story?.id
        assertFalse(store.loadMemoryBookChapter(oldReaderScope, 1))
        assertEquals(currentReaderStory, store.state.value.memoryBooks?.story?.id)
        assertEquals(currentChildReads, api.childReads)
    }

    @Test fun speechAdvanceWaitsForMetadataAndRejectsUnavailableReader() = runTest {
        val community = CommunityApi()
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val store = newStore(api, community)
        openBookReader(store)
        val scope = store.captureMemoryBookSpeechAdvance()!!
        val gate = CompletableDeferred<Unit>()
        api.childReadGateId = secondStoryId
        api.childReadGate = gate
        api.childReadGateEntered = CompletableDeferred()
        store.loadMemoryBookStory(1)
        runCurrent()
        assertTrue(api.childReadGateEntered.isCompleted)
        assertTrue(store.state.value.memoryBooks!!.readerBusy)
        assertFalse(store.isCurrentMemoryBookSpeechAdvance(scope))
        assertFalse(store.advanceMemoryBookSpeech(scope))
        gate.complete(Unit); runCurrent()
        assertEquals(secondStoryId, store.state.value.memoryBooks?.story?.id)
    }

    @Test fun speechAdvanceIsBlockedByPendingSourceInspection() = runTest {
        val community = CommunityApi()
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val store = newStore(api, community)
        openBookReader(store)
        store.openMemoryBookEditorial(); runCurrent()
        val source = store.memoryBookEditorialCatalogState.value.sources.first()
        val gate = CompletableDeferred<Unit>()
        api.contributionDetailGate = gate
        api.contributionDetailGateEntered = CompletableDeferred()
        store.inspectMemoryBookEditorialSource(source)
        runCurrent()
        assertTrue(api.contributionDetailGateEntered.isCompleted)
        assertTrue(store.state.value.memoryBooks!!.sourceInspection.busy)
        assertNull(store.captureMemoryBookSpeechAdvance())
        gate.complete(Unit); runCurrent()
        store.editMemoryBookEditorial(listOf(source), emptyList())
        assertTrue(store.memoryBookEditorialState.value.dirty)
        assertNull("a private editorial draft also blocks speech navigation", store.captureMemoryBookSpeechAdvance())
    }

    @Test fun speechAdvanceIsBlockedByCompanionDraftAndMemoirEditorInput() = runTest {
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val store = newStore(api, CommunityApi())
        openBookReader(store)
        assertNotNull(store.captureMemoryBookSpeechAdvance())
        assertTrue(store.updateMemoryBookChatDraft("A family question still being composed"))
        assertNull(store.captureMemoryBookSpeechAdvance())
        assertTrue(store.updateMemoryBookChatDraft(""))
        assertTrue(store.updateMemoryBookNarrativeInstructions("Keep this private outline in progress"))
        assertNull(store.captureMemoryBookSpeechAdvance())
    }

    @Test fun speechAdvanceIsBlockedDuringActiveVoiceCaptureAndUnreviewedTranscript() = runTest {
        val api = StoryApi().apply { voiceEnabled = true; storyChapterIds = listOf("chapter-1", "chapter-2") }
        val store = newStore(api, CommunityApi())
        openBookReader(store)
        assertTrue(store.openMemoryBookNarrativeDictation())
        val dictation = store.memoryBookNarrativeDictationState.value ?: error("dictation should open explicitly")
        dictation.loadCapabilities(); runCurrent()
        assertNotNull(dictation.beginRecording())
        assertNull(store.captureMemoryBookSpeechAdvance())
        dictation.stopRecording(instructionWav()); runCurrent()
        assertNotNull(dictation.state.value.transcript)
        assertNull("an unreviewed voice transcript remains private work", store.captureMemoryBookSpeechAdvance())
        dictation.cancel()
    }

    @Test fun speechAdvanceValidationAllowsPreviewFetchAndUsesNoMetadataOrOriginalReads() = runTest {
        val community = CommunityApi()
        val api = StoryApi().apply { storyChapterIds = listOf("chapter-1", "chapter-2") }
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        val gate = CompletableDeferred<Unit>()
        api.mediaGate = gate
        store.loadMemoryBookStory(0); runCurrent()
        assertTrue(store.state.value.memoryBooks!!.framesBusy)
        val scope = store.captureMemoryBookSpeechAdvance() ?: error("preview work should not block target validation")
        assertTrue(store.isCurrentMemoryBookSpeechAdvance(scope))
        assertTrue(store.advanceMemoryBookSpeech(scope))
        assertTrue(store.isCurrentMemoryBookSpeechDestination(scope))
        gate.complete(Unit); runCurrent()
        assertEquals(0, api.originalReads)
        assertEquals(listOf(storyId), api.childReads)
    }

    @Test fun currentDenialClearsMatchingAccountPositionsAndStorageFailureDoesNotBlockReading() = runTest {
        val community = CommunityApi()
        val api = StoryApi().apply { deniedChildId = storyId }
        val positions = ReaderPositionMemoryStore()
        positions.seed(MemoryBookReaderPosition("account", "family", bookId, 1, storyId, 3, "chapter-1", "1"))
        val deniedStore = newStore(api, community, readerPositionPersistence = positions)
        deniedStore.authenticate("+12025550123", "synthetic-password"); runCurrent()
        deniedStore.openMemoryBooks(); runCurrent()
        deniedStore.openMemoryBook(bookId); runCurrent()
        assertEquals(listOf("account"), positions.clearedAccounts)
        assertTrue(positions.load("account").isEmpty())

        val unavailablePositions = ReaderPositionMemoryStore().apply { failLoad = true; failSave = true }
        val ordinaryApi = StoryApi()
        val ordinaryStore = newStore(ordinaryApi, CommunityApi(), readerPositionPersistence = unavailablePositions)
        ordinaryStore.authenticate("+12025550123", "synthetic-password"); runCurrent()
        ordinaryStore.openMemoryBooks(); runCurrent()
        ordinaryStore.openMemoryBook(bookId); runCurrent()
        assertNull("failed persistence reads must not resurrect an in-memory offer", ordinaryStore.state.value.memoryBooks?.resumePosition)
        ordinaryStore.loadMemoryBookStory(0); runCurrent()
        assertEquals(storyId, ordinaryStore.state.value.memoryBooks?.story?.id)
        assertFalse(ordinaryStore.state.value.memoryBooks!!.readerUnavailable)
    }

    @Test fun staleOldAccountOfferFailuresCannotDeleteReplacementPositionOrMountOldBook() = runTest {
        val failures = listOf(
            ApiFailure(FailureKind.HTTP, 403), ApiFailure(FailureKind.HTTP, 404),
            ApiFailure(FailureKind.HTTP, 409), IllegalStateException("stale transport failure"),
        )
        failures.forEach { failure ->
            val community = CommunityApi()
            val positions = ReaderPositionMemoryStore()
            val oldPosition = MemoryBookReaderPosition("account", "family", bookId, 1,
                storyId, 3, "chapter-1", "1")
            val replacementPosition = oldPosition.copy(accountId = "replacement-account", assetId = "2")
            positions.seed(oldPosition)
            positions.seed(replacementPosition)
            val gate = CompletableDeferred<Unit>()
            val api = StoryApi().apply {
                childReadGateId = storyId
                childReadGate = gate
                when (failure) {
                    is ApiFailure -> childReadFailure = failure
                    else -> childReadException = failure
                }
            }
            val store = newStore(api, community, readerPositionPersistence = positions)
            store.authenticate("+12025550123", "synthetic-password"); runCurrent()
            store.openMemoryBooks(); runCurrent()
            store.openMemoryBook(bookId); runCurrent()
            api.childReadGateEntered.await()

            api.accountId = "replacement-account"
            store.authenticate("+12025550124", "synthetic-password"); runCurrent()
            assertEquals("replacement-account", store.state.value.session?.account_id)
            assertTrue(positions.load("replacement-account").contains(replacementPosition))

            gate.complete(Unit); runCurrent()
            assertTrue("stale offer failure must not clear either account", positions.clearedAccounts.isEmpty())
            assertTrue(positions.load("account").contains(oldPosition))
            assertTrue(positions.load("replacement-account").contains(replacementPosition))
            assertNull("stale offer completion must not mount the old account's book", store.state.value.memoryBooks?.selectedBook)
            assertEquals("replacement-account", store.state.value.session?.account_id)
        }
    }

    @Test fun selectingFrameWhilePageLoadsDoesNotCancelPageOrStickBusy() = runTest {
        val community = CommunityApi()
        community.bookItemCount = 10
        val api = StoryApi().apply { tenFrameStory = true }
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.loadMemoryBookStory(0); runCurrent()
        val gate = CompletableDeferred<Unit>()
        api.mediaGate = gate
        store.loadMemoryBookFramePage(1); runCurrent()
        assertTrue(store.state.value.memoryBooks?.framesBusy == true)
        store.selectMemoryBookAsset("10")
        assertTrue(store.state.value.memoryBooks?.framesBusy == true)
        gate.complete(Unit); runCurrent()
        assertFalse(store.state.value.memoryBooks?.framesBusy ?: true)
        assertEquals(setOf("9", "10"), store.state.value.memoryBooks?.frames?.keys)
    }

    @Test fun featureOffNeverCallsCommunityApi() = runTest {
        val api = CommunityApi(); val store = newStore(StoryApi(), api, enabled = false)
        openStory(store)
        assertNull(store.state.value.savedMemoryStories?.community)
        assertEquals(0, api.listReads)
        assertEquals(0, api.conversationReads)
    }

    @Test fun enabledReaderLoadsMemberStateAndOnlySendsExplicitChat() = runTest {
        val community = CommunityApi(); val store = newStore(StoryApi(), community)
        openStory(store)
        runCurrent()
        assertTrue(store.memoryCommunityAvailable)
        assertTrue(store.state.value.savedMemoryStories?.community?.capabilities?.generationEnabled == true)
        assertNotNull(store.state.value.savedMemoryStories?.community?.contributions)
        assertEquals(1, community.listReads)
        assertEquals(1, community.conversationReads)
        store.startMemoryConversation(); runCurrent()
        assertEquals(community.startedConversationId, store.state.value.savedMemoryStories?.community?.conversationId)
        store.updateMemoryChatDraft("Tell me about the garden")
        runCurrent()
        assertTrue(community.sentBodies.isEmpty())
        store.sendMemoryChat(); runCurrent()
        assertEquals(1, community.sentBodies.size)
        assertEquals("queued", store.state.value.savedMemoryStories?.community?.job?.state)
    }

    @Test fun selectedStoryConversationReopensFromFreshHistoryWithoutDraftOrWrites() = runTest {
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.selectMemoryConversation(secondConversationId); runCurrent()
        store.updateMemoryChatDraft("private unsent words")
        val reads = community.conversationReads
        val turnReads = community.turnConversationIds.size

        store.closeSavedMemoryStoryDetail()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()

        val chat = store.state.value.savedMemoryStories!!.community!!
        assertEquals(secondConversationId, chat.conversationId)
        assertTrue(chat.conversationRestored)
        assertEquals("", chat.chatDraft)
        assertTrue(chat.threadDrafts.values.all { it.isEmpty() })
        assertEquals(reads + 1, community.conversationReads)
        assertEquals(secondConversationId, community.turnConversationIds.last())
        assertEquals(turnReads + 1, community.turnConversationIds.size)
        assertEquals(0, community.startedPosts)
        assertTrue(community.sentBodies.isEmpty())
    }

    @Test fun missingSelectedStoryThreadFallsBackFromFreshHistoryWithoutReadingOldId() = runTest {
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.selectMemoryConversation(secondConversationId); runCurrent()
        store.closeSavedMemoryStoryDetail()
        community.extraConversationIds = emptyList()
        val turnReads = community.turnConversationIds.size

        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()

        val chat = store.state.value.savedMemoryStories!!.community!!
        assertEquals(conversationId, chat.conversationId)
        assertFalse(chat.conversationRestored)
        assertEquals(listOf(conversationId), community.turnConversationIds.drop(turnReads))
        assertTrue(community.sentBodies.isEmpty())
    }

    @Test fun selectedMemoirConversationReopensWithoutDraftOrResendingAndRecoversJob() = runTest {
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        store.selectMemoryBookConversation(secondConversationId); runCurrent()
        store.updateMemoryBookChatDraft("unsent memoir words")
        val reads = community.conversationReads
        val turnReads = community.turnConversationIds.size

        store.closeMemoryBook()
        community.existingActiveTurn = true
        store.openMemoryBook(bookId); runCurrent()

        val chat = store.state.value.memoryBooks!!.companion!!
        assertEquals(secondConversationId, chat.conversationId)
        assertTrue(chat.conversationRestored)
        assertEquals("", chat.draft)
        assertTrue(chat.threadDrafts.isEmpty())
        assertEquals(reads + 1, community.conversationReads)
        assertEquals(secondConversationId, community.turnConversationIds.last())
        assertEquals(turnReads + 1, community.turnConversationIds.size)
        assertEquals("running", chat.job?.state)
        assertEquals(1, community.jobReads)
        assertTrue(community.sentBodies.isEmpty())
        assertEquals(0, community.startedPosts)
        assertEquals(0, community.cancelJobReads)
    }

    @Test fun backgroundRevalidatesMembershipBeforeRestoringConversation() = runTest {
        val api = StoryApi()
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(api, community)
        openStory(store)
        store.selectMemoryConversation(secondConversationId); runCurrent()
        store.updateMemoryChatDraft("private words")

        store.background()
        api.membershipRevision = 2
        store.foreground(); runCurrent()
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()

        val chat = store.state.value.savedMemoryStories!!.community!!
        assertEquals(conversationId, chat.conversationId)
        assertFalse(chat.conversationRestored)
        assertEquals("", chat.chatDraft)
        assertTrue(community.sentBodies.isEmpty())
    }

    @Test fun sameMembershipBackgroundRestoresSelectedStoryWithBlankComposer() = runTest {
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.selectMemoryConversation(secondConversationId); runCurrent()
        store.updateMemoryChatDraft("unsent words")

        store.background(); store.foreground(); runCurrent()
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()

        val chat = store.state.value.savedMemoryStories!!.community!!
        assertEquals(secondConversationId, chat.conversationId)
        assertTrue(chat.conversationRestored)
        assertEquals("", chat.chatDraft)
        assertTrue(chat.threadDrafts.values.all { it.isEmpty() })
        assertTrue(community.sentBodies.isEmpty())
        assertEquals(0, community.startedPosts)
    }

    @Test fun failedFreshTurnsReadDoesNotClaimRestorationOrSend() = runTest {
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.selectMemoryConversation(secondConversationId); runCurrent()
        store.closeSavedMemoryStoryDetail()
        community.turnFailure = ApiFailure(FailureKind.OFFLINE)

        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()

        val chat = store.state.value.savedMemoryStories!!.community!!
        assertFalse(chat.conversationRestored)
        assertEquals("", chat.chatDraft)
        assertEquals(0, community.startedPosts)
        assertTrue(community.sentBodies.isEmpty())
    }

    @Test fun storyRevisionChangeInvalidatesSelectedConversationHint() = runTest {
        val api = StoryApi()
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(api, community)
        openStory(store)
        store.selectMemoryConversation(secondConversationId); runCurrent()
        store.closeSavedMemoryStoryDetail()
        api.storyRevision = 4

        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()

        val chat = store.state.value.savedMemoryStories!!.community!!
        assertEquals(conversationId, chat.conversationId)
        assertFalse(chat.conversationRestored)
        assertEquals(conversationId, community.turnConversationIds.last())
    }

    @Test fun deferredOldConversationTurnsCannotRestoreStaleHintAfterReopen() = runTest {
        val api = StoryApi()
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(api, community)
        openStory(store)
        store.selectMemoryConversation(secondConversationId); runCurrent()
        store.closeSavedMemoryStoryDetail()

        val oldTurns = CompletableDeferred<Unit>()
        community.turnGate = oldTurns
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()
        assertEquals(secondConversationId, community.turnConversationIds.last())
        store.closeSavedMemoryStoryDetail()
        api.storyRevision = 4
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.first()); runCurrent()
        assertEquals(conversationId, store.state.value.savedMemoryStories?.community?.conversationId)

        oldTurns.complete(Unit); runCurrent()

        val chat = store.state.value.savedMemoryStories!!.community!!
        assertEquals(conversationId, chat.conversationId)
        assertFalse(chat.conversationRestored)
        assertTrue(community.sentBodies.isEmpty())
    }

    @Test fun memoirChildRevisionAndOrderChangesInvalidateSelectedConversationHint() = runTest {
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        store.selectMemoryBookConversation(secondConversationId); runCurrent()
        store.closeMemoryBook()
        community.bookChildRevisions[storyId] = "4"

        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        var chat = store.state.value.memoryBooks!!.companion!!
        assertEquals(conversationId, chat.conversationId)
        assertFalse(chat.conversationRestored)

        store.selectMemoryBookConversation(secondConversationId); runCurrent()
        store.closeMemoryBook()
        community.bookOrder = listOf(secondStoryId, storyId)
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()

        chat = store.state.value.memoryBooks!!.companion!!
        assertEquals(conversationId, chat.conversationId)
        assertFalse(chat.conversationRestored)
        assertTrue(community.sentBodies.isEmpty())
    }

    @Test fun logoutAndAccountChangeClearSelectedConversationHint() = runTest {
        val api = StoryApi()
        val community = CommunityApi().apply { existingConversation = true; extraConversationIds = listOf(secondConversationId) }
        val store = newStore(api, community)
        openStory(store)
        store.selectMemoryConversation(secondConversationId); runCurrent()

        store.logout(); runCurrent()
        api.accountId = "different-account"
        openStory(store)

        val chat = store.state.value.savedMemoryStories!!.community!!
        assertEquals(conversationId, chat.conversationId)
        assertFalse(chat.conversationRestored)
        assertTrue(community.sentBodies.isEmpty())
    }

    @Test fun textContributionUsesReviewConsentAndDetailScopeDropsLateResults() = runTest {
        val community = CommunityApi(); val store = newStore(StoryApi(), community)
        openStory(store); runCurrent()
        store.submitMemoryText("Words from home", "zh", "Family member", consent = true)
        runCurrent()
        assertEquals(1, community.sentBodies.size)
        assertTrue(community.sentBodies.single().contains("\"consent\":\"1\""))
        assertNull(store.state.value.savedMemoryStories?.community?.pendingText)
        assertEquals("", store.state.value.savedMemoryStories?.community?.contributionDraft)
        assertEquals(contributionId, store.state.value.savedMemoryStories?.community?.selectedContribution?.receipt?.contribution?.id)

        val gate = CompletableDeferred<Unit>()
        community.contributionGate = gate
        store.reloadMemoryContributions(); runCurrent()
        store.closeSavedMemoryStoryDetail()
        gate.complete(Unit); runCurrent()
        assertNull(store.state.value.savedMemoryStories?.detail)
        assertNull(store.state.value.savedMemoryStories?.community)
    }

    @Test fun lateSubmissionPreservesEditsMadeWhileRequestIsSuspended() = runTest {
        val community = CommunityApi().apply { textGate = CompletableDeferred() }
        val store = newStore(StoryApi(), community)
        openStory(store); runCurrent()
        store.updateMemoryContributionDraft("Submitted memory")
        store.updateMemoryContributionConsent(textConsent = true, audioConsent = true)
        store.submitMemoryText("Submitted memory", "zh", "Family member", consent = true)
        runCurrent()
        assertTrue(store.state.value.savedMemoryStories?.community?.busy == true)
        store.updateMemoryContributionDraft("A newer unsent edit")
        store.updateMemoryContributionConsent(textConsent = false, audioConsent = false)
        store.updateMemoryContributionLanguage("en")
        store.selectMemoryCommunityTab(1)
        store.updateMemoryChatDraft("A chat draft entered during upload")
        community.textGate!!.complete(Unit)
        runCurrent()
        val result = store.state.value.savedMemoryStories!!.community!!
        assertEquals("A newer unsent edit", result.contributionDraft)
        assertFalse(result.contributionConsent)
        assertFalse(result.audioConsent)
        assertEquals("en", result.contributionLanguage)
        assertEquals(1, result.tab)
        assertEquals("A chat draft entered during upload", result.chatDraft)
        assertNull(result.pendingText)
    }

    @Test fun contributionAndTurnHistoryPagesAreBoundedAndRefreshKeepsCurrentPage() = runTest {
        val community = CommunityApi(); val store = newStore(StoryApi(), community)
        openStory(store); runCurrent()
        store.loadMemoryContributionPage(2); runCurrent()
        assertEquals(2, store.state.value.savedMemoryStories?.community?.contributions?.page)
        store.reloadMemoryContributions(); runCurrent()
        assertEquals(2, store.state.value.savedMemoryStories?.community?.contributions?.page)
        assertEquals(listOf(1, 2, 2), community.contributionPages)
        store.startMemoryConversation(); runCurrent()
        assertEquals(listOf(1), community.turnPages)
        store.loadMemoryTurnsPage(2); runCurrent()
        assertEquals(2, store.state.value.savedMemoryStories?.community?.turns?.page)
        store.refreshMemoryChat(); runCurrent()
        assertEquals(2, store.state.value.savedMemoryStories?.community?.turns?.page)
        store.loadMemoryTurnsPage(8); runCurrent()
        store.loadMemoryTurnsPage(9); runCurrent()
        assertEquals(8, store.state.value.savedMemoryStories?.community?.turns?.page)
        assertEquals(listOf(1, 2, 2, 8), community.turnPages)
        store.loadMemoryContributionPage(100001); runCurrent()
        assertEquals(listOf(1, 2, 2), community.contributionPages)
    }

    @Test fun narrativeOutputIsKeptAsReviewOnlyStoryScopedJob() = runTest {
        val community = CommunityApi(); val store = newStore(StoryApi().apply { storyCanEdit = true }, community)
        assertEquals("ready", ProtectedMemoryCommunityWire.job(community.narrativeResponse()).state)
        openStory(store); runCurrent()
        store.selectMemoryCommunityTab(2)
        store.requestMemoryNarrative("Keep uncertainty and ask questions")
        runCurrent()
        val result = store.state.value.savedMemoryStories?.community?.narrativeJob
        assertEquals("ready", result?.state)
        assertEquals("narrative", result?.kind)
        assertEquals(3L, result?.baseRevision)
        assertNotNull(result?.result)
        assertNull(store.state.value.savedMemoryStories?.community?.pendingNarrative)
        assertEquals(3L, store.state.value.savedMemoryStories?.detail?.revision)
    }

    @Test fun viewerCannotRequestOrRetryNarrative() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi().apply { storyCanEdit = false }, community)
        openStory(store); runCurrent()
        store.selectMemoryCommunityTab(2)
        store.requestMemoryNarrative("A viewer must not send a narrative request")
        store.retryMemoryNarrative()
        runCurrent()
        assertEquals(0, community.narrativeWrites)
        assertNull(store.state.value.savedMemoryStories?.community?.pendingNarrative)
        assertNull(store.state.value.savedMemoryStories?.community?.narrativeJob)
        assertFalse(store.state.value.covered)
    }

    @Test fun capabilityDenialCoversAndClearsThePrivateReader() = runTest {
        val community = CommunityApi().apply { capFailure = ApiFailure(FailureKind.HTTP, 403) }
        val store = newStore(StoryApi(), community)
        store.authenticate("+12025550123", "synthetic-password")
        runCurrent()
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(summary); runCurrent()
        assertTrue(store.state.value.covered)
        assertNull(store.state.value.savedMemoryStories)
        assertEquals(Message.ACCESS_DENIED, store.state.value.problem?.message)
    }

    @Test fun fullStoryConversationContinuesOnlyAfterExplicitCreateAndKeepsRejectedWordsEditable() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.startMemoryConversation(); runCurrent()
        val oldConversation = store.state.value.savedMemoryStories!!.community!!.conversationId!!
        assertEquals(oldConversation, community.startedConversationIds.single())
        assertTrue(store.updateMemoryChatDraft("Rejected request"))
        community.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, retryAfterMillis = 5000, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        store.sendMemoryChat(); runCurrent()
        val failed = store.state.value.savedMemoryStories!!.community!!
        val rejected = failed.pendingTurn!!
        assertEquals(Message.MEMORY_CONVERSATION_FULL, failed.failure?.message)
        assertEquals(5000L, failed.failure?.retryAtMillis)
        assertEquals("Rejected request", rejected.text)
        assertEquals(oldConversation, failed.conversationId)

        assertTrue(store.updateMemoryChatDraft("A later note"))
        val scope = store.memoryStoryChatContinuationScope()!!
        assertEquals("a".repeat(64), scope.sourceFingerprint)
        val createGate = CompletableDeferred<Unit>()
        community.conversationStartGate = createGate
        assertEquals(MemoryConversationContinuationResult.STARTED, store.continueMemoryStoryChatInNewConversation(scope))
        assertEquals(MemoryConversationContinuationResult.ALREADY_PENDING, store.continueMemoryStoryChatInNewConversation(scope))
        runCurrent()
        assertTrue(store.updateMemoryChatDraft("Rejected request\nA later note\nTyped while create was pending"))
        createGate.complete(Unit)
        runCurrent()
        val continued = store.state.value.savedMemoryStories!!.community!!
        assertNull(continued.pendingConversation)
        assertNull(continued.pendingTurn)
        assertNull(continued.continuation)
        assertNotEquals(oldConversation, continued.conversationId)
        assertEquals("Rejected request\nA later note\nTyped while create was pending", continued.chatDraft)
        assertEquals(continued.conversationId, continued.turns?.conversationId)
        assertEquals("Rejected request\nA later note\nTyped while create was pending", continued.threadDrafts[continued.conversationId])
        assertEquals(1, community.chatTurnPosts)
        assertEquals(2, community.startedPosts)
    }

    @Test fun failedStoryConversationCreateRetriesSameIdAndDoesNotDropRejectedTurn() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.startMemoryConversation(); runCurrent()
        assertTrue(store.updateMemoryChatDraft("Please continue this thought"))
        community.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        store.sendMemoryChat(); runCurrent()
        val oldConversation = store.state.value.savedMemoryStories!!.community!!.conversationId
        val rejected = store.state.value.savedMemoryStories!!.community!!.pendingTurn
        assertNotNull(rejected)
        assertTrue(store.updateMemoryChatDraft("And this added note"))
        val scope = store.memoryStoryChatContinuationScope()!!
        community.conversationStartFailure = ApiFailure(FailureKind.OFFLINE)
        assertEquals(MemoryConversationContinuationResult.STARTED, store.continueMemoryStoryChatInNewConversation(scope))
        runCurrent()
        val firstAttempt = community.startedConversationIds.last()
        val held = store.state.value.savedMemoryStories!!.community!!
        assertEquals(oldConversation, held.conversationId)
        assertEquals(rejected, held.pendingTurn)
        assertEquals(firstAttempt, held.pendingConversation?.id)
        assertEquals("Please continue this thought\nAnd this added note", held.chatDraft)
        assertEquals(1, community.chatTurnPosts)

        assertEquals(MemoryConversationContinuationResult.STARTED,
            store.retryMemoryStoryChatContinuation(scope, held.pendingConversation!!))
        runCurrent()
        val completed = store.state.value.savedMemoryStories!!.community!!
        assertEquals(listOf(firstAttempt, firstAttempt), community.startedConversationIds.takeLast(2))
        assertEquals(firstAttempt, completed.conversationId)
        assertEquals("Please continue this thought\nAnd this added note", completed.chatDraft)
        assertNull(completed.pendingTurn)
        assertNull(completed.continuation)
        assertEquals(1, community.chatTurnPosts)
    }

    @Test fun malformedStoryContinuationReadbackRetainsPendingTurnAndGuardedRetryReusesRequest() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.startMemoryConversation(); runCurrent()
        assertTrue(store.updateMemoryChatDraft("Keep the failed words"))
        community.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        store.sendMemoryChat(); runCurrent()
        assertTrue(store.updateMemoryChatDraft("And the new draft"))
        val scope = store.memoryStoryChatContinuationScope()!!
        assertEquals(MemoryConversationContinuationResult.STARTED, store.continueMemoryStoryChatInNewConversation(scope))
        val pendingId = store.state.value.savedMemoryStories!!.community!!.pendingConversation!!.id
        community.hideNewestStartedConversation = true
        runCurrent()
        val unresolved = store.state.value.savedMemoryStories!!.community!!
        assertEquals(Message.INVALID_RESPONSE, unresolved.failure?.message)
        assertEquals(pendingId, unresolved.pendingConversation?.id)
        assertEquals(scope.rejectedTurn, unresolved.pendingTurn)
        assertEquals("Keep the failed words\nAnd the new draft", unresolved.chatDraft)

        community.hideNewestStartedConversation = false
        assertEquals(MemoryConversationContinuationResult.STARTED,
            store.retryMemoryStoryChatContinuation(scope, unresolved.pendingConversation!!))
        runCurrent()
        val completed = store.state.value.savedMemoryStories!!.community!!
        assertEquals(pendingId, completed.conversationId)
        assertNull(completed.pendingTurn)
        assertNull(completed.continuation)
        assertEquals(1, community.chatTurnPosts)
        assertEquals(listOf(pendingId, pendingId), community.startedConversationIds.takeLast(2))
    }

    @Test fun replacedStoryReaderBeforeContinuationPostPreventsTheCreateRequest() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.startMemoryConversation(); runCurrent()
        assertTrue(store.updateMemoryChatDraft("Keep this request"))
        community.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        store.sendMemoryChat(); runCurrent()
        val scope = store.memoryStoryChatContinuationScope()!!
        assertEquals(MemoryConversationContinuationResult.STARTED, store.continueMemoryStoryChatInNewConversation(scope))
        store.closeSavedMemoryStoryDetail()
        runCurrent()
        assertEquals(1, community.startedPosts)
        assertEquals(1, community.chatTurnPosts)
        assertEquals(MemoryConversationContinuationResult.STALE,
            store.retryMemoryStoryChatContinuation(scope, MemoryConversationRequest(targetType = "story", targetId = storyId)))
    }

    @Test fun lateContinuationCreateDenialCannotInvalidateReplacementStoryReader() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.startMemoryConversation(); runCurrent()
        assertTrue(store.updateMemoryChatDraft("Keep this request"))
        community.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        store.sendMemoryChat(); runCurrent()
        val oldScope = store.memoryStoryChatContinuationScope()!!
        val gate = CompletableDeferred<Unit>()
        community.conversationStartGate = gate
        community.conversationStartFailure = ApiFailure(FailureKind.HTTP, 403)
        assertEquals(MemoryConversationContinuationResult.STARTED, store.continueMemoryStoryChatInNewConversation(oldScope))
        runCurrent()
        assertTrue(store.state.value.savedMemoryStories!!.community!!.busy)
        val currentSummary = store.state.value.savedMemoryStories!!.selectedSummary!!
        store.closeSavedMemoryStoryDetail()
        store.openSavedMemoryStory(currentSummary); runCurrent()
        val replacement = store.state.value.savedMemoryStories!!
        val generation = store.state.value.generation
        assertEquals(storyId, replacement.detail?.id)
        gate.complete(Unit); runCurrent()
        assertFalse(store.state.value.covered)
        assertEquals(generation, store.state.value.generation)
        assertEquals(replacement, store.state.value.savedMemoryStories)
        assertNull(community.conversationStartFailure)
        assertEquals(2, community.startedPosts)
    }

    @Test fun memoirContinuationUsesCapturedOrderedChildrenAndNeverSendsAutomatically() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        store.queueMemoryBookConversation(); runCurrent()
        assertTrue(store.updateMemoryBookChatDraft("Memoir request"))
        community.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        store.sendMemoryBookChat(); runCurrent()
        val failed = store.state.value.memoryBooks!!.companion!!
        val rejected = failed.pendingTurn!!
        assertEquals(Message.MEMORY_CONVERSATION_FULL, failed.failure?.message)
        assertEquals(2, store.memoryBookChatContinuationScope()!!.orderedChildren.size)
        assertTrue(store.updateMemoryBookChatDraft("One more memoir note"))
        val scope = store.memoryBookChatContinuationScope()!!
        assertEquals(MemoryConversationContinuationResult.STARTED, store.continueMemoryBookChatInNewConversation(scope))
        runCurrent()
        val completed = store.state.value.memoryBooks!!.companion!!
        assertEquals("Memoir request\nOne more memoir note", completed.draft)
        assertEquals(completed.conversationId, completed.turns?.conversationId)
        assertNull(completed.pendingTurn)
        assertEquals(1, community.chatTurnPosts)
        assertEquals(rejected.text, community.sentBodies.first().let { Json.parseToJsonElement(it).jsonObject.getValue("text").jsonPrimitive.content })
        assertEquals("book" to bookId, community.startedTargets.last())
    }

    @Test fun failedMemoirCreateRetainsSameConversationIdAndRejectedMutationUntilRetryConfirms() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        store.queueMemoryBookConversation(); runCurrent()
        assertTrue(store.updateMemoryBookChatDraft("Original memoir question"))
        community.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        store.sendMemoryBookChat(); runCurrent()
        val rejected = store.state.value.memoryBooks!!.companion!!.pendingTurn
        assertNotNull(rejected)
        assertTrue(store.updateMemoryBookChatDraft("Later memoir detail"))
        val scope = store.memoryBookChatContinuationScope()!!
        community.conversationStartFailure = ApiFailure(FailureKind.OFFLINE)
        assertEquals(MemoryConversationContinuationResult.STARTED, store.continueMemoryBookChatInNewConversation(scope))
        runCurrent()
        val firstAttempt = community.startedConversationIds.last()
        val waiting = store.state.value.memoryBooks!!.companion!!
        assertEquals(rejected, waiting.pendingTurn)
        assertEquals(firstAttempt, waiting.pendingConversation?.id)
        assertEquals("Original memoir question\nLater memoir detail", waiting.draft)

        assertEquals(MemoryConversationContinuationResult.STARTED,
            store.retryMemoryBookChatContinuation(scope, waiting.pendingConversation!!))
        runCurrent()
        val completed = store.state.value.memoryBooks!!.companion!!
        assertEquals(listOf(firstAttempt, firstAttempt), community.startedConversationIds.takeLast(2))
        assertEquals(rejected?.text, community.sentBodies.first().let { Json.parseToJsonElement(it).jsonObject.getValue("text").jsonPrimitive.content })
        assertEquals("Original memoir question\nLater memoir detail", completed.draft)
        assertNull(completed.pendingTurn)
        assertNull(completed.continuation)
        assertEquals(1, community.chatTurnPosts)
    }

    @Test fun continuationOverLimitAndStaleScopeLeavePendingRequestAndComposerUntouched() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        openStory(store)
        store.startMemoryConversation(); runCurrent()
        val oversizedBase = "x".repeat(4090)
        assertTrue(store.updateMemoryChatDraft(oversizedBase))
        community.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        store.sendMemoryChat(); runCurrent()
        assertTrue(store.updateMemoryChatDraft("1234567"))
        val pending = store.state.value.savedMemoryStories!!.community!!.pendingTurn
        val before = store.state.value.savedMemoryStories!!.community!!.chatDraft
        val scope = store.memoryStoryChatContinuationScope()!!
        assertEquals(MemoryConversationContinuationResult.LIMIT, store.continueMemoryStoryChatInNewConversation(scope))
        val limited = store.state.value.savedMemoryStories!!.community!!
        assertEquals(pending, limited.pendingTurn)
        assertEquals(before, limited.chatDraft)
        assertNull(limited.pendingConversation)
        assertEquals(1, community.startedPosts)

        store.closeSavedMemoryStoryDetail()
        assertEquals(MemoryConversationContinuationResult.STALE, store.continueMemoryStoryChatInNewConversation(scope))
        assertEquals(1, community.chatTurnPosts)
        assertEquals(1, community.startedPosts)
    }

    @Test fun unrelatedRateLimitStaysGenericAndAccountChangeInvalidatesContinuationScope() = runTest {
        val ordinaryApi = CommunityApi()
        val ordinaryStore = newStore(StoryApi(), ordinaryApi)
        openStory(ordinaryStore)
        ordinaryStore.startMemoryConversation(); runCurrent()
        assertTrue(ordinaryStore.updateMemoryChatDraft("Keep this failed request"))
        ordinaryApi.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, retryAfterMillis = 5000)
        ordinaryStore.sendMemoryChat(); runCurrent()
        val ordinary = ordinaryStore.state.value.savedMemoryStories!!.community!!
        assertEquals(Message.RATE_LIMITED, ordinary.failure?.message)
        assertNull(ordinaryStore.memoryStoryChatContinuationScope())
        assertEquals(1, ordinaryApi.startedPosts)

        val scopedApi = CommunityApi()
        val scopedStore = newStore(StoryApi(), scopedApi)
        openStory(scopedStore)
        scopedStore.startMemoryConversation(); runCurrent()
        assertTrue(scopedStore.updateMemoryChatDraft("Retain the pending words"))
        scopedApi.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        scopedStore.sendMemoryChat(); runCurrent()
        val captured = scopedStore.memoryStoryChatContinuationScope()!!
        scopedStore.logout(); runCurrent()
        assertEquals(MemoryConversationContinuationResult.STALE, scopedStore.continueMemoryStoryChatInNewConversation(captured))
        assertEquals(1, scopedApi.chatTurnPosts)
        assertEquals(1, scopedApi.startedPosts)
    }

    @Test fun memoirContinuationRejectsChangedOrderedChildSnapshot() = runTest {
        val community = CommunityApi()
        val store = newStore(StoryApi(), community)
        openBookReader(store)
        store.queueMemoryBookConversation(); runCurrent()
        assertTrue(store.updateMemoryBookChatDraft("Memoir request"))
        community.chatTurnFailure = ApiFailure(FailureKind.HTTP, 429, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        store.sendMemoryBookChat(); runCurrent()
        val scope = store.memoryBookChatContinuationScope()!!
        val staleOrder = scope.copy(orderedChildren = scope.orderedChildren.reversed())
        assertEquals(MemoryConversationContinuationResult.STALE, store.continueMemoryBookChatInNewConversation(staleOrder))
        assertNull(store.state.value.memoryBooks!!.companion!!.pendingConversation)
        assertEquals(1, community.startedPosts)
        assertEquals(1, community.chatTurnPosts)
    }

    @Test fun composerIntroductionVoiceKeepsLatestWordsAndRequiresExplicitSave() = runTest {
        val api = StoryApi().apply { voiceEnabled = true }
        val community = CommunityApi()
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        val shelf = store.state.value.memoryBooks!!
        assertTrue(store.startMemoryBookComposition("account", store.state.value.generation, "family",
            shelf.shelfScopeId, "Garden memoir", "en"))
        runCurrent()
        val composer = store.memoryBookCompositionCoordinator!!
        val epoch = composer.state.value.actionEpoch
        composer.toggleStory(storyId, 3, shelf.shelfScopeId, epoch); runCurrent()
        composer.updateIntroduction("First typed sentence.", shelf.shelfScopeId, epoch)
        assertEquals(0, api.voiceCapabilityReads)
        val dictation = store.memoryBookCompositionDictationCoordinator
        val voice = dictation.open()!!
        assertFalse(composer.save(shelf.shelfScopeId, epoch, composer.state.value.draftRevision))
        runCurrent()
        assertEquals(1, api.voiceCapabilityReads)
        assertEquals(30, voice.beginRecording())
        assertFalse(composer.save(shelf.shelfScopeId, epoch, composer.state.value.draftRevision))
        voice.stopRecording(instructionWav())
        assertTrue(composer.updateIntroduction("Latest typed sentence.", shelf.shelfScopeId, epoch))
        runCurrent()
        assertEquals(api.instructionTranscript, voice.state.value.transcript)
        assertFalse(composer.save(shelf.shelfScopeId, epoch, composer.state.value.draftRevision))
        assertEquals(0, community.bookSaveCalls)
        assertTrue(dictation.insertTranscript(voice) { text ->
            composer.updateIntroduction(composer.state.value.introduction + "\n" + text, shelf.shelfScopeId, epoch)
        })
        val combined = "Latest typed sentence.\n" + api.instructionTranscript
        assertEquals(combined, composer.state.value.introduction)
        assertNull(voice.state.value.transcript)
        assertEquals(0, community.bookSaveCalls)
        assertTrue(composer.save(shelf.shelfScopeId, epoch, composer.state.value.draftRevision))
        runCurrent()
        assertEquals(MemoryBookCompositionStatus.CREATED, composer.state.value.status)
        assertEquals(combined, composer.state.value.createdBook?.introduction)
        assertEquals(1, community.bookSaveCalls)
        assertNull("a stale helper cannot start another capture after creation", voice.beginRecording())
        assertEquals(0, community.narrativeWrites)
        assertEquals(0, community.chatTurnPosts)
        assertTrue(api.instructionAudioBuffers.single().all { it == 0.toByte() })
    }

    @Test fun composerVoiceCloseRejectsOldEpochAndBackgroundClearsPrivateDraft() = runTest {
        val api = StoryApi().apply { voiceEnabled = true }
        val store = newStore(api, CommunityApi())
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        val shelf = store.state.value.memoryBooks!!
        val generation = store.state.value.generation
        assertTrue(store.startMemoryBookComposition("account", generation, "family", shelf.shelfScopeId, "First", "en"))
        runCurrent()
        val oldEpoch = store.memoryBookCompositionState.value.actionEpoch
        val oldVoice = store.memoryBookCompositionDictationCoordinator.open()!!; runCurrent()
        store.closeMemoryBookComposition(shelf.shelfScopeId, oldEpoch)
        assertNull(store.memoryBookCompositionDictationState.value)
        assertTrue(store.startMemoryBookComposition("account", generation, "family", shelf.shelfScopeId, "Replacement", "en"))
        runCurrent()
        val newVoice = store.memoryBookCompositionDictationCoordinator.open()!!; runCurrent()
        newVoice.beginRecording(); newVoice.stopRecording(instructionWav()); runCurrent()
        store.closeMemoryBookComposition(shelf.shelfScopeId, oldEpoch)
        assertSame(newVoice, store.memoryBookCompositionDictationState.value)
        assertEquals(api.instructionTranscript, newVoice.state.value.transcript)
        assertNull(oldVoice.beginRecording())
        store.background()
        assertNull(store.memoryBookCompositionDictationState.value)
        assertEquals(MemoryDictationState(), newVoice.state.value)
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.memoryBookCompositionState.value.status)
        assertEquals("", store.memoryBookCompositionState.value.title)
        assertTrue(store.memoryBookCompositionState.value.selectedStories.isEmpty())
    }

    @Test fun bookComposerStartsOnlyFromCurrentOwnerShelfAndOpensVerifiedBookWithoutChildPrefetch() = runTest {
        val api = StoryApi()
        val community = CommunityApi()
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        val shelf = store.state.value.memoryBooks!!
        val generation = store.state.value.generation
        assertEquals(0, api.savedStoryListReads)
        assertEquals(0, community.bookSaveCalls)
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.memoryBookCompositionState.value.status)

        assertFalse(store.startMemoryBookComposition("wrong-account", generation, shelf.library,
            shelf.shelfScopeId, "Family book", "en"))
        assertFalse(store.startMemoryBookComposition("account", generation + 1, shelf.library,
            shelf.shelfScopeId, "Family book", "en"))
        assertFalse(store.startMemoryBookComposition("account", generation, "other-library",
            shelf.shelfScopeId, "Family book", "en"))
        assertFalse(store.startMemoryBookComposition("account", generation, shelf.library,
            shelf.shelfScopeId + 1, "Family book", "en"))
        assertEquals(0, api.savedStoryListReads)

        assertTrue(store.startMemoryBookComposition("account", generation, shelf.library,
            shelf.shelfScopeId, "Family memories", "en"))
        runCurrent()
        assertEquals(1, api.savedStoryListReads)
        val composition = store.memoryBookCompositionCoordinator!!
        val composeState = composition.state.value
        assertTrue(composeState.canCreate)
        assertTrue(composition.toggleStory(storyId, 3, shelf.shelfScopeId, composeState.actionEpoch))
        runCurrent()
        assertTrue(composition.updateTitle("Garden memoir", shelf.shelfScopeId, composeState.actionEpoch))
        assertTrue(composition.updateIntroduction("A collection of family moments.", shelf.shelfScopeId, composeState.actionEpoch))
        assertTrue(composition.save(shelf.shelfScopeId, composeState.actionEpoch, composition.state.value.draftRevision))
        runCurrent()
        assertEquals(1, community.bookSaveCalls)
        assertEquals(MemoryBookCompositionStatus.CREATED, composition.state.value.status)
        val createdId = composition.state.value.createdBook!!.id
        val createdEpoch = composition.state.value.actionEpoch
        val childReadsBeforeOpen = api.childReads.size
        assertFalse(store.openComposedMemoryBook("wrong-account", generation, shelf.library, shelf.shelfScopeId,
            createdEpoch, createdId))
        assertFalse(store.openComposedMemoryBook("account", generation + 1, shelf.library, shelf.shelfScopeId,
            createdEpoch, createdId))
        assertFalse(store.openComposedMemoryBook("account", generation, "other-library", shelf.shelfScopeId,
            createdEpoch, createdId))
        assertFalse(store.openComposedMemoryBook("account", generation, shelf.library, shelf.shelfScopeId + 1,
            createdEpoch, createdId))
        assertEquals("stale result callbacks do not trigger a book read", 0, community.bookReads)
        assertTrue(store.openComposedMemoryBook("account", generation, shelf.library, shelf.shelfScopeId,
            createdEpoch, createdId))
        runCurrent()
        assertEquals(createdId, store.state.value.memoryBooks?.selectedBook?.id)
        assertEquals("opening the parent book does not add child reads", childReadsBeforeOpen, api.childReads.size)
        assertFalse(store.openComposedMemoryBook("account", generation, shelf.library, shelf.shelfScopeId,
            createdEpoch, createdId))
        val pageReadsBeforeClose = community.bookPageReads
        store.closeMemoryBook(); runCurrent()
        assertEquals("closing a newly created book refreshes page one", pageReadsBeforeClose + 1, community.bookPageReads)
        assertEquals(1, community.bookPageRequests.last())
    }

    @Test fun bookComposerRechecksCanCreateAndStaleShelfCallbacksCannotCreateOrOpen() = runTest {
        val api = StoryApi().apply { availableLibraries = listOf("family", "family-2") }
        val community = CommunityApi().apply { bookCanCreate = false }
        val store = newStore(api, community)
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        val deniedShelf = store.state.value.memoryBooks!!
        val generation = store.state.value.generation
        assertFalse(store.startMemoryBookComposition("account", generation, deniedShelf.library,
            deniedShelf.shelfScopeId, "No book", "en"))
        assertEquals(0, api.savedStoryListReads)

        community.bookCanCreate = true
        store.openMemoryBooks(); runCurrent()
        val oldShelf = store.state.value.memoryBooks!!
        assertTrue(store.startMemoryBookComposition("account", generation, oldShelf.library,
            oldShelf.shelfScopeId, "Private title", "en"))
        runCurrent()
        val oldEpoch = store.memoryBookCompositionState.value.actionEpoch
        val oldCoordinator = store.memoryBookCompositionCoordinator!!
        assertTrue(oldCoordinator.updateTitle("Private title", oldShelf.shelfScopeId, oldEpoch))
        store.closeMemoryBooks()
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.memoryBookCompositionState.value.status)
        assertEquals("", store.memoryBookCompositionState.value.title)
        assertTrue(store.state.value.memoryBooks == null)

        store.openMemoryBooks(); runCurrent()
        val newShelf = store.state.value.memoryBooks!!
        assertNotEquals(oldShelf.shelfScopeId, newShelf.shelfScopeId)
        assertFalse(store.startMemoryBookComposition("account", generation, oldShelf.library,
            oldShelf.shelfScopeId, "Stale", "en"))
        assertFalse(store.openComposedMemoryBook("account", generation, oldShelf.library,
            oldShelf.shelfScopeId, oldEpoch, bookId))
        assertEquals(0, community.bookSaveCalls)

        store.closeMemoryBooks()
        store.selectLibrary("family-2"); runCurrent()
        assertFalse(store.startMemoryBookComposition("account", generation, "family",
            newShelf.shelfScopeId, "Old library", "en"))
        assertFalse(store.openComposedMemoryBook("account", generation, "family",
            newShelf.shelfScopeId, oldEpoch, bookId))
        assertEquals(0, community.bookSaveCalls)
    }
    @Test fun memoirShelfLoadsOnlyCoverAndWipesItForComposerReaderAndBackground() = runTest {
        val api = StoryApi().apply { thumbnailFixture = byteArrayOf(0xff.toByte(), 0xd8.toByte(), 0xff.toByte(), 1) }
        val store = newStore(api, CommunityApi())
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        api.thumbnailReads.clear()
        store.openMemoryBooks(); runCurrent()
        val shelf = store.state.value.memoryBooks!!
        val generation = store.state.value.generation
        assertEquals(listOf("1"), api.thumbnailReads)
        assertTrue(api.childReads.isEmpty())
        assertEquals(0, api.originalReads)
        val cover = store.memoryBookShelfCoverState.value.images.getValue(bookId)
        assertFalse(cover.all { it == 0.toByte() })
        assertTrue(store.startMemoryBookComposition("account", generation, "family", shelf.shelfScopeId, "Memoir", "en"))
        assertTrue(cover.all { it == 0.toByte() })
        assertEquals(MemoryBookShelfCoverState(), store.memoryBookShelfCoverState.value)
        runCurrent()
        val epoch = store.memoryBookCompositionState.value.actionEpoch
        store.closeMemoryBookComposition(shelf.shelfScopeId, epoch); runCurrent()
        val replacement = store.memoryBookShelfCoverState.value.images.getValue(bookId)
        assertNotSame(cover, replacement)
        store.openMemoryBook(bookId); runCurrent()
        assertTrue(replacement.all { it == 0.toByte() })
        assertTrue(api.childReads.isEmpty())
        store.closeMemoryBook(); runCurrent()
        val returned = store.memoryBookShelfCoverState.value.images.getValue(bookId)
        store.background()
        assertTrue(returned.all { it == 0.toByte() })
        assertEquals(MemoryBookShelfCoverState(), store.memoryBookShelfCoverState.value)
        assertFalse(store.retryMemoryBookShelfCovers("account", generation, "family", shelf.shelfScopeId))
    }

    @Test fun lateShelfCoverAndDenialCannotRestoreClosedShelfOrInvalidateNewReader() = runTest {
        for (denied in listOf(false, true)) {
            val api = StoryApi().apply { thumbnailFixture = byteArrayOf(0xff.toByte(), 0xd8.toByte(), 0xff.toByte(), 1) }
            val store = newStore(api, CommunityApi())
            store.authenticate("+12025550123", "synthetic-password"); runCurrent()
            api.mediaGate = CompletableDeferred()
            api.thumbnailFailure = if (denied) ApiFailure(FailureKind.HTTP, 403) else null
            store.openMemoryBooks(); runCurrent()
            assertTrue(store.memoryBookShelfCoverState.value.busy)
            val oldShelf = store.state.value.memoryBooks!!
            store.openMemoryBook(bookId); runCurrent()
            assertEquals(bookId, store.state.value.memoryBooks?.selectedBook?.id)
            api.mediaGate!!.complete(Unit); runCurrent()
            assertEquals(bookId, store.state.value.memoryBooks?.selectedBook?.id)
            assertEquals(MemoryBookShelfCoverState(), store.memoryBookShelfCoverState.value)
            assertFalse(store.isCurrentMemoryBookShelf("account", store.state.value.generation, "family", oldShelf.shelfScopeId))
            if (!denied) assertTrue(api.lateMediaBytes!!.all { it == 0.toByte() })
            assertNull(store.state.value.problem)
            store.background()
        }
    }

    @Test fun currentShelfCoverDenialCoversPrivateSessionAndClearsShelf() = runTest {
        val api = StoryApi()
        val store = newStore(api, CommunityApi())
        store.authenticate("+12025550123", "synthetic-password"); runCurrent()
        api.thumbnailFailure = ApiFailure(FailureKind.HTTP, 403)
        store.openMemoryBooks(); runCurrent()
        assertEquals(MemoryBookShelfCoverState(), store.memoryBookShelfCoverState.value)
        assertNull(store.state.value.memoryBooks)
        assertEquals(Message.ACCESS_DENIED, store.state.value.problem?.message)
    }

}
