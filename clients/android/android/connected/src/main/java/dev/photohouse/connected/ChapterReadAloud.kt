package dev.photohouse.connected

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import java.nio.charset.StandardCharsets
import java.util.concurrent.atomic.AtomicLong

internal enum class ReaderAudioKind { RECORDING, SPEECH, PLAYBACK }

internal class ReaderAudioCoordinator {
    internal class Lease internal constructor(val id: Long, val kind: ReaderAudioKind, internal val stop: () -> Unit)
    private var active: Lease? = null
    private val ids = AtomicLong()
    @Synchronized fun acquire(kind: ReaderAudioKind, stopCurrent: () -> Unit): Lease? {
        val owner = active
        if (owner?.kind == ReaderAudioKind.RECORDING) return null
        if (owner != null) { active = null; runCatching { owner.stop() } }
        return Lease(ids.incrementAndGet(), kind, stopCurrent).also { active = it }
    }
    @Synchronized fun release(lease: Lease?) { if (lease != null && active?.id == lease.id) active = null }
    @Synchronized fun isOwned(lease: Lease?): Boolean = lease != null && active?.id == lease.id
}

internal val LocalReaderAudioCoordinator = staticCompositionLocalOf<ReaderAudioCoordinator?> { null }

internal fun narrationChunks(text: String, maxCodePoints: Int = 180, maxChunkBytes: Int = 720, maxTotalCodePoints: Int = 6400): List<String> {
    require(maxCodePoints > 0 && maxChunkBytes > 0 && maxTotalCodePoints > 0)
    val source = text.trim()
    require(source.codePointCount(0, source.length) <= maxTotalCodePoints) { "chapter text exceeds narration limit" }
    require(source.toByteArray(StandardCharsets.UTF_8).size <= 25_600) { "chapter text exceeds narration byte limit" }
    val cps = source.codePoints().toArray()
    val result = mutableListOf<String>()
    var offset = 0
    while (offset < cps.size) {
        var end = offset; var bytes = 0
        while (end < cps.size && end - offset < maxCodePoints) {
            val width = String(Character.toChars(cps[end])).toByteArray(StandardCharsets.UTF_8).size
            if (bytes + width > maxChunkBytes) break
            bytes += width; end++
        }
        require(end > offset) { "narration chunk cannot fit one code point" }
        var split = end
        if (end < cps.size) {
            val punctuation = (offset until end).lastOrNull { Character.toChars(cps[it]).concatToString() in "。！？；，.!?;,:\n" }
            if (punctuation != null && punctuation - offset + 1 >= (end - offset) / 2) split = punctuation + 1
        }
        result += buildString { for (i in offset until split) appendCodePoint(cps[i]) }.trim()
        offset = split
        while (offset < cps.size && Character.isWhitespace(cps[offset])) offset++
    }
    return result.filter(String::isNotBlank)
}

internal fun selectOfflineVoice(voices: Set<Voice>, language: String): Voice? {
    if (language !in setOf("zh", "en")) return null
    return voices.asSequence().filter { it.locale.language == language }
        .filterNot { it.isNetworkConnectionRequired }
        .filterNot { TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED in it.features.orEmpty() }
        .sortedBy { it.name }.firstOrNull()
}

internal interface ChapterSpeechAdapter {
    fun initialize(done: (Boolean, Set<Voice>) -> Unit)
    fun setVoice(voice: Voice): Boolean
    fun speak(text: String, id: String, done: (String) -> Unit, failed: (String) -> Unit)
    fun stop()
    fun shutdown()
}
internal fun interface ChapterSpeechAdapterFactory { fun create(context: Context): ChapterSpeechAdapter }
internal val LocalChapterSpeechAdapterFactory = staticCompositionLocalOf<ChapterSpeechAdapterFactory> { AndroidChapterSpeechAdapterFactory }
private object AndroidChapterSpeechAdapterFactory : ChapterSpeechAdapterFactory {
    override fun create(context: Context): ChapterSpeechAdapter = AndroidChapterSpeechAdapter(context.applicationContext)
}
private class AndroidChapterSpeechAdapter(private val context: Context) : ChapterSpeechAdapter {
    private val main = Handler(Looper.getMainLooper())
    private var engine: TextToSpeech? = null
    override fun initialize(done: (Boolean, Set<Voice>) -> Unit) {
        engine = TextToSpeech(context) { status -> main.post {
            // Resolve after the constructor has assigned engine; some implementations
            // can deliver onInit synchronously from TextToSpeech(...).
            val tts = engine
            val voices = runCatching { tts?.voices }.getOrNull()
            val ready = status == TextToSpeech.SUCCESS && tts != null && voices != null
            done(ready, if (ready) voices.orEmpty() else emptySet())
        } }
    }
    override fun setVoice(voice: Voice): Boolean = engine?.setVoice(voice) == TextToSpeech.SUCCESS
    override fun speak(text: String, id: String, done: (String) -> Unit, failed: (String) -> Unit) {
        val tts = engine
        if (tts == null) { main.post { failed(id) }; return }
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) = Unit
            override fun onDone(utteranceId: String?) { utteranceId?.let { value -> main.post { done(value) } } }
            @Suppress("DEPRECATION")
            override fun onError(utteranceId: String?) { utteranceId?.let { value -> main.post { failed(value) } } }
            override fun onError(utteranceId: String?, errorCode: Int) { utteranceId?.let { value -> main.post { failed(value) } } }
        })
        val params = Bundle().apply { putString(TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID, id) }
        if (tts.speak(text, TextToSpeech.QUEUE_FLUSH, params, id) != TextToSpeech.SUCCESS) main.post { failed(id) }
    }
    override fun stop() { engine?.stop() }
    override fun shutdown() {
        val old = engine; engine = null
        runCatching { old?.stop() }
        runCatching { old?.shutdown() }
    }
}

internal interface ChapterAudioFocus { fun request(onLost: () -> Unit): Boolean; fun abandon() }
internal fun interface ChapterAudioFocusFactory { fun create(context: Context): ChapterAudioFocus }
private object AndroidChapterAudioFocusFactory : ChapterAudioFocusFactory {
    override fun create(context: Context): ChapterAudioFocus = AndroidChapterAudioFocus(context.applicationContext)
}
internal val LocalChapterAudioFocusFactory = staticCompositionLocalOf<ChapterAudioFocusFactory> { AndroidChapterAudioFocusFactory }
private class AndroidChapterAudioFocus(context: Context) : ChapterAudioFocus {
    private val manager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var request: AudioFocusRequest? = null
    override fun request(onLost: () -> Unit): Boolean {
        val attrs = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()
        val listener = AudioManager.OnAudioFocusChangeListener { change -> if (change != AudioManager.AUDIOFOCUS_GAIN) onLost() }
        val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT).setAudioAttributes(attrs)
            .setWillPauseWhenDucked(true).setOnAudioFocusChangeListener(listener, Handler(Looper.getMainLooper())).build()
        request = focus
        return manager.requestAudioFocus(focus) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
    }
    override fun abandon() { request?.let(manager::abandonAudioFocusRequest); request = null }
}

internal class ChapterReadAloudController(
    private val context: Context, text: String, private val language: String, private val coordinator: ReaderAudioCoordinator,
    private val adapterFactory: ChapterSpeechAdapterFactory, private val focusFactory: ChapterAudioFocusFactory,
) {
    val status = mutableStateOf("idle")
    private val main = Handler(Looper.getMainLooper())
    private val chunks = runCatching { narrationChunks(text) }.getOrDefault(emptyList())
    private var generation = 0L
    private var adapter: ChapterSpeechAdapter? = null
    private var focus: ChapterAudioFocus? = null
    private var lease: ReaderAudioCoordinator.Lease? = null
    private var chunkIndex = 0
    private var activeUtterance: String? = null
    private var closed = false
    fun start() {
        check(Looper.myLooper() == Looper.getMainLooper())
        if (closed || chunks.isEmpty() || status.value == "loading" || status.value == "speaking") return
        chunkIndex = 0
        begin(preserveChunk = false)
    }
    fun pause() {
        check(Looper.myLooper() == Looper.getMainLooper())
        if (closed || status.value != "speaking") return
        // TTS has no position-resume API. Keep the current bounded chunk and replay it on resume.
        stopWith("paused", preserveChunk = true)
    }
    fun resume() {
        check(Looper.myLooper() == Looper.getMainLooper())
        if (closed || chunks.isEmpty() || status.value !in setOf("paused", "paused_busy")) return
        begin(preserveChunk = true)
    }
    private fun begin(preserveChunk: Boolean) {
        val run = ++generation
        val speechLease = coordinator.acquire(ReaderAudioKind.SPEECH) { stop() }
        if (speechLease == null) {
            status.value = if (preserveChunk) "paused_busy" else "busy"
            return
        }
        lease = speechLease
        val audioFocus = runCatching { focusFactory.create(context) }.getOrElse { stopWith("failed"); return }
        focus = audioFocus
        val focusGranted = runCatching { audioFocus.request { main.post { if (isCurrent(run)) stopWith("focus") } } }.getOrDefault(false)
        if (!focusGranted) { stopWith("focus"); return }
        val player = runCatching { adapterFactory.create(context) }.getOrElse { stopWith("failed"); return }
        adapter = player
        if (!preserveChunk) chunkIndex = 0
        activeUtterance = null; status.value = "loading"
        val initialized = runCatching { player.initialize { ok, voices -> main.post {
                if (!isCurrent(run, player)) { runCatching { player.shutdown() }; return@post }
                val voice = if (ok) selectOfflineVoice(voices, language) else null
                val selected = voice != null && runCatching { player.setVoice(voice) }.getOrDefault(false)
                if (!selected) { stopWith("unavailable"); return@post }
                status.value = "speaking"; speakNext(run, player)
            } }
        }.isSuccess
        if (!initialized) stopWith("failed")
    }
    private fun speakNext(run: Long, player: ChapterSpeechAdapter) {
        if (!isCurrent(run, player)) return
        val index = chunkIndex
        if (index >= chunks.size) { stopWith("done"); return }
        val id = "$run:$index"; activeUtterance = id
        val accepted = runCatching { player.speak(chunks[index], id, done = { callback -> main.post {
            if (isCurrent(run, player) && activeUtterance == id && callback == id) {
                activeUtterance = null; chunkIndex = index + 1; speakNext(run, player)
            }
        } }, failed = { callback -> main.post {
            if (isCurrent(run, player) && activeUtterance == id && callback == id) stopWith("failed")
        } }) }.isSuccess
        if (!accepted && isCurrent(run, player)) stopWith("failed")
    }
    private fun isCurrent(run: Long, player: ChapterSpeechAdapter? = adapter): Boolean =
        !closed && generation == run && player != null && adapter === player && coordinator.isOwned(lease)
    fun stop() = stopWith("idle")
    private fun stopWith(nextStatus: String, preserveChunk: Boolean = false) {
        if (Looper.myLooper() != Looper.getMainLooper()) { main.post { stopWith(nextStatus, preserveChunk) }; return }
        generation++
        val old = adapter; adapter = null
        runCatching { old?.stop() }
        runCatching { old?.shutdown() }
        activeUtterance = null
        runCatching { focus?.abandon() }; focus = null
        coordinator.release(lease); lease = null
        if (!preserveChunk) chunkIndex = 0
        status.value = nextStatus
    }
    fun close() {
        if (Looper.myLooper() != Looper.getMainLooper()) { main.post { close() }; return }
        closed = true
        stopWith("idle")
    }
}

internal data class ChapterReadAloudLabels(
    val read: String,
    val stop: String,
    val tagPrefix: String,
    val languageNotice: String? = null,
    val tooLong: String? = null,
    val done: String? = null,
    val pause: String? = null,
    val resume: String? = null,
    val resumeChunkNotice: String? = null,
    val pausedBusyNotice: String? = null,
)

@Composable
@OptIn(ExperimentalLayoutApi::class)
internal fun ChapterReadAloud(
    text: String, language: String, scopeKey: Any, zh: Boolean, enabled: Boolean = true,
    labels: ChapterReadAloudLabels? = null,
) {
    val context = LocalContext.current
    val coordinator = checkNotNull(LocalReaderAudioCoordinator.current)
    val adapterFactory = LocalChapterSpeechAdapterFactory.current
    val focusFactory = LocalChapterAudioFocusFactory.current
    val lifecycleOwner = LocalLifecycleOwner.current
    // Include the full text and language so a reused row can never keep a controller
    // whose immutable utterance snapshot belongs to an earlier reply.
    val snapshotKey = remember(scopeKey, text, language) { Any() }
    val controller = remember(snapshotKey) { ChapterReadAloudController(context, text, language, coordinator, adapterFactory, focusFactory) }
    val status by controller.status
    DisposableEffect(snapshotKey, controller, lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_PAUSE || event == Lifecycle.Event.ON_STOP) controller.stop() }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer); controller.close() }
    }
    val chunksPresent = remember(snapshotKey, text) { runCatching { narrationChunks(text).isNotEmpty() }.getOrDefault(false) }
    val tag = labels?.tagPrefix ?: if (scopeKey.toString().contains("memoir")) "memory-book-narration" else "saved-memory-narration"
    val t = { en: String, cn: String -> if (zh) cn else en }
    val active = status == "speaking" || status == "loading"
    val paused = status == "paused" || status == "paused_busy"
    FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Button(onClick = when (status) {
            "speaking" -> controller::pause
            "paused", "paused_busy" -> controller::resume
            "loading" -> controller::stop
            else -> controller::start
        }, enabled = chunksPresent && (active || enabled), modifier = Modifier.testTag("$tag-toggle")) {
            Text(when (status) {
                "speaking" -> labels?.pause ?: t("Pause reading", "暂停朗读")
                "paused", "paused_busy" -> labels?.resume ?: t("Resume reading", "继续朗读")
                "loading" -> labels?.stop ?: t("Stop reading", "停止朗读")
                else -> labels?.read ?: t("Read aloud", "朗读本章")
            })
        }
        if (status == "speaking" || paused) TextButton(onClick = controller::stop,
            modifier = Modifier.testTag("$tag-stop")) { Text(labels?.stop ?: t("Stop reading", "停止朗读")) }
        if (paused) Text(labels?.resumeChunkNotice ?: t(
            "Resume restarts the current short segment; part of it may repeat.",
            "继续朗读会从当前短句开头重读，可能重复一小段内容。"), modifier = Modifier.testTag("$tag-paused-notice"))
        if (status == "paused_busy") Text(labels?.pausedBusyNotice ?: t(
            "Recording is active. Finish it, then choose Resume.", "录音正在进行。结束录音后，请手动选择继续朗读。"),
            color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("$tag-paused-busy"))
        labels?.languageNotice?.let { Text(it, style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("$tag-language-notice")) }
        if (status == "unavailable") Text(t("Installed offline voice unavailable.", "没有可用的本地离线语音。"), color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("$tag-unavailable"))
        if (status == "busy") Text(t("Finish audio recording before reading.", "请先结束录音再朗读。"), color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("$tag-busy"))
        if (status == "focus") Text(t("Audio focus was interrupted.", "其他音频打断了朗读。"), color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("$tag-focus"))
        if (status == "failed") Text(t("Reading stopped after an audio error.", "朗读遇到问题，已停止。"), color = MaterialTheme.colorScheme.error,
            modifier = Modifier.testTag("$tag-failed"))
        if (status == "done") Text(labels?.done ?: t("Finished reading this chapter.", "本章朗读完毕。"), modifier = Modifier.testTag("$tag-done"))
        if (text.isNotBlank() && !chunksPresent) Text(labels?.tooLong ?: t("This chapter is too long to read aloud.", "本章内容过长，无法朗读。"),
            color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("$tag-too-long"))
    }
}
