package dev.photohouse.connected

import kotlinx.coroutines.CompletableDeferred
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*

/** Generated protected memoir data shared by navigation and audio UI journeys. */
internal class GeneratedMemoirReaderApi : PhotoHouseApi, MemoryCommunityApi {
    override val protectedNativeV2Enabled = true
    var childReads = 0
    var originalCalls = 0
    var videoCalls = 0
    val previewReads = mutableListOf<String>()
    val previewResponses = mutableListOf<ByteArray?>()
    var previewGate: CompletableDeferred<Unit>? = null
    private val assets = (1..12).map { Asset(it.toString(), "image", 800, 600, null, null, "/synthetic-thumbnail") }
    override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
    override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
    override suspend fun session(token: Bearer) = Session(ACCOUNT, "+12025550123",
        listOf(Membership(LIBRARY, "approved", "viewer", 1, null, 0, true)))
    override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
    override suspend fun logout(token: Bearer) = Unit
    override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 0, false, emptyList())
    override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, assets.first { it.id == assetId })
    override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
    override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
    override suspend fun detailPreview(token: Bearer, library: String, asset: Asset): ByteArray? {
        previewReads += asset.id
        previewGate?.await()
        return if (previewResponses.isEmpty()) null else previewResponses.removeAt(0)?.copyOf()
    }
    override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk {
        videoCalls++; error("Original playback is outside this reader fixture")
    }
    override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray {
        originalCalls++; error("Original photos are outside this reader fixture")
    }
    override suspend fun capabilities(token: Bearer, library: String) =
        """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()
    private fun book() = """{"version":1,"type":"memoir","id":"$BOOK","revision":"2","can_edit":false,"title":"Garden memoir / 花园回忆册","introduction":"A generated reading fixture.","language":"zh","stories":[{"id":"$FIRST","title":"A garden day / 花园的一天","revision":"3","item_count":12,"cover_asset_id":"1"},{"id":"$SECOND","title":"The way home / 回家的路","revision":"5","item_count":12,"cover_asset_id":"1"}]}"""
    override suspend fun listBooks(token: Bearer, library: String, page: Int) =
        """{"version":1,"library_id":"$library","page":$page,"page_size":8,"has_more":false,"can_create":false,"items":[${book()}]}""".toByteArray()
    override suspend fun getBook(token: Bearer, library: String, bookId: String) = book().toByteArray()
    override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
        childReads++
        return SavedMemoryStory(storyId, library, revision, 1710000000, 1720000000, false, "a".repeat(64),
            "Generated story / 合成故事", "everyday", "zh", assets.map { MemoryStoryAsset(it, emptyList()) },
            (1..3).map { chapter -> SavedMemoryStoryChapter("chapter-$chapter", "Chapter $chapter / 第 $chapter 章",
                "A generated family walk.", assets.drop((chapter - 1) * 4).take(4).map { it.id }, emptyList()) }, emptyList())
    }

    companion object {
        const val ACCOUNT = "memoir-reader"
        const val LIBRARY = "family"
        const val BOOK = "00000000-0000-4000-8000-000000000011"
        const val FIRST = "00000000-0000-4000-8000-000000000012"
        const val SECOND = "00000000-0000-4000-8000-000000000013"
    }
}
