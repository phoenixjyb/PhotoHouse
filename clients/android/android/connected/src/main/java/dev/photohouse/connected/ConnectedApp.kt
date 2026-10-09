package dev.photohouse.connected

import android.graphics.BitmapFactory
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import android.net.Uri
import android.content.Context
import android.content.pm.PackageManager
import android.Manifest
import java.io.ByteArrayOutputStream
import java.time.Instant
import java.time.ZoneId
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import dev.photohouse.connected.core.*
import dev.photohouse.ota.PhotoHouseOtaControl
import dev.photohouse.protocol.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

internal class Words(val zh: Boolean) {
    fun t(en: String, cn: String) = if (zh) cn else en
    fun date(asset: Asset): String {
        asset.taken_at?.let { return it }
        val hint = asset.date_hint ?: return t("Date unknown", "日期未知")
        val date = if (hint.value.endsWith('Z'))
            runCatching { Instant.parse(hint.value).atZone(ZoneId.systemDefault()).toLocalDate().toString() }
                .getOrDefault(hint.value.take(10))
        else hint.value.take(10)
        val label = if (hint.source == "received") t("Received", "收到于") else t("Filename date", "文件名日期")
        return "$label · $date"
    }
    fun dateExplanation(asset: Asset) = when {
        asset.taken_at != null -> t("Source date, shown as received", "原始日期，按原文显示")
        asset.date_hint?.source == "received" -> t("PhotoHouse upload receipt date; capture date is unknown", "PhotoHouse 上传接收日期；拍摄日期未知")
        asset.date_hint?.source == "filename" -> t("Read from filename; capture date is unknown", "从文件名读取；拍摄日期未知")
        else -> t("No reliable date is recorded", "未记录可靠日期")
    }
    fun message(m: Message) = when (m) {
        Message.SESSION_STORAGE_UNAVAILABLE -> t("Secure sign-in storage is unavailable on this device. Sign in again next time; if signing out, check server revocation.", "此设备的安全登录存储不可用，下次需重新登录；退出时请确认服务器已撤销会话。")
        Message.SIGNED_OUT_LOCAL -> t("Signed out on this phone. Server acknowledgement is unavailable.", "已在本机退出，尚未获得服务器确认。")
        Message.SIGNED_OUT_CONFIRMED -> t("Signed out. The server confirmed session revocation.", "已退出，服务器已确认会话撤销。")
        Message.SESSION_ENDED -> t("Your session ended. Please sign in again.", "会话已结束，请重新登录。")
        Message.ACCESS_DENIED -> t("Access was not granted. Check your account, invitation or library access.", "未获授权，请检查账号、邀请或资料库权限。")
        Message.UNAVAILABLE -> t("PhotoHouse is temporarily unavailable. If registration was submitted, try signing in when it returns.", "相册服务暂不可用。如果已提交注册，请在恢复后尝试登录。")
        Message.NETWORK_UNAVAILABLE -> t("Cannot reach PhotoHouse. Check this device’s network and server connection. If registration may have completed, try Sign in.", "无法连接 PhotoHouse，请检查手机网络和服务器连接。如果注册可能已完成，请尝试登录。")
        Message.TLS_ERROR -> t("The server's secure connection could not be verified. Contact your administrator.", "无法验证服务器的安全连接，请联系管理员。")
        Message.CLOSED -> t("This request was blocked. Contact your administrator.", "请求已被阻止，请联系管理员。")
        Message.RATE_LIMITED -> t("Too many attempts. Wait before trying again.", "尝试过于频繁，请稍后重试。")
        Message.INVALID_INPUT -> t("Check your inputs and the password rules shown. Use an explicit country code. If already registered, sign in.", "请检查输入和显示的密码要求，手机号应包含国家码。已注册请登录。")
        Message.INVALID_RESPONSE -> t("The server response could not be displayed safely.", "无法安全显示服务器响应。")
        Message.TOO_LARGE -> t("This file is too large to display here.", "文件过大，无法在此处显示。")
        Message.DISCOVERY_CHANGED -> t("Search information changed. Refresh options and apply your filters again.", "搜索资料已更新，请刷新选项后重新选择并应用条件。")
        Message.DISCOVERY_INPUT -> t("Check your search filters and dates.", "请检查搜索条件和日期。")
        Message.VIDEO_NOT_READY -> t("This video is not ready for playback yet. You can try again later.", "此视频尚未准备好，可稍后重试。")
        Message.VIDEO_CHANGED -> t("This video changed. Open it again to load the current version.", "此视频已更新，请重新打开。")
        Message.VIDEO_BUSY -> t("Video playback is busy. Wait a moment before trying again.", "视频播放繁忙，请稍候重试。")
        Message.PLAYBACK_UNAVAILABLE -> t("Video playback is temporarily unavailable. Your album is still available.", "视频播放暂不可用，仍可继续浏览相册。")
        Message.MEDIA_UNAVAILABLE -> t("This media is unavailable.", "此媒体不可用。")
    }
    fun membership(m: Membership) = when {
        m.available -> t("Available", "可访问")
        m.status == "requested" -> t("Awaiting approval", "等待批准")
        m.status == "rejected" -> t("Not approved", "未获批准")
        m.status == "revoked" -> t("Access revoked", "权限已撤销")
        m.expires_at != null -> t("Membership expired or unavailable", "成员资格过期或不可用")
        else -> t("Library unavailable", "资料库不可用")
    }
}

private enum class UploadDestinationAction { DIRECT, BATCH }
private data class AnnotationWavSelection(
    val account: String, val generation: Long, val target: UploadAnnotationTarget,
    val language: String, val consent: String, val uri: Uri? = null,
)
private data class PendingAnnotationCapture(
    val selection: AnnotationWavSelection, val capture: AnnotationAudioRecorder.Capture,
)
private data class AssistantCaptureSelection(val account: String, val library: String, val generation: Long, val maxSeconds: Int)
private data class PendingAssistantCapture(val selection: AssistantCaptureSelection, val capture: AnnotationAudioRecorder.Capture)

private fun readAnnotationWav(context: Context, uri: Uri): ByteArray? {
    val limit = 2 * 1024 * 1024
    val output = ByteArrayOutputStream()
    context.contentResolver.openInputStream(uri)?.use { input ->
        val buffer = ByteArray(32 * 1024)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            if (count == 0) return null
            if (output.size() + count > limit) return null
            output.write(buffer, 0, count)
        }
    } ?: return null
    return output.toByteArray()
}

@OptIn(ExperimentalLayoutApi::class)
@Composable fun ConnectedApp(store: ConnectedStore?, initialLanguage: String = "zh") {
    var language by remember { mutableStateOf(initialLanguage) }
    var settings by remember { mutableStateOf(false) }
    val config = LocalConfiguration.current
    val words = Words(language == "zh" || language == "system" && config.locales[0].language == "zh")
    val t = words::t
    val state = store?.state?.collectAsState()?.value ?: LiveState()
    var assistantOpen by remember(state.generation, state.library) { mutableStateOf(false) }
    var handledAssistantExchange by remember(state.session?.account_id, state.library) { mutableIntStateOf(0) }
    val batchQueue = store?.batchUploads
    val batchItems = batchQueue?.state?.collectAsState()?.value ?: emptyList()
    var batchQueueExpanded by remember(state.generation, state.session?.account_id) { mutableStateOf(false) }
    var uploadHistoryExpanded by remember(state.generation, state.session?.account_id) { mutableStateOf(false) }
    var contributeExpanded by remember(state.generation, state.session?.account_id) { mutableStateOf(false) }
    var jumpPage by remember(state.generation) { mutableStateOf(false) }
    var lookupAsset by remember(state.generation) { mutableStateOf(false) }
    var familyTagQuery by remember(state.session?.account_id, state.library) { mutableStateOf(state.familyTags?.query.orEmpty()) }
    LaunchedEffect(state.session?.account_id, state.library, state.familyTags?.query) {
        familyTagQuery = state.familyTags?.query.orEmpty()
    }
    val context = LocalContext.current
    val availableMemberships = state.session?.memberships?.filter { it.available }.orEmpty()
    LaunchedEffect(store, state.generation, state.library, state.covered) {
        if (store?.assistantEnabled == true && state.library != null && state.session != null && !state.covered)
            store.loadAssistantCapabilities()
    }
    val assistantExchangeCount = state.assistant?.turns?.size ?: 0
    val assistantEffect = state.assistant?.turns?.lastOrNull()?.turn?.effect
    LaunchedEffect(assistantOpen, assistantExchangeCount, assistantEffect) {
        if (assistantOpen && assistantExchangeCount > handledAssistantExchange && assistantEffect?.type == "open_asset") {
            handledAssistantExchange = assistantExchangeCount
            assistantOpen = false
            store?.openAssetById(assistantEffect.assetId)
        }
    }
    val selectedUploadLibrary = state.library?.takeIf { library -> availableMemberships.any { it.library_id == library } }
    var directUploadDestination by remember(state.generation, state.session?.account_id, state.upload) {
        mutableStateOf(state.upload?.destinationLibraryId)
    }
    var batchReviewDestination by remember(state.generation, state.session?.account_id) { mutableStateOf<String?>(null) }
    var batchPickerDestination by remember { mutableStateOf<String?>(null) }
    var destinationDialogAction by remember { mutableStateOf<UploadDestinationAction?>(null) }
    var destinationDialogLibrary by remember(destinationDialogAction, state.generation) { mutableStateOf<String?>(null) }
    var pickerAccount by remember { mutableStateOf<String?>(null) }
    var pendingUpload by remember { mutableStateOf<Pair<String, Uri>?>(null) }
    var batchPickerAccount by remember { mutableStateOf<String?>(null) }
    var batchUris by remember { mutableStateOf<Pair<String, List<Uri>>?>(null) }
    var batchTree by remember { mutableStateOf<Pair<String, Uri>?>(null) }
    var batchReview by remember { mutableStateOf<List<BatchUploadSource>>(emptyList()) }
    var batchSkipped by remember { mutableIntStateOf(0) }
    var batchApproved by remember { mutableStateOf(false) }
    var selectionError by remember(state.session?.account_id) { mutableStateOf(false) }
    var annotationTarget by remember(state.generation, state.session?.account_id) { mutableStateOf<UploadAnnotationTarget?>(null) }
    var annotationWavPicker by remember { mutableStateOf<AnnotationWavSelection?>(null) }
    var pendingAnnotationWav by remember { mutableStateOf<AnnotationWavSelection?>(null) }
    var annotationWavSelectionError by remember(annotationTarget, state.generation) { mutableStateOf(false) }
    var readyMicrophoneCapture by remember { mutableStateOf<PendingAnnotationCapture?>(null) }
    var recordingRequestSerial by remember { mutableIntStateOf(0) }
    var microphonePermissionContext by remember { mutableStateOf<AnnotationWavSelection?>(null) }
    var assistantPermissionContext by remember { mutableStateOf<AssistantCaptureSelection?>(null) }
    var assistantPendingCapture by remember { mutableStateOf<PendingAssistantCapture?>(null) }
    var assistantRecordingSerial by remember { mutableIntStateOf(0) }
    var assistantRecording by remember(state.generation, state.library) { mutableStateOf(false) }
    var assistantRecordError by remember(state.generation, state.library) { mutableStateOf(false) }
    var assistantCaptureRecorder = remember(state.generation, state.library) { AnnotationAudioRecorder() }
    DisposableEffect(assistantCaptureRecorder) { onDispose { assistantCaptureRecorder.stop() } }
    var activeRecording by remember(annotationTarget, state.generation) { mutableStateOf(false) }
    var recordingError by remember(annotationTarget, state.generation) { mutableStateOf(false) }
    var microphonePermissionDenied by remember(annotationTarget, state.generation) { mutableStateOf(false) }
    val audioRecorder = remember(annotationTarget, state.generation) { AnnotationAudioRecorder() }
    DisposableEffect(audioRecorder) { onDispose { audioRecorder.stop() } }
    fun enqueueMicrophoneCapture(selection: AnnotationWavSelection) {
        runCatching { audioRecorder.beginCapture() }
            .onSuccess { capture ->
                readyMicrophoneCapture = PendingAnnotationCapture(selection, capture)
                recordingRequestSerial += 1
            }
            .onFailure { recordingError = true }
    }
    fun beginAnnotation(library: String, batch: String, assetId: String, readAssetId: String = assetId) {
        annotationTarget = UploadAnnotationTarget(library, batch, assetId, readAssetId)
        store?.clearUploadAnnotationWrite(); store?.clearUploadAudioAnnotationWrite(); store?.clearUploadAnnotationRead(); store?.clearUploadAnnotationAudio()
        if (readAssetId.isNotEmpty()) store?.loadUploadAnnotations(library, readAssetId)
    }
    LaunchedEffect(annotationTarget, state.uploadAnnotationWrite?.result?.id, state.uploadAudioAnnotationWrite?.result?.id) {
        val target = annotationTarget ?: return@LaunchedEffect
        val saved = state.uploadAnnotationWrite?.takeIf { it.library == target.library && it.request.batch == target.batch && it.request.assetId == target.assetId }?.result
        val audioSaved = state.uploadAudioAnnotationWrite?.takeIf { it.library == target.library && it.request.batch == target.batch && it.request.assetId == target.assetId }?.result
        if ((saved != null || audioSaved != null) && target.readAssetId.isNotEmpty()) store?.loadUploadAnnotations(target.library, target.readAssetId)
    }
    LaunchedEffect(annotationTarget, state.uploadAnnotationRead?.result?.batch) {
        val target = annotationTarget ?: return@LaunchedEffect
        val read = state.uploadAnnotationRead?.takeIf { it.library == target.library && it.assetId == target.readAssetId }?.result
        if (target.batch.isEmpty() && read != null) annotationTarget = target.copy(batch = read.batch)
    }
    // The launcher survives the privacy cover while Android's picker is in front.
    // Keep only an ephemeral URI, then recheck the account before opening its bytes.
    val pickPhoto = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        pendingUpload = pickerAccount?.let { account -> uri?.let { account to it } }
        pickerAccount = null
    }
    val pickAnnotationWav = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        pendingAnnotationWav = annotationWavPicker?.let { snapshot -> uri?.let { snapshot.copy(uri = it) } }
        annotationWavPicker = null
    }
    val requestMicrophone = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            microphonePermissionDenied = false
            microphonePermissionContext?.let(::enqueueMicrophoneCapture)
            assistantPermissionContext?.let { selection ->
                runCatching { assistantCaptureRecorder.beginCapture(selection.maxSeconds) }.onSuccess { capture ->
                    assistantPendingCapture = PendingAssistantCapture(selection, capture); assistantRecordingSerial++
                }.onFailure { assistantRecordError = true }
            }
        } else {
            microphonePermissionDenied = true
            assistantRecordError = true
        }
        microphonePermissionContext = null
        assistantPermissionContext = null
    }
    LaunchedEffect(assistantRecordingSerial) {
        val pending = assistantPendingCapture ?: return@LaunchedEffect
        val selected = pending.selection
        if (store == null || state.covered || state.session?.account_id != selected.account || state.library != selected.library || state.generation != selected.generation) {
            pending.capture.discard(); return@LaunchedEffect
        }
        assistantRecordError = false; assistantRecording = true
        val wav = try { withContext(Dispatchers.IO) { runCatching { pending.capture.record() }.getOrNull() } }
        catch (cancelled: kotlinx.coroutines.CancellationException) { pending.capture.discard(); throw cancelled }
        finally { pending.capture.stop() }
        assistantRecording = false
        val authorized = store.state.value.generation == selected.generation && !store.state.value.covered &&
            store.state.value.session?.account_id == selected.account && store.state.value.library == selected.library
        if (wav != null && authorized && pending.capture.consumeForUpload()) store.transcribeAssistant(wav)
        else if (!pending.capture.wasDiscarded && wav == null) assistantRecordError = true
        assistantPendingCapture = null
    }
    LaunchedEffect(recordingRequestSerial) {
        val pending = readyMicrophoneCapture ?: return@LaunchedEffect
        val selected = pending.selection
        if (store == null || state.covered || state.session?.account_id != selected.account ||
            state.generation != selected.generation || annotationTarget != selected.target) {
            pending.capture.discard()
            return@LaunchedEffect
        }
        recordingError = false
        activeRecording = true
        val wav = try {
            withContext(Dispatchers.IO) { runCatching { pending.capture.record() }.getOrNull() }
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            pending.capture.discard()
            throw cancelled
        } finally {
            pending.capture.stop()
        }
        activeRecording = false
        val uploadStillAuthorized = store.state.value.generation == selected.generation && !store.state.value.covered &&
            store.state.value.session?.account_id == selected.account && annotationTarget == selected.target
        if (wav != null && uploadStillAuthorized && pending.capture.consumeForUpload()) {
            store.saveUploadAudioAnnotation(selected.target.library, selected.target.batch,
                selected.target.assetId, selected.language, selected.consent, wav)
        } else if (!pending.capture.wasDiscarded && wav == null) recordingError = true
    }
    LaunchedEffect(pendingAnnotationWav) {
        val selected = pendingAnnotationWav ?: return@LaunchedEffect
        pendingAnnotationWav = null
        if (store == null || state.covered || state.session?.account_id != selected.account ||
            state.generation != selected.generation || annotationTarget != selected.target) return@LaunchedEffect
        val uri = selected.uri ?: return@LaunchedEffect
        val wav = withContext(Dispatchers.IO) { runCatching { readAnnotationWav(context, uri) }.getOrNull() }
        if (store.state.value.generation != selected.generation || store.state.value.covered ||
            store.state.value.session?.account_id != selected.account || annotationTarget != selected.target) return@LaunchedEffect
        if (wav == null) annotationWavSelectionError = true
        else store.saveUploadAudioAnnotation(selected.target.library, selected.target.batch,
            selected.target.assetId, selected.language, selected.consent, wav)
    }
    val launchDirectPhotoPicker: () -> Unit = {
        pickerAccount = state.session?.account_id
        pickPhoto.launch(arrayOf("image/jpeg", "image/png"))
    }
    val pickBatch = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        uris.forEach { uri -> runCatching { context.contentResolver.takePersistableUriPermission(uri, android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION) } }
        batchUris = batchPickerAccount?.let { it to uris }; batchReviewDestination = batchPickerDestination
        batchPickerAccount = null; batchPickerDestination = null; batchApproved = false
    }
    val pickBatchFolder = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        uri?.let { selected -> runCatching { context.contentResolver.takePersistableUriPermission(selected, android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION) }; batchTree = batchPickerAccount?.let { it to selected } }
        batchReviewDestination = batchPickerDestination
        batchPickerAccount = null; batchPickerDestination = null; batchApproved = false
    }
    LaunchedEffect(batchUris, state.session?.account_id, state.generation) {
        val selected = batchUris ?: return@LaunchedEffect
        if (selected.first != state.session?.account_id || state.covered) { batchUris = null; batchReview = emptyList(); batchReviewDestination = null; return@LaunchedEffect }
        val sources = withContext(Dispatchers.IO) { selected.second.take(100).mapNotNull { runCatching { batchUploadSource(context, it) }.getOrNull() } }
        if (selected.first != store?.state?.value?.session?.account_id || store?.state?.value?.covered != false) { batchUris = null; batchReviewDestination = null; return@LaunchedEffect }
        var total = 0L
        val accepted = sources.filter { source ->
            if (source.bytes > 64L * 1024 * 1024 * 1024 - total) false else { total += source.bytes; true }
        }
        batchSkipped = selected.second.size - accepted.size; batchReview = accepted; batchUris = null
    }
    LaunchedEffect(batchTree, state.session?.account_id, state.generation) {
        val selected = batchTree ?: return@LaunchedEffect
        if (selected.first != state.session?.account_id || state.covered) { batchTree = null; batchReview = emptyList(); batchReviewDestination = null; return@LaunchedEffect }
        val result = withContext(Dispatchers.IO) { runCatching { batchUploadTree(context, selected.second) }.getOrElse { BatchTreeResult(emptyList(), 1, 0) } }
        if (selected.first != store?.state?.value?.session?.account_id || store?.state?.value?.covered != false) { batchTree = null; batchReviewDestination = null; return@LaunchedEffect }
        batchSkipped = result.skipped; batchReview = result.sources; batchTree = null
    }
    LaunchedEffect(pendingUpload, state.covered, state.session?.account_id, state.busy) {
        val pending = pendingUpload ?: return@LaunchedEffect
        if (state.covered || state.busy) return@LaunchedEffect
        if (store == null || state.session?.account_id != pending.first) { pendingUpload = null; return@LaunchedEffect }
        val generation = state.generation
        val source = withContext(Dispatchers.IO) { runCatching { uploadSource(context, pending.second) }.getOrNull() }
        pendingUpload = null
        if (store.state.value.generation != generation || store.state.value.covered) return@LaunchedEffect
        selectionError = source == null
        val upload = store.openUpload()
        val destination = directUploadDestination ?: upload?.destinationLibraryId
        if (source != null && destination != null) upload?.start(source, network = uploadNetwork(context), destinationLibraryId = destination)
        else selectionError = source == null
    }
    val enqueueReviewedBatch: (String) -> Unit = { destination ->
        val queued = batchQueue?.enqueue(batchReview, destination).orEmpty()
        if (queued.isNotEmpty()) {
            batchQueue?.resume()
            batchReview = emptyList(); batchSkipped = 0; batchReviewDestination = null; batchApproved = false
        }
    }
    val scroll = rememberLazyListState()
    LaunchedEffect(state.generation) { scroll.scrollToItem(0) }
    PhotoHouseTheme {
        if (!state.covered && store != null && state.session != null && state.library != null) {
            state.groupedStoryCreation?.let { creation -> GroupedStoryCreationDialog(store, creation, words.zh) }
        }
        if (!state.covered && store != null) state.storyEditor?.let { editor ->
            ProtectedStoryEditorDialog(editor, onDismiss = store::closeStoryEditor, zh = words.zh)
        }
        if (!state.covered && store != null && state.session != null && state.library != null && store.protectedNativeV2Enabled) {
            state.savedMemoryStories?.let { reading -> SavedMemoryStoriesDialog(
                store = store,
                reading = reading, zh = words.zh,
                onClose = store::closeSavedMemoryStories,
                onRetry = { page -> store.openSavedMemoryStories(page, reading.theme) },
                onSelectTheme = { theme -> store.openSavedMemoryStories(1, theme) },
                onOpenStory = store::openSavedMemoryStory,
                onRetryDetail = store::retrySavedMemoryStory,
                onCloseDetail = store::closeSavedMemoryStoryDetail,
                onChapter = store::loadSavedMemoryChapter,
                onSelectFrame = store::loadSavedMemoryHero,
                onOpenAsset = { id -> store.closeSavedMemoryStories(); store.openAssetById(id) },
            ) }
        }
        if (!state.covered && store != null && state.session != null && store.memoryCommunityAvailable) {
            state.memoryBooks?.let { books -> MemoryBooksDialog(books, store, words.zh, store::openMemoryBooks,
                store::openMemoryBook, store::loadMemoryBookStory, store::resumeMemoryBookReading, store::loadMemoryBookChapter,
                store::loadMemoryBookFramePage, store::selectMemoryBookAsset,
                { assetId -> store.closeMemoryBooks(); store.openAssetById(assetId) },
                store::closeMemoryBook, store::closeMemoryBooks) }
        }
        if (lookupAsset && state.library != null && !state.covered && store != null) AssetLookupDialog(
            words.zh, { lookupAsset = false }, { id -> lookupAsset = false; store.openAssetById(id) })
        val galleryForJump = state.gallery
        if (jumpPage && galleryForJump != null && !state.covered && store != null) PhonePageJump(
            galleryForJump.page, galleryForJump.page_size, galleryForJump.total, words.zh,
            { jumpPage = false }, { target -> jumpPage = false; store.navigatePage(target) })
        if (settings) AlertDialog(
            onDismissRequest = { settings = false },
            title = { Text(t("Settings", "设置")) },
            text = { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(t("App language", "界面语言"), style = MaterialTheme.typography.titleSmall)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("system" to t("System", "系统"), "en" to "English", "zh" to "简体中文").forEach { (value, label) ->
                        FilterChip(selected = language == value, onClick = { language = value; settings = false }, label = { Text(label) })
                    }
                }
                if (state.session != null && !state.covered && store != null) {
                    HorizontalDivider()
                    TextButton(onClick = { settings = false; store.logout() }) { Text(t("Sign out", "退出登录")) }
                }
                HorizontalDivider()
                PhotoHouseOtaControl("phone", BuildConfig.PHOTOHOUSE_ORIGIN, words.zh, Modifier.testTag("ota-control"))
            } },
            confirmButton = { TextButton(onClick = { settings = false }) { Text(t("Done", "完成")) } }
        )
        annotationTarget?.let { target ->
            val onRecordAudio: (String, String) -> Unit = { lang, consent ->
                val account = state.session?.account_id
                if (account != null && !state.covered && target.batch.matches(Regex("[0-9a-f]{32}"))) {
                    microphonePermissionDenied = false
                    val request = AnnotationWavSelection(account, state.generation, target, lang, consent)
                    if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        enqueueMicrophoneCapture(request)
                    } else {
                        microphonePermissionContext = request
                        requestMicrophone.launch(Manifest.permission.RECORD_AUDIO)
                    }
                }
            }
            UploadAnnotationComposer(target, words.zh, state.uploadAnnotationRead, state.uploadAnnotationWrite,
                state.uploadAudioAnnotationWrite, annotationWavSelectionError,
                activeRecording, recordingError, microphonePermissionDenied,
                audioPlayback = state.uploadAnnotationAudio,
                onDismiss = { annotationTarget = null; store?.clearUploadAnnotationWrite(); store?.clearUploadAudioAnnotationWrite(); store?.clearUploadAnnotationRead(); store?.clearUploadAnnotationAudio() },
                onSave = { text, lang, consent -> store?.saveUploadTextAnnotation(target.library, target.batch, target.assetId, lang, consent, text) },
                onRetry = { store?.retryUploadTextAnnotation() },
                onPickAudio = { lang, consent ->
                    val account = state.session?.account_id
                    if (account != null && !state.covered && target.batch.matches(Regex("[0-9a-f]{32}"))) {
                        annotationWavSelectionError = false
                        annotationWavPicker = AnnotationWavSelection(account, state.generation, target, lang, consent)
                        pickAnnotationWav.launch(arrayOf("audio/wav", "audio/x-wav", "application/octet-stream"))
                    }
                },
                onRetryAudio = { store?.retryUploadAudioAnnotation() },
                onRecordAudio = onRecordAudio,
                onStopRecording = { readyMicrophoneCapture?.capture?.stop() },
                onDiscardRecording = { readyMicrophoneCapture?.capture?.discard() },
                onPlayAudio = { store?.loadUploadAnnotationAudio(target.library, it) },
                onRetryAudioPlayback = { store?.loadUploadAnnotationAudio(target.library, it) },
                onRefresh = { if (target.readAssetId.isNotEmpty()) store?.loadUploadAnnotations(target.library, target.readAssetId) })
        }
        if (destinationDialogAction != null && state.session != null && !state.covered) AlertDialog(
            modifier = Modifier.testTag("upload-destination-dialog"),
            onDismissRequest = { destinationDialogAction = null },
            title = { Text(t("Choose destination library", "选择目标资料库")) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(t("Choose the library for these uploads.", "请选择这些上传内容的目标资料库。"))
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        availableMemberships.forEach { membership ->
                            FilterChip(selected = destinationDialogLibrary == membership.library_id,
                                onClick = { destinationDialogLibrary = membership.library_id },
                                label = { Text(LibraryNames.display(membership.library_id, words.zh)) },
                                modifier = Modifier.testTag("upload-destination-${membership.library_id}"))
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = {
                val destination = destinationDialogLibrary
                val action = destinationDialogAction
                if (destination != null) when (action) {
                    UploadDestinationAction.DIRECT -> {
                        if (state.upload?.chooseDestination(destination) == true) {
                            directUploadDestination = destination
                            launchDirectPhotoPicker()
                        }
                    }
                    UploadDestinationAction.BATCH -> {
                        batchReviewDestination = destination
                        enqueueReviewedBatch(destination)
                    }
                    null -> Unit
                }
                destinationDialogAction = null
            }, enabled = destinationDialogLibrary != null) { Text(t("Continue", "继续")) } },
            dismissButton = { TextButton(onClick = { destinationDialogAction = null }) { Text(t("Cancel", "取消")) } }
        )
        Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            BackHandler(store != null && state.library != null && !state.covered) {
                if (assistantOpen) assistantOpen = false
                else if (state.video != null) store?.closeVideo()
                else if (state.viewingOriginal) store?.closeOriginalPhoto()
                else if (state.detail != null || state.photoNavigation != null) store?.backToPhotos()
                else if (state.familyTags != null) { if (state.familyTags?.selectedTag != null) store?.backToFamilyTags() else store?.loadPage(1) }
                else if (state.discovery != null) { if (state.discovery?.editing == true) store?.loadPage(1) else store?.editDiscovery() } else store?.libraries()
            }
            if (state.upload != null && !state.covered && store != null) {
                BackHandler { store.closeUpload() }
                Column(Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(androidx.compose.foundation.rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    TextButton(onClick = store::closeUpload) { Text(t("Back to album", "返回相册")) }
                    if (selectionError) Text(t("Choose a JPEG or PNG up to 25 MiB with a known file size.", "请选择大小已知且不超过 25 MiB 的 JPEG 或 PNG 照片。"), color = MaterialTheme.colorScheme.error)
                    val destinationLabel = directUploadDestination?.let { id -> availableMemberships.firstOrNull { it.library_id == id }?.let { LibraryNames.display(it.library_id, words.zh) } }
                    UploadPanel(state.upload!!, words.zh, destinationLabel = destinationLabel, onPick = {
                        selectionError = false
                        val destination = directUploadDestination ?: state.upload?.destinationLibraryId
                        if (destination == null) {
                            destinationDialogAction = UploadDestinationAction.DIRECT
                        } else if (state.upload?.chooseDestination(destination) == true) {
                            directUploadDestination = destination
                            launchDirectPhotoPicker()
                        } else destinationDialogAction = UploadDestinationAction.DIRECT
                    }, onClose = store::closeUpload, onDescribe = { receipt ->
                        val library = receipt.destinationLibraryId ?: state.upload?.destinationLibraryId
                        if (library != null) beginAnnotation(library, receipt.batch, receipt.assetId)
                    })
                }
                return@Surface
            }
            if (state.video != null && !state.covered && store != null) {
                val reader = state.video!!
                key(reader) { VideoPlayer(reader, words.zh, { store.closeVideo(reader) },
                    { store.videoPlaybackFailed(reader, nativeFailure = true, reason = it) }, state.videoBookmark,
                    previous = if (store.adjacentVideoId(-1) != null) ({ store.adjacentVideo(-1) }) else null,
                    next = if (store.adjacentVideoId(1) != null) ({ store.adjacentVideo(1) }) else null) }
                return@Surface
            }
            if (state.viewingOriginal && !state.covered && store != null) {
                OriginalPhotoViewer(state.originalPhoto, state.busy, words.zh, store::closeOriginalPhoto,
                    state.photoNavigation, state.photoSlideshow, { store.adjacentOriginalPhoto(it) },
                    store::togglePhotoSlideshow, store::stopPhotoSlideshow, store::advancePhotoSlideshow,
                    originalQuality = state.photoOriginalQuality,
                    previewOnly = state.photoPreviewOnly,
                    onOriginal = if (state.detail?.originals_allowed == true) store::openOriginalPhoto else null)
                return@Surface
            }
            if (assistantOpen && state.library != null && !state.covered && store != null) {
                AssistantScreen(state.assistant, words.zh, previews = state.previews, onBack = { store.clearAssistantSpeech(); assistantOpen = false },
                    onRetryCapabilities = { store.loadAssistantCapabilities() },
                    onSend = store::sendAssistantText, onClear = store::clearAssistant,
                    onOpen = { id, requestId -> store.reportAssistantOpenRequested(requestId); assistantOpen = false; store.openAssetById(id) },
                    onCheckReceipt = store::checkAssistantReceipt,
                    onRecord = {
                        val capability = state.assistant?.capabilities
                        val account = state.session?.account_id
                        if (account != null && !state.covered && capability?.let { it.enabled && it.transcribe && it.maxAudioSeconds in 1..30 } == true) {
                            val library = state.library ?: return@AssistantScreen
                            val selection = AssistantCaptureSelection(account, library, state.generation, capability.maxAudioSeconds)
                            val start = {
                                runCatching { assistantCaptureRecorder.beginCapture(selection.maxSeconds) }.onSuccess { capture ->
                                    assistantPendingCapture = PendingAssistantCapture(selection, capture); assistantRecordingSerial++
                                }.onFailure { assistantRecordError = true }
                            }
                            if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) start()
                            else { assistantPermissionContext = selection; requestMicrophone.launch(Manifest.permission.RECORD_AUDIO) }
                        }
                    },
                    onStopRecording = { assistantPendingCapture?.capture?.stop() },
                    onCancelRecording = { assistantPendingCapture?.capture?.discard(); assistantPendingCapture = null; assistantRecording = false },
                    recording = assistantRecording, recordError = assistantRecordError,
                    onClearTranscript = store::clearAssistantTranscript,
                    onPlaySpeech = { store.loadAssistantSpeech(if (words.zh) "zh" else "en") },
                    onStopSpeech = store::clearAssistantSpeech)
                return@Surface
            }
            LazyColumn(Modifier.fillMaxSize().safeDrawingPadding().testTag("connected-screen"), state = scroll,
                contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                item {
                    FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                        verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(t("PhotoHouse", "拾光相册"), style = MaterialTheme.typography.headlineLarge,
                                fontFamily = FontFamily.Serif, color = MaterialTheme.colorScheme.primary)
                            Text(t("Family memories, together", "家人的回忆，共同珍藏"), style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        TextButton(onClick = { settings = true }, modifier = Modifier.testTag("app-settings")) { Text(t("Settings", "设置")) }
                    }
                }
                if (store == null) {
                    item { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(t("Server setup needed", "需要配置服务器"), style = MaterialTheme.typography.headlineSmall, modifier = Modifier.testTag("server-not-configured"))
                        Text(t("Ask your administrator for a build configured for your PhotoHouse HTTPS server. Sign-in is unavailable until then.", "请向管理员获取已配置相册 HTTPS 服务器的版本。配置完成前无法登录。"))
                    } }
                } else {
                    if (state.busy) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
                    state.problem?.let { problem -> item {
                        Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp)) {
                            Text(problem.playbackFailure?.message(words.zh) ?: if ((problem.message == Message.UNAVAILABLE || problem.message == Message.NETWORK_UNAVAILABLE) && state.session != null)
                                t("Could not load this item. Check the connection and retry.", "暂时无法加载此内容，请检查网络连接后重试。")
                            else words.message(problem.message))
                            var now by remember(problem) { mutableLongStateOf(System.currentTimeMillis()) }
                            LaunchedEffect(problem) { while (now < problem.retryAtMillis) { delay(500); now = System.currentTimeMillis() } }
                            if (now < problem.retryAtMillis) Text(t("Please wait", "请稍候"))
                            if (store.canRetry(now)) TextButton(onClick = store::retry) { Text(t("Retry", "重试")) }
                        } }
                    } }
                    when {
                        state.covered -> {
                            item { Text(t("Private content is covered while your session is checked.", "检查会话期间，私人内容已遮盖。")) }
                            item { Button(onClick = store::foreground, enabled = !state.busy) { Text(t("Check session", "检查会话")) } }
                            item { Button(onClick = store::logout) { Text(t("Sign out locally", "在本机退出")) } }
                        }
                        state.session == null -> item { key(state.generation) { AdmissionForm(store, state, words) } }
                        else -> {
                            if (availableMemberships.isNotEmpty() &&
                                (store.protectedNativeV2Enabled || store.memoryCommunityAvailable)) item {
                                Card(Modifier.fillMaxWidth().testTag("home-memory-section")) {
                                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                        Text(t("Family memories", "家庭回忆"), style = MaterialTheme.typography.titleLarge)
                                        val intro = when {
                                            store.protectedNativeV2Enabled && store.memoryCommunityAvailable ->
                                                t("Open one saved story by chapter, or browse longer family memory books.", "打开一段故事，按章节回看；也可以翻阅较长的家庭回忆册。")
                                            store.protectedNativeV2Enabled ->
                                                t("Open one saved story by chapter.", "打开一段已保存的故事，按章节回看。")
                                            else ->
                                                t("Browse longer family memories collected into books.", "翻阅集中整理的较长家庭回忆册。")
                                        }
                                        Text(
                                            intro,
                                            style = MaterialTheme.typography.bodyMedium,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                        if (store.protectedNativeV2Enabled) OutlinedButton(
                                            onClick = { store.openSavedMemoryStories(1) }, enabled = !state.busy,
                                            modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp).testTag("open-saved-memory-stories"),
                                        ) {
                                            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                                Text(t("Stories and chapters", "故事与章节"), style = MaterialTheme.typography.titleSmall)
                                                Text(t("A single saved story, read one chapter at a time", "一段已保存的故事，逐章阅读"), style = MaterialTheme.typography.bodySmall)
                                            }
                                        }
                                        if (store.memoryCommunityAvailable) OutlinedButton(
                                            onClick = { store.openMemoryBooks(1) }, enabled = !state.busy,
                                            modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp).testTag("open-memory-books"),
                                        ) {
                                            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                                Text(t("Family memory books", "家庭回忆册"), style = MaterialTheme.typography.titleSmall)
                                                Text(t("Longer memories collected on a shelf", "集中翻阅较长的家庭回忆"), style = MaterialTheme.typography.bodySmall)
                                            }
                                        }
                                    }
                                }
                            }
                            if (store.uploadEnabled && state.session?.memberships?.any { it.available } == true) item {
                                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                Card(Modifier.fillMaxWidth().testTag("contribute-panel")) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(t("Add to your album", "为相册添加内容"), style = MaterialTheme.typography.titleMedium)
                                    Text(t("Choose a photo, or open more ways to add a batch and review uploads.", "选择一张照片，或展开更多方式以添加一批文件及查看上传记录。"),
                                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                        Button(onClick = { selectionError = false; store.openUpload() }, enabled = !state.busy,
                                            modifier = Modifier.testTag("open-upload")) { Text(t("Add a photo", "添加照片")) }
                                        TextButton(onClick = { contributeExpanded = !contributeExpanded },
                                            modifier = Modifier.testTag("contribute-toggle").semantics {
                                                stateDescription = t(if (contributeExpanded) "Expanded" else "Collapsed", if (contributeExpanded) "已展开" else "已收起")
                                            }) { Text(if (contributeExpanded) t("Fewer options", "收起选项") else t("More options", "更多选项")) }
                                    }
                                    if (contributeExpanded) {
                                        HorizontalDivider()
                                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                            OutlinedButton(onClick = { store.loadUploadHistory(1) }, enabled = !state.busy && state.uploadHistory?.busy != true,
                                                modifier = Modifier.testTag("open-upload-history")) { Text(t("Upload history", "上传记录")) }
                                            if (batchQueue != null) OutlinedButton(onClick = {
                                                batchPickerAccount = state.session?.account_id
                                                batchPickerDestination = selectedUploadLibrary
                                                pickBatch.launch(arrayOf("image/jpeg", "image/png", "video/mp4", "video/quicktime"))
                                            }, enabled = !state.busy, modifier = Modifier.testTag("batch-pick")) { Text(t("Choose files", "选择文件")) }
                                            if (batchQueue != null) OutlinedButton(onClick = { batchPickerAccount = state.session?.account_id; batchPickerDestination = selectedUploadLibrary; pickBatchFolder.launch(null) }, enabled = !state.busy, modifier = Modifier.testTag("batch-pick-folder")) { Text(t("Choose folder", "选择文件夹")) }
                                        }
                                    }
                                } }
                                if (batchReview.isNotEmpty() || batchSkipped > 0) Card(Modifier.fillMaxWidth().testTag("batch-review")) {
                                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Text(t("Review uploads", "检查上传"), style = MaterialTheme.typography.titleMedium)
                                        Text(t("${batchReview.size} files · ${batchReview.sumOf { it.bytes }} bytes", "${batchReview.size} 个文件 · ${batchReview.sumOf { it.bytes }} 字节"))
                                        val batchDestination = batchReviewDestination?.let { id -> availableMemberships.firstOrNull { it.library_id == id }?.let { LibraryNames.display(it.library_id, words.zh) } }
                                        Text(batchDestination?.let { t("Destination: $it", "目标资料库：$it") }
                                            ?: t("Choose a destination library before starting.", "开始前请选择目标资料库。"),
                                            style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("batch-destination-summary"))
                                        if (batchSkipped > 0) Text(t("$batchSkipped unsupported or unknown-size files were skipped.", "已跳过 $batchSkipped 个不支持或大小未知的文件。"), color = MaterialTheme.colorScheme.error)
                                        if (!batchApproved && uploadNetwork(context) != UploadNetwork.UNMETERED) Text(t("This connection may incur data charges. Continue only after review.", "当前网络可能产生流量费用，请确认后继续。"))
                                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                            Button(onClick = { if (uploadNetwork(context) == UploadNetwork.UNMETERED || batchApproved) {
                                                val destination = batchReviewDestination ?: selectedUploadLibrary
                                                if (destination != null) enqueueReviewedBatch(destination)
                                                else destinationDialogAction = UploadDestinationAction.BATCH
                                            } else batchApproved = true }, modifier = Modifier.testTag("batch-start")) { Text(if (batchApproved || uploadNetwork(context) == UploadNetwork.UNMETERED) t("Start", "开始") else t("Continue", "继续")) }
                                            OutlinedButton(onClick = { batchReview = emptyList(); batchReviewDestination = null; batchSkipped = 0 }, modifier = Modifier.testTag("batch-discard")) { Text(t("Discard", "放弃")) }
                                        }
                                    }
                                }
                                if (batchItems.isNotEmpty()) Card(Modifier.fillMaxWidth().testTag("batch-queue")) {
                                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                        val uploadingCount = batchItems.count { it.record.status == "uploading" }
                                        val waitingCount = batchItems.count { it.record.status in setOf("needs_hash", "queued", "paused") }
                                        val failedCount = batchItems.count { it.record.status == "failed" }
                                        val completedCount = batchItems.count { it.record.status == "complete" }
                                        val transferred = batchItems.sumOf { item ->
                                            when (item.record.status) {
                                                "complete" -> item.record.bytes.coerceAtLeast(0)
                                                "uploading" -> item.record.offset.coerceAtLeast(0)
                                                else -> 0L
                                            }
                                        }
                                        val totalBytes = batchItems.sumOf { it.record.bytes.coerceAtLeast(0) }
                                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                                Text(t("Upload queue", "上传队列"), style = MaterialTheme.typography.titleMedium)
                                                val summary = t(
                                                    "${batchItems.size} ${if (batchItems.size == 1) "item" else "items"} · $uploadingCount uploading · $waitingCount waiting · $completedCount done${if (failedCount > 0) " · $failedCount failed" else ""}",
                                                    "${batchItems.size} 项 · 上传中 $uploadingCount · 等待中 $waitingCount · 已完成 $completedCount${if (failedCount > 0) " · 失败 $failedCount" else ""}"
                                                )
                                                Text(summary, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                    modifier = Modifier.testTag("batch-queue-summary"))
                                            }
                                            TextButton(onClick = { batchQueueExpanded = !batchQueueExpanded },
                                                modifier = Modifier.testTag("batch-queue-toggle").semantics {
                                                    stateDescription = t(if (batchQueueExpanded) "Expanded" else "Collapsed", if (batchQueueExpanded) "已展开" else "已收起")
                                                }) {
                                                Text(if (batchQueueExpanded) t("Hide", "收起") else t("Show", "展开"))
                                            }
                                        }
                                        if (totalBytes > 0) {
                                            LinearProgressIndicator(progress = { (transferred.toFloat() / totalBytes).coerceIn(0f, 1f) },
                                                modifier = Modifier.fillMaxWidth().testTag("batch-queue-progress"))
                                        }
                                        if (!batchQueueExpanded && failedCount > 0) OutlinedButton(
                                            onClick = { batchQueueExpanded = true }, modifier = Modifier.testTag("batch-review-failures")) {
                                            Text(t("Review $failedCount failed uploads", "查看 $failedCount 个失败上传"))
                                        }
                                        if (batchQueueExpanded) batchItems.filter { it.record.status == "complete" && it.record.destinationLibraryId != null }
                                            .groupBy { it.record.batch }.forEach { (batch, items) ->
                                                val destination = items.first().record.destinationLibraryId!!
                                                OutlinedButton(onClick = { beginAnnotation(destination, batch, "", items.firstNotNullOfOrNull { it.record.assetId } ?: "") },
                                                    modifier = Modifier.testTag("batch-describe-$batch")) {
                                                    Text(t("Describe this batch", "描述这批上传内容"))
                                                }
                                            }
                                        if (batchQueueExpanded) batchItems.forEach { item ->
                                            val status = when (item.record.status) {
                                                "needs_hash" -> t("needs_hash", "等待校验")
                                                "queued" -> t("queued", "等待上传")
                                                "uploading" -> t("uploading", "上传中")
                                                "paused" -> t("paused", "已暂停")
                                                "failed" -> t("failed", "上传中断")
                                                "cancelling" -> t("cancelling", "正在取消")
                                                "cancelled" -> t("cancelled", "已取消")
                                                "complete" -> t("complete", "已收到，等待审核")
                                                else -> t("unknown", "状态未知")
                                            }
                                            Text("${item.record.filename}: $status ${item.record.offset}/${item.record.bytes}", modifier = Modifier.testTag("batch-status-${item.record.localId}"))
                                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                                val itemDestination = item.record.destinationLibraryId
                                                val completedAssetId = item.record.assetId
                                                if (item.record.status == "complete" && itemDestination != null && completedAssetId != null)
                                                    OutlinedButton(onClick = { beginAnnotation(itemDestination, item.record.batch, completedAssetId) },
                                                        modifier = Modifier.testTag("batch-describe-item-${item.record.localId}")) { Text(t("Describe photo", "描述照片")) }
                                                if (item.record.status == "uploading") OutlinedButton(onClick = { batchQueue!!.pause() }, modifier = Modifier.testTag("batch-pause")) { Text(t("Pause", "暂停")) }
                                                if (item.record.status in setOf("paused", "failed", "queued", "needs_hash")) OutlinedButton(onClick = { batchQueue!!.resume(item.record.localId) }, modifier = Modifier.testTag("batch-resume")) { Text(t("Resume", "继续")) }
                                                if (item.record.status == "failed") OutlinedButton(onClick = { batchQueue!!.retry(item.record.localId) }, modifier = Modifier.testTag("batch-retry")) { Text(t("Retry", "重试")) }
                                                if (item.record.status !in setOf("complete", "cancelled")) OutlinedButton(onClick = { batchQueue!!.cancel(item.record.localId) }, modifier = Modifier.testTag("batch-cancel")) { Text(t("Cancel", "取消")) }
                                            }
                                        }
                                    }
                                }
                                state.uploadHistory?.let { history ->
                                    Card(Modifier.fillMaxWidth().testTag("upload-history")) {
                                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                                    Text(t("My uploads", "我的上传记录"), style = MaterialTheme.typography.titleMedium)
                                                    val historySummary = when {
                                                        history.busy -> t("Loading upload history", "正在加载上传记录")
                                                        history.unavailable -> t("History unavailable", "记录暂不可用")
                                                        else -> t("${history.total} uploads · page ${history.page}", "共 ${history.total} 条 · 第 ${history.page} 页")
                                                    }
                                                    Text(historySummary, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                        modifier = Modifier.testTag("upload-history-summary"))
                                                }
                                                TextButton(onClick = { uploadHistoryExpanded = !uploadHistoryExpanded },
                                                    modifier = Modifier.testTag("upload-history-toggle").semantics {
                                                        stateDescription = t(if (uploadHistoryExpanded) "Expanded" else "Collapsed", if (uploadHistoryExpanded) "已展开" else "已收起")
                                                    }) {
                                                    Text(if (uploadHistoryExpanded) t("Hide", "收起") else t("Show", "展开"))
                                                }
                                                TextButton(onClick = store::closeUploadHistory) { Text(t("Close", "关闭")) }
                                            }
                                            if (history.busy) LinearProgressIndicator(Modifier.fillMaxWidth().testTag("upload-history-progress"))
                                            if (history.unavailable) {
                                                Text(t("Upload history is unavailable right now. Regular uploads remain available.", "上传记录暂不可用，仍可继续普通上传。"),
                                                    color = MaterialTheme.colorScheme.error)
                                                if (!uploadHistoryExpanded) OutlinedButton(onClick = { store.loadUploadHistory(history.page) }, enabled = !history.busy,
                                                    modifier = Modifier.testTag("upload-history-refresh-collapsed")) { Text(t("Retry", "重试")) }
                                            }
                                            if (uploadHistoryExpanded && !history.busy && !history.unavailable && history.items.isEmpty()) Text(t("No uploads yet.", "还没有上传记录。"))
                                            if (uploadHistoryExpanded && !history.busy && !history.unavailable) history.items.forEach { item ->
                                                val locale = if (words.zh) java.util.Locale.SIMPLIFIED_CHINESE else java.util.Locale.ENGLISH
                                                val uploadedAt = java.text.DateFormat.getDateTimeInstance(java.text.DateFormat.MEDIUM, java.text.DateFormat.SHORT, locale).format(java.util.Date(item.createdAt * 1000))
                                                Column(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                                                        verticalAlignment = Alignment.CenterVertically) {
                                                        Text("#${item.assetId}", style = MaterialTheme.typography.titleSmall)
                                                        Text(when (item.state) {
                                                            "available" -> t("Available", "可浏览")
                                                            "awaiting_review" -> t("Awaiting review", "等待审核")
                                                            else -> t("Unavailable", "暂不可用")
                                                        }, style = MaterialTheme.typography.bodySmall,
                                                            color = if (item.state == "available") MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
                                                    }
                                                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                                                        verticalAlignment = Alignment.CenterVertically) {
                                                        Text("$uploadedAt · ${String.format(locale, "%.1f KiB", item.bytes / 1024.0)}",
                                                            style = MaterialTheme.typography.bodySmall,
                                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                            modifier = Modifier.weight(1f))
                                                        if (item.state == "available") TextButton(onClick = { store.openUploadHistory(item) }) {
                                                            Text(t("Open", "打开"))
                                                        }
                                                        item.libraryId?.takeIf { item.state == "available" }?.let { libraryId ->
                                                            TextButton(onClick = { beginAnnotation(libraryId, "", item.assetId) },
                                                                modifier = Modifier.testTag("upload-history-descriptions-${item.assetId}")) {
                                                                Text(t("Descriptions", "描述"))
                                                            }
                                                        }
                                                    }
                                                }
                                                HorizontalDivider()
                                            }
                                            if (uploadHistoryExpanded) {
                                                if (!history.busy && !history.unavailable && history.total > 0) Text(t("Page ${history.page} of ${(history.total + 9L) / 10}", "第 ${history.page} / ${(history.total + 9L) / 10} 页"), style = MaterialTheme.typography.bodySmall)
                                                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                                    OutlinedButton(onClick = { store.loadUploadHistory(history.page) }, enabled = !history.busy,
                                                        modifier = Modifier.testTag("upload-history-refresh")) { Text(t("Refresh", "刷新")) }
                                                    OutlinedButton(onClick = { store.loadUploadHistory(history.page - 1) }, enabled = !history.busy && !history.unavailable && history.page > 1,
                                                        modifier = Modifier.testTag("upload-history-previous")) { Text(t("Previous", "上一页")) }
                                                    OutlinedButton(onClick = { store.loadUploadHistory(history.page + 1) }, enabled = !history.busy && !history.unavailable && history.page * 10 < history.total,
                                                        modifier = Modifier.testTag("upload-history-next")) { Text(t("Next", "下一页")) }
                                                }
                                            }
                                        }
                                    }
                                }
                                }
                            }
                            if (state.library != null && state.detail == null && state.photoNavigation == null) item {
                                TextButton(onClick = store::libraries) { Text(t("Libraries", "资料库")) }
                            }
                            when {
                                state.library == null -> {
                                    item { Text(t("Your libraries", "你的资料库"), style = MaterialTheme.typography.headlineSmall) }
                                    state.session?.displayName?.let { name -> item { Text(t("Welcome, $name", "欢迎，$name"), modifier = Modifier.testTag("account-name")) } }
                                    if (state.session!!.memberships.isEmpty()) item { Text(t("You have no library memberships.", "尚未加入任何资料库。")) }
                                    val memberships = state.session!!.memberships.sortedWith(compareBy { if (it.library_id == "family") 0 else 1 })
                                    items(memberships, key = { it.library_id }) { membership ->
                                        Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                            Text(t("Photo and video library", "照片与视频资料库"), style = MaterialTheme.typography.titleLarge)
                                            Text(LibraryNames.display(membership.library_id, words.zh), style = MaterialTheme.typography.bodyMedium,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                                            Text(words.membership(membership), color = MaterialTheme.colorScheme.primary)
                                            Button(onClick = { store.selectLibrary(membership.library_id) }, enabled = membership.available && !state.busy) { Text(t("Open library", "打开资料库")) }
                                        } }
                                    }
                                    item { key(state.generation) { InvitationForm(store, state, words) } }
                                }
                                state.familyTags?.selectedTag == null && state.familyTags != null -> {
                                    val family = state.familyTags!!
                                    item { TextButton(onClick = { store.loadPage(1) }, enabled = !state.busy) { Text(t("Back to Photos", "返回照片")) } }
                                    item { Text(t("Family note tags", "家庭笔记标签"), style = MaterialTheme.typography.headlineMedium, fontFamily = FontFamily.Serif) }
                                    item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                                        OutlinedTextField(familyTagQuery, { if (FamilyTagsWire.validQuery(it)) familyTagQuery = it },
                                            label = { Text(t("Search labels", "搜索标签")) }, singleLine = true,
                                            enabled = !state.busy, modifier = Modifier.weight(1f).testTag("family-tags-query"))
                                        Button(onClick = { store.openFamilyTags(familyTagQuery) }, enabled = !state.busy,
                                            modifier = Modifier.testTag("family-tags-search")) { Text(t("Search", "搜索")) }
                                    } }
                                    family.problem?.let { problem -> item { Text(words.message(problem.message), color = MaterialTheme.colorScheme.error) } }
                                    family.result?.let { result ->
                                        if (result.items.isEmpty()) item { Text(t("No accepted family note tags found.", "没有已采纳的家庭笔记标签。")) }
                                        items(result.items, key = { it.name }) { choice ->
                                            Card(onClick = { store.openFamilyTag(choice.name) }, enabled = !state.busy,
                                                modifier = Modifier.fillMaxWidth().testTag("family-tag-${result.items.indexOf(choice)}")) {
                                                Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween,
                                                    verticalAlignment = Alignment.CenterVertically) {
                                                    Text(choice.name, style = MaterialTheme.typography.titleMedium)
                                                    Text(t("${choice.assetCount} items", "${choice.assetCount} 项"), style = MaterialTheme.typography.bodyMedium)
                                                }
                                            }
                                        }
                                        item { FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.Center) {
                                            Text(if (result.total <= result.pageSize) t("${result.total} ${if (result.total == 1) "label" else "labels"}", "${result.total} 个标签")
                                                else t("Page ${result.page} · ${result.total} labels", "第 ${result.page} 页 · ${result.total} 个标签"))
                                            if (result.total > result.pageSize) {
                                                OutlinedButton(onClick = { store.navigatePage(result.page - 1) }, enabled = !state.busy && result.page > 1) { Text(t("Previous", "上一页")) }
                                                OutlinedButton(onClick = { store.navigatePage(result.page + 1) }, enabled = !state.busy && result.page.toLong() * result.pageSize < result.total) { Text(t("Next", "下一页")) }
                                            }
                                        } }
                                    }
                                }
                                state.familyTags?.selectedTag != null && state.detail == null -> {
                                    val family = state.familyTags!!
                                    item { TextButton(onClick = store::backToFamilyTags, enabled = !state.busy) { Text(t("Back to labels", "返回标签")) } }
                                    item { Text(family.selectedTag!!, style = MaterialTheme.typography.headlineMedium, fontFamily = FontFamily.Serif) }
                                    family.problem?.let { problem -> item { Text(words.message(problem.message), color = MaterialTheme.colorScheme.error) } }
                                    state.gallery?.let { gallery ->
                                        if (gallery.items.isEmpty()) item { Text(t("No items use this label.", "此标签下没有项目。")) }
                                        val columns = if (gallery.items.size == 1 || config.fontScale > 1.3f || config.screenWidthDp < 360) 1 else 2
                                        items(gallery.items.chunked(columns)) { row -> Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                            row.forEach { asset -> Card(onClick = { store.openMedia(asset) }, modifier = Modifier.weight(1f).testTag("family-tag-media-${asset.id}")) {
                                                Preview(asset, state.previews[asset.id], words)
                                                Column(Modifier.padding(start = 14.dp, end = 10.dp, top = 10.dp, bottom = 6.dp)) {
                                                    Text(words.date(asset), style = MaterialTheme.typography.titleSmall,
                                                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                                                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                                                        horizontalArrangement = Arrangement.SpaceBetween) {
                                                        Text(t("No. ${asset.id}", "编号 ${asset.id}"), style = MaterialTheme.typography.labelSmall,
                                                            color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                                                        TextButton(onClick = { store.openAsset(asset) }, modifier = Modifier.testTag("family-tag-details-${asset.id}")) { Text(t("Details", "详情")) }
                                                    }
                                                }
                                            } }
                                            if (row.size < columns) Spacer(Modifier.weight(1f))
                                        } }
                                        item { FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.Center) {
                                            Text(if (gallery.total <= gallery.page_size) t("${gallery.total} ${if (gallery.total == 1L) "item" else "items"}", "${gallery.total} 项")
                                                else t("Page ${gallery.page} · ${gallery.total} items", "第 ${gallery.page} 页 · ${gallery.total} 项"))
                                            if (gallery.total > gallery.page_size) {
                                                OutlinedButton(onClick = { store.navigatePage(gallery.page - 1) }, enabled = !state.busy && gallery.page > 1) { Text(t("Previous", "上一页")) }
                                                OutlinedButton(onClick = { store.navigatePage(gallery.page + 1) }, enabled = !state.busy && gallery.page.toLong() * gallery.page_size < gallery.total) { Text(t("Next", "下一页")) }
                                            }
                                        } }
                                    }
                                }
                                state.discovery?.editing == true -> phoneDiscoveryEditor(store, state, words.zh)
                                state.detail != null || state.photoNavigation != null -> {
                                    item { TextButton(onClick = store::backToPhotos) { Text(when {
                                        state.familyTags?.selectedTag != null -> t("Back to tagged items", "返回标签项目")
                                        state.photoNavigation?.discovery != null -> t("Back to results", "返回结果")
                                        else -> t("Back to Photos", "返回照片")
                                    }) } }
                                    state.detail?.let { detail ->
                                        item { Text(t("No. ${detail.asset.id}", "编号 ${detail.asset.id}"), style = MaterialTheme.typography.titleMedium) }
                                        item { Preview(detail.asset, state.previews[detail.asset.id], words, detail = true) }
                                    }
                                    state.photoNavigation?.let { navigation ->
                                        item { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                            Text(t("Photo ${navigation.index + 1} of ${navigation.assetIds.size} · Page ${navigation.page}", "第 ${navigation.page} 页 · 第 ${navigation.index + 1}/${navigation.assetIds.size} 张"))
                                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                                OutlinedButton(onClick = { store.adjacentPhoto(-1) }, enabled = !state.busy && navigation.index > 0) { Text(t("Previous photo", "上一张")) }
                                                OutlinedButton(onClick = { store.adjacentPhoto(1) }, enabled = !state.busy && navigation.index < navigation.assetIds.lastIndex) { Text(t("Next photo", "下一张")) }
                                            }
                                        } }
                                    }
                                    state.detail?.let { detail ->
                                    if (detail.asset.kind == "image" && store.photoDeliveryEnabled) item {
                                        Button(onClick = store::openDisplayPhoto, enabled = !state.busy) { Text(t("View photo", "查看照片")) }
                                    }
                                    if (detail.asset.kind == "image" && store.protectedNativeV2Enabled && !store.photoDeliveryEnabled) item {
                                        Button(onClick = store::openPreviewPhoto, enabled = !state.busy,
                                            modifier = Modifier.testTag("view-protected-preview")) { Text(t("View preview", "查看预览")) }
                                        Text(t("Preview quality. Full screen and zoom do not download the original.",
                                            "预览画质。全屏与缩放不会下载原始文件。"), style = MaterialTheme.typography.bodySmall)
                                    }
                                    if (detail.asset.kind == "image" && detail.originals_allowed) item {
                                        Button(onClick = store::openOriginalPhoto, enabled = !state.busy) { Text(t("Open original photo", "打开原始照片")) }
                                    }
                                    if (detail.asset.kind == "video" && (store.preparedVideoEnabled || detail.originals_allowed)) item {
                                        var videoNow by remember(state.problem) { mutableLongStateOf(System.currentTimeMillis()) }
                                        LaunchedEffect(state.problem) { while (videoNow < (state.problem?.retryAtMillis ?: 0)) { delay(500); videoNow = System.currentTimeMillis() } }
                                        val videoEnabled = !state.busy && videoNow >= (state.problem?.retryAtMillis ?: 0)
                                        Button(onClick = store::openVideo, enabled = videoEnabled, modifier = Modifier.testTag("open-video")) { Text(t("Open video", "打开视频")) }
                                        if (store.preparedVideoEnabled && state.busy) Text(t("Checking video availability…", "正在检查视频是否可播放…"))
                                        if (store.preparedVideoEnabled && detail.originals_allowed)
                                            TextButton(onClick = store::openOriginalVideo, enabled = videoEnabled, modifier = Modifier.testTag("open-original-video")) { Text(t("Open original video", "打开原始视频")) }
                                    }
                                    item { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Text(words.date(detail.asset), style = MaterialTheme.typography.titleLarge)
                                        Text(words.dateExplanation(detail.asset),
                                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        if (!detail.originals_allowed) Text(t("Original access is not permitted.", "无原始文件访问权限。"))
                                    } }
                                    if (store.protectedNativeV2Enabled) item {
                                        ProtectedStoriesPanel(state.stories, state.busy, words,
                                            load = store::loadStories, edit = store::editStory)
                                    }
                                    item { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                        HorizontalDivider(Modifier.padding(vertical = 12.dp))
                                        Text(t("Captions · AI unless marked edited", "描述 · 未标注编辑时为 AI 内容"), style = MaterialTheme.typography.titleMedium)
                                        Text(t("Caption language information is not supplied.", "未提供描述语言信息。"),
                                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    } }
                                    if (state.captions?.items.isNullOrEmpty()) item { Text(t("No captions yet", "暂无描述")) }
                                    items(state.captions?.items.orEmpty(), key = { it.id }) { caption ->
                                        Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                            Text(caption.text, style = MaterialTheme.typography.bodyLarge)
                                            if (caption.user_edited) Text(t("Edited", "已编辑"))
                                            if (caption.truncated) Text(t("Text truncated", "文本已截断"))
                                        } }
                                    }
                                    if (state.captions?.has_more == true) item { Text(t("More captions exist", "还有更多描述")) }
                                    }
                                }
                                else -> {
                                    item { Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                        Text(if (state.discovery != null) t("Search results", "搜索结果") else t("Your memories", "家庭相册"), style = MaterialTheme.typography.headlineMedium, fontFamily = FontFamily.Serif)
                                        Text(LibraryNames.display(state.library.orEmpty(), words.zh), style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    } }
                                    if (store.groupedStoryCreationAvailable) item {
                                        OutlinedButton(onClick = { store.beginGroupedStoryCreation() }, enabled = !state.busy,
                                            modifier = Modifier.fillMaxWidth().testTag("open-grouped-story-creation")) {
                                            Text(t("Create a story from these moments", "用照片和视频创建故事"))
                                        }
                                    }
                                    if (store.familyTagsEnabled && state.familyTags == null && state.discovery == null) item {
                                        OutlinedButton(onClick = { familyTagQuery = ""; store.openFamilyTags() }, enabled = !state.busy,
                                            modifier = Modifier.testTag("open-family-tags")) { Text(t("Family note tags", "家庭笔记标签")) }
                                    }
                                    if (store.mediaFilterEnabled && state.discovery == null) item {
                                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                            for (media in GalleryMedia.entries.filter { it != GalleryMedia.PREPARED_VIDEOS || store.preparedBrowseEnabled }) FilterChip(
                                                selected = state.media == media, onClick = { store.selectMedia(media) },
                                                modifier = Modifier.testTag("gallery-media-${media.wire}"), label = { Text(when(media) {
                                                    GalleryMedia.ALL -> t("All", "全部")
                                                    GalleryMedia.PHOTOS -> t("Photos", "照片")
                                                    GalleryMedia.VIDEOS -> t("Videos", "视频")
                                                    GalleryMedia.PREPARED_VIDEOS -> t("Prepared videos", "已准备视频")
                                                }) })
                                        }
                                    }
                                    item { Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                        state.gallery?.let { gallery -> Text(t("Page ${gallery.page} · ${gallery.total} items", "第 ${gallery.page} 页 · ${gallery.total} 项"),
                                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                                        FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                            TextButton(onClick = { lookupAsset = true }, modifier = Modifier.testTag("open-asset-lookup")) { Text(t("Open by number", "按编号打开")) }
                                            if (state.gallery?.let { it.total > it.page_size } == true) TextButton(onClick = { jumpPage = true }) { Text(t("Go to page", "跳转页面")) }
                                        }
                                    } }
                                    if (store.discoveryEnabled) item { FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Button(onClick = { if (state.discovery == null) store.openDiscovery() else store.editDiscovery() }, enabled = !state.busy,
                                            modifier = Modifier.testTag("open-discovery")) { Text(if (state.discovery == null) t("Find a memory", "寻找回忆") else t("Edit filters", "修改条件")) }
                                        if (state.discovery != null) TextButton(onClick = { store.loadPage(1) }, enabled = !state.busy) { Text(t("All photos", "全部照片")) }
                                    } }
                                    if (store.assistantEnabled) item {
                                        OutlinedButton(onClick = { assistantOpen = true }, enabled = !state.busy,
                                            modifier = Modifier.fillMaxWidth().testTag("open-assistant")) {
                                            Text(t("Ask the PhotoHouse assistant", "询问拾光相册助手"))
                                        }
                                    }
                                    state.gallery?.let { gallery ->
                                        if (gallery.items.isEmpty()) item { Text(t("No matching items on this page", "此页暂无符合条件的内容")) }
                                        val columns = if (gallery.items.size == 1 || config.fontScale > 1.3f || config.screenWidthDp < 360) 1 else 2
                                        items(gallery.items.chunked(columns)) { row -> Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                            row.forEach { asset -> Card(onClick = { store.openMedia(asset) }, modifier = Modifier.weight(1f).testTag("media-${asset.id}")) {
                                                Preview(asset, state.previews[asset.id], words)
                                                Column(Modifier.padding(start = 14.dp, end = 10.dp, top = 10.dp, bottom = 6.dp)) {
                                                    Text(words.date(asset), style = MaterialTheme.typography.titleSmall,
                                                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                                                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                                                        horizontalArrangement = Arrangement.SpaceBetween) {
                                                        Text(t("${if (asset.kind == "video") "Video" else "Photo"} · No. ${asset.id}",
                                                            "${if (asset.kind == "video") "视频" else "照片"} · 编号 ${asset.id}"),
                                                            style = MaterialTheme.typography.labelSmall,
                                                            color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                                                        TextButton(onClick = { store.openAsset(asset) }, modifier = Modifier.testTag("details-${asset.id}")) {
                                                            Text(t("Details", "详情"))
                                                        }
                                                    }
                                                }
                                            } }
                                            if (row.size < columns) Spacer(Modifier.weight(1f))
                                        } }
                                        item {
                                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                                if (gallery.total > gallery.page_size) {
                                                    OutlinedButton(onClick = { store.navigatePage(gallery.page - 1) }, enabled = !state.busy && gallery.page > 1) { Text(t("Previous", "上一页")) }
                                                    OutlinedButton(onClick = { store.navigatePage(gallery.page + 1) }, enabled = !state.busy && gallery.page < 100000 && gallery.page.toLong() * gallery.page_size < gallery.total) { Text(t("Next", "下一页")) }
                                                }
                                                OutlinedButton(onClick = { store.navigatePage(1) }, enabled = !state.busy) { Text(t("Refresh", "刷新")) }
                                                if (gallery.total > gallery.page_size) OutlinedButton(onClick = { jumpPage = true }, enabled = !state.busy) { Text(t("Go to page", "跳转页面")) }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable private fun AdmissionForm(store: ConnectedStore, state: LiveState, words: Words) {
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    var register by remember { mutableStateOf(false) }
    var rememberSession by remember { mutableStateOf(true) }
    val defaultPhone = ""
    var phone by remember { mutableStateOf(defaultPhone) }
    var password by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var now by remember(state.problem) { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(state.problem) { while (now < (state.problem?.retryAtMillis ?: 0)) { delay(500); now = System.currentTimeMillis() } }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(words.t(if (register) "Invited registration" else "Sign in", if (register) "受邀注册" else "登录"), style = MaterialTheme.typography.headlineSmall)
            Text(words.t(if (register) "Join your photo library with an invitation from its owner." else "Welcome back to your photo library.",
                if (register) "使用所有者发出的邀请，加入你的照片资料库。" else "欢迎回到你的照片资料库。"), color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (register && store.protectedNativeV2Enabled) OutlinedTextField(name,
                { if (it.length <= 512) name = it }, label = { Text(words.t("Your name", "你的名字")) },
                supportingText = { Text(words.t("How your family will see you · 1–64 characters", "家人看到的名字 · 1–64 个字符")) },
                singleLine = true, enabled = !state.busy, modifier = Modifier.fillMaxWidth().testTag("registration-name"))
            OutlinedTextField(phone, { if (it.length <= 32) phone = it }, label = { Text(words.t("Phone number", "手机号码")) },
                supportingText = { Text(if (store.protectedNativeV2Enabled) words.t("China (+86) is the default. Other countries: include + and country code.", "默认中国区号 +86。其他国家请填写 + 和国家区号。") else words.t("Include + and your country code.", "请填写 + 和国家区号。")) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone), singleLine = true, enabled = !state.busy, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(password, { if (it.codePointCount(0, it.length) <= 128) password = it }, label = { Text(if (store.protectedNativeV2Enabled) { if (register) words.t("Password (8–128 characters)", "密码（8–128 个字符）") else words.t("Password", "密码") } else words.t("Password (15–128 characters)", "密码（15–128 个字符）")) }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrect = false), visualTransformation = PasswordVisualTransformation(), singleLine = true, enabled = !state.busy, modifier = Modifier.fillMaxWidth())
            if (register) OutlinedTextField(code, { if (it.length <= 512) code = it }, label = { Text(words.t("Invitation code", "邀请码")) }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrect = false), visualTransformation = PasswordVisualTransformation(), singleLine = true, enabled = !state.busy, modifier = Modifier.fillMaxWidth())
            if (store.canRememberSession) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(rememberSession, { rememberSession = it }, enabled = !state.busy, modifier = Modifier.testTag("remember-session"))
                    Text(words.t("Remember sign-in on this device", "在此设备记住登录"))
                }
                Text(words.t("Encrypted on this device. Sign-in still expires after 24 hours; your password is never saved.",
                    "在此设备加密保存。登录仍会在 24 小时后过期，不保存密码。"), style = MaterialTheme.typography.bodySmall)
            }
            val valid = runCatching { Admission.phoneFromForm(phone, store.protectedNativeV2Enabled); Admission.password(password, protectedNativeV2 = store.protectedNativeV2Enabled, registration = register); if (register && store.protectedNativeV2Enabled) { Admission.displayName(name); Admission.invitationCode(code) }; !register || code.isNotBlank() }.getOrDefault(false)
            Button(onClick = { focus.clearFocus(); keyboard?.hide(); store.authenticate(Admission.phoneFromForm(phone, store.protectedNativeV2Enabled), password, if (register) code else null, if (register) name else null, remember = rememberSession); phone = defaultPhone; password = ""; code = ""; name = "" }, enabled = valid && !state.busy && now >= (state.problem?.retryAtMillis ?: 0), modifier = Modifier.fillMaxWidth()) { Text(words.t(if (register) "Register with invitation" else "Sign in", if (register) "使用邀请注册" else "登录")) }
            TextButton(onClick = { focus.clearFocus(); keyboard?.hide(); register = !register; phone = defaultPhone; password = ""; code = ""; name = "" }, enabled = !state.busy) { Text(words.t(if (register) "Already registered? Sign in" else "Have an invitation? Register", if (register) "已有账号？登录" else "收到邀请？注册")) }
            if (!valid) Text(words.t(
                if (register && store.protectedNativeV2Enabled) "Complete your name, phone, invitation and the password requirements above to register." else if (register) "Complete your phone, invitation and the password requirements above to register." else "Enter your phone and password to sign in.",
                if (register && store.protectedNativeV2Enabled) "请填写名字、手机号、邀请码，并满足上方密码要求后注册。" else if (register) "请填写手机号、邀请码，并满足上方密码要求后注册。" else "请填写手机号和密码后登录。"),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(words.t("Already registered on the website? Use Sign in here with the same phone and password.", "已在网页注册？请在这里选择登录，使用相同的手机号和密码。"),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable private fun InvitationForm(store: ConnectedStore, state: LiveState, words: Words) {
    var code by remember { mutableStateOf("") }
    OutlinedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(words.t("Join another library", "加入其他资料库"), style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(code, { if (it.length <= 512) code = it }, label = { Text(words.t("Invitation for another library", "其他资料库的邀请码")) }, singleLine = true, visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrect = false), modifier = Modifier.fillMaxWidth())
            Button(onClick = { store.acceptInvitation(code); code = "" }, enabled = code.isNotBlank() && !state.busy) { Text(words.t("Accept invitation", "接受邀请")) }
        }
    }
}

@Composable internal fun Preview(asset: Asset, bytes: ByteArray?, words: Words, detail: Boolean = false, modifier: Modifier = Modifier) {
    val image = remember(bytes) {
        bytes?.let {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(it, 0, it.size, bounds)
            if (bounds.outWidth in 1..1024 && bounds.outHeight in 1..1024) BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() else null
        }
    }
    val ratio = if (detail && image != null) (image.width.toFloat() / image.height).coerceIn(0.7f, 1.8f) else 4f / 3
    Box(modifier.fillMaxWidth().aspectRatio(ratio).clip(RoundedCornerShape(if (detail) 20.dp else 0.dp))
        .background(MaterialTheme.colorScheme.surfaceVariant), contentAlignment = Alignment.Center) {
        if (image == null) Text(words.t("Preview unavailable", "预览不可用"), Modifier.padding(20.dp),
            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        else Image(image, contentDescription = if (detail) words.t("Photo ${asset.id}", "照片 ${asset.id}") else null,
            contentScale = if (detail) ContentScale.Fit else ContentScale.Crop, modifier = Modifier.fillMaxSize())
        if (asset.kind == "video") Surface(Modifier.align(Alignment.TopStart).padding(12.dp),
            shape = RoundedCornerShape(8.dp), color = MaterialTheme.colorScheme.surface.copy(alpha = 0.95f)) {
            Text(words.t("Video", "视频"), Modifier.padding(horizontal = 10.dp, vertical = 6.dp), style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable internal fun PhotoHouseTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Color(0xFF365347), onPrimary = Color.White,
            primaryContainer = Color(0xFFDEE9DF), onPrimaryContainer = Color(0xFF203A2E),
            secondary = Color(0xFF705D49), onSecondary = Color.White,
            secondaryContainer = Color(0xFFEEE5D7), onSecondaryContainer = Color(0xFF493D2E),
            tertiary = Color(0xFF80603C), onTertiary = Color.White,
            tertiaryContainer = Color(0xFFF2E8D5), onTertiaryContainer = Color(0xFF503D24),
            background = Color(0xFFF7F5F0), onBackground = Color(0xFF252D28),
            surface = Color(0xFFFFFEFA), onSurface = Color(0xFF252D28),
            surfaceDim = Color(0xFFE3E0D7), surfaceBright = Color(0xFFFFFEFA),
            surfaceContainerLowest = Color(0xFFFFFFFF), surfaceContainerLow = Color(0xFFF6F4EE),
            surfaceContainer = Color(0xFFEFEFE8), surfaceContainerHigh = Color(0xFFE8EAE2),
            surfaceContainerHighest = Color(0xFFDFE3D9),
            surfaceVariant = Color(0xFFE8EAE2), onSurfaceVariant = Color(0xFF505C53),
            inverseSurface = Color(0xFF27352D), inverseOnSurface = Color(0xFFF5F1E8),
            inversePrimary = Color(0xFFBBD4C1),
            outline = Color(0xFF737C71), outlineVariant = Color(0xFFD7DDD2)
        ),
        shapes = Shapes(small = RoundedCornerShape(12.dp), medium = RoundedCornerShape(16.dp), large = RoundedCornerShape(24.dp)),
        content = content
    )
}


@OptIn(ExperimentalLayoutApi::class)
@Composable private fun ProtectedStoriesPanel(reading: StoryReading?, detailBusy: Boolean, words: Words, load: (Int) -> Unit, edit: (String?) -> Unit) {
    val t = words::t
    var expanded by remember(reading?.result) { mutableStateOf<String?>(null) }
    reading?.result?.items?.firstOrNull { it.id == expanded }?.let { story ->
        Dialog(onDismissRequest = { expanded = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            PhotoHouseTheme { Surface(Modifier.fillMaxSize().safeDrawingPadding(), color = MaterialTheme.colorScheme.background) {
                Column(Modifier.fillMaxSize().padding(horizontal = 22.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { expanded = null }, modifier = Modifier.testTag("story-reader-close")) {
                            Text(t("Close story", "返回回忆"))
                        }
                        if (story.canEdit) TextButton(onClick = { expanded = null; edit(story.id) }, enabled = !detailBusy,
                            modifier = Modifier.testTag("story-reader-edit")) { Text(t("Edit", "编辑")) }
                    }
                    Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(18.dp)) {
                        Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(t("FAMILY MEMORY", "家人回忆"), Modifier.testTag("story-reader-source"), style = MaterialTheme.typography.labelLarge,
                                color = MaterialTheme.colorScheme.onPrimaryContainer, letterSpacing = 1.2.sp)
                            Text(story.title.ifBlank { t("A family story", "家人的故事") }, Modifier.testTag("story-reader-title"), style = MaterialTheme.typography.headlineMedium,
                                fontFamily = FontFamily.Serif, color = MaterialTheme.colorScheme.onPrimaryContainer)
                            if (story.byline.isNotBlank()) {
                                Text(t("BYLINE · SELF SUPPLIED", "署名 · 自行填写"), style = MaterialTheme.typography.labelSmall,
                                    modifier = Modifier.testTag("story-reader-byline-label"),
                                    color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.78f))
                                Text(story.byline, Modifier.testTag("story-reader-byline"), style = MaterialTheme.typography.titleSmall,
                                    color = MaterialTheme.colorScheme.onPrimaryContainer)
                            }
                            Text(t("Attached to this photo or video", "属于这张照片或视频"), Modifier.testTag("story-reader-asset-note"), style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.78f))
                        }
                    }
                    val chunks = remember(story.text) {
                        buildList {
                            var offset = 0
                            while (offset < story.text.length) {
                                // Keep items short enough to scroll reliably, while ending on
                                // sentence or paragraph boundaries whenever the story allows.
                                val limit = minOf(offset + 220, story.text.length)
                                val stops = charArrayOf('\n', '。', '！', '？', '.', '!', '?')
                                val previousStop = story.text.lastIndexOfAny(stops, limit - 1)
                                val nextStop = if (previousStop < offset + 80 && limit < story.text.length)
                                    story.text.indexOfAny(stops, limit).takeIf { it >= 0 && it <= limit + 120 }
                                else null
                                var end = when {
                                    previousStop >= offset + 80 -> previousStop + 1
                                    nextStop != null -> nextStop + 1
                                    else -> limit
                                }
                                if (end < story.text.length && story.text[end - 1].isHighSurrogate()) end--
                                add(story.text.substring(offset, end)); offset = end
                            }
                        }
                    }
                    LazyColumn(Modifier.weight(1f).fillMaxWidth().testTag("story-reader"), verticalArrangement = Arrangement.spacedBy(10.dp),
                        contentPadding = PaddingValues(top = 6.dp, bottom = 28.dp)) {
                        items(chunks.size) { index -> Text(chunks[index], style = MaterialTheme.typography.bodyLarge.copy(lineHeight = 31.sp),
                            color = MaterialTheme.colorScheme.onBackground) }
                    }
                }
            } }
        }
    }
    var now by remember(reading?.problem) { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(reading?.problem) {
        while (now < (reading?.problem?.retryAtMillis ?: 0)) { delay(500); now = System.currentTimeMillis() }
    }
    Column(Modifier.fillMaxWidth().testTag("protected-stories"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        HorizontalDivider()
        Text(t("Family stories", "家人的故事"), style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif)
        Text(t("Memories written by your family, kept separate from AI descriptions.", "家人亲笔记录的回忆，与 AI 描述分开呈现。"),
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (reading == null) {
            OutlinedButton(onClick = { load(1) }, enabled = !detailBusy, modifier = Modifier.testTag("stories-open")) {
                Text(t("Stories & memories", "故事与回忆"))
            }
        } else if (reading.busy) {
            LinearProgressIndicator(Modifier.fillMaxWidth())
            Text(t("Loading stories…", "正在加载故事…"))
        } else {
            reading.problem?.let { error ->
                Text(words.message(error.message), color = MaterialTheme.colorScheme.error)
                OutlinedButton(onClick = { load(reading.page) },
                    enabled = !detailBusy && now >= error.retryAtMillis, modifier = Modifier.testTag("stories-retry")) {
                    Text(t("Try again", "重试"))
                }
            }
            reading.result?.let { result ->
                if (result.canCreate) Button(onClick = { edit(null) }, enabled = !detailBusy,
                    modifier = Modifier.testTag("story-add")) { Text(t("Add a memory", "添加回忆")) }
                if (result.items.isEmpty()) Text(t("No family stories on this page yet.", "此页暂无家人的故事。"))
                result.items.forEach { story ->
                    Card(Modifier.fillMaxWidth().testTag("story-${story.id}")) {
                        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text(t("Family memory", "家人回忆"), color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelLarge)
                            if (story.title.isNotEmpty()) Text(story.title, style = MaterialTheme.typography.titleMedium)
                            if (story.canEdit) TextButton(onClick = { edit(story.id) }, enabled = !detailBusy,
                                modifier = Modifier.testTag("story-edit-${story.id}")) { Text(t("Edit memory", "编辑回忆")) }
                            if (story.byline.isNotEmpty()) Text(story.byline, style = MaterialTheme.typography.labelMedium)
                            if (story.text.length <= 2000) Text(story.text, style = MaterialTheme.typography.bodyLarge)
                            else {
                                Text(story.text.take(240) + "…", style = MaterialTheme.typography.bodyLarge)
                                TextButton(onClick = { expanded = story.id }, modifier = Modifier.testTag("story-read-full")) {
                                    Text(t("Read full story", "阅读全文"))
                                }
                            }
                        }
                    }
                }
                Text(t("Story page ${result.page}", "故事第 ${result.page} 页"))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { load(result.page - 1) }, enabled = !detailBusy && result.page > 1,
                        modifier = Modifier.testTag("stories-previous")) { Text(t("Previous", "上一页")) }
                    OutlinedButton(onClick = { load(result.page + 1) }, enabled = !detailBusy && result.hasMore && result.page < 100000,
                        modifier = Modifier.testTag("stories-next")) { Text(t("Next", "下一页")) }
                    TextButton(onClick = { load(1) }, enabled = !detailBusy, modifier = Modifier.testTag("stories-refresh")) {
                        Text(t("Refresh", "刷新"))
                    }
                }
                Text(t("Stories can change while you browse. Refresh to see the latest. Review your words before saving.",
                    "浏览期间故事可能更新，可刷新查看。保存前请检查你的文字。"), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
