package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.*
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Synthetic edition closure, with no account, original media or provider access. */
internal object EditionSourceFixture {
    const val book = "11111111-1111-4111-8111-111111111111"
    const val child = "22222222-2222-4222-8222-222222222222"
    const val edition = "33333333-3333-4333-8333-333333333333"
    const val contribution = "44444444-4444-4444-8444-444444444444"
    val textId = "contribution-$contribution"
    val audioId = "contribution-55555555-5555-4555-8555-555555555555"
    val ids = listOf(textId,audioId,"family-$child","caption-101","editorial-book-$book","editorial-$child-chapter-1")
    fun scope() = MemoryBookEditionSourceScope(MemoryBookNarrativeScope("synthetic-reader",
        Bearer.from(SessionToken(86400,"a".repeat(43),"Bearer")),"family-a",1,book,7,
        listOf(EditorialChild(child,"2")),10),edition,ids)
    fun meta(id: String): JsonObject = buildJsonObject {
        put("source_id",id)
        put("origin",when(id) {
            textId -> "contribution_text"; audioId -> "contribution_audio"
            "family-$child" -> "asset_note"; "editorial-book-$book" -> "book_introduction"
            "editorial-$child-chapter-1" -> "story_chapter"; else -> "caption"
        })
        put("kind",when(id) { audioId -> "transcript"; "caption-101" -> "ai"
            "editorial-book-$book", "editorial-$child-chapter-1" -> "editorial"; else -> "family" })
        put("asset_id",if (id.startsWith("caption-") || id.startsWith("family-")) JsonPrimitive("101") else JsonNull)
    }
    fun page(page: Int = 1, state: String = "current", all: List<String> = ids) = buildJsonObject {
        put("version",1); put("book_id",book); put("edition_id",edition); put("book_revision","7")
        put("state",state); put("page",page); put("page_size",16)
        put("has_more",state == "current" && page * 16 < all.size)
        put("items",JsonArray(if (state == "current") all.drop((page-1)*16).take(16).map(::meta) else emptyList()))
    }
    fun detail(id: String, state: String = "current") = buildJsonObject {
        put("version",1); put("book_id",book); put("edition_id",edition); put("book_revision","7")
        put("source_id",id); put("state",state)
        put("source",if (state != "current") JsonNull else buildJsonObject {
            val m = meta(id)
            m.forEach { (k,v) -> if (k != "source_id") put(k,v) }
            put("story_id",if (id in listOf(textId,audioId,"editorial-$child-chapter-1")) JsonPrimitive(child) else JsonNull)
            put("byline",if (id == textId || id == audioId) JsonPrimitive("奶奶") else JsonNull)
            put("original_text",if (id == audioId) JsonNull else JsonPrimitive("家人原话，不把整理结果当原文。"))
            put("original_truncated",false)
            put("transcript",if (id == audioId) JsonPrimitive("这是一段需听原声核对的 AI 转写。") else JsonNull)
            put("transcript_truncated",false); put("prompt_excerpt","整理时使用的有限节选。")
            put("audio_available",id == audioId)
        })
    }
    fun wav(): ByteArray = ByteArray(44 + 320).also { bytes ->
        ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("RIFF".toByteArray()); putInt(bytes.size-8); put("WAVEfmt ".toByteArray()); putInt(16)
            putShort(1); putShort(1); putInt(16000); putInt(32000); putShort(2); putShort(16)
            put("data".toByteArray()); putInt(320)
        }
    }
}

class MemoryBookEditionSourceWireTest {
    private val f = EditionSourceFixture
    private fun page(value: JsonObject, n: Int = 1) = MemoryBookEditionSourceWire.decodePage(
        value.toString().toByteArray(),f.book,f.edition,7,n,listOf(f.child))
    private fun detail(value: JsonObject, id: String) = MemoryBookEditionSourceWire.decodeDetail(
        value.toString().toByteArray(),f.book,f.edition,7,id,listOf(f.child))
    private fun bad(block: () -> Unit) { try { block(); fail("Malformed source response admitted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE,e.kind) } }
    private fun edit(value: JsonObject, field: String, replacement: JsonElement) = JsonObject(value + (field to replacement))
    private fun material(id: String, field: String, replacement: JsonElement): JsonObject {
        val v=f.detail(id); return edit(v,"source",edit(v.getValue("source").jsonObject,field,replacement))
    }
    @Test fun sixOriginsKeepOriginalDerivedAndEditorialMaterialDistinct() {
        assertEquals(MemoryBookEditionSourceOrigin.entries.toSet(),page(f.page()).items.map { it.origin }.toSet())
        f.ids.forEach { id ->
            val source=detail(f.detail(id),id).source!!
            if (id == f.audioId) { assertNull(source.originalText); assertNotNull(source.transcript); assertTrue(source.audioAvailable) }
            else { assertNotNull(source.originalText); assertNull(source.transcript); assertFalse(source.audioAvailable) }
            assertFalse(source.toString().contains("家人原话"))
        }
    }
    @Test fun paginatedMetadataIsBoundedUniqueAndContainsNoRawMaterial() {
        val all=(101..117).map { "caption-$it" }
        assertTrue(page(f.page(all=all)).hasMore)
        assertEquals(16,page(f.page(all=all)).items.size)
        assertEquals(listOf("caption-117"),page(f.page(2,all=all),2).items.map { it.sourceId })
        bad { page(f.page(all=listOf(f.textId,f.textId))) }
        bad { page(edit(f.page(),"items",JsonArray(listOf(edit(f.meta(f.textId),"original_text",JsonPrimitive("leak")))))) }
        bad { page(edit(f.page(),"page_size",JsonPrimitive(17))) }
        bad { page(edit(f.page(),"has_more",JsonPrimitive(true))) }
        bad { page(edit(f.page(),"page",JsonPrimitive(7)),7) }
    }
    @Test fun foreignBookChildReceiptAndAmbiguousIdentityAreRejected() {
        bad { page(edit(f.page(),"book_revision",JsonPrimitive("8"))) }
        bad { detail(edit(f.detail(f.textId),"edition_id",JsonPrimitive(f.child)),f.textId) }
        bad { detail(material(f.textId,"story_id",JsonPrimitive(f.book)),f.textId) }
        bad { page(edit(f.page(),"items",JsonArray(listOf(edit(f.meta("editorial-${f.child}-chapter-1"),"source_id",JsonPrimitive("editorial-${f.book}-chapter-1")))))) }
        bad { detail(material(f.ids.last(),"byline",JsonPrimitive("independent witness")),f.ids.last()) }
        bad { detail(material(f.textId,"audio_available",JsonPrimitive(true)),f.textId) }
        bad { detail(material(f.audioId,"audio_available",JsonPrimitive(false)),f.audioId) }
        assertFalse(MemoryBookEditionSourceWire.validSourceId("../audio"))
        assertFalse(MemoryBookEditionSourceWire.validSourceId("caption-1%2faudio"))
    }
    @Test fun originalAndTranscriptByteLimitsTruncationAndStrictJsonAreEnforced() {
        val bounded="中".repeat(2730)
        assertEquals(bounded,detail(material(f.textId,"original_text",JsonPrimitive(bounded)),f.textId).source!!.originalText)
        bad { detail(material(f.textId,"original_text",JsonPrimitive(bounded+"中")),f.textId) }
        bad { detail(material(f.textId,"original_text",JsonPrimitive("raw\u0000text")),f.textId) }
        bad { detail(material(f.textId,"byline",JsonPrimitive("中".repeat(86))),f.textId) }
        bad { detail(material(f.audioId,"original_truncated",JsonPrimitive(true)),f.audioId) }
        bad { detail(material(f.textId,"transcript",JsonPrimitive("derived replaces raw")),f.textId) }
        val bytes=f.page().toString().replace("\"version\":1","\"version\":1,\"version\":1").toByteArray()
        bad { MemoryBookEditionSourceWire.decodePage(bytes,f.book,f.edition,7,1,listOf(f.child)) }
    }
    @Test fun changedAndInvalidatedResponsesHaveNoMaterialAndKeepImmutableRevision() {
        for (state in listOf("source_changed","source_invalidated")) {
            assertTrue(page(f.page(state=state)).items.isEmpty())
            assertNull(detail(f.detail(f.textId,state),f.textId).source)
            bad { detail(edit(f.detail(f.textId,state),"source",f.detail(f.textId).getValue("source")),f.textId) }
            bad { detail(edit(f.detail(f.textId,state),"book_revision",JsonPrimitive("8")),f.textId) }
        }
    }
}

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class MemoryBookEditionSourceStoreTest {
    private val f=EditionSourceFixture
    private class Fake : MemoryBookEditionSourceApi {
        val calls=mutableListOf<String>(); var state="current"; var failure: ApiFailure?=null
        var gate: CompletableDeferred<Unit>?=null; var bytes: ByteArray?=null; var invalidAudio=false
        private suspend fun answer(action: String, value: () -> ByteArray): ByteArray {
            calls+=action; gate?.let { withContext(NonCancellable) { it.await() } }; failure?.let { throw it }
            return value().also { bytes=it }
        }
        override suspend fun editionSources(token: Bearer, library: String, bookId: String, editionId: String, page: Int) =
            answer("page-$page") { EditionSourceFixture.page(page,state,(101..117).map { "caption-$it" }).toString().toByteArray() }
        override suspend fun editionSource(token: Bearer, library: String, bookId: String, editionId: String, sourceId: String) =
            answer("detail-$sourceId") { EditionSourceFixture.detail(sourceId,state).toString().toByteArray() }
        override suspend fun editionSourceAudio(token: Bearer, library: String, bookId: String, editionId: String, sourceId: String) =
            answer("audio-$sourceId") { if (invalidAudio) ByteArray(2*1024*1024+1) else EditionSourceFixture.wav() }
    }
    private fun repo(api: Fake, current: () -> MemoryBookEditionSourceScope?, denied: () -> Unit = {}) =
        MemoryBookEditionSourceRepository(api,{ current()?.book?.let { MemoryCommunityBinding(it.credential,it.library,it.generation) } },denied)
    @Test fun readsAreExplicitAndOnlyCurrentMetadataOrChapterReferencesSelectMaterial() = runTest {
        val current=f.scope(); val api=Fake(); val store=MemoryBookEditionSourceStore(repo(api,{current}),this,{current})
        assertTrue(api.calls.isEmpty()); assertFalse(store.loadAudio()); assertFalse(store.read("caption-999"))
        assertTrue(store.read(f.textId)); runCurrent()
        assertEquals(listOf("detail-${f.textId}"),api.calls); assertTrue(api.bytes!!.all { it==0.toByte() })
        assertTrue(store.loadPage()); assertNull(store.state.value.detail); runCurrent()
        assertEquals(16,store.state.value.listing!!.items.size)
        assertTrue(store.loadPage(2)); runCurrent(); assertEquals("caption-117",store.state.value.listing!!.items.single().sourceId)
        assertFalse(store.read("caption-116")); assertTrue(store.read("caption-117")); runCurrent()
        assertEquals(MemoryBookEditionSourceStatus.DETAIL,store.state.value.status)
        assertTrue(api.calls.none { it.startsWith("audio-") })
    }
    @Test fun audioNeedsCurrentTranscriptAndExplicitLoadAndIsWipedOnEveryReloadAndClose() = runTest {
        val current=f.scope(); val api=Fake(); val store=MemoryBookEditionSourceStore(repo(api,{current}),this,{current})
        store.read(f.audioId); runCurrent(); assertNotNull(store.state.value.detail!!.source!!.transcript)
        assertNull(store.state.value.audio); assertEquals(1,api.calls.size)
        store.loadAudio(); runCurrent(); val owned=store.state.value.audio!!
        assertFalse(owned.isClosed); assertTrue(api.bytes!!.all { it==0.toByte() })
        api.gate=CompletableDeferred(); store.loadAudio(); assertTrue(owned.isClosed)
        assertNull(store.state.value.audio); assertNotNull(store.state.value.detail!!.source!!.transcript); runCurrent()
        store.closeAudio(); api.gate!!.complete(Unit); runCurrent(); assertNull(store.state.value.audio)
        assertNotNull(store.state.value.detail); api.gate=null
        store.loadAudio(); runCurrent(); val replacement=store.state.value.audio!!
        store.read(f.textId); assertTrue(replacement.isClosed); assertNull(store.state.value.detail); runCurrent()
        assertFalse(store.loadAudio()); store.clear(); assertNull(store.state.value.detail)
    }
    @Test fun failedAudioCannotFallBackToEarlierRecordingOrTextAndMalformedBytesAreWiped() = runTest {
        val current=f.scope(); val api=Fake(); val store=MemoryBookEditionSourceStore(repo(api,{current}),this,{current})
        store.read(f.audioId); runCurrent(); store.loadAudio(); runCurrent(); val owned=store.state.value.audio!!
        api.invalidAudio=true; store.loadAudio(); assertTrue(owned.isClosed); runCurrent()
        assertEquals(MemoryBookEditionSourceStatus.FAILED,store.state.value.status)
        assertNull(store.state.value.audio); assertNull(store.state.value.detail); assertTrue(api.bytes!!.all { it==0.toByte() })
    }
    @Test fun changedDeletedOrConflictInvalidatesParentAndDoesNotDisplayOldMaterial() = runTest {
        for (state in listOf("source_changed","source_invalidated","conflict")) {
            val current=f.scope(); val api=Fake(); var invalidated=0
            val store=MemoryBookEditionSourceStore(repo(api,{current}),this,{current}) { invalidated++ }
            store.read(f.audioId); runCurrent(); store.loadAudio(); runCurrent(); val owned=store.state.value.audio!!
            if (state=="conflict") api.failure=ApiFailure(FailureKind.HTTP,409) else api.state=state
            store.read(f.audioId); assertTrue(owned.isClosed); assertNull(store.state.value.detail); runCurrent()
            assertEquals(1,invalidated); assertEquals(MemoryBookEditionSourceStatus.SOURCE_CHANGED,store.state.value.status)
            assertNull(store.state.value.detail); assertNull(store.state.value.listing); assertNull(store.state.value.audio)
        }
    }
    @Test fun accountLibraryCredentialChildAndEditionChangesDiscardLateRepliesAndDeniedResults() = runTest {
        val base=f.scope()
        val changed=listOf(base.copy(book=base.book.copy(accountId="other",generation=2)),
            base.copy(book=base.book.copy(library="family-b")),
            base.copy(book=base.book.copy(credential=Bearer.from(SessionToken(86400,"b".repeat(43),"Bearer")))),
            base.copy(book=base.book.copy(children=listOf(EditorialChild(f.child,"3")))),base.copy(editionId=f.child),null)
        for (next in changed) {
            var current: MemoryBookEditionSourceScope?=base; val api=Fake(); var denied=0
            val store=MemoryBookEditionSourceStore(repo(api,{current}) { denied++ },this,{current})
            store.read(f.textId); runCurrent(); api.gate=CompletableDeferred(); store.read(f.audioId); runCurrent()
            current=next; api.failure=ApiFailure(FailureKind.HTTP,403); api.gate!!.complete(Unit); runCurrent()
            assertEquals(0,denied); assertEquals(MemoryBookEditionSourceStatus.CLOSED,store.state.value.status)
            assertNull(store.state.value.detail); assertNull(store.state.value.audio)
        }
    }
    @Test fun currentDenialLocksCurrentAccessAndClearsTextAndAudio() = runTest {
        val current=f.scope(); val api=Fake(); var denied=0
        val store=MemoryBookEditionSourceStore(repo(api,{current}) { denied++ },this,{current})
        store.read(f.audioId); runCurrent(); store.loadAudio(); runCurrent(); val owned=store.state.value.audio!!
        api.failure=ApiFailure(FailureKind.HTTP,403); store.loadPage(); assertTrue(owned.isClosed); runCurrent()
        assertEquals(1,denied); assertNull(store.state.value.detail); assertNull(store.state.value.audio)
    }
    @Test fun closedReaderCancelsLateAudioAndNoFeatureOrOriginalFallbackRuns() = runTest {
        var current: MemoryBookEditionSourceScope?=f.scope(); val api=Fake()
        val store=MemoryBookEditionSourceStore(repo(api,{current}),this,{current})
        store.read(f.audioId); runCurrent(); api.gate=CompletableDeferred(); store.loadAudio(); runCurrent()
        store.clear(); current=null; api.gate!!.complete(Unit); runCurrent()
        assertNull(store.state.value.audio); assertTrue(api.bytes!!.all { it==0.toByte() })
        assertFalse(store.read(f.textId)); assertFalse(store.loadPage()); assertFalse(store.loadAudio())
        current=f.scope(); api.gate=null; api.failure=ApiFailure(FailureKind.HTTP,503)
        store.read(f.textId); runCurrent(); assertEquals(MemoryBookEditionSourceStatus.UNAVAILABLE,store.state.value.status)
        assertEquals(3,api.calls.size)
    }
}
