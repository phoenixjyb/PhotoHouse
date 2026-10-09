package dev.photohouse.connected

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.WindowManager
import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.File

/** Synthetic component tests. No configured origin, network or test bypass in the APK. */
@RunWith(AndroidJUnit4::class)
class ConnectedUiTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun stop() { scope.cancel() }
    private class SyntheticApi : PhotoHouseApi {
        override var discoveryEnabled = false
        override var familyTagsEnabled = false
        override var uploadEnabled = false
        override var protectedNativeV2Enabled = false
        override var assistantEnabled = false
        var assistantTurns = 0
        var assistantSpeechEnabled = false
        var assistantSpeechCalls = 0
        val assistantContexts = mutableListOf<JsonObject?>()
        override suspend fun assistantCapabilities(token: Bearer, library: String) = AssistantCapabilities(true, true, false, assistantSpeechEnabled, 0)
        override suspend fun assistantSpeech(token: Bearer, library: String, context: JsonObject?, language: String): ByteArray {
            assistantSpeechCalls++
            return ByteArray(46).also { "RIFF".toByteArray().copyInto(it); "WAVE".toByteArray().copyInto(it, 8) }
        }
        override suspend fun assistantTurn(token: Bearer, library: String, text: String, context: JsonObject?): AssistantTurn {
            assistantTurns++; assistantContexts += context
            val next = buildJsonObject { put("visible_ids", buildJsonArray { add("1") }); put("revision", "synthetic-revision") }
            return if (assistantTurns == 1) AssistantTurn("results", "Found one memory.", next, null, photos, 1, false, null)
            else AssistantTurn("open", "Opening the selected memory.", next, null, emptyList(), 0, false, AssistantEffect("open_asset", "1"))
        }
        var uploadCalls = 0
        val directDestinations = mutableListOf<String?>()
        val sessionDestinations = mutableListOf<String?>()
        override suspend fun uploadPhoto(token: Bearer, source: UploadSource, batch: String, destinationLibraryId: String?, onProgress: (Long) -> Unit): UploadReceipt {
            uploadCalls++; directDestinations += destinationLibraryId; onProgress(source.bytes)
            return UploadReceipt("7", destinationLibraryId, "synthetic-member", batch, "image", 1, 1, "a".repeat(64), source.bytes, 5)
        }
        var discoveryError: ApiFailure? = null
        var discoverySearches = 0
        val placeQueries = mutableListOf<String>()
        var discoveredFilters: PhoneFilters? = null
        private val pinned = PhoneChoice("7", "Sample family", 1, listOf("示例家人"))
        override suspend fun facets(token: Bearer, library: String, facet: PhoneFacet, page: Int, binding: String?): PhoneFacetPage {
            val snap = PhoneSnapshot(library, "b".repeat(64), "1", PhoneDiscoveryWire.fields, 51, 51,
                PhoneDiscoveryWire.fields.associateWith { PhoneCoverage(51, 0) }, "2026-01-01", "2026-12-31", listOf(pinned))
            val choices = if (page == 1) (1..50).map { if (it == 7) pinned else PhoneChoice(it.toString(), "Sample $it · 示例", 1) }
                else listOf(PhoneChoice("51", "Later choice · 后页选项", 1))
            return PhoneFacetPage(snap, facet, page, 50, 51, page == 1, choices)
        }
        override suspend fun placeFacets(token: Bearer, library: String, page: Int, query: String, binding: String?): PhoneFacetPage {
            placeQueries += query
            return facets(token, library, PhoneFacet.PLACES, page, binding)
        }
        override suspend fun familyTags(token: Bearer, library: String, page: Int, query: String): FamilyTagsPage =
            FamilyTagsPage(library, page, 25, 1, listOf(FamilyTagChoice("Garden walks", photos.size)))
        override suspend fun familyTagAssets(token: Bearer, library: String, tag: String, page: Int): Gallery =
            Gallery(library, page, 25, photos.size.toLong(), originalsAllowed, photos)
        override suspend fun search(token: Bearer, library: String, binding: String, filters: PhoneFilters, page: Int, fingerprint: String?): PhoneSearchPage {
            discoverySearches++; discoveredFilters = filters; discoveryError?.let { throw it }
            return PhoneSearchPage(Gallery(library, page, 50, 51, originalsAllowed, photos), binding, "f".repeat(64), page == 1)
        }
        var previewBytes: ByteArray? = null
        override var preparedVideoEnabled = false
        var preparedHeads = 0
        var originalVideoReads = 0
        var preparedError: ApiFailure? = null
        override suspend fun preparedVideoInfo(token: Bearer, library: String, assetId: String): PreparedVideoInfo {
            preparedHeads++; preparedError?.let { throw it }
            return PreparedVideoInfo(videoBytes.size.toLong(), "\"" + "a".repeat(64) + "\"")
        }
        override suspend fun preparedVideoRange(token: Bearer, library: String, assetId: String, info: PreparedVideoInfo, start: Long, length: Int): VideoChunk {
            preparedError?.let { throw it }; return readVideo(start, length)
        }
        var videoBytes = byteArrayOf()
        val videoReads = java.util.concurrent.CopyOnWriteArrayList<Pair<Long, Int>>()
        var registrationCode: String? = null
        val photo = Asset("1", "video", null, null, null, "2026-01-01", "/assets/1/thumbnail?library=synthetic-library")
        var photos = listOf(photo)
        var total = 1L
        var originalsAllowed = false
        var uploadHistoryPages: Map<Int, UploadHistoryPage> = emptyMap()
        var memberships = listOf(Membership("synthetic-library", "approved", "viewer", 1, null, 0, true))
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String): SessionToken { registrationCode = code; return login(phone, password) }
        override suspend fun session(token: Bearer) = Session("synthetic-account", "+12025550123", memberships)
        override suspend fun logout(token: Bearer) { }
        override suspend fun acceptInvitation(token: Bearer, code: String) { }
        override suspend fun uploadHistory(token: Bearer, page: Int): UploadHistoryPage =
            uploadHistoryPages[page] ?: UploadHistoryPage(page, 10, 0, emptyList())
        var batchOffset = 0L
        override suspend fun createUploadSession(token: Bearer, request: UploadSessionRequest): UploadSession {
            sessionDestinations += request.destinationLibraryId
            return UploadSession("c".repeat(32), request.bytes, batchOffset, 4194304, "uploading", null)
        }
        override suspend fun uploadSession(token: Bearer, uploadId: String) = UploadSession(uploadId, 4, batchOffset, 4194304, "uploading", null)
        override suspend fun uploadChunk(token: Bearer, uploadId: String, offset: Long, chunk: ByteArray, sha256: String): UploadSession { batchOffset = offset + chunk.size; return UploadSession(uploadId, 4, batchOffset, 4194304, "uploading", null) }
        override suspend fun completeUploadSession(token: Bearer, uploadId: String) = UploadSession(uploadId, 4, 4, 4194304, "complete", "902")
        override suspend fun cancelUploadSession(token: Bearer, uploadId: String) = UploadSession(uploadId, 4, batchOffset, 4194304, "cancelled", null)
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, total, false, photos)
        var transientDetailFailures = 0
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail {
            if (transientDetailFailures > 0) { transientDetailFailures--; throw ApiFailure(FailureKind.HTTP, 503) }
            return Detail(library, originalsAllowed, photos.first { it.id == assetId })
        }
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, listOf(Caption("1", "<b>Literal 原文</b>", false, false, null, null)))
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = previewBytes
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk {
            originalVideoReads++; return readVideo(start, length)
        }
        private fun readVideo(start: Long, length: Int): VideoChunk {
            videoReads += start to length
            return VideoChunk(start, videoBytes.size.toLong(), videoBytes.copyOfRange(start.toInt(), minOf(videoBytes.size, start.toInt() + length)))
        }
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray {
            val bitmap = Bitmap.createBitmap(800, 600, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            canvas.drawColor(android.graphics.Color.rgb(60, 120, 160))
            val paint = android.graphics.Paint().apply { color = android.graphics.Color.YELLOW }
            canvas.drawRect(80f, 80f, 400f, 360f, paint)
            return java.io.ByteArrayOutputStream().use { stream ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream); bitmap.recycle(); stream.toByteArray()
            }
        }
    }
    private fun reveal(matcher: SemanticsMatcher) { rule.onNodeWithTag("connected-screen").performScrollToNode(matcher) }
    private fun awaitLibrary(store: ConnectedStore, library: String = "synthetic-library") {
        rule.waitUntil(5000) { store.state.value.library == library }
        rule.waitForIdle()
    }
    private fun click(text: String) {
        val matcher = hasText(text) and hasClickAction()
        if (text in listOf("简体中文", "English", "System", "系统", "Sign out", "退出登录")) {
            reveal(hasTestTag("app-settings")); rule.onNodeWithTag("app-settings").performClick()
        } else reveal(matcher)
        if (text in listOf("Go to page", "跳转页面")) rule.onAllNodes(matcher).onFirst().performClick() else rule.onNode(matcher).performClick()
        rule.waitForIdle()
    }
    private fun details(id: String) {
        reveal(hasTestTag("details-$id")); rule.onNodeWithTag("details-$id").performClick(); rule.waitForIdle()
    }
    private fun positionSeconds(): Int {
        val clock = rule.onNodeWithTag("video-position").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.Text].first().text.substringBefore(" / ")
        return clock.split(':').fold(0) { total, part -> total * 60 + part.toInt() }
    }
    private fun input(label: String, text: String) { val matcher = hasText(label) and hasSetTextAction(); reveal(matcher); rule.onNode(matcher).performTextInput(text) }
    private fun screenAwake(): Boolean {
        fun awake(view: android.view.View): Boolean = view.keepScreenOn || view is android.view.ViewGroup &&
            (0 until view.childCount).any { awake(view.getChildAt(it)) }
        return rule.runOnIdle { awake(rule.activity.window.decorView) }
    }
    private fun capture(name: String) {
        rule.waitForIdle()
        val videoBounds = if (name.startsWith("video-")) rule.onNodeWithTag("video-surface").fetchSemanticsNode().boundsInWindow else null
        rule.runOnUiThread {
            // Dialogs own a separate window; draw that owned window without
            // disabling FLAG_SECURE or capturing another application's surface.
            val view = if (name.startsWith("settings-")) {
                check(android.os.Build.VERSION.SDK_INT >= 29) { "Dialog render evidence requires API 29+" }
                android.view.inspector.WindowInspector.getGlobalWindowViews()
                    .last { it.isShown && it !== rule.activity.window.decorView }
            } else rule.activity.window.decorView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            view.draw(canvas)
            // Software View.draw may omit the hardware video layer. Keep a separate
            // test-owned decoded frame; do not composite or disable FLAG_SECURE.
            if (name.startsWith("video-")) {
                fun textures(node: android.view.View): List<android.view.TextureView> = when (node) {
                    is android.view.TextureView -> listOf(node)
                    is android.view.ViewGroup -> (0 until node.childCount).flatMap { textures(node.getChildAt(it)) }
                    else -> emptyList()
                }
                val texture = textures(view).single()
                assertEquals("Video keeps its decoded aspect ratio", 16f / 9f, texture.width.toFloat() / texture.height, 0.02f)
                val frame = requireNotNull(texture.bitmap)
                val colors = mutableSetOf<Int>()
                for (y in 0 until frame.height step 8) for (x in 0 until frame.width step 8) colors += frame.getPixel(x, y)
                assertTrue("Decoded synthetic video must contain colored pixels", colors.size > 8)
                val bounds = requireNotNull(videoBounds)
                assertEquals(16f / 9f, bounds.width / bounds.height, 0.02f)
                File(rule.activity.filesDir, "$name-frame.png").outputStream().use { frame.compress(Bitmap.CompressFormat.PNG, 100, it) }
                frame.recycle()
            }
            File(rule.activity.filesDir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            bitmap.recycle()
        }
    }
    private fun clickTag(tag: String) { reveal(hasTestTag(tag)); rule.onNodeWithTag(tag).performClick(); rule.waitForIdle() }
    @Test fun discoverySelectionPagingMediaReturnAndBilingualLayout() {
        val api = SyntheticApi().apply { discoveryEnabled = true }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); clickTag("open-discovery")
        clickTag("pin-7")
        capture("discovery-en")
        clickTag("facet-next"); clickTag("choice-people-51"); clickTag("facet-previous")
        assertEquals(listOf("7", "51"), store.state.value.discovery!!.filters.people.map { it.id })
        clickTag("facet-tags")
        clickTag("choice-tags-1")
        clickTag("browse-places")
        rule.onNodeWithTag("discovery-places-coverage").assertTextContains("51", substring = true)
        rule.onNodeWithTag("place-query").performTextInput("Beijing")
        clickTag("place-query-search")
        assertEquals("Beijing", api.placeQueries.last())
        reveal(hasTestTag("place-query-search")); rule.onNodeWithTag("place-query-search").assertIsDisplayed()
        clickTag("choice-locations-2")
        capture("discovery-place-selected")
        reveal(hasTestTag("discovery-caption")); rule.onNodeWithTag("discovery-caption").performTextInput("生日 birthday")
        reveal(hasTestTag("discovery-from")); rule.onNodeWithTag("discovery-from").performTextInput("2026-01-01")
        clickTag("discovery-media-video")
        reveal(hasTestTag("discovery-filter-summary")); rule.onNodeWithTag("discovery-filter-summary").assertTextContains("2026-01-01", substring = true)
        assertEquals(0, api.discoverySearches)
        clickTag("discovery-quick-apply")
        assertEquals(1, api.discoverySearches); assertEquals("生日 birthday", api.discoveredFilters!!.caption)
        assertEquals("2026-01-01", api.discoveredFilters!!.from)
        assertEquals(listOf("2"), api.discoveredFilters!!.places.map { it.id })
        click("Next")
        reveal(hasTestTag("media-1")); rule.onNodeWithTag("media-1").performClick(); rule.waitForIdle()
        assertNull(store.state.value.video) // Fresh detail denies originals; discovery does not grant them.
        click("Back to results")
        assertEquals(2, store.state.value.gallery!!.page)
        clickTag("open-discovery")
        click("简体中文")
        reveal(hasText("寻找回忆")); capture("discovery-zh")
        clickTag("discovery-apply")
        rule.runOnUiThread { store.background() }
        rule.waitForIdle(); assertNull(store.state.value.discovery); assertTrue(store.state.value.previews.isEmpty())
    }
    @Test fun assistantReceiptShowsChineseConfirmedStateAndSelectableRequestId() {
        val id = "123e4567-e89b-42d3-a456-426614174000"
        val clientState = androidx.compose.runtime.mutableStateOf(AssistantClientState("synthetic-library", 1,
            capabilities = AssistantCapabilities(true,true,false,false,0),
            lastRequestReceipt = AssistantRequestReceipt(id,"unknown",null)))
        var checks = 0; var sends = 0
        rule.runOnUiThread { rule.activity.setContent {
            PhotoHouseTheme { AssistantScreen(clientState.value, true, onBack={}, previews=emptyMap(), onSend={ sends++; true }, onClear={},
                onOpen={_,_->}, onCheckReceipt={ checks++; clientState.value=clientState.value.copy(lastRequestReceipt=AssistantRequestReceipt(id,"enabled","succeeded")) },
                onRetryCapabilities={}, recording=false, recordError=false, onRecord={}, onStopRecording={},
                onCancelRecording={}, onClearTranscript={}, onPlaySpeech={}, onStopSpeech={}) }
        } }
        rule.onNodeWithTag("assistant-suggestion-0").performClick()
        rule.onNodeWithTag("assistant-text").assertTextContains("找去年的视频")
        assertEquals("Choosing an example only fills the composer", 0, sends)
        rule.onNodeWithTag("assistant-receipt").assertTextContains("尚未确认服务器回执", substring=true)
        rule.onNodeWithTag("assistant-receipt").assertTextContains(id, substring=true)
        rule.onNodeWithTag("assistant-check-receipt").performClick()
        rule.onNodeWithTag("assistant-receipt").assertTextContains("服务器已完成", substring=true)
        assertEquals(1,checks)
        rule.onNodeWithTag("assistant-suggestion-2").performClick()
        rule.onNodeWithTag("assistant-text").assertTextContains("打开第一个结果")
        assertEquals("Selecting a follow-up suggestion does not send it", 0, sends)
        val image=rule.onRoot().captureToImage().asAndroidBitmap()
        File(rule.activity.filesDir,"assistant-receipts-zh.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG,100,it) }
    }
    @Test fun assistantUncertainTurnKeepsReviewedTextAndReceiptCheckNeverResends() {
        val transcriptId = "123e4567-e89b-42d3-a456-426614174000"
        val turnId = "123e4567-e89b-42d3-a456-426614174001"
        val lastContext = buildJsonObject { put("revision", "known-context") }
        val prompt = "找已确认的海边照片" + "A".repeat(500)
        val clientState = androidx.compose.runtime.mutableStateOf(AssistantClientState("synthetic-library", 1,
            capabilities = AssistantCapabilities(true, true, true, false, 30),
            context = lastContext, transcript = AssistantTranscript(prompt, "zh",
                AssistantRequestReceipt(transcriptId, "enabled", "succeeded")),
            confirmedTranscriptRequestId = null,
            lastRequestReceipt = AssistantRequestReceipt(transcriptId, "enabled", "succeeded")))
        var checks = 0
        var sends = 0
        rule.runOnUiThread { rule.activity.setContent {
            PhotoHouseTheme { AssistantScreen(clientState.value, true, onBack={}, previews=emptyMap(), onSend={ text ->
                sends++
                val latest = clientState.value
                clientState.value = latest.copy(busy = false,
                    pendingTurn = AssistantPendingTurn("synthetic-account", latest.library, latest.generation, text,
                        latest.context, latest.confirmedTranscriptRequestId, turnId),
                    lastRequestReceipt = AssistantRequestReceipt(turnId, "unknown", null))
                true
            },
                onClear={ clientState.value = clientState.value.copy(turns = emptyList(), context = null, pendingTurn = null,
                    transcript = null, confirmedTranscriptRequestId = null, lastRequestReceipt = null, receiptDetail = null) }, onOpen={_,_->},
                onCheckReceipt={ checks++; clientState.value = clientState.value.copy(
                    lastRequestReceipt = AssistantRequestReceipt(turnId, "enabled", "succeeded"),
                    receiptDetail = AssistantReceipt(turnId, "turn", transcriptId, "succeeded", "2026-10-03T00:00:00Z",
                        "2026-10-03T00:00:01Z", "2026-11-02T00:00:00Z", 200, null, prompt, null, "results", 1, null)) },
                onRetryCapabilities={}, recording=false, recordError=false, onRecord={}, onStopRecording={},
                onCancelRecording={}, onClearTranscript={ clientState.value = clientState.value.copy(transcript = null, confirmedTranscriptRequestId = null) },
                onUseTranscript={ expected ->
                    val current = clientState.value
                    if (current.transcript !== expected || current.confirmedTranscriptRequestId != null) null
                    else {
                        clientState.value = current.copy(transcript = null, confirmedTranscriptRequestId = expected.receipt?.requestId)
                        expected.text
                    }
                }, onPlaySpeech={}, onStopSpeech={}) }
        } }
        rule.onNodeWithTag("assistant-text").assertTextContains("询问相册内容", substring = true)
        assertEquals("A transcript is not prefilled into the message", "", rule.onNodeWithTag("assistant-text").fetchSemanticsNode().config[
            androidx.compose.ui.semantics.SemanticsProperties.EditableText].text)
        rule.onNodeWithTag("assistant-send").assertIsNotEnabled()
        assertNull(clientState.value.confirmedTranscriptRequestId)
        rule.onNodeWithTag("assistant-turns").performScrollToNode(hasTestTag("assistant-transcript-review"))
        rule.onNodeWithTag("assistant-insert-transcript").assertIsEnabled().performClick()
        rule.onNodeWithTag("assistant-text").assertTextContains(prompt)
        assertNull(clientState.value.transcript)
        assertEquals(transcriptId, clientState.value.confirmedTranscriptRequestId)
        rule.onNodeWithTag("assistant-text").performImeAction()
        assertEquals(1, sends)
        val pending = clientState.value.pendingTurn!!
        assertEquals(prompt, pending.text)
        assertEquals(transcriptId, pending.parentRequestId)
        assertEquals(lastContext, pending.context)
        rule.onNodeWithTag("assistant-turns").performScrollToNode(hasTestTag("assistant-pending-status"))
        rule.onNodeWithTag("assistant-pending-status").assertIsDisplayed()
        rule.onNodeWithTag("assistant-check-receipt").assertIsDisplayed()
        rule.onNodeWithTag("assistant-close-pending").assertIsDisplayed()
        rule.onNodeWithTag("assistant-pending-status").assertTextContains("结果尚不确定", substring = true)
        rule.onNodeWithTag("assistant-text").assertTextContains("询问相册内容", substring = true)
        rule.onNodeWithTag("assistant-text").assertIsEnabled()
        rule.onNodeWithTag("assistant-send").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-check-receipt").performClick()
        assertEquals(1, checks); assertEquals(1, sends)
        rule.onNodeWithTag("assistant-pending-status").assertTextContains("回复和更新后的上下文没有取回", substring = true)
        rule.onNodeWithTag("assistant-pending-explanation").assertTextContains("查询回执不会重新发送请求", substring = true)
        rule.onNodeWithTag("assistant-discard-transcript").assertDoesNotExist()
        assertEquals(pending, clientState.value.pendingTurn)
        assertEquals(lastContext, clientState.value.context)
        rule.onNodeWithTag("assistant-text").performTextInput("新的未发送问题")
        rule.onNodeWithTag("assistant-send").assertIsNotEnabled()
        assertEquals(pending.text, clientState.value.pendingTurn!!.text)
        val image = rule.onRoot().captureToImage().asAndroidBitmap()
        val screenshotUri = rule.activity.contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            android.content.ContentValues().apply {
                put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, "assistant-pending-receipt-150pct.png")
                put(android.provider.MediaStore.MediaColumns.MIME_TYPE, "image/png")
                put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH, android.os.Environment.DIRECTORY_PICTURES)
            })
        assertNotNull(screenshotUri)
        rule.activity.contentResolver.openOutputStream(screenshotUri!!).use { output ->
            requireNotNull(output).use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
        rule.onNodeWithTag("assistant-text").performClick()
        rule.waitUntil(5000) { rule.activity.window.decorView.rootWindowInsets?.isVisible(android.view.WindowInsets.Type.ime()) == true }
        rule.onNodeWithTag("assistant-text").assertIsDisplayed()
        rule.onNodeWithTag("assistant-pending-status").assertIsDisplayed()
        rule.onNodeWithTag("assistant-check-receipt").assertIsDisplayed()
        rule.onNodeWithTag("assistant-close-pending").assertIsDisplayed()
        rule.onNodeWithTag("assistant-close-pending").performClick()
        assertNull(clientState.value.pendingTurn); assertNull(clientState.value.context)
        rule.onNodeWithTag("assistant-text").assertTextContains("新的未发送问题", substring = true)
        rule.onNodeWithTag("assistant-send").assertIsEnabled()
        assertEquals("Starting fresh clears the old question without resubmitting it", 1, sends)
    }
    @Test fun assistantFailedReceiptMustBeExplicitlyRestoredBeforeNewSend() {
        val transcriptId = "123e4567-e89b-42d3-a456-426614174000"
        val turnId = "123e4567-e89b-42d3-a456-426614174001"
        val prompt = "打开经审核的结果"
        val pending = AssistantPendingTurn("synthetic-account", "synthetic-library", 1, prompt,
            null, transcriptId, turnId)
        val clientState = androidx.compose.runtime.mutableStateOf(AssistantClientState("synthetic-library", 1,
            capabilities = AssistantCapabilities(true, true, false, false, 0),
            transcript = AssistantTranscript(prompt, "zh", AssistantRequestReceipt(transcriptId, "enabled", "succeeded")),
            lastRequestReceipt = AssistantRequestReceipt(turnId, "enabled", "failed"),
            receiptDetail = AssistantReceipt(turnId, "turn", transcriptId, "failed", "2026-10-03T00:00:00Z",
                "2026-10-03T00:00:01Z", "2026-11-02T00:00:00Z", 503, "provider_unavailable", prompt, null, null, null, null),
            pendingTurn = pending))
        var sends = 0
        rule.runOnUiThread { rule.activity.setContent {
            PhotoHouseTheme { AssistantScreen(clientState.value, true, onBack={}, previews=emptyMap(), onSend={ sends++; true },
                onClear={ clientState.value = clientState.value.copy(pendingTurn = null, context = null, turns = emptyList(),
                    transcript = null, confirmedTranscriptRequestId = null, lastRequestReceipt = null, receiptDetail = null) },
                onOpen={_,_->}, onCheckReceipt={}, onRetryCapabilities={}, recording=false, recordError=false,
                onRecord={}, onStopRecording={}, onCancelRecording={}, onClearTranscript={}, onPlaySpeech={}, onStopSpeech={}) }
        } }
        rule.onNodeWithTag("assistant-text").assertIsEnabled()
        rule.onNodeWithTag("assistant-close-pending").assertTextContains("关闭并恢复问题")
        rule.onNodeWithTag("assistant-close-pending").performClick()
        rule.onNodeWithTag("assistant-text").assertTextContains(prompt)
        rule.onNodeWithTag("assistant-send").assertIsEnabled()
        assertEquals("Restoring a failed request is a draft only; it is not auto-sent", 0, sends)
    }
    @Test fun assistantComposerClearsOnlyAfterAcceptedSubmission() {
        val clientState = androidx.compose.runtime.mutableStateOf(AssistantClientState("synthetic-library", 1,
            capabilities = AssistantCapabilities(true, true, false, false, 0)))
        var accept = false
        var sends = 0
        rule.runOnUiThread { rule.activity.setContent {
            PhotoHouseTheme { AssistantScreen(clientState.value, true, onBack={}, previews=emptyMap(), onSend={ text ->
                sends++
                if (!accept) false else {
                    clientState.value = clientState.value.copy(turns = listOf(AssistantExchange(text,
                        AssistantTurn("results", "synthetic success", null, null, emptyList(), 0, false, null))),
                        context = buildJsonObject { put("revision", "new-known-context") })
                    true
                }
            }, onClear={}, onOpen={_,_->}, onCheckReceipt={}, onRetryCapabilities={}, recording=false, recordError=false,
                onRecord={}, onStopRecording={}, onCancelRecording={}, onClearTranscript={}, onPlaySpeech={}, onStopSpeech={}) }
        } }
        rule.onNodeWithTag("assistant-text").performTextInput("keep this if rejected")
        rule.onNodeWithTag("assistant-text").performImeAction()
        rule.onNodeWithTag("assistant-text").assertTextContains("keep this if rejected", substring = true)
        assertEquals(1, sends)
        accept = true
        rule.onNodeWithTag("assistant-text").performImeAction()
        rule.onNodeWithTag("assistant-text").assertTextContains("询问相册内容", substring = true)
        assertEquals(2, sends)
        rule.onNodeWithTag("assistant-user-turn").assertTextContains("keep this if rejected", substring = true)
    }
    @Test fun assistantTextRefinesWithServerContextAndOpenUsesProtectedDetail() {
        val api = SyntheticApi().apply { assistantEnabled = true }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "zh") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store)
        rule.waitUntil(5000) { store.state.value.assistant?.capabilities?.text == true }
        clickTag("open-assistant")
        rule.onNodeWithTag("assistant-text").performTextInput("找夏天的照片")
        rule.onNodeWithTag("assistant-send").performClick()
        rule.waitUntil(5000) { store.state.value.assistant?.turns?.size == 1 }
        assertTrue(store.state.value.assistant!!.turns.single().turn.reply.contains("Found one memory"))
        rule.onNodeWithTag("assistant-open-1").assertExists()
        capture("assistant-phone-zh")
        val serverContext = store.state.value.assistant!!.turns.single().turn.context
        rule.onNodeWithTag("assistant-text").performTextInput("打开它")
        rule.onNodeWithTag("assistant-send").performClick()
        rule.waitUntil(5000) { store.state.value.detail?.asset?.id == "1" }
        assertEquals(2, api.assistantTurns)
        assertNull(api.assistantContexts.first())
        assertEquals(serverContext, api.assistantContexts.last())
        assertEquals("synthetic-library", store.state.value.detail?.library_id)
        rule.runOnUiThread { store.backToPhotos() }
        rule.waitUntil(5000) { store.state.value.detail == null && store.state.value.gallery != null }
        clickTag("open-assistant")
        rule.onNodeWithTag("assistant-text").assertExists()
        assertNull(store.state.value.detail)
    }
    @Test fun assistantSpeechIsGatedToLatestResultsAndStopClearsPrivateAudio() {
        val api = SyntheticApi().apply { assistantEnabled = true; assistantSpeechEnabled = true }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "zh") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); rule.waitUntil(5000) { store.state.value.assistant?.capabilities?.speech == true }
        clickTag("open-assistant")
        rule.onNodeWithTag("assistant-text").performTextInput("找去年9月的照片")
        rule.onNodeWithTag("assistant-send").performClick()
        rule.waitUntil(5000) { store.state.value.assistant?.turns?.size == 1 }
        rule.onNodeWithTag("assistant-turns").performScrollToNode(hasTestTag("assistant-reply"))
        rule.onNodeWithTag("assistant-reply").assertTextContains("Found one memory", substring = true)
        rule.onNodeWithTag("assistant-play-speech").assertExists()
        rule.onNodeWithTag("assistant-play-speech").performClick()
        rule.waitUntil(5000) { store.state.value.assistant?.speechAudio != null }
        assertEquals(1, api.assistantSpeechCalls)
        capture("assistant-speech")
        rule.onNodeWithTag("assistant-stop-speech").performClick()
        assertNull(store.state.value.assistant?.speechAudio)
    }
    @Test fun discoveryDatePickerAppliesSelectedDayAndCancelsWithoutMutation() {
        val api = SyntheticApi().apply { discoveryEnabled = true }
        val store = ConnectedStore(api,scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123","synthetic-password-only") }
        awaitLibrary(store); clickTag("open-discovery")
        reveal(hasTestTag("discovery-from")); rule.onNodeWithTag("discovery-from").performTextInput("2026-01-01")
        clickTag("discovery-from-picker")
        rule.onNodeWithText("Thursday, January 15, 2026").performClick()
        rule.onNodeWithText("Apply",substring=false).performClick()
        assertEquals("2026-01-15",store.state.value.discovery!!.filters.from)
        clickTag("discovery-to-picker")
        rule.onNodeWithText("Cancel",substring=false).performClick()
        assertEquals("",store.state.value.discovery!!.filters.to)
    }
    @Test fun discoveryInvalidDatesAndStaleBindingRequireExplicitReapply() {
        val api = SyntheticApi().apply { discoveryEnabled = true }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); clickTag("open-discovery")
        reveal(hasTestTag("discovery-from")); rule.onNodeWithTag("discovery-from").performTextInput("2026-02-30")
        clickTag("discovery-apply"); assertEquals(0, api.discoverySearches)
        reveal(hasTestTag("discovery-input-error")); rule.onNodeWithTag("discovery-input-error").assertIsDisplayed()
        clickTag("discovery-clear")
        reveal(hasTestTag("discovery-filter-summary")); rule.onNodeWithTag("discovery-filter-summary").assertTextContains("No filters selected")
        api.discoveryError = ApiFailure(FailureKind.HTTP, 409)
        clickTag("discovery-apply")
        assertTrue(store.state.value.discovery!!.changed); assertEquals(1, api.discoverySearches)
        api.discoveryError = null; clickTag("discovery-reload")
        assertEquals(1, api.discoverySearches); assertEquals("", store.state.value.discovery!!.filters.from)
        clickTag("discovery-apply"); assertEquals(2, api.discoverySearches)
        rule.runOnUiThread { store.logout() }; rule.waitForIdle()
        assertNull(store.state.value.discovery); assertNull(store.state.value.gallery)
    }
    @Test fun galleryTapOpensPhotoAndDetailsActionKeepsMetadataReachable() {
        val api = SyntheticApi().apply { photos = listOf(photo.copy(kind = "image")); originalsAllowed = true; total = 100 }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); click("Next")
        reveal(hasTestTag("media-1")); rule.onNodeWithTag("media-1").performClick()
        rule.waitUntil(5000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1 }
        if (rule.onAllNodesWithTag("photo-exit-fullscreen").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("photo-exit-fullscreen").performClick()
        assertEquals(2, store.state.value.photoNavigation?.page)
        rule.waitForIdle()
        rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
        rule.waitForIdle()
        assertNull(store.state.value.originalPhoto)
        click("Back to Photos"); details("1")
        assertFalse(store.state.value.viewingOriginal)
        reveal(hasText("<b>Literal 原文</b>")); rule.onNodeWithText("<b>Literal 原文</b>").assertIsDisplayed()
    }
    @Test fun longVideoStartsWithoutFullDownloadAndSeeksPastOneMinute() = longVideoJourney(false)
    @Test fun preparedViewerStreamsAndSeeksWithoutOriginalPermission() = longVideoJourney(true)
    private fun longVideoJourney(prepared: Boolean) {
        val api = SyntheticApi().apply {
            preparedVideoEnabled = prepared
            originalsAllowed = !prepared
            videoBytes = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().context.assets.open("synthetic-long-video.mp4").use { it.readBytes() }
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store)
        reveal(hasTestTag("media-1")); rule.onNodeWithTag("media-1").performClick()
        fun ready() { rule.waitUntil(30000) { rule.onAllNodes(hasText("Play") and isEnabled()).fetchSemanticsNodes().isNotEmpty() } }
        ready()
        rule.onNodeWithTag("video-position").assertTextEquals("0:00 / 2:05")
        val reader = store.state.value.video!!
        // The decoder can request headers and a small read-ahead. It must not
        // require all bytes before presenting Play for this fast-start fixture.
        val ranges = api.videoReads.map { it.first until minOf(api.videoBytes.size.toLong(), it.first + it.second) }
        assertTrue(ranges.sumOf { it.last - it.first + 1 } < api.videoBytes.size)
        for (target in listOf(90000f, 123000f, 2000f)) {
            rule.onNodeWithTag("video-seek").performScrollTo().performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.SetProgress) { it(target) }
            ready(); rule.waitUntil(10000) { positionSeconds() in (target.toInt() / 1000 - 1)..(target.toInt() / 1000 + 1) }
        }
        rule.onNodeWithText("Play").performScrollTo().performClick()
        rule.waitUntil(10000) { positionSeconds() >= 3 }
        rule.onNodeWithText("Pause").performScrollTo().performClick(); ready()
        capture(if (prepared) "video-prepared-en" else "video-long-en")
        if (prepared) { assertEquals(1, api.preparedHeads); assertEquals(0, api.originalVideoReads) }
        assertTrue(api.videoReads.all { it.second in 1..262144 })
        rule.runOnUiThread { store.background() }; rule.waitForIdle()
        assertTrue(reader.isClosed); assertNull(store.state.value.video)
    }
    @Test fun preparedReadinessShowsErrorsAndRequiresExplicitRetry() {
        val api = SyntheticApi().apply {
            preparedVideoEnabled = true
            preparedError = ApiFailure(FailureKind.HTTP, 404)
            videoBytes = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().context.assets.open("synthetic-video.mp4").use { it.readBytes() }
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); clickTag("media-1")
        val unavailable = "This video is not ready for playback yet. You can try again later."
        reveal(hasText(unavailable)); rule.onNodeWithText(unavailable).assertIsDisplayed()
        capture("prepared-not-ready-en")
        rule.onAllNodesWithTag("open-original-video").assertCountEquals(0)
        assertEquals(1, api.preparedHeads); assertTrue(api.videoReads.isEmpty())
        api.preparedError = ApiFailure(FailureKind.HTTP, 429, 4000)
        clickTag("open-video")
        reveal(hasTestTag("open-video")); rule.onNodeWithTag("open-video").assertIsNotEnabled()
        api.preparedError = null
        rule.waitUntil(8000) { rule.onAllNodes(hasTestTag("open-video") and isEnabled()).fetchSemanticsNodes().size == 1 }
        assertEquals(2, api.preparedHeads)
        clickTag("open-video")
        rule.waitUntil(30000) { rule.onAllNodes(hasText("Play") and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        assertEquals(3, api.preparedHeads); assertEquals(0, api.originalVideoReads)
        val reader = store.state.value.video!!
        rule.runOnUiThread { store.logout() }; rule.waitForIdle()
        assertTrue(reader.isClosed); assertNull(store.state.value.video)
    }
    @Test fun unconfiguredAppDisablesAdmissionAndKeepsSecureWindow() {
        assertEquals("", BuildConfig.PHOTOHOUSE_ORIGIN)
        rule.onNodeWithTag("server-not-configured").assertIsDisplayed()
        rule.onNodeWithText("需要配置服务器").assertIsDisplayed()
        rule.onAllNodes(hasSetTextAction()).assertCountEquals(0)
        assertTrue(rule.activity.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE != 0)
        capture("unconfigured-zh")
        click("English"); rule.onNodeWithText("Server setup needed").assertIsDisplayed(); capture("unconfigured-en")
    }
    @Test fun syntheticLoginBrowsingAndLiteralCaptionComponents() {
        val store = ConnectedStore(SyntheticApi(), scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") } }
        capture("admission-en")
        input("Phone number", "+12025550123"); input("Password (15–128 characters)", "synthetic-password-only")
        click("Sign in"); awaitLibrary(store)
        rule.onNodeWithText("Preview unavailable").assertExists()
        details("1")
        reveal(hasText("<b>Literal 原文</b>")); rule.onNodeWithText("<b>Literal 原文</b>").assertIsDisplayed(); capture("literal-caption-en")
        click("简体中文"); reveal(hasText("<b>Literal 原文</b>")); rule.onNodeWithText("<b>Literal 原文</b>").assertIsDisplayed(); capture("literal-caption-zh")
        click("退出登录"); assertFalse(store.hasSession)
        rule.onAllNodes(hasText("<b>Literal 原文</b>")).assertCountEquals(0)
    }
    @Test fun photoLedGalleryDetailAndSettingsRemainReachableInBothLanguages() {
        val bitmap = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val paint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG)
        canvas.drawColor(android.graphics.Color.rgb(196, 219, 225))
        paint.color = android.graphics.Color.rgb(246, 220, 165); canvas.drawCircle(460f, 100f, 48f, paint)
        paint.color = android.graphics.Color.rgb(138, 169, 151); canvas.drawOval(-120f, 220f, 680f, 700f, paint)
        paint.color = android.graphics.Color.rgb(68, 107, 88); canvas.drawOval(180f, 270f, 880f, 790f, paint)
        val preview = java.io.ByteArrayOutputStream().use { stream ->
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream); bitmap.recycle(); stream.toByteArray()
        }
        val api = SyntheticApi().apply {
            previewBytes = preview; originalsAllowed = true
            photos = listOf(photo.copy(kind = "image"), photo.copy(id = "2", taken_at = "2026-01-02"),
                photo.copy(id = "3", kind = "image", taken_at = null))
            total = photos.size.toLong()
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); click("Libraries"); reveal(hasText("Your libraries")); capture("libraries-en")
        click("Open library")
        rule.waitUntil(5000) { store.state.value.previews.size == 3 }
        reveal(hasText("Your memories")); capture("gallery-en")
        details("1")
        reveal(hasContentDescription("Photo 1")); rule.onNodeWithContentDescription("Photo 1").assertIsDisplayed(); capture("detail-en")
        click("简体中文")
        reveal(hasContentDescription("照片 1")); rule.onNodeWithContentDescription("照片 1").assertIsDisplayed(); capture("detail-zh")
        click("返回照片"); reveal(hasText("家庭相册", substring = false)); capture("gallery-zh")
        click("资料库"); reveal(hasText("你的资料库")); capture("libraries-zh")
        reveal(hasTestTag("app-settings")); rule.onNodeWithTag("app-settings").performClick()
        rule.onNodeWithText("界面语言").assertIsDisplayed(); rule.onNodeWithText("退出登录").assertIsDisplayed(); capture("settings-zh")
        rule.onNodeWithText("退出登录").performClick(); rule.waitForIdle()
        assertFalse(store.hasSession); assertTrue(store.state.value.previews.isEmpty())
        rule.onNodeWithText("你的资料库").assertDoesNotExist()
    }
    @Test fun familyNoteTagsKeepAlbumContextAndRenderOnPhone() {
        val api = SyntheticApi().apply {
            protectedNativeV2Enabled = true
            familyTagsEnabled = true
            photos = listOf(photo.copy(kind = "image"))
            previewBytes = runBlocking { originalPhoto(Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer")), "synthetic-library", "1") }
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store)
        clickTag("open-family-tags")
        rule.onNodeWithText("Garden walks").assertIsDisplayed()
        capture("family-tags-catalog")
        rule.onNodeWithText("Garden walks").performClick()
        rule.waitUntil(5000) { store.state.value.gallery?.items?.size == 1 && !store.state.value.busy }
        rule.onNodeWithTag("family-tag-media-1").assertIsDisplayed()
        capture("family-tags-assets")
        rule.onNodeWithTag("family-tag-details-1").performClick()
        rule.waitUntil(5000) { store.state.value.detail?.asset?.id == "1" }
        click("Back to tagged items")
        assertEquals("Garden walks", store.state.value.familyTags?.selectedTag)
    }
    @Test fun syntheticInvitedRegistrationRequiresAllInputs() {
        val api = SyntheticApi(); val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") } }
        click("Have an invitation? Register")
        reveal(hasText("Register with invitation")); rule.onNode(hasText("Register with invitation") and hasClickAction()).assertIsNotEnabled()
        input("Phone number", "+12025550123"); input("Password (15–128 characters)", "synthetic-password-only"); input("Invitation code", "synthetic-invitation")
        click("Register with invitation")
        assertEquals("synthetic-invitation", api.registrationCode)
        assertNotNull(store.state.value.session)
        rule.onAllNodes(hasText("synthetic-invitation")).assertCountEquals(0)
    }
    @Test fun nativeUploadEntryWarnsBeforeTransferAndShowsIncomingReceipt() {
        val api = SyntheticApi().apply { uploadEnabled = true; protectedNativeV2Enabled = true }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread {
            rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }
            store.authenticate("+12025550123", "synthetic-password-only")
        }
        clickTag("open-upload")
        rule.onNodeWithTag("upload-pick").assertIsDisplayed()
        assertEquals("synthetic-library", store.state.value.upload?.destinationLibraryId)
        capture("upload-choose")
        rule.runOnUiThread {
            store.state.value.upload!!.start(UploadSource("photo.jpg", 4) { java.io.ByteArrayInputStream(byteArrayOf(1,2,3,4)) }, network = UploadNetwork.METERED)
        }
        rule.onNodeWithTag("upload-network-warning").assertIsDisplayed()
        assertEquals(0, api.uploadCalls)
        capture("upload-warning")
        rule.onNodeWithTag("upload-network-approve").performClick()
        rule.waitUntil(5000) { store.state.value.upload?.state?.value is UploadState.Succeeded }
        rule.onNodeWithTag("upload-received").assertIsDisplayed()
        capture("upload-received")
        assertEquals(1,api.uploadCalls)
        rule.onNodeWithTag("upload-done").performClick()
        assertEquals(listOf("synthetic-library"), api.directDestinations)
        rule.runOnUiThread { store.logout() }
        rule.onNodeWithTag("upload-panel").assertDoesNotExist()
    }
    @Test fun uploadOpenedWithoutLibraryRequiresExplicitDestinationChoice() {
        val api = SyntheticApi().apply { uploadEnabled = true; protectedNativeV2Enabled = true }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store)
        rule.runOnUiThread { store.libraries() }
        rule.waitUntil(5000) { store.state.value.library == null && !store.state.value.busy }
        clickTag("open-upload")
        assertNull(store.state.value.upload?.destinationLibraryId)
        rule.onNodeWithTag("upload-pick").performClick()
        rule.onNodeWithTag("upload-destination-dialog").assertIsDisplayed()
        rule.onNodeWithTag("upload-destination-synthetic-library").performClick()
        rule.onNode(hasText("Continue") and hasClickAction()).performClick()
        assertEquals("synthetic-library", store.state.value.upload?.destinationLibraryId)
        androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK)
    }
    @Test fun preparedVideoNavigationAndExplicitResumeKeepAccessBoundaries() {
        val api = SyntheticApi().apply {
            preparedVideoEnabled = true
            videoBytes = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().context.assets.open("synthetic-long-video.mp4").use { it.readBytes() }
            photos = listOf(photo, photo.copy(id="2",kind="image"), photo.copy(id="3"))
            total = 3
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread {
            rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }
            store.authenticate("+12025550123", "synthetic-password-only")
        }
        awaitLibrary(store); details("1"); click("Open video")
        rule.waitUntil(30000) { rule.onAllNodes(hasText("Play") and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("video-previous").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("video-seek").performScrollTo().performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.SetProgress) { it(15000f) }
        rule.waitUntil(15000) { positionSeconds() >= 14 }
        val old = store.state.value.video!!
        rule.onNodeWithTag("video-next").performScrollTo().performClick()
        rule.waitUntil(30000) { store.state.value.detail?.asset?.id == "3" && store.state.value.video != null }
        assertTrue(old.isClosed)
        rule.onNodeWithTag("video-previous").performScrollTo().performClick()
        rule.waitUntil(30000) { rule.onAllNodes(hasTestTag("video-resume")).fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText("Play").assertExists() // offer does not autoplay
        rule.onNodeWithTag("video-resume").performScrollTo().performClick()
        rule.waitUntil(15000) { positionSeconds() >= 14 && rule.onAllNodes(hasText("Pause")).fetchSemanticsNodes().isNotEmpty() }
        capture("video-journey-resume")
        rule.onNodeWithText("Close video").performScrollTo().performClick()
        assertTrue(api.preparedHeads >= 3); assertEquals(0, api.originalVideoReads)
    }
    @Test fun nativeVideoPlaysPausesSeeksAndClosesInBothLanguages() {
        val api = SyntheticApi().apply {
            originalsAllowed = true
            videoBytes = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().context.assets.open("synthetic-video.mp4").use { it.readBytes() }
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread {
            rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }
            store.authenticate("+12025550123", "synthetic-password-only")
        }
        awaitLibrary(store); details("1"); click("Open video")
        val reader = store.state.value.video!!
        fun ready(label: String) { rule.waitUntil(30000) {
            rule.onAllNodes(hasText(label) and isEnabled()).fetchSemanticsNodes().isNotEmpty()
        } }
        ready("Play")
        rule.onNodeWithText("Play").performScrollTo().performClick()
        rule.waitUntil(15000) {
            positionSeconds() >= 1
        }
        // A competing transient audio focus request must pause, without auto-resume.
        val audio = rule.activity.getSystemService(android.media.AudioManager::class.java)
        val focus = android.media.AudioFocusRequest.Builder(android.media.AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
            .setOnAudioFocusChangeListener { }.build()
        try {
            assertEquals(android.media.AudioManager.AUDIOFOCUS_REQUEST_GRANTED, audio.requestAudioFocus(focus))
            ready("Play")
        } finally { audio.abandonAudioFocusRequest(focus) }
        rule.onNodeWithText("Play").assertExists()
        rule.onNodeWithText("Play").performScrollTo().performClick(); ready("Pause")
        rule.onNodeWithText("Pause").performScrollTo().performClick(); ready("Play")
        rule.onNodeWithText("Forward 10s").performScrollTo().performClick(); ready("Play")
        rule.waitUntil(10000) { positionSeconds() >= 10 }
        capture("video-en")
        rule.onNodeWithTag("video-seek").performScrollTo().performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.SetProgress) { it(3000f) }
        ready("Play")
        rule.waitUntil(10000) { positionSeconds() in 2..4 }
        rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
        assertTrue(reader.isClosed); assertNull(store.state.value.video)
        click("简体中文"); click("打开视频"); ready("播放")
        rule.onNodeWithText("播放").performScrollTo().performClick()
        rule.waitUntil(15000) { positionSeconds() >= 1 }
        rule.onNodeWithText("暂停").performScrollTo().performClick(); ready("播放"); capture("video-zh")
        val second = store.state.value.video!!
        rule.onNodeWithText("关闭视频").performScrollTo().performClick(); assertTrue(second.isClosed)
        click("打开视频"); ready("播放")
        val third = store.state.value.video!!
        rule.runOnUiThread { store.background() }; rule.waitForIdle()
        assertTrue(third.isClosed); assertNull(store.state.value.video)
        rule.onNodeWithTag("video-player").assertDoesNotExist()
        assertTrue(api.videoReads.size > 3)
        assertTrue(api.videoReads.all { it.second in 1..262144 })
    }
    @Test fun corruptVideoExitsPlayerWithoutRetryOrPrivateResidue() {
        val api = SyntheticApi().apply { originalsAllowed = true; videoBytes = ByteArray(128) { 7 } }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); details("1"); click("Open video")
        rule.waitUntil(30000) { store.state.value.video == null && store.state.value.problem != null }
        assertEquals(Message.MEDIA_UNAVAILABLE, store.state.value.problem?.message)
        assertFalse(store.canRetry()); rule.onNodeWithTag("video-player").assertDoesNotExist()
        val diagnosis = requireNotNull(store.state.value.problem?.playbackFailure)
        assertTrue(diagnosis in listOf(VideoPlaybackFailure.UNSUPPORTED, VideoPlaybackFailure.INVALID_MEDIA))
        reveal(hasText(diagnosis.message(false)))
        rule.onNodeWithText(diagnosis.message(false)).assertIsDisplayed()
        capture("playback-error-en")
        click("简体中文")
        reveal(hasText(diagnosis.message(true)))
        rule.onNodeWithText(diagnosis.message(true)).assertIsDisplayed()
        capture("playback-error-zh")
    }
    @Test fun failedPhotoSwitchRetriesBackIntoFullscreenWithoutRegistrationMessage() {
        val api = SyntheticApi().apply {
            photos = listOf(photo.copy(id = "1", kind = "image"), photo.copy(id = "2", kind = "image"))
            originalsAllowed = true
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); details("1"); click("Open original photo")
        rule.waitUntil(10000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1 }
        rule.runOnIdle { api.transientDetailFailures = 2 }
        rule.onNodeWithTag("photo-fullscreen-next").performClick()
        rule.waitUntil(10000) { store.state.value.problem != null }
        rule.onNodeWithText("Could not load this item. Check the connection and retry.").assertExists()
        assertNotNull(store.state.value.session)
        click("Retry")
        rule.waitUntil(10000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1 }
        assertEquals("2", store.state.value.detail?.asset?.id)
        rule.onNodeWithTag("photo-controls").assertDoesNotExist()
        rule.onNodeWithTag("photo-fullscreen-previous").assertIsEnabled()
        rule.runOnIdle { store.background() }
    }
    @Test fun originalViewerZoomCloseAndPrivacyUseSyntheticImageBytes() {
        val api = SyntheticApi().apply { photos = listOf(photo.copy(kind = "image")); originalsAllowed = true }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread {
            rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }
            store.authenticate("+12025550123", "synthetic-password-only")
        }
        awaitLibrary(store); details("1"); click("Open original photo")
        rule.waitUntil(5000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1 }
        if (rule.onAllNodesWithTag("photo-exit-fullscreen").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("photo-exit-fullscreen").performClick()
        rule.onNodeWithTag("photo-zoom").assertTextEquals("100%")
        rule.onNode(hasText("Zoom in") and hasClickAction()).performScrollTo().performClick()
        rule.onNodeWithTag("photo-zoom").assertTextEquals("150%")
        rule.onNode(hasText("Fit photo") and hasClickAction()).performScrollTo().performClick()
        rule.onNodeWithTag("original-image").performTouchInput {
            val delta = androidx.compose.ui.geometry.Offset(35f, 0f)
            pinch(center - delta, center + delta, center - delta * 2f, center + delta * 2f, 300)
        }
        rule.onNodeWithTag("photo-zoom").assertTextContains("%", substring = true)
        rule.onNodeWithTag("photo-zoom").assert(hasText("100%").not())
        rule.onNode(hasText("Fit photo") and hasClickAction()).performScrollTo().performClick()
        rule.onNodeWithTag("original-image").performTouchInput { doubleClick(center) }
        rule.onNodeWithTag("photo-zoom").assertTextEquals("200%")
        rule.onNodeWithTag("original-image").performTouchInput { swipe(center, center + androidx.compose.ui.geometry.Offset(40f, 20f), 200) }
        capture("original-photo-en")
        rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
        rule.waitForIdle(); assertNull(store.state.value.originalPhoto)
        rule.onAllNodesWithTag("original-viewer").assertCountEquals(0)
        click("简体中文"); click("打开原始照片")
        rule.waitUntil(5000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1 }
        if (rule.onAllNodesWithTag("photo-exit-fullscreen").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("photo-exit-fullscreen").performClick()
        rule.onNodeWithTag("photo-zoom").assertTextEquals("100%")
        capture("original-photo-zh")
        rule.onNode(hasText("关闭照片") and hasClickAction()).performScrollTo().performClick()
        rule.waitForIdle(); assertNull(store.state.value.originalPhoto)
        click("打开原始照片")
        rule.waitUntil(5000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1 }
        if (rule.onAllNodesWithTag("photo-exit-fullscreen").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("photo-exit-fullscreen").performClick()
        rule.runOnUiThread { store.background() }
        rule.waitForIdle(); rule.onAllNodesWithTag("original-viewer").assertCountEquals(0)
        assertNull(store.state.value.originalPhoto); assertTrue(store.state.value.covered)
    }
    @Test fun photoFitFillFullscreenAndSlideshowPreservePageAndClearOnBackground() {
        val api = SyntheticApi().apply {
            photos = (1..3).map { photo.copy(id = it.toString(), kind = "image", taken_at = "2026-01-0$it") }
            originalsAllowed = true; total = 100
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); click("Next"); details("1"); click("Open original photo")
        fun ready() { rule.waitUntil(5000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1 } }
        fun mediaClick(label: String) { rule.onNode(hasText(label) and hasClickAction()).performScrollTo().performClick() }
        ready(); rule.onNodeWithTag("photo-exit-fullscreen").performClick(); val original = store.state.value.originalPhoto
        mediaClick("Fill screen"); rule.onNodeWithTag("photo-fit-mode").assertTextEquals("Fill · edges cropped")
        rule.onNodeWithTag("original-image").performTouchInput {
            swipe(center, center + androidx.compose.ui.geometry.Offset(width * 0.3f, height * 0.3f), 300)
        }
        val viewport = rule.onNodeWithTag("photo-viewport").fetchSemanticsNode().boundsInWindow
        rule.runOnUiThread {
            val view = rule.activity.window.decorView
            val image = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(image))
            for (x in listOf(viewport.left.toInt() + 8, viewport.right.toInt() - 8))
                for (y in listOf(viewport.top.toInt() + 8, viewport.bottom.toInt() - 8))
                    assertNotEquals("Fill pan must reveal image edges, not black gaps", android.graphics.Color.BLACK, image.getPixel(x, y))
            image.recycle()
        }
        mediaClick("Full screen"); rule.onNodeWithTag("photo-exit-fullscreen").assertIsDisplayed()
        rule.onNodeWithTag("photo-controls").assertDoesNotExist(); capture("parity-photo-fullscreen")
        rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
        assertSame(original, store.state.value.originalPhoto)
        rule.onNodeWithTag("photo-controls").assertExists(); mediaClick("Fit photo")
        mediaClick("Start slideshow"); assertTrue(store.state.value.photoSlideshow)
        assertTrue(screenAwake())
        rule.mainClock.autoAdvance = false
        rule.mainClock.advanceTimeBy(8200)
        rule.waitUntil(5000) { store.state.value.detail?.asset?.id == "2" }
        // Decoder work uses a real worker thread. Pump frames while yielding wall
        // time instead of letting the spinner advance virtual slideshow time.
        rule.waitUntil(5000) {
            rule.mainClock.advanceTimeByFrame()
            rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size == 1
        }
        assertTrue("Slideshow must still be active on the second photo", store.state.value.photoSlideshow)
        rule.mainClock.autoAdvance = true
        mediaClick("Pause slideshow"); assertFalse(store.state.value.photoSlideshow)
        capture("parity-photo-slideshow")
        mediaClick("Previous photo"); ready(); assertEquals("1", store.state.value.detail?.asset?.id)
        mediaClick("Full screen")
        rule.runOnUiThread { store.background() }; rule.waitForIdle()
        rule.onNodeWithTag("original-viewer").assertDoesNotExist()
        assertFalse(store.state.value.photoSlideshow); assertNull(store.state.value.originalPhoto)
        assertFalse(screenAwake())
    }
    @Test fun nativeVideoFitFillAndFullscreenKeepTheSameReaderAndRestoreControls() {
        val api = SyntheticApi().apply {
            originalsAllowed = true
            videoBytes = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().context.assets.open("synthetic-video.mp4").use { it.readBytes() }
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); details("1"); click("Open video")
        rule.waitUntil(30000) { rule.onAllNodes(hasText("Play") and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        val reader = store.state.value.video!!
        fun mediaClick(label: String) { rule.onNode(hasText(label) and hasClickAction()).performScrollTo().performClick() }
        mediaClick("Fill screen"); rule.onNodeWithTag("video-fit-mode").assertTextEquals("Fill · edges cropped")
        mediaClick("Fit video"); mediaClick("Play")
        rule.waitUntil(15000) { positionSeconds() >= 1 }
        mediaClick("Full screen"); rule.onNodeWithTag("video-exit-fullscreen").assertIsDisplayed()
        assertTrue(screenAwake())
        rule.onNodeWithTag("video-controls").assertDoesNotExist()
        assertSame(reader, store.state.value.video); assertFalse(reader.isClosed)
        capture("video-parity-fullscreen")
        rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }; rule.waitForIdle()
        assertSame(reader, store.state.value.video); assertFalse(reader.isClosed)
        rule.onNodeWithTag("video-controls").assertExists(); mediaClick("Pause")
        rule.waitUntil(5000) { rule.onAllNodes(hasText("Play") and isEnabled()).fetchSemanticsNodes().isNotEmpty() }
        assertFalse(screenAwake())
        mediaClick("Full screen"); rule.onNodeWithTag("video-exit-fullscreen").performClick()
        mediaClick("Close video"); assertTrue(reader.isClosed)
        assertTrue(rule.activity.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE != 0)
    }
    @Test fun undecodablePhotoStopsSlideshowWithoutAdvancingOrKeepingScreenAwake() {
        var stopped = 0; var advanced = 0
        rule.runOnUiThread { rule.activity.setContent {
            OriginalPhotoViewer(byteArrayOf(1, 2, 3), false, false, {}, PhotoNavigation(1, listOf("1", "2"), 0),
                true, onStopSlideshow = { stopped++ }, onAdvanceSlideshow = { advanced++ })
        } }
        rule.waitUntil(5000) { stopped > 0 }
        rule.onNodeWithText("This image format or size cannot be displayed here.").assertExists()
        assertEquals(0, advanced); assertFalse(screenAwake())
    }
    @Test fun pageJumpRejectsInvalidInputAndClearsOnPrivateLifecycleBoundary() {
        val api = SyntheticApi().apply { total = 1000 }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store); click("Go to page")
        rule.onNodeWithTag("phone-page-input").performTextReplacement("0")
        rule.onNodeWithTag("phone-page-go").assertIsNotEnabled()
        rule.onNodeWithTag("phone-page-input").performTextReplacement("21")
        rule.onNodeWithTag("phone-page-go").assertIsNotEnabled()
        rule.onNodeWithTag("phone-page-input").performTextReplacement("12")
        rule.onNodeWithTag("phone-page-go").performClick(); rule.waitForIdle()
        assertEquals(12, store.state.value.gallery?.page)
        click("简体中文"); click("跳转页面")
        rule.onNodeWithText("选择第 1 至 20 页").assertIsDisplayed()
        rule.runOnUiThread { store.background() }; rule.waitForIdle()
        rule.onNodeWithTag("phone-page-input").assertDoesNotExist()
        assertTrue(store.state.value.covered)
    }
    @Test fun originalDecoderRejectsCorruptionBoundsPixelsAndHandlesAllExifOrientations() {
        assertNull(decodeOriginalPhoto(byteArrayOf(1, 2, 3)))
        val large = Bitmap.createBitmap(3200, 2000, Bitmap.Config.ARGB_8888)
        large.eraseColor(android.graphics.Color.BLUE)
        val bytes = java.io.ByteArrayOutputStream().use { stream ->
            large.compress(Bitmap.CompressFormat.PNG, 100, stream); large.recycle(); stream.toByteArray()
        }
        val reduced = requireNotNull(decodeOriginalPhoto(bytes))
        assertTrue(reduced.downsampled); assertTrue(reduced.bitmap.width.toLong() * reduced.bitmap.height <= 4_000_000)
        reduced.bitmap.recycle()
        val landscape = Bitmap.createBitmap(200, 100, Bitmap.Config.ARGB_8888)
        val jpeg = java.io.ByteArrayOutputStream().use { stream ->
            landscape.compress(Bitmap.CompressFormat.JPEG, 90, stream); landscape.recycle(); stream.toByteArray()
        }
        // Generated EXIF APP1 segment: little-endian TIFF with orientation 6.
        val tiff = java.nio.ByteBuffer.allocate(26).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            .put(0x49.toByte()).put(0x49.toByte()).putShort(42.toShort()).putInt(8).putShort(1.toShort())
            .putShort(0x112.toShort()).putShort(3.toShort()).putInt(1).putShort(6.toShort()).putShort(0.toShort()).putInt(0).array()
        val exif = byteArrayOf(0xff.toByte(), 0xe1.toByte(), 0, 34) + byteArrayOf(69, 120, 105, 102, 0, 0) + tiff
        val rotated = requireNotNull(decodeOriginalPhoto(jpeg.copyOfRange(0, 2) + exif + jpeg.copyOfRange(2, jpeg.size)))
        assertEquals(100, rotated.bitmap.width); assertEquals(200, rotated.bitmap.height); rotated.bitmap.recycle()
        val colors = intArrayOf(0xffff0000.toInt(), 0xff00ff00.toInt(), 0xff0000ff.toInt(), 0xffffffff.toInt(), 0xffffff00.toInt(), 0xff00ffff.toInt())
        val orders = listOf(listOf(0,1,2,3,4,5), listOf(2,1,0,5,4,3), listOf(5,4,3,2,1,0),
            listOf(3,4,5,0,1,2), listOf(0,3,1,4,2,5), listOf(3,0,4,1,5,2),
            listOf(5,2,4,1,3,0), listOf(2,5,1,4,0,3))
        for (orientation in 1..8) {
            val input = Bitmap.createBitmap(colors, 3, 2, Bitmap.Config.ARGB_8888)
            val output = orientPhoto(input, orientation)
            assertEquals(if (orientation < 5) 3 else 2, output.width)
            assertEquals(if (orientation < 5) 2 else 3, output.height)
            val actual = IntArray(6); output.getPixels(actual, 0, output.width, 0, 0, output.width, output.height)
            assertArrayEquals(orders[orientation - 1].map { colors[it] }.toIntArray(), actual)
            output.recycle()
        }
    }
    @Test fun photoNavigationReturnsToSelectedPageAndSupportsBothLanguages() {
        val api = SyntheticApi().apply { photos = listOf(photo, photo.copy(id = "2", taken_at = "2026-01-02")); total = 100 }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread {
            rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }
            store.authenticate("+12025550123", "synthetic-password-only")
        }
        awaitLibrary(store); click("Next"); details("1")
        reveal(hasText("Photo 1 of 2 · Page 2"))
        rule.onNodeWithText("Photo 1 of 2 · Page 2").assertIsDisplayed()
        rule.onNode(hasText("Previous photo") and hasClickAction()).assertIsNotEnabled()
        click("Next photo")
        reveal(hasText("Photo 2 of 2 · Page 2"))
        rule.onNodeWithText("Photo 2 of 2 · Page 2").assertIsDisplayed()
        rule.onNode(hasText("Next photo") and hasClickAction()).assertIsNotEnabled()
        capture("photo-navigation-en")
        click("简体中文"); reveal(hasText("第 2 页 · 第 2/2 张"))
        rule.onNodeWithText("第 2 页 · 第 2/2 张").assertIsDisplayed()
        capture("photo-navigation-zh")
        click("上一张"); click("返回照片")
        reveal(hasText("第 2 页 · 100 项")); rule.onAllNodesWithText("第 2 页 · 100 项").onFirst().assertIsDisplayed()
        details("1")
        rule.runOnUiThread { rule.activity.onBackPressedDispatcher.onBackPressed() }
        rule.waitForIdle()
        reveal(hasText("第 2 页 · 100 项")); rule.onAllNodesWithText("第 2 页 · 100 项").onFirst().assertIsDisplayed()
        click("退出登录"); assertNull(store.state.value.photoNavigation)
        rule.onAllNodes(hasText("第 2 页 · 第 1/2 张")).assertCountEquals(0)
    }

    @Test fun familyLibraryOpensFirstAndExplicitSwitchRemainsAvailable() {
        val api = SyntheticApi().apply {
            memberships = listOf(
                Membership("alpha", "approved", "viewer", 1, null, 0, true),
                Membership("family", "approved", "viewer", 1, null, 0, true),
            )
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread {
            rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }
            store.authenticate("+12025550123", "synthetic-password-only")
        }

        awaitLibrary(store, "family")
        assertEquals("family", store.state.value.gallery?.library_id)
        click("Libraries")
        reveal(hasText("Your libraries"))
        rule.onNodeWithText("Family").assertIsDisplayed()
        reveal(hasText("alpha"))
        rule.onNodeWithText("alpha").assertIsDisplayed()
        val open = hasText("Open library") and hasClickAction()
        rule.onAllNodes(open).onLast().performScrollTo().performClick()
        rule.waitForIdle()
        awaitLibrary(store, "alpha")
        assertEquals("alpha", store.state.value.gallery?.library_id)
    }

    @Test fun uploadHistoryShowsStatesPagesTenPlusTwoAndOpensAvailableAsset() {
        fun item(id: String, state: String, library: String? = if (state == "available") "synthetic-library" else null) =
            UploadHistoryItem(id, 1760000000, 1234, "image", state, library)
        val pageOne = listOf(item("1", "available"), item("2", "awaiting_review"), item("3", "unavailable")) +
            (4..10).map { item(it.toString(), "awaiting_review") }
        val pageTwo = listOf(item("11", "awaiting_review"), item("12", "unavailable"))
        val api = SyntheticApi().apply {
            protectedNativeV2Enabled = true; uploadEnabled = true
            uploadHistoryPages = mapOf(
                1 to UploadHistoryPage(1, 10, 12, pageOne),
                2 to UploadHistoryPage(2, 10, 12, pageTwo),
            )
        }
        val store = ConnectedStore(api, scope)
        rule.runOnUiThread {
            rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }
            store.authenticate("+12025550123", "synthetic-password-only")
        }
        awaitLibrary(store)
        clickTag("contribute-toggle")
        click("Upload history")
        reveal(hasTestTag("upload-history"))
        rule.waitUntil(5000) { store.state.value.uploadHistory?.busy == false }
        rule.onNodeWithTag("upload-history-summary").assertTextContains("12 uploads", substring = true)
        rule.onNodeWithText("#1").assertDoesNotExist()
        rule.onNodeWithTag("upload-history-toggle").assertTextContains("Show")
        rule.onNodeWithTag("upload-history-toggle").performClick()
        rule.onAllNodesWithText("Awaiting review").onFirst().assertIsDisplayed()
        rule.onNodeWithText("Unavailable").performScrollTo().assertIsDisplayed()
        val bitmap = rule.onRoot().captureToImage().asAndroidBitmap()
        File(rule.activity.filesDir, "upload-history-phone.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        val uploadImageUri = rule.activity.contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            android.content.ContentValues().apply {
                put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, "upload-history-visible-150pct.png")
                put(android.provider.MediaStore.MediaColumns.MIME_TYPE, "image/png")
                put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH, android.os.Environment.DIRECTORY_PICTURES)
            })
        assertNotNull(uploadImageUri)
        rule.activity.contentResolver.openOutputStream(uploadImageUri!!).use { output ->
            requireNotNull(output).use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
        bitmap.recycle()
        click("简体中文"); reveal(hasTestTag("upload-history"))
        rule.onNodeWithText("我的上传记录").assertIsDisplayed()
        rule.onNodeWithTag("upload-history-toggle").performClick()
        rule.onNodeWithText("#1").assertDoesNotExist()
        rule.onNodeWithTag("upload-history-toggle").performClick()
        val chinese = rule.onRoot().captureToImage().asAndroidBitmap()
        File(rule.activity.filesDir, "upload-history-phone-zh.png").outputStream().use { chinese.compress(Bitmap.CompressFormat.PNG, 100, it) }
        chinese.recycle(); click("English")
        assertEquals(10, store.state.value.uploadHistory?.items?.size)
        rule.onNodeWithTag("upload-history-next").performScrollTo().assertIsDisplayed().assertIsEnabled().performClick()
        rule.waitUntil(5000) { store.state.value.uploadHistory?.page == 2 && store.state.value.uploadHistory?.busy == false }
        assertEquals(2, store.state.value.uploadHistory?.items?.size)
        clickTag("upload-history-previous")
        rule.waitUntil(5000) { store.state.value.uploadHistory?.page == 1 && store.state.value.uploadHistory?.busy == false }
        reveal(hasTestTag("upload-history"))
        rule.onNode(hasText("Open") and hasClickAction()).performClick()
        rule.waitUntil(5000) { store.state.value.detail?.asset?.id == "1" }
        assertEquals("synthetic-library", store.state.value.detail?.library_id)
    }
    @Test fun batchQueueReviewAndProgressRequiresExplicitResume() {
        val api = SyntheticApi().apply { uploadEnabled = true; protectedNativeV2Enabled = true }
        val source = BatchUploadSource("batch.jpg", 4, UploadKind.IMAGE, { java.io.ByteArrayInputStream(byteArrayOf(1, 2, 3, 4)) }, "content://batch")
        val store = ConnectedStore(api, scope, batchPersistence = InMemoryUploadQueuePersistence(), batchSource = { source })
        rule.runOnUiThread { rule.activity.setContent { ConnectedApp(store, initialLanguage = "en") }; store.authenticate("+12025550123", "synthetic-password-only") }
        awaitLibrary(store)
        val queue = requireNotNull(store.batchUploads); val id = queue.enqueue(listOf(source), "synthetic-library").single()
        rule.onNodeWithTag("batch-queue").assertIsDisplayed()
        rule.onNodeWithTag("batch-queue-summary").assertTextContains("1 item", substring = true)
        rule.onNodeWithTag("batch-status-$id").assertDoesNotExist()
        rule.onNodeWithTag("batch-queue-toggle").assertTextContains("Show")
        rule.onNodeWithTag("batch-queue-toggle").performClick()
        rule.onNodeWithTag("batch-status-$id").assertTextContains("needs_hash", substring = true)
        rule.runOnUiThread { queue.resume(id) }
        rule.waitUntil(5000) { runCatching { rule.onNodeWithTag("batch-status-$id").assertTextContains("complete", substring = true) }.isSuccess }
        assertEquals(listOf("synthetic-library"), api.sessionDestinations)
        rule.onNodeWithTag("batch-queue-summary").assertTextContains("1 done", substring = true)
        rule.onNodeWithTag("batch-queue-toggle").performClick()
        rule.onNodeWithTag("batch-status-$id").assertDoesNotExist()
        rule.onNodeWithTag("batch-queue-toggle").assertTextContains("Show")
        val bitmap = rule.onRoot().captureToImage().asAndroidBitmap()
        File(rule.activity.filesDir, "batch-upload-queue-phone.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
}
