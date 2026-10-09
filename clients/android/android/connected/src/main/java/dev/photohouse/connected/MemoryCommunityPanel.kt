package dev.photohouse.connected

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.photohouse.connected.core.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.text.SimpleDateFormat
import java.text.NumberFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

internal fun memoryAudioDurationText(durationMs: Long?, zh: Boolean): String? {
    if (durationMs == null || durationMs <= 0) return null
    val number = NumberFormat.getNumberInstance(if (zh) Locale.SIMPLIFIED_CHINESE else Locale.ENGLISH).apply {
        maximumFractionDigits = 1
        minimumFractionDigits = 0
        isGroupingUsed = false
    }.format(durationMs / 1000.0)
    return if (zh) "$number 秒" else "$number sec"
}

private fun memoryConversationLabel(createdAt: Long, zh: Boolean): String {
    // Wire timestamps are Unix seconds. Tiny synthetic fixtures intentionally fall back
    // to a neutral label instead of presenting an epoch date as conversation metadata.
    if (createdAt !in 946_684_800L..4_102_444_800L) return if (zh) "对话" else "Chat"
    val locale = if (zh) Locale.SIMPLIFIED_CHINESE else Locale.getDefault()
    val pattern = if (zh) "yyyy/M/d HH:mm:ss" else "M/d/yyyy h:mm:ss a"
    return SimpleDateFormat(pattern, locale).format(Date(createdAt * 1000))
}

@Composable
private fun MemoryConversationChipLabel(createdAt: Long, firstMessagePreview: String?, zh: Boolean) {
    Column(
        modifier = Modifier.widthIn(max = 240.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(memoryConversationLabel(createdAt, zh), maxLines = 1, overflow = TextOverflow.Ellipsis)
        if (!firstMessagePreview.isNullOrEmpty()) {
            Text(firstMessagePreview, style = MaterialTheme.typography.bodySmall,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
    }
}

/** Preserve complete words and controls while separating the two speakers. */
@Composable
private fun MemoryChatMessageBubble(
    user: Boolean,
    tag: String,
    content: @Composable ColumnScope.() -> Unit,
) {
    Box(Modifier.fillMaxWidth(), contentAlignment = if (user) Alignment.CenterEnd else Alignment.CenterStart) {
        Surface(
            modifier = Modifier.fillMaxWidth(if (user) 0.94f else 1f).testTag(tag),
            color = if (user) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceContainerLow,
            contentColor = if (user) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurface,
            shape = MaterialTheme.shapes.large,
        ) {
            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content)
        }
    }
}

private fun hasActiveMemoryChatJob(job: MemoryJob?, turns: MemoryTurnPage?): Boolean =
    job?.state in setOf("queued", "running") || turns?.items?.any { it.state in setOf("queued", "running") } == true

private fun hasUnfinishedMemoryDictation(state: MemoryDictationState?): Boolean =
    state?.let { it.loading || it.recording || it.transcribing || it.transcript != null } == true

private data class StoryChatReplyJobBinding(val conversationId: String?, val jobId: String?, val rejectedJobId: String? = null)

internal fun replySpeechLanguage(sourceLanguage: String, uiZh: Boolean): Pair<String, Boolean> {
    val normalized = sourceLanguage.trim().lowercase(Locale.ROOT)
    val base = normalized.substringBefore('-').substringBefore('_')
    return when (base) {
        "zh", "en" -> base to false
        "", "mixed", "und" -> (if (uiZh) "zh" else "en") to true
        else -> base to false
    }
}

private fun replyReadAloudLabels(sourceLanguage: String, zh: Boolean, tagPrefix: String): Pair<String, ChapterReadAloudLabels> {
    val language = replySpeechLanguage(sourceLanguage, zh)
    val t = { en: String, cn: String -> if (zh) cn else en }
    val notice = if (!language.second) null else if (zh)
        "内容语言是混合或未标注，将按当前界面语言（中文）朗读。"
    else "The reply language is mixed or unspecified; it will use the current app language (English)."
    return language.first to ChapterReadAloudLabels(
        read = t("Read reply", "朗读回复"), stop = t("Stop reading", "停止朗读"), tagPrefix = tagPrefix,
        languageNotice = notice,
        tooLong = t("This reply is too long for local reading; the full text remains available.",
            "回复过长，无法使用本地语音完整朗读；原文仍可查看。"),
        done = t("Finished reading this reply.", "回复朗读完毕。"),
        pause = t("Pause reply", "暂停回复朗读"), resume = t("Resume reply", "继续回复朗读"),
        resumeChunkNotice = t("Resume restarts the current short segment; part of it may repeat.",
            "继续朗读会从当前短句开头重读，可能重复一小段内容。"),
        pausedBusyNotice = t("Recording is active. Finish it, then choose Resume.",
            "录音正在进行。结束录音后，请手动选择继续朗读。"),
    )
}

private fun storyReplySourceLabels(
    sourceIds: List<String>, story: SavedMemoryStory, community: MemoryCommunityStoryState?, zh: Boolean,
): List<String> = sourceIds.map { sourceId ->
    val evidence = story.items.asSequence().flatMap { it.evidence.asSequence() }.firstOrNull { it.id == sourceId }
    val loadedContributions = community?.contributions?.takeIf { it.storyId == story.id }?.items.orEmpty()
    val selectedContribution = community?.selectedContribution?.receipt?.contribution
        ?.takeIf { it.storyId == story.id }
    val matchingContribution = (loadedContributions + listOfNotNull(selectedContribution)).firstOrNull {
        sourceId == "contribution-${it.id}" && it.state == "accepted" && it.baseStoryRevision == story.revision
    }
    when {
        story.chapters.any { sourceId == "editorial-${story.id}-${it.id}" } -> if (zh) "故事整理文字" else "Story editorial text"
        matchingContribution?.kind == "text" -> if (zh) "家人提供的文字" else "Family-provided text"
        matchingContribution?.kind == "audio" -> if (zh) "家人录音 · AI 转写" else "Family recording · AI transcript"
        evidence?.source == "family" -> if (zh) "家人提供的回忆" else "Family-provided memory"
        evidence?.source == "ai" -> if (zh) "AI 观察 · 需核实" else "AI observation · review"
        else -> if (zh) "来源尚未加载" else "Source not loaded"
    }
}

private fun memoirReplySourceLabels(
    sourceIds: List<String>, reading: MemoryBooksReading, zh: Boolean,
): List<String> {
    val book = reading.selectedBook
    val story = reading.story
    return sourceIds.map { sourceId ->
        val evidence = story?.items?.asSequence()?.flatMap { it.evidence.asSequence() }?.firstOrNull { it.id == sourceId }
        when {
            book != null && sourceId == "editorial-book-${book.id}" -> if (zh) "回忆册说明" else "Memoir introduction"
            story != null && story.chapters.any { sourceId == "editorial-${story.id}-${it.id}" } -> if (zh) "故事整理文字" else "Story editorial text"
            evidence?.source == "family" -> if (zh) "家人提供的回忆" else "Family-provided memory"
            evidence?.source == "ai" -> if (zh) "AI 观察 · 需核实" else "AI observation · review"
            else -> if (zh) "来源尚未加载" else "Source not loaded"
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun ReplyContextControls(
    tagPrefix: String, context: MemoryReplyContext, sourceLabels: List<String>, enabled: Boolean,
    zh: Boolean, clarification: Boolean, onChoose: (String) -> MemoryChatFollowupResult,
) {
    var expanded by remember(tagPrefix) { mutableStateOf(false) }
    var status by remember(tagPrefix) { mutableStateOf("") }
    val t = { en: String, cn: String -> if (zh) cn else en }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(3.dp)) {
        if (clarification) {
            Text(t("AI would like to know more", "AI 想再了解一点"),
                style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.testTag("$tagPrefix-clarification"))
            Text(if (context.questions.isEmpty())
                t("Add the missing detail in your own words. Review your message before sending.",
                    "可以用自己的话补充细节，检查消息后再发送。")
                else t("Add details in your own words, or choose a question below as an editable draft. Send when ready.",
                    "可以用自己的话补充细节，也可以选下面的问题作为可编辑草稿，准备好后再发送。"),
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("$tagPrefix-clarification-help"))
        }
        if (context.questions.isNotEmpty()) {
            Text(t("Suggested follow-up questions", "还可以这样问"), style = MaterialTheme.typography.labelMedium)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(2.dp),
                modifier = Modifier.fillMaxWidth().testTag("$tagPrefix-questions")) {
                context.questions.forEachIndexed { index, question ->
                    AssistChip(onClick = {
                        status = when (onChoose(question)) {
                            MemoryChatFollowupResult.SELECTED -> ""
                            MemoryChatFollowupResult.BLOCKED -> t(
                                "Finish the current draft, voice input, or chat task first.",
                                "请先处理当前草稿、语音输入或对话任务。",
                            )
                            MemoryChatFollowupResult.STALE -> t(
                                "This reply changed. Refresh the conversation and try again.",
                                "这条回复已变化，请刷新对话后重试。",
                            )
                        }
                    }, enabled = enabled, label = { Text(question) },
                        modifier = Modifier.testTag("$tagPrefix-question-$index"))
                }
            }
        }
        if (context.sourceIds.isNotEmpty()) {
            TextButton(onClick = { expanded = !expanded }, modifier = Modifier.testTag("$tagPrefix-sources-toggle")) {
                Text(if (expanded) t("Hide references", "收起参考线索") else
                    t("Show references · ${context.sourceIds.size}", "查看参考线索 · ${context.sourceIds.size}"))
            }
            if (expanded) {
                Column(Modifier.fillMaxWidth().testTag("$tagPrefix-sources"), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    sourceLabels.forEach { label -> Text("• $label", style = MaterialTheme.typography.bodySmall) }
                    Text(t("Loaded labels identify materials available in this reader; they do not verify the reply as factual.",
                        "已加载标签只说明本阅读器当前可用的材料；不代表回复已核实为事实。"), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        if (status.isNotEmpty()) Text(status, color = MaterialTheme.colorScheme.error,
            style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("$tagPrefix-status"))
    }
}

/** Test seam for the UI's capture lifecycle; production uses the shared native recorder unchanged. */
internal interface MemoryContributionCapture {
    val recordedMillis: Int
    val wasDiscarded: Boolean
    fun record(): ByteArray?
    fun stop()
    fun discard()
}

internal fun interface MemoryContributionCaptureFactory {
    fun begin(): MemoryContributionCapture
}

internal val LocalMemoryContributionCaptureFactory = staticCompositionLocalOf<MemoryContributionCaptureFactory> {
    DefaultMemoryContributionCaptureFactory
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun MemoryCommunityPanel(store: ConnectedStore, reading: SavedMemoryStoriesReading, zh: Boolean) {
    val live by store.state.collectAsState()
    val detail = reading.detail ?: return
    val community = reading.community
    val t = { en: String, cn: String -> if (zh) cn else en }
    Column(Modifier.fillMaxWidth().testTag("memory-community-panel"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (!store.memoryCommunityAvailable) return@Column
        if (community == null || community.busy && community.capabilities == null) {
            LinearProgressIndicator(Modifier.fillMaxWidth())
            Text(t("Checking family memory features…", "正在检查家庭回忆功能…"))
            return@Column
        }
        val caps = community.capabilities
        if (caps == null || !caps.enabled) {
            Text(t("Family contributions and story chat are unavailable on this server.", "此服务器暂未开放家人分享和故事对话。"),
                style = MaterialTheme.typography.bodyMedium)
            return@Column
        }
        FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)) {
            listOf(t("Family memories", "共同讲述"), t("Story chat", "聊聊故事"),
                t("Draft suggestions", "整理建议")).forEachIndexed { index, label ->
                FilterChip(selected = community.tab == index, onClick = { store.selectMemoryCommunityTab(index) },
                    enabled = (!community.contributionAudioBusy || community.tab == index) && (index != 2 || reading.detail?.canEdit == true),
                    label = { Text(label) }, modifier = Modifier.testTag("memory-community-tab-$index"))
            }
        }
        if (community.failure != null) {
            Text(communityMessage(community.failure!!, zh), color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag("memory-community-failure"))
        }
        if (community.busy) LinearProgressIndicator(Modifier.fillMaxWidth().testTag("memory-community-loading"))
        val generation = live.generation
        when (community.tab) {
            0 -> if (!caps.contributionsEnabled) {
                Text(t("Family contributions are turned off.", "家人分享功能已关闭。"))
            } else ContributionsPanel(store, reading.library, detail.id, detail.revision, generation,
                community.readerScopeId, community, live.session?.displayName, zh)
            1 -> if (!caps.generationEnabled) {
                Text(t("Story chat is turned off.", "故事对话功能已关闭。"))
            } else StoryChatPanel(store, reading.library, detail, detail.revision, generation,
                community.readerScopeId, detail.language, community, zh)
            2 -> if (!caps.generationEnabled) {
                Text(t("Story suggestions are turned off.", "整理建议功能已关闭。"))
            } else if (reading.detail?.canEdit != true) {
                Text(t("Only story editors can prepare a narrative draft.", "只有故事编辑者可以整理叙事草稿。"),
                    modifier = Modifier.testTag("memory-narrative-viewer-only"))
            } else NarrativePanel(store, reading, community, zh)
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun ContributionsPanel(
    store: ConnectedStore, library: String, storyId: String, revision: Long, generation: Long, readerScopeId: Long,
    community: MemoryCommunityStoryState, accountDisplayName: String?, zh: Boolean,
) {
    val t = { en: String, cn: String -> if (zh) cn else en }
    val textFocusRequester = remember { FocusRequester() }
    LaunchedEffect(community.contributionFocusRequestId, community.tab) {
        if (community.tab == 0 && community.contributionFocusRequestId > 0) textFocusRequester.requestFocus()
    }
    val text = community.contributionDraft
    val consent = community.contributionConsent
    val audioConsent = community.audioConsent
    val language = community.contributionLanguage
    val wholeStory = community.contributionWholeStory
    val canChangeScope = !community.busy && !community.contributionAudioBusy && !community.chatTurnContributionSeeded &&
        community.pendingText == null && community.pendingAudio == null
    Text(t("Share a memory with this story. Processing original words or audio is optional.",
        "为这个故事分享一段回忆。是否处理原话或录音由你选择。"), style = MaterialTheme.typography.bodySmall)
    Text(t("One shared memory can cover all media in this story. Choose the current chapter for a narrower scope.",
        "一段分享可以涵盖这个故事中的所有媒体；也可以选择当前篇章，缩小分享范围。"),
        style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("memory-contribution-scope-description"))
    FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        FilterChip(selected = wholeStory, onClick = { store.updateMemoryContributionWholeStory(true) },
            enabled = canChangeScope, label = { Text(t("Entire story", "整个故事")) },
            modifier = Modifier.testTag("memory-contribution-scope-whole-story"))
        FilterChip(selected = !wholeStory, onClick = { store.updateMemoryContributionWholeStory(false) },
            enabled = canChangeScope, label = { Text(t("Current chapter", "当前篇章")) },
            modifier = Modifier.testTag("memory-contribution-scope-current-chapter"))
    }
    if (community.chatTurnContributionSeeded) Text(
        t("This memory kept from story chat belongs to the entire story.", "这段从故事聊天保留的回忆属于整个故事。"),
        style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("memory-contribution-chat-scope"))
    OutlinedTextField(value = text, onValueChange = store::updateMemoryContributionDraft,
        label = { Text(t("Your words", "想分享的话")) }, minLines = 3, maxLines = 6,
        modifier = Modifier.fillMaxWidth().focusRequester(textFocusRequester).testTag("memory-contribution-text"))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(t("Language", "语言"))
        listOf("zh", "en", "mixed").forEach { code ->
            FilterChip(selected = language == code, onClick = { store.updateMemoryContributionLanguage(code) }, label = {
                Text(when (code) { "zh" -> "中文"; "en" -> "English"; else -> t("Mixed", "混合") })
            })
        }
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = consent, onCheckedChange = { store.updateMemoryContributionConsent(textConsent = it) }, modifier = Modifier.testTag("memory-contribution-consent"))
        Text(t("Allow server processing to prepare a transcript and draft. The original remains until the owner deletes it.",
            "允许服务器处理并准备转写和草稿。原始内容会保留，直到所有者删除。"), style = MaterialTheme.typography.bodySmall)
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = { store.submitMemoryText(text, language,
            accountDisplayName?.takeIf { it.isNotBlank() } ?: if (zh) "家人" else "Family member", consent) },
            enabled = text.isNotBlank() && !community.busy && community.pendingText == null,
            modifier = Modifier.testTag("memory-contribution-submit")) { Text(t("Share text", "分享文字")) }
        if (community.pendingText != null && community.failure != null) {
            OutlinedButton(onClick = store::retryMemoryText, enabled = !community.busy,
                modifier = Modifier.testTag("memory-contribution-retry")) { Text(t("Retry same submission", "重试这次提交")) }
        }
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = audioConsent, onCheckedChange = { store.updateMemoryContributionConsent(audioConsent = it) }, modifier = Modifier.testTag("memory-audio-consent"))
        Text(t("I also allow processing this recording", "我也同意处理这段录音"), style = MaterialTheme.typography.bodySmall)
    }
    val audioActivityId = remember(library, storyId, revision, generation, readerScopeId) { UUID.randomUUID().toString() }
    MemoryContributionAudioInput(library, community.storyId, zh, language, audioConsent,
        accountDisplayName?.takeIf { it.isNotBlank() } ?: if (zh) "家人" else "Family member",
        enabled = !community.busy && community.pendingAudio == null,
        onActivityChanged = { busy -> store.setMemoryContributionAudioBusy(
            library, storyId, revision, generation, readerScopeId, audioActivityId, busy,
        ) },
        onAudio = { wav, currentLanguage, byline, currentConsent ->
            store.submitMemoryAudio(wav, currentLanguage, byline, currentConsent)
        })
    if (community.pendingAudio != null) {
        Text(if (zh) "上一段录音尚未提交完成，请先重试同一段录音。" else "Your previous recording is still pending. Retry that same submission before recording another.",
            style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("memory-audio-retry-needed"))
    }
    if (community.pendingAudio != null && community.failure != null) {
        OutlinedButton(onClick = store::retryMemoryAudio, enabled = !community.busy,
            modifier = Modifier.testTag("memory-audio-retry")) { Text(t("Retry same recording", "重试这段录音")) }
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Text(t("Family contributions", "家人分享"), style = MaterialTheme.typography.titleMedium, fontFamily = FontFamily.Serif)
        TextButton(onClick = store::reloadMemoryContributions, enabled = !community.busy,
            modifier = Modifier.testTag("memory-contributions-refresh")) { Text(t("Refresh", "刷新")) }
    }
    val page = community.contributions
    if (page == null) Text(t("No contributions to show yet.", "暂时没有可显示的家人分享。"))
    page?.items?.forEach { item ->
        Card(onClick = { store.loadMemoryContribution(item.id) }, modifier = Modifier.fillMaxWidth()
            .testTag("memory-contribution-${item.id}")) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(if (item.kind == "audio") t("Voice memory", "语音回忆") else item.text.orEmpty(),
                    style = MaterialTheme.typography.bodyLarge, maxLines = 4, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                Text("${item.byline} · ${when (item.state) { "pending" -> t("Needs review", "待审核"); "accepted" -> t("Accepted", "已接受"); else -> t("Declined", "已婉拒") }}",
                    style = MaterialTheme.typography.labelMedium)
            }
        }
    }
    page?.let {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { store.loadMemoryContributionPage(it.page - 1) }, enabled = !community.busy && it.page > 1,
                modifier = Modifier.testTag("memory-contributions-previous")) { Text(t("Previous", "上一页")) }
            Text(t("Page ${it.page}", "第 ${it.page} 页"), modifier = Modifier.testTag("memory-contributions-page"))
            TextButton(onClick = { store.loadMemoryContributionPage(it.page + 1) }, enabled = !community.busy && it.hasMore,
                modifier = Modifier.testTag("memory-contributions-next")) { Text(t("Next", "下一页")) }
        }
    }
    community.selectedContribution?.let { detail ->
        val contribution = detail.receipt.contribution
        HorizontalDivider()
        Text(t("Contribution details", "分享详情"), style = MaterialTheme.typography.titleSmall)
        if (contribution.kind == "audio") {
            val duration = memoryAudioDurationText(contribution.durationMs, zh)
            Text(t("Original voice recording", "原始语音录音") + (duration?.let { " · $it" } ?: ""))
            OutlinedButton(onClick = store::playMemoryContributionAudio, enabled = !community.busy,
                modifier = Modifier.testTag("memory-audio-play")) { Text(t("Load original audio", "加载原始录音")) }
            community.audio?.let { AnnotationAudioPlayback(it, zh) }
        } else Text(contribution.text.orEmpty(), modifier = Modifier.testTag("memory-original-text"))
        detail.derivation?.let { derivation ->
            Text(t("Processing · ${derivation.state}", "处理状态 · ${derivation.state}"), style = MaterialTheme.typography.labelLarge)
            derivation.transcript?.takeIf { it.isNotBlank() }?.let { Text("${t("Transcript", "转写")}\n$it") }
            derivation.polishedText?.takeIf { it.isNotBlank() }?.let { Text("${t("Draft for review", "待检查草稿")}\n$it") }
            derivation.errorCode?.let { Text(t("Processing could not finish.", "处理未能完成。"), color = MaterialTheme.colorScheme.error) }
        }
        if (detail.receipt.canReview && contribution.state == "pending") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { store.reviewMemoryContribution(true) }, enabled = !community.busy,
                    modifier = Modifier.testTag("memory-contribution-accept")) { Text(t("Accept", "接受")) }
                OutlinedButton(onClick = { store.reviewMemoryContribution(false) }, enabled = !community.busy,
                    modifier = Modifier.testTag("memory-contribution-decline")) { Text(t("Decline", "婉拒")) }
            }
        }
    }
}

@Composable
internal fun MemoryContributionAudioInput(
    library: String, storyId: String, zh: Boolean, language: String, consent: Boolean, byline: String,
    enabled: Boolean, onActivityChanged: (Boolean) -> Unit, onAudio: (ByteArray, String, String, Boolean) -> Unit,
) {
    key(library, storyId) {
        AudioContributionRecorder(zh, language, consent, byline, enabled, onActivityChanged, onAudio)
    }
}

@Composable
private fun AudioContributionRecorder(
    zh: Boolean, language: String, consent: Boolean, byline: String, enabled: Boolean,
    onActivityChanged: (Boolean) -> Unit, onAudio: (ByteArray, String, String, Boolean) -> Unit,
) {
    val context = LocalContext.current
    val audioCoordinator = LocalReaderAudioCoordinator.current
    val factory = LocalMemoryContributionCaptureFactory.current
    val recorder = remember(factory) { AnnotationAudioRecorder() }
    var capture by remember { mutableStateOf<MemoryContributionCapture?>(null) }
    var audioLease by remember { mutableStateOf<ReaderAudioCoordinator.Lease?>(null) }
    var draft by remember { mutableStateOf<ByteArray?>(null) }
    var permissionDenied by remember { mutableStateOf(false) }
    var permissionRequestActive by remember { mutableStateOf(false) }
    var audioBusy by remember { mutableStateOf(false) }
    var elapsed by remember { mutableIntStateOf(0) }
    val currentLanguage by rememberUpdatedState(language)
    val currentConsent by rememberUpdatedState(consent)
    val currentByline by rememberUpdatedState(byline)
    val currentEnabled by rememberUpdatedState(enabled)
    val currentActivityCallback by rememberUpdatedState(onActivityChanged)
    val lifecycleOwner = LocalLifecycleOwner.current
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        permissionDenied = !granted
        if (granted && permissionRequestActive && currentEnabled) capture = beginCapture(factory, recorder)
        else { audioCoordinator?.release(audioLease); audioLease = null }
        if (capture == null) { audioCoordinator?.release(audioLease); audioLease = null }
        permissionRequestActive = false
    }
    fun clearDraft() { draft?.fill(0); draft = null }
    LaunchedEffect(capture, draft, permissionRequestActive) {
        currentActivityCallback(capture != null || draft != null || permissionRequestActive)
    }
    DisposableEffect(recorder, lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) {
                permissionRequestActive = false
                capture?.discard(); capture = null
                audioCoordinator?.release(audioLease); audioLease = null
                clearDraft()
                currentActivityCallback(false)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            permissionRequestActive = false
            capture?.discard(); capture = null
            audioCoordinator?.release(audioLease); audioLease = null
            recorder.stop()
            clearDraft()
            currentActivityCallback(false)
        }
    }
    LaunchedEffect(capture) {
        val current = capture ?: return@LaunchedEffect
        val currentLease = audioLease
        val captureJob = currentCoroutineContext()[Job]
        val resultLock = Any()
        var abandoned = false
        var wav: ByteArray? = null
        try {
            withContext(Dispatchers.IO) {
                val result = current.record()
                synchronized(resultLock) {
                    if (abandoned || captureJob?.isActive != true) result?.fill(0)
                    else wav = result
                }
            }
            // The callback can beat LaunchedEffect cancellation after ON_STOP. The
            // main-thread attempt identity closes that gap before publishing audio.
            if (capture === current && !current.wasDiscarded && wav != null && wav!!.size in 46..(2 * 1024 * 1024)) {
                clearDraft()
                draft = wav
                wav = null
            }
        } catch (cancelled: CancellationException) {
            synchronized(resultLock) { abandoned = true; wav?.fill(0); wav = null }
            current.discard(); throw cancelled
        } finally {
            wav?.fill(0); current.stop(); if (capture === current) capture = null
            audioCoordinator?.release(currentLease)
            if (audioLease?.id == currentLease?.id) audioLease = null
        }
    }
    LaunchedEffect(capture) {
        while (capture != null) { elapsed = capture?.recordedMillis ?: 0; delay(100) }
    }
    when {
        capture != null -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (zh) "录音中 ${elapsed / 1000}/30 秒" else "Recording ${elapsed / 1000}/30 sec",
                modifier = Modifier.testTag("memory-audio-recording"))
            Button(onClick = { capture?.stop() }, enabled = elapsed >= 500 || (capture?.recordedMillis ?: 0) >= 500,
                modifier = Modifier.testTag("memory-audio-stop")) { Text(if (zh) "停止录音" else "Stop recording") }
            TextButton(onClick = { capture?.discard(); capture = null; currentActivityCallback(false) }) { Text(if (zh) "取消" else "Cancel") }
        }
        draft != null -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(if (zh) "录音已就绪 · ${if (consent) "允许处理" else "不允许处理"}" else "Recording ready · ${if (consent) "processing allowed" else "processing not allowed"}",
                modifier = Modifier.testTag("memory-audio-draft"))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = {
                    val ready = draft ?: return@Button
                    draft = null
                    onAudio(ready, currentLanguage, currentByline, currentConsent)
                }, enabled = enabled, modifier = Modifier.testTag("memory-audio-share")) {
                    Text(if (zh) "分享录音" else "Share recording")
                }
                TextButton(onClick = { clearDraft(); currentActivityCallback(false) }, modifier = Modifier.testTag("memory-audio-discard")) {
                    Text(if (zh) "丢弃录音" else "Discard recording")
                }
            }
        }
        else -> OutlinedButton(onClick = {
            permissionDenied = false
            if (audioCoordinator != null && audioLease == null) {
                val candidate = audioCoordinator.acquire(ReaderAudioKind.RECORDING) { capture?.discard(); capture = null }
                if (candidate == null) { audioBusy = true; return@OutlinedButton }
                audioLease = candidate
            }
            audioBusy = false
            if (factory !== DefaultMemoryContributionCaptureFactory ||
                context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
                capture = beginCapture(factory, recorder).also { if (it != null) currentActivityCallback(true) }
            else { permissionRequestActive = true; currentActivityCallback(true); permission.launch(Manifest.permission.RECORD_AUDIO) }
            if (capture == null && !permissionRequestActive) { audioCoordinator?.release(audioLease); audioLease = null }
        }, enabled = enabled && !permissionRequestActive, modifier = Modifier.testTag("memory-audio-record")) {
            Text(if (zh) "录音分享（最长 30 秒）" else "Record audio (up to 30 sec)")
        }
    }
    if (permissionDenied) Text(if (zh) "未获得麦克风权限。" else "Microphone permission was denied.",
        color = MaterialTheme.colorScheme.error)
    if (audioBusy) Text(if (zh) "请先结束其他阅读音频，再开始录音。" else "Finish other reader audio before recording.",
        color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("memory-audio-busy"))
}

private fun beginCapture(factory: MemoryContributionCaptureFactory, recorder: AnnotationAudioRecorder): MemoryContributionCapture? =
    runCatching {
        if (factory !== DefaultMemoryContributionCaptureFactory) factory.begin()
        else NativeMemoryContributionCapture(recorder.beginCapture(30))
    }.getOrNull()

private object DefaultMemoryContributionCaptureFactory : MemoryContributionCaptureFactory {
    override fun begin(): MemoryContributionCapture = error("Native recorder is created with its owning composable")
}

internal fun canReplaceComposerWithReplyQuestion(value: TextFieldValue): Boolean =
    value.composition == null && value.text.isBlank()

private class NativeMemoryContributionCapture(private val capture: AnnotationAudioRecorder.Capture) : MemoryContributionCapture {
    override val recordedMillis: Int get() = capture.recordedMillis
    override val wasDiscarded: Boolean get() = capture.wasDiscarded
    override fun record(): ByteArray? = capture.record()
    override fun stop() = capture.stop()
    override fun discard() = capture.discard()
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun StoryChatPanel(
    store: ConnectedStore, library: String, detail: SavedMemoryStory, revision: Long, generation: Long, readerScopeId: Long, storyLanguage: String,
    community: MemoryCommunityStoryState, zh: Boolean,
) {
    val t = { en: String, cn: String -> if (zh) cn else en }
    val live by store.state.collectAsState()
    val composerFocusRequester = remember { FocusRequester() }
    var composerValue by remember(library, generation, readerScopeId, community.storyId, revision, community.conversationId) {
        mutableStateOf(TextFieldValue(community.chatDraft, selection = TextRange(community.chatDraft.length)))
    }
    var draftRejected by remember(library, generation, readerScopeId, community.storyId, revision, community.conversationId) {
        mutableStateOf(false)
    }
    val accountId = live.session?.account_id.orEmpty()
    var handledFocusRequest by remember(library, generation, readerScopeId, community.storyId, revision, community.conversationId) {
        mutableIntStateOf(community.chatDraftFocusRequestId)
    }
    LaunchedEffect(community.chatDraft, community.chatDraftFocusRequestId) {
        if (community.chatDraftFocusRequestId != handledFocusRequest) {
            handledFocusRequest = community.chatDraftFocusRequestId
            composerValue = TextFieldValue(community.chatDraft, selection = TextRange(community.chatDraft.length))
            draftRejected = false
            composerFocusRequester.requestFocus()
        } else if (composerValue.composition == null && composerValue.text != community.chatDraft) {
            composerValue = TextFieldValue(community.chatDraft, selection = TextRange(community.chatDraft.length))
            draftRejected = false
        }
    }
    var dictation by remember(community.storyId) { mutableStateOf(community.dictation) }
    val dictationState = dictation?.state?.collectAsState(initial = MemoryDictationState())?.value
    var transcriptLimit by remember(library, generation, readerScopeId, community.storyId, revision,
        community.conversationId, dictation) { mutableStateOf(false) }
    var jobBindingInitialized by remember(readerScopeId) { mutableStateOf(false) }
    var jobBinding by remember(readerScopeId) { mutableStateOf(StoryChatReplyJobBinding(community.conversationId, null)) }
    LaunchedEffect(community.conversationId, community.job?.id, community.turns?.conversationId,
        community.turns?.items?.map { it.jobId }) {
        val selectedConversation = community.conversationId
        val jobId = community.job?.id
        val pageMatches = community.turns?.conversationId == selectedConversation
        val pageRepresentsJob = pageMatches && community.turns?.items?.any { it.jobId == jobId } == true
        when {
            !jobBindingInitialized -> {
                jobBindingInitialized = true
                jobBinding = StoryChatReplyJobBinding(selectedConversation, jobId.takeIf { pageRepresentsJob },
                    jobId.takeUnless { pageRepresentsJob })
            }
            selectedConversation != jobBinding.conversationId ->
                jobBinding = StoryChatReplyJobBinding(selectedConversation, jobId.takeIf { pageRepresentsJob },
                    jobId.takeUnless { pageRepresentsJob })
            jobId == null -> jobBinding = StoryChatReplyJobBinding(selectedConversation, null)
            pageRepresentsJob -> jobBinding = StoryChatReplyJobBinding(selectedConversation, jobId)
            jobBinding.rejectedJobId == jobId -> Unit
            jobBinding.jobId == null -> jobBinding = StoryChatReplyJobBinding(selectedConversation, jobId)
            jobBinding.jobId != jobId -> jobBinding = StoryChatReplyJobBinding(selectedConversation, jobId)
        }
    }
    val canChangeThread = !community.busy && community.pendingTurn == null && community.pendingConversation == null &&
        !hasActiveMemoryChatJob(community.job, community.turns) && !hasUnfinishedMemoryDictation(dictationState)
    community.conversations?.items?.let { conversations ->
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
            conversations.forEachIndexed { index, row ->
                FilterChip(selected = row.id == community.conversationId,
                    onClick = { store.selectMemoryConversation(row.id) }, enabled = canChangeThread,
                    label = { MemoryConversationChipLabel(row.createdAt, row.firstMessagePreview, zh) },
                    modifier = Modifier.testTag("memory-chat-thread-$index"))
            }
            TextButton(onClick = store::startMemoryConversation, enabled = canChangeThread,
                modifier = Modifier.testTag("memory-chat-new")) { Text(t("New chat", "新对话")) }
        }
    }
    if (community.conversationRestored) Text(
        t("Back in the conversation you last selected.", "已回到上次选择的对话。"),
        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.testTag("memory-chat-restored").semantics { liveRegion = LiveRegionMode.Polite })
    if (community.conversationId == null) {
        Text(t("Start a private conversation about this story.", "开始一段只围绕这个故事的对话。"))
        Button(onClick = store::startMemoryConversation, enabled = canChangeThread,
            modifier = Modifier.testTag("memory-chat-start")) { Text(t("Start story chat", "开始聊聊故事")) }
        if (community.pendingConversation != null && community.failure != null) {
            OutlinedButton(onClick = store::retryStartMemoryConversation, modifier = Modifier.testTag("memory-chat-start-retry")) {
                Text(t("Retry same chat", "重试创建对话"))
            }
        }
        return
    }
    community.turns?.items?.forEach { turn ->
        var seedStatus by remember(community.storyId, community.conversationId, turn.id) { mutableStateOf("") }
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            MemoryChatMessageBubble(user = true, tag = "memory-chat-user-bubble-${turn.id}") {
                Text(t("YOU", "你"), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.testTag("memory-chat-user-speaker-${turn.id}"))
                Text(turn.inputText, style = MaterialTheme.typography.bodyLarge)
                if (community.capabilities?.contributionsEnabled == true && turn.inputText.isNotBlank()) {
                    TextButton(onClick = {
                        seedStatus = when (store.keepMemoryChatTurnAsContribution(
                            library, community.storyId, revision, generation, readerScopeId,
                            community.conversationId ?: return@TextButton, turn.id,
                        )) {
                            MemoryChatTurnSeedResult.SEEDED -> ""
                            MemoryChatTurnSeedResult.BLOCKED -> t(
                                "Finish or discard the existing memory draft or recording, then finish the current chat task and try again.",
                                "请先完成或丢弃现有回忆草稿或录音，再等待当前对话任务结束后重试。",
                            )
                            MemoryChatTurnSeedResult.STALE -> t(
                                "This story conversation changed. Refresh it and try again.",
                                "这段故事对话已变化，请刷新后重试。",
                            )
                        }
                    }, modifier = Modifier.testTag("memory-chat-keep-turn-${turn.id}")) {
                        Text(t("Keep my words as a memory", "把这句话留作回忆"))
                    }
                    if (seedStatus.isNotEmpty()) Text(seedStatus, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.testTag("memory-chat-keep-turn-status-${turn.id}"))
                }
            }
            MemoryChatMessageBubble(user = false, tag = "memory-chat-assistant-bubble-${turn.id}") {
                turn.replyText?.let { reply ->
                    Text(t("STORY COMPANION", "故事助手"), style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.testTag("memory-chat-assistant-speaker-${turn.id}"))
                    Text(reply, style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.testTag("memory-chat-reply"))
                    val replyContext = if (turn.state == "ready") memoryReplyContext(turn, community.job, revision) else null
                    if (replyContext != null && (turn.replyKind == "clarification" || replyContext.questions.isNotEmpty() || replyContext.sourceIds.isNotEmpty())) {
                        val canChooseQuestion = canReplaceComposerWithReplyQuestion(composerValue) &&
                            !community.busy && community.pendingConversation == null && community.pendingTurn == null &&
                            community.pendingText == null && community.pendingAudio == null && community.pendingNarrative == null &&
                            !community.contributionAudioBusy && !hasActiveMemoryChatJob(community.job, community.turns) &&
                            !hasUnfinishedMemoryDictation(dictationState)
                        ReplyContextControls("memory-chat-followup-${turn.sequence}", replyContext,
                            storyReplySourceLabels(replyContext.sourceIds, detail, community, zh), canChooseQuestion, zh,
                            clarification = turn.replyKind == "clarification") { question ->
                            if (!canReplaceComposerWithReplyQuestion(composerValue)) MemoryChatFollowupResult.BLOCKED
                            else store.chooseMemoryChatFollowup(
                                accountId, generation, library, readerScopeId, community.storyId, revision,
                                community.conversationId.orEmpty(), community.turns?.page ?: -1, turn.id, question)
                        }
                    }
                    val speechScope = listOf("story-chat", live.session?.account_id, generation, library,
                        readerScopeId, community.storyId, revision, community.conversationId, turn.id, turn.jobId, reply)
                    val (speechLanguage, labels) = replyReadAloudLabels(
                        storyLanguage, zh, "memory-chat-reply-reading-${turn.id}")
                    ChapterReadAloud(reply, speechLanguage, speechScope, zh, enabled = !community.busy, labels = labels)
                } ?: Text(memoirTurnStatus(turn.state, zh), style = MaterialTheme.typography.labelMedium)
            }
        }
    }
    community.turns?.let { page ->
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(if (page.page == 1) t("Latest messages", "最新消息") else t("Earlier messages · page ${page.page}", "更早的消息 · 第 ${page.page} 页"),
                modifier = Modifier.align(Alignment.CenterHorizontally).testTag("memory-chat-page"))
            FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                TextButton(onClick = { store.loadMemoryTurnsPage(page.page - 1) }, enabled = !community.busy && page.page > 1,
                    modifier = Modifier.testTag("memory-chat-previous")) { Text(t("Newer messages", "较新的消息")) }
                TextButton(onClick = { store.loadMemoryTurnsPage(page.page + 1) }, enabled = !community.busy && page.hasMore && page.page < 8,
                    modifier = Modifier.testTag("memory-chat-next")) { Text(t("Older messages", "更早的消息")) }
            }
        }
    }
    community.job?.let { job ->
        val representedByTurn = community.turns?.let { page ->
            page.conversationId == community.conversationId && page.items.any { it.jobId == job.id }
        } == true
        val boundToSelectedConversation = jobBinding.conversationId == community.conversationId && jobBinding.jobId == job.id
        if (boundToSelectedConversation || representedByTurn) {
            Text(when (job.state) {
                "ready" -> t("Reply ready · Review before using", "回复已生成 · 使用前请检查")
                "failed" -> t("Reply could not be prepared.", "暂时无法生成回复。")
                "stale" -> t("The story changed. Start a fresh turn.", "故事内容已变化，请重新提问。")
                else -> memoirJobStatus(job.state, zh)
            }, modifier = Modifier.testTag("memory-chat-job-state"))
            val jobReply = job.result?.get("reply")?.jsonPrimitive?.contentOrNull
            if (boundToSelectedConversation && !representedByTurn) jobReply?.let { reply ->
                Text(t("STORY COMPANION", "故事助手"), style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary, modifier = Modifier.testTag("memory-chat-assistant-speaker-job"))
                Text(reply, modifier = Modifier.testTag("memory-chat-reply"))
                val speechScope = listOf("story-chat-job", live.session?.account_id, generation, library,
                    readerScopeId, community.storyId, revision, community.conversationId, job.id, reply)
                val (speechLanguage, labels) = replyReadAloudLabels(
                    storyLanguage, zh, "memory-chat-job-reply-reading-${job.id}")
                ChapterReadAloud(reply, speechLanguage, speechScope, zh, enabled = !community.busy, labels = labels)
            }
            val proposal = parseStoryProposal(job.result?.get("proposal"))
            if (proposal != null && job.kind == "chat" && job.state == "ready" && community.storyId == detail.id) {
                val canBindOriginals = job.baseRevision == revision && (boundToSelectedConversation || representedByTurn)
                StoryProposalReview(
                    tagPrefix = "memory-chat-proposal-${job.id}", readerScopeId = readerScopeId,
                    story = detail.takeIf { it.id == community.storyId }, community = community,
                    job = job, proposal = proposal, bindOriginals = canBindOriginals, zh = zh,
                )
                Text(t("This AI proposal is for review only; it has not been applied or saved.",
                    "这份 AI 建议仅供核对，尚未应用或保存。"), modifier = Modifier.testTag("memory-chat-proposal-review-only"))
            }
        }
    }
    val storyTurnPage = community.turns
    val storyChatNeedsRefresh = storyTurnPage == null || community.job?.state in setOf("queued", "running") ||
        storyTurnPage.items.any { it.state in setOf("queued", "running") }
    if (community.conversationId != null && storyChatNeedsRefresh) TextButton(onClick = store::refreshMemoryChat,
        enabled = !community.busy, modifier = Modifier.testTag("memory-chat-refresh")) {
        Text(t("Refresh messages and reply", "刷新消息和回复"))
    }
    Text(t(
        "Replies use this story's materials, your question, and up to 7 earlier exchanges. Older messages stay readable but are not included automatically; add important background to your question.",
        "回复参考当前故事材料、当前问题和此前最多 7 轮对话。更早消息可查看但不自动带入；重要背景请补充到问题中。",
    ), style = MaterialTheme.typography.bodySmall, modifier = Modifier.fillMaxWidth().testTag("memory-chat-context-window"))
    OutlinedTextField(value = composerValue, onValueChange = { value ->
        composerValue = value
        draftRejected = !store.updateMemoryChatDraft(value.text)
    },
        label = { Text(t("Ask about this story", "聊聊这个故事")) }, minLines = 2, maxLines = 5, enabled = !community.busy,
        isError = draftRejected,
        supportingText = if (draftRejected) ({
            Text(t("This message exceeds the draft limit. Shorten it before sending.",
                "这条消息超出草稿长度限制，请缩短后再发送。"),
                modifier = Modifier.testTag("memory-chat-draft-limit").semantics { liveRegion = LiveRegionMode.Polite })
        }) else null,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text), modifier = Modifier.fillMaxWidth()
            .focusRequester(composerFocusRequester).testTag("memory-chat-input"))
    if (dictation == null) TextButton(onClick = { dictation = store.memoryCommunityDictation() },
        enabled = store.assistantEnabled, modifier = Modifier.testTag("memory-chat-enable-dictation")) {
        Text(t("Add voice input", "使用语音输入"))
    }
    dictation?.let { speech -> MemoryDictationInput(speech, zh, onInsert = {
        val current = store.state.value
        val latestReading = current.savedMemoryStories ?: return@MemoryDictationInput
        val latestDetail = latestReading.detail ?: return@MemoryDictationInput
        val latestChat = latestReading.community ?: return@MemoryDictationInput
        if (current.library != library || current.generation != generation || latestReading.library != library ||
            latestDetail.id != community.storyId || latestDetail.revision != revision ||
            latestChat.readerScopeId != readerScopeId || latestChat.storyId != community.storyId ||
            latestChat.conversationId != community.conversationId || latestChat.dictation !== speech) return@MemoryDictationInput
        val transcript = speech.state.value.transcript ?: return@MemoryDictationInput
        val joined = listOf(latestChat.chatDraft, transcript).filter { it.isNotBlank() }.joinToString("\n")
        if (joined.toByteArray(Charsets.UTF_8).size > 4096) {
            transcriptLimit = true
            return@MemoryDictationInput
        }
        if (speech.takeTranscript() == null) return@MemoryDictationInput
        store.updateMemoryChatDraft(joined)
        transcriptLimit = false
    }, purpose = MemoryDictationPurpose.CHAT_MESSAGE) }
    if (transcriptLimit) Text(t("The edited transcript was kept. Shorten it or the draft to fit 4,096 bytes.",
        "已保留编辑后的转写。请缩短转写或草稿，使合计不超过 4,096 字节。"), color = MaterialTheme.colorScheme.error,
        modifier = Modifier.testTag("memory-chat-dictation-limit"))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = store::sendMemoryChat, enabled = !draftRejected && composerValue.text == community.chatDraft &&
            !community.busy && (community.conversationId == null || community.turns != null) && community.pendingTurn == null &&
            !hasActiveMemoryChatJob(community.job, community.turns) && !hasUnfinishedMemoryDictation(dictationState) && community.chatDraft.isNotBlank(),
            modifier = Modifier.testTag("memory-chat-send")) { Text(t("Send", "发送")) }
        if (community.pendingTurn != null && community.failure != null) OutlinedButton(onClick = store::retryMemoryChatTurn,
            enabled = !community.busy, modifier = Modifier.testTag("memory-chat-retry")) { Text(t("Retry same message", "重试这条消息")) }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class, ExperimentalFoundationApi::class)
internal fun MemoryBookCompanionPanel(store: ConnectedStore, reading: MemoryBooksReading, zh: Boolean) {
    val t = { en: String, cn: String -> if (zh) cn else en }
    if (!store.memoryCommunityAvailable) return
    if (reading.capabilities?.generationEnabled != true) {
        Text(t("Memoir conversations are turned off.", "回忆册对话功能尚未开放。"),
            Modifier.fillMaxWidth().testTag("memory-book-chat-disabled"))
        return
    }
    val chat = reading.companion ?: return
    val live by store.state.collectAsState()
    val language = reading.selectedBook?.language ?: "und"
    val dictationState = chat.dictation?.state?.collectAsState(initial = MemoryDictationState())?.value
    val bookComposerFocusRequester = remember { FocusRequester() }
    val bookComposerKeyboard = LocalSoftwareKeyboardController.current
    val bookKeyboardVisible = WindowInsets.isImeVisible
    val bookComposerVisibility = remember { BringIntoViewRequester() }
    val bookSendVisibility = remember { BringIntoViewRequester() }
    var bookComposerFocused by remember { mutableStateOf(false) }
    LaunchedEffect(bookKeyboardVisible, bookComposerFocused) {
        if (bookKeyboardVisible && bookComposerFocused) {
            withFrameNanos { }
            bookComposerVisibility.bringIntoView()
            bookSendVisibility.bringIntoView()
        }
    }
    var bookComposerValue by remember(live.generation, reading.library, reading.readerScopeId, chat.bookId, chat.bookRevision,
        reading.story?.id, reading.story?.revision, chat.conversationId) {
        mutableStateOf(TextFieldValue(chat.draft, selection = TextRange(chat.draft.length)))
    }
    var bookDraftRejected by remember(live.generation, reading.library, reading.readerScopeId, chat.bookId, chat.bookRevision,
        reading.story?.id, reading.story?.revision, chat.conversationId) { mutableStateOf(false) }
    val accountId = live.session?.account_id.orEmpty()
    var handledBookFocusRequest by remember(live.generation, reading.library, reading.readerScopeId, chat.bookId, chat.bookRevision,
        reading.story?.id, reading.story?.revision, chat.conversationId) {
        mutableIntStateOf(chat.chatDraftFocusRequestId)
    }
    LaunchedEffect(chat.draft, chat.chatDraftFocusRequestId) {
        if (chat.chatDraftFocusRequestId != handledBookFocusRequest) {
            handledBookFocusRequest = chat.chatDraftFocusRequestId
            bookComposerValue = TextFieldValue(chat.draft, selection = TextRange(chat.draft.length))
            bookDraftRejected = false
            bookComposerFocusRequester.requestFocus()
            // Follow this explicit insertion action with the software keyboard
            // after the focused field's input session has been established.
            withFrameNanos { }
            bookComposerKeyboard?.show()
        } else if (bookComposerValue.composition == null && bookComposerValue.text != chat.draft) {
            bookComposerValue = TextFieldValue(chat.draft, selection = TextRange(chat.draft.length))
            bookDraftRejected = false
        }
    }
    val canChangeThread = !chat.busy && chat.pendingTurn == null && chat.pendingConversation == null &&
        !hasActiveMemoryChatJob(chat.job, chat.turns) && !hasUnfinishedMemoryDictation(dictationState)
    val chapterDiscussion = store.memoryBookChapterDiscussionContext()
    var chapterDiscussionNotice by remember(chapterDiscussion) { mutableStateOf("") }
    Column(Modifier.fillMaxWidth().testTag("memory-book-companion"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        HorizontalDivider()
        Text(t("A conversation about this memoir", "聊聊这本回忆册"), style = MaterialTheme.typography.titleLarge,
            fontFamily = FontFamily.Serif, modifier = Modifier.testTag("memory-book-chat-title"))
        Text(t("This thread stays with the memoir as you move between its stories.", "切换回忆册中的故事时，这段对话会继续保留。"),
            style = MaterialTheme.typography.bodySmall)
        chat.conversations?.items?.let { rows ->
            FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                rows.forEachIndexed { index, row ->
                    FilterChip(selected = row.id == chat.conversationId,
                        onClick = { store.selectMemoryBookConversation(row.id) }, enabled = canChangeThread,
                        label = { MemoryConversationChipLabel(row.createdAt, row.firstMessagePreview, zh) },
                        modifier = Modifier.testTag("memory-book-chat-thread-$index"))
                }
                TextButton(onClick = store::queueMemoryBookConversation, enabled = canChangeThread,
                    modifier = Modifier.testTag("memory-book-chat-new")) { Text(t("New chat", "新对话")) }
            }
        }
        if (chat.conversationRestored) Text(
            t("Back in the conversation you last selected.", "已回到上次选择的对话。"),
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.testTag("memory-book-chat-restored").semantics { liveRegion = LiveRegionMode.Polite })
        if (chat.failure != null) Text(communityMessage(chat.failure!!, zh), color = MaterialTheme.colorScheme.error,
            modifier = Modifier.testTag("memory-book-chat-failure"))
        if (chat.conversationId == null) {
            Text(t("Start a private conversation about this memoir.", "开始一段只围绕这本回忆册的对话。"))
            Button(onClick = store::queueMemoryBookConversation, enabled = !chat.busy,
                modifier = Modifier.testTag("memory-book-chat-start")) { Text(t("Start memoir chat", "开始聊聊回忆册")) }
            if (chat.pendingConversation != null && chat.failure != null) OutlinedButton(
                onClick = store::retryStartMemoryBookConversation, enabled = !chat.busy,
                modifier = Modifier.testTag("memory-book-chat-start-retry")) { Text(t("Retry same chat", "重试创建对话")) }
        } else {
            chat.turns?.items?.forEach { turn ->
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    MemoryChatMessageBubble(user = true, tag = "memory-book-chat-user-bubble-${turn.id}") {
                        Text(t("YOU", "你"), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.testTag("memory-book-chat-user-speaker"))
                        Text(turn.inputText, style = MaterialTheme.typography.bodyLarge)
                    }
                    MemoryChatMessageBubble(user = false, tag = "memory-book-chat-assistant-bubble-${turn.id}") {
                        turn.replyText?.let { reply ->
                            Text(t("MEMOIR COMPANION", "回忆册助手"), style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary, modifier = Modifier.testTag("memory-book-chat-assistant-speaker"))
                            Text(reply, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("memory-book-chat-turn-reply"))
                            val replyContext = if (turn.state == "ready") memoryReplyContext(turn, chat.job, chat.bookRevision) else null
                            if (replyContext != null && (turn.replyKind == "clarification" || replyContext.questions.isNotEmpty() || replyContext.sourceIds.isNotEmpty())) {
                                val canChooseQuestion = canReplaceComposerWithReplyQuestion(bookComposerValue) &&
                                    !live.busy && !reading.busy && !reading.readerBusy && !chat.busy &&
                                    chat.pendingConversation == null && chat.pendingTurn == null &&
                                    !hasActiveMemoryChatJob(chat.job, chat.turns) && !hasUnfinishedMemoryDictation(dictationState)
                                ReplyContextControls("memory-book-chat-followup-${turn.sequence}", replyContext,
                                    memoirReplySourceLabels(replyContext.sourceIds, reading, zh), canChooseQuestion, zh,
                                    clarification = turn.replyKind == "clarification") { question ->
                                    if (!canReplaceComposerWithReplyQuestion(bookComposerValue)) MemoryChatFollowupResult.BLOCKED
                                    else store.chooseMemoryBookChatFollowup(
                                        accountId, live.generation, reading.library, reading.readerScopeId, chat.bookId,
                                        chat.bookRevision, reading.story?.id.orEmpty(), reading.story?.revision ?: -1,
                                        chat.conversationId.orEmpty(), chat.turns?.page ?: -1, turn.id, question)
                                }
                            }
                            val speechScope = listOf("memoir-chat", live.session?.account_id, live.generation, reading.library,
                                chat.bookId, chat.bookRevision, reading.story?.id, reading.story?.revision,
                                chat.conversationId, turn.id, turn.jobId, reply)
                            val (speechLanguage, labels) = replyReadAloudLabels(
                                language, zh, "memory-book-chat-reply-reading-${turn.id}")
                            ChapterReadAloud(reply, speechLanguage, speechScope, zh, enabled = !chat.busy, labels = labels)
                        } ?: Text(memoirTurnStatus(turn.state, zh), style = MaterialTheme.typography.labelMedium,
                            modifier = Modifier.testTag("memory-book-turn-state-${turn.sequence}"))
                    }
                }
            }
            chat.turns?.let { page ->
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(if (page.page == 1) t("Latest messages", "最新消息") else t("Earlier messages · page ${page.page}", "更早的消息 · 第 ${page.page} 页"),
                        modifier = Modifier.align(Alignment.CenterHorizontally).testTag("memory-book-chat-page"))
                    FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        TextButton(onClick = { store.loadMemoryBookTurnsPage(page.page - 1) }, enabled = !chat.busy && page.page > 1,
                            modifier = Modifier.testTag("memory-book-chat-previous")) { Text(t("Newer messages", "较新的消息")) }
                        TextButton(onClick = { store.loadMemoryBookTurnsPage(page.page + 1) }, enabled = !chat.busy && page.hasMore && page.page < 8,
                            modifier = Modifier.testTag("memory-book-chat-next")) { Text(t("Older messages", "更早的消息")) }
                    }
                }
            }
            chat.job?.let { job ->
                Text(memoirJobStatus(job.state, zh), modifier = Modifier.testTag("memory-book-chat-job-state"))
                val representedByTurn = chat.turns?.items?.any { it.jobId == job.id } == true
                if (!representedByTurn) job.result?.get("reply")?.jsonPrimitive?.contentOrNull?.let { reply ->
                    Text(t("MEMOIR COMPANION", "回忆册助手"), style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary, modifier = Modifier.testTag("memory-book-chat-assistant-speaker-job"))
                    Text(reply, modifier = Modifier.testTag("memory-book-chat-reply"))
                    val speechScope = listOf("memoir-chat-job", live.session?.account_id, live.generation, reading.library,
                        chat.bookId, chat.bookRevision, reading.story?.id, reading.story?.revision,
                        chat.conversationId, job.id, reply)
                    val (speechLanguage, labels) = replyReadAloudLabels(
                        language, zh, "memory-book-chat-job-reply-reading-${job.id}")
                    ChapterReadAloud(reply, speechLanguage, speechScope, zh, enabled = !chat.busy, labels = labels)
                }
            }
            val queuedTurnNeedsCheck = chat.turns?.items?.any { it.state in setOf("queued", "running") } == true
            if (chat.conversationId != null && (chat.turns == null || chat.job?.state in setOf("queued", "running") || queuedTurnNeedsCheck)) TextButton(
                onClick = store::refreshMemoryBookChat, enabled = !chat.busy,
                modifier = Modifier.testTag("memory-book-chat-refresh")) { Text(t("Refresh messages and reply", "刷新消息和回复")) }
            if (chapterDiscussion != null) {
                OutlinedButton(onClick = {
                    val result = if (!canReplaceComposerWithReplyQuestion(bookComposerValue)) MemoryChatFollowupResult.BLOCKED
                        else store.chooseMemoryBookChapterDiscussion(chapterDiscussion, zh)
                    chapterDiscussionNotice = when (result) {
                        MemoryChatFollowupResult.SELECTED -> ""
                        MemoryChatFollowupResult.BLOCKED -> t("Your input is kept. Finish it before choosing a chapter question.",
                            "已保留你的输入。请先完成当前输入，再选择篇章问题。")
                        MemoryChatFollowupResult.STALE -> t("The reading context changed. Choose the current chapter again.",
                            "正在阅读的内容已变化，请重新选择当前篇章。")
                    }
                }, enabled = !live.busy && !reading.busy && !reading.readerBusy && canChangeThread &&
                    canReplaceComposerWithReplyQuestion(bookComposerValue),
                    modifier = Modifier.fillMaxWidth().testTag("memory-book-chat-discuss-chapter")) {
                    Text(t("Discuss this chapter", "聊聊正在阅读的篇章"))
                }
                Text(t("Adds an editable question about “${chapterDiscussion.chapterTitle}”. Send when you are ready.",
                    "带入“${chapterDiscussion.chapterTitle}”的可编辑问题，核对后再发送。"),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.testTag("memory-book-chat-chapter-context"))
            }
            if (chapterDiscussionNotice.isNotEmpty()) Text(chapterDiscussionNotice,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("memory-book-chat-chapter-notice").semantics { liveRegion = LiveRegionMode.Polite })
            Text(t(
                "Replies use this memoir's materials, your question, and up to 7 earlier exchanges. Older messages stay readable but are not included automatically; add important background to your question.",
                "回复参考当前回忆册材料、当前问题和此前最多 7 轮对话。更早消息可查看但不自动带入；重要背景请补充到问题中。",
            ), style = MaterialTheme.typography.bodySmall, modifier = Modifier.fillMaxWidth().testTag("memory-book-chat-context-window"))
            OutlinedTextField(value = bookComposerValue, onValueChange = { value ->
                bookComposerValue = value
                bookDraftRejected = !store.updateMemoryBookChatDraft(value.text)
            }, enabled = !chat.busy,
                label = { Text(t("Ask about this memoir", "聊聊这本回忆册")) }, minLines = 2,
                maxLines = if (bookKeyboardVisible) 3 else 5,
                isError = bookDraftRejected,
                supportingText = if (bookDraftRejected) ({
                    Text(t("This message exceeds the draft limit. Shorten it before sending.",
                        "这条消息超出草稿长度限制，请缩短后再发送。"),
                        modifier = Modifier.testTag("memory-book-chat-draft-limit").semantics { liveRegion = LiveRegionMode.Polite })
                }) else null,
                modifier = Modifier.fillMaxWidth().focusRequester(bookComposerFocusRequester)
                    .onFocusChanged { bookComposerFocused = it.isFocused }
                    .bringIntoViewRequester(bookComposerVisibility).testTag("memory-book-chat-input"))
            val contextChoice = chat.editorialContext
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)
                .toggleable(value = contextChoice == MemoryBookChatEditorialContext.READY, role = Role.Checkbox,
                    enabled = canChangeThread,
                    onValueChange = store::chooseMemoryBookChatEditorialContext)
                .testTag("memory-book-chat-editorial-context"), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = contextChoice == MemoryBookChatEditorialContext.READY, onCheckedChange = null,
                    enabled = canChangeThread)
                Column(Modifier.weight(1f)) {
                    Text(t("Include the saved opening and transitions", "结合已保存的开篇与章节过渡"))
                    Text(t("Checked before sending; your message stays in the draft.", "先检查可用内容，消息仍由你确认发送。"),
                        style = MaterialTheme.typography.bodySmall)
                }
            }
            if (contextChoice != MemoryBookChatEditorialContext.BASIC) {
                Text(memoirEditorialContextStatus(contextChoice, zh),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.testTag("memory-book-chat-editorial-status")
                        .semantics { liveRegion = LiveRegionMode.Polite })
            }
            if (contextChoice !in setOf(MemoryBookChatEditorialContext.BASIC, MemoryBookChatEditorialContext.CHECKING,
                    MemoryBookChatEditorialContext.READY)) {
                TextButton(onClick = { store.chooseMemoryBookChatEditorialContext(false) }, enabled = canChangeThread,
                    modifier = Modifier.testTag("memory-book-chat-basic-context")) { Text(t("Use saved stories only", "仅使用已保存的故事")) }
            }
            if (chat.dictation == null) TextButton(onClick = { store.memoryBookChatDictation() }, enabled = store.assistantEnabled && !chat.busy,
                modifier = Modifier.testTag("memory-book-chat-enable-dictation")) { Text(t("Add voice input", "使用语音输入")) }
            var transcriptLimit by remember(live.generation, reading.library, chat.bookId, chat.bookRevision,
                reading.story?.id, reading.story?.revision, chat.conversationId, chat.dictation) { mutableStateOf(false) }
            chat.dictation?.takeUnless { contextChoice == MemoryBookChatEditorialContext.CHECKING }?.let { dictation -> MemoryDictationInput(dictation, zh, onInsert = {
                val current = store.state.value
                val latestReading = current.memoryBooks ?: return@MemoryDictationInput
                val latestBook = latestReading.selectedBook ?: return@MemoryDictationInput
                val latestStory = latestReading.story ?: return@MemoryDictationInput
                val latestChat = latestReading.companion ?: return@MemoryDictationInput
                if (current.generation != live.generation || current.session?.account_id != live.session?.account_id ||
                    current.library != reading.library || latestReading.library != reading.library ||
                    latestBook.id != chat.bookId || latestBook.revision != chat.bookRevision ||
                    latestStory.id != reading.story?.id || latestStory.revision != reading.story?.revision ||
                    latestChat.bookId != chat.bookId || latestChat.bookRevision != chat.bookRevision ||
                    latestChat.conversationId != chat.conversationId || latestChat.dictation !== dictation) return@MemoryDictationInput
                val transcript = dictation.state.value.transcript ?: return@MemoryDictationInput
                val combined = listOf(latestChat.draft, transcript).filter { it.isNotBlank() }.joinToString("\n")
                if (combined.toByteArray(Charsets.UTF_8).size > 4096) {
                    transcriptLimit = true
                    return@MemoryDictationInput
                }
                if (dictation.takeTranscript() == null) return@MemoryDictationInput
                store.updateMemoryBookChatDraft(combined)
                transcriptLimit = false
            }, purpose = MemoryDictationPurpose.CHAT_MESSAGE) }
            if (transcriptLimit) Text(t("The edited transcript was kept. Shorten it or the draft to fit 4,096 bytes.",
                "已保留编辑后的转写。请缩短转写或草稿，使合计不超过 4,096 字节。"),
                color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("memory-book-chat-transcript-limit"))
            Row(Modifier.bringIntoViewRequester(bookSendVisibility), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = store::sendMemoryBookChat, enabled = !bookDraftRejected && bookComposerValue.text == chat.draft &&
                    contextChoice in setOf(MemoryBookChatEditorialContext.BASIC, MemoryBookChatEditorialContext.READY) &&
                    !chat.busy && (chat.conversationId == null || chat.turns != null) && chat.pendingTurn == null &&
                    !hasActiveMemoryChatJob(chat.job, chat.turns) && !hasUnfinishedMemoryDictation(dictationState) && chat.draft.isNotBlank(),
                    modifier = Modifier.testTag("memory-book-chat-send")) { Text(t("Send", "发送")) }
                if (chat.pendingTurn != null && chat.failure != null) OutlinedButton(onClick = store::retryMemoryBookChatTurn,
                    enabled = !chat.busy, modifier = Modifier.testTag("memory-book-chat-retry")) { Text(t("Retry same message", "重试这条消息")) }
            }
        }
    }
}

private fun memoirEditorialContextStatus(choice: MemoryBookChatEditorialContext, zh: Boolean): String = when (choice) {
    MemoryBookChatEditorialContext.CHECKING -> if (zh) "正在检查已保存的开篇、引用和章节过渡…" else "Checking the saved opening, references and transitions…"
    MemoryBookChatEditorialContext.READY -> if (zh) "发送时会结合已保存的编辑内容；AI 的回复仍需核对。" else "The reply will use saved editorial context and still needs your review."
    MemoryBookChatEditorialContext.UNAVAILABLE -> if (zh) "服务器暂未开放这项功能。草稿已保留，可重试检查或选择仅使用故事。" else "The server has not enabled this feature. Your draft is kept; check again or choose stories only."
    MemoryBookChatEditorialContext.CHANGED -> if (zh) "回忆册或引用已变化，请刷新并核对已保存的开篇和过渡。草稿已保留。" else "The memoir or its references changed. Refresh and review the saved opening and transitions. Your draft is kept."
    MemoryBookChatEditorialContext.SMALLER_SCOPE -> if (zh) "整本回忆册的内容超过本次处理范围。可选择仅使用故事，或先缩小回忆册范围。" else "This memoir exceeds the current context limit. Choose stories only or reduce its scope."
    MemoryBookChatEditorialContext.FAILED -> if (zh) "未能完成内容检查，草稿已保留。请重试检查或选择仅使用故事。" else "The context check could not finish. Your draft is kept; check again or choose stories only."
    MemoryBookChatEditorialContext.BASIC -> ""
}

private fun memoirTurnStatus(state: String?, zh: Boolean): String = when (state) {
    "queued" -> if (zh) "已排队" else "Queued"
    "running" -> if (zh) "正在准备回复" else "Preparing a reply"
    "failed" -> if (zh) "回复准备失败" else "Reply preparation failed"
    "cancelled", "canceled" -> if (zh) "已取消" else "Cancelled"
    "stale" -> if (zh) "回忆册内容已变化" else "Memoir changed"
    "ready" -> if (zh) "回复已准备好" else "Reply ready"
    else -> if (zh) "等待回复" else "Waiting for a reply"
}

private fun memoirJobStatus(state: String, zh: Boolean): String = when (state) {
    "queued" -> if (zh) "回复已排队" else "Reply queued"
    "running" -> if (zh) "正在准备回复" else "Preparing a reply"
    "ready" -> if (zh) "回复已生成 · 使用前请检查" else "Reply ready · Review before using"
    "failed" -> if (zh) "暂时无法生成回复" else "Reply could not be prepared"
    "cancelled", "canceled" -> if (zh) "回复已取消" else "Reply cancelled"
    "stale" -> if (zh) "回忆册内容已变化，请重新提问" else "The memoir changed. Start a fresh turn."
    else -> if (zh) "回复状态暂不可用" else "Reply status unavailable"
}

@Composable
private fun NarrativePanel(store: ConnectedStore, reading: SavedMemoryStoriesReading, community: MemoryCommunityStoryState, zh: Boolean) {
    val t = { en: String, cn: String -> if (zh) cn else en }
    var instructions by remember(community.storyId) { mutableStateOf(if (zh) "请整理家人分享的回忆，保留不确定之处并提出待确认的问题。" else "Organize the family memories, preserve uncertainty, and ask about anything unclear.") }
    Text(t("Prepare a story draft from the available family contributions. The saved story will not be changed.",
        "根据现有家人分享整理故事草稿。不会修改已保存的故事。"), style = MaterialTheme.typography.bodySmall)
    OutlinedTextField(value = instructions, onValueChange = { if (it.toByteArray(Charsets.UTF_8).size <= 4096) instructions = it },
        label = { Text(t("Instructions", "整理要求")) }, minLines = 2, maxLines = 4,
        modifier = Modifier.fillMaxWidth().testTag("memory-narrative-instructions"))
    Button(onClick = { store.requestMemoryNarrative(instructions) }, enabled = !community.busy && community.pendingNarrative == null,
        modifier = Modifier.testTag("memory-narrative-request")) { Text(t("Prepare draft", "整理草稿")) }
    if (community.pendingNarrative != null && community.failure != null) {
        OutlinedButton(onClick = store::retryMemoryNarrative, enabled = !community.busy,
            modifier = Modifier.testTag("memory-narrative-retry")) { Text(t("Retry same request", "重试这次请求")) }
    }
    community.narrativeJob?.let { job ->
        Text(t("Draft status · ${job.state}", "草稿状态 · ${job.state}"), modifier = Modifier.testTag("memory-narrative-state"))
        if (job.state in setOf("queued", "running")) TextButton(onClick = store::refreshMemoryNarrative,
            enabled = !community.busy, modifier = Modifier.testTag("memory-narrative-refresh")) { Text(t("Check draft", "查看草稿")) }
        job.result?.let { result ->
            val proposal = parseStoryProposal(result)
            if (proposal != null) {
                val story = reading.detail?.takeIf { it.id == community.storyId }
                val bindOriginals = story != null && job.kind == "narrative" && job.state == "ready" &&
                    job.baseRevision == story.revision
                StoryProposalReview("memory-narrative", community.readerScopeId, story, community, job, proposal,
                    bindOriginals, zh)
                Text(t("Review this proposal before any manual use. It has not been applied or saved.", "使用前请检查这份建议。它尚未应用或保存。"),
                    style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.testTag("memory-narrative-review-only"))
            }
        }
    }
}

private data class StoryProposalChapter(val id: String, val narration: String, val sourceIds: List<String>)
private data class StoryProposal(val title: String, val chapters: List<StoryProposalChapter>, val questions: List<String>)

/** The API decoder validates these exact shapes; keep the UI defensive around optional JSON values. */
private fun parseStoryProposal(value: JsonElement?): StoryProposal? {
    val result = value as? JsonObject ?: return null
    fun stringField(obj: JsonObject, key: String, limit: Int): String? =
        (obj[key] as? JsonPrimitive)?.takeIf { it.isString }?.content?.takeIf { it.length <= limit }
    val title = stringField(result, "title", 2048) ?: return null
    val chapterArray = result["chapters"] as? JsonArray ?: return null
    if (chapterArray.isEmpty() || chapterArray.size > 24) return null
    val chapters = ArrayList<StoryProposalChapter>(chapterArray.size)
    for (element in chapterArray) {
        val chapter = element as? JsonObject ?: return null
        val id = stringField(chapter, "id", 128) ?: return null
        val narration = stringField(chapter, "narration", 12_000) ?: return null
        val refs = chapter["source_ids"] as? JsonArray ?: return null
        if (refs.size > 96) return null
        val sourceIds = ArrayList<String>(refs.size)
        for (ref in refs) sourceIds += ((ref as? JsonPrimitive)?.takeIf { it.isString }?.content ?: return null)
        if (sourceIds.distinct().size != sourceIds.size) return null
        chapters += StoryProposalChapter(id, narration, sourceIds)
    }
    val questionArray = result["questions"] as? JsonArray ?: return null
    if (questionArray.size > 6) return null
    val questions = ArrayList<String>(questionArray.size)
    for (question in questionArray) questions += ((question as? JsonPrimitive)?.takeIf { it.isString }?.content ?: return null)
    return StoryProposal(title, chapters, questions)
}

@Composable
private fun StoryProposalReview(
    tagPrefix: String,
    readerScopeId: Long,
    story: SavedMemoryStory?,
    community: MemoryCommunityStoryState,
    job: MemoryJob,
    proposal: StoryProposal,
    bindOriginals: Boolean,
    zh: Boolean,
) {
    val t = { en: String, cn: String -> if (zh) cn else en }
    val boundStory = story?.takeIf {
        bindOriginals && it.id == community.storyId && it.revision == job.baseRevision && job.state == "ready"
    }
    Column(Modifier.fillMaxWidth().testTag("$tagPrefix-review"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(t("AI suggestion · review required", "AI 建议 · 待核对"),
            style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.testTag("$tagPrefix-review-badge"))
        Text(proposal.title, style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif,
            modifier = Modifier.testTag("$tagPrefix-title"))
        proposal.chapters.forEachIndexed { index, chapter ->
            val original = boundStory?.chapters?.firstOrNull { it.id == chapter.id }
            var comparisonExpanded by remember(tagPrefix, readerScopeId, story?.id, story?.revision, job.id, chapter.id) {
                mutableStateOf(false)
            }
            var sourcesExpanded by remember(tagPrefix, readerScopeId, story?.id, story?.revision, job.id, chapter.id) {
                mutableStateOf(false)
            }
            Column(Modifier.fillMaxWidth().testTag("$tagPrefix-chapter-$index"), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(original?.title ?: t("Suggested section ${index + 1}", "建议段落 ${index + 1}"),
                    style = MaterialTheme.typography.titleMedium, fontFamily = FontFamily.Serif,
                    modifier = Modifier.testTag("$tagPrefix-chapter-title-$index"))
                Text(chapter.narration, style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.testTag("$tagPrefix-narration-$index"))
                if (chapter.sourceIds.isNotEmpty()) {
                    TextButton(onClick = { sourcesExpanded = !sourcesExpanded },
                        modifier = Modifier.testTag("$tagPrefix-sources-toggle-$index")) {
                        Text(if (sourcesExpanded) t("Hide references", "收起参考线索") else
                            t("Show references · ${chapter.sourceIds.size}", "查看参考线索 · ${chapter.sourceIds.size}"))
                    }
                    if (sourcesExpanded) {
                        val labels = boundStory?.let { storyReplySourceLabels(chapter.sourceIds, it, community, zh) }
                            ?: List(chapter.sourceIds.size) { t("Source not loaded", "来源尚未加载") }
                        Column(Modifier.fillMaxWidth().testTag("$tagPrefix-sources-$index"),
                            verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            labels.forEach { label -> Text("• $label", style = MaterialTheme.typography.bodySmall) }
                            Text(t("Available labels identify reader materials; they do not verify this suggestion.",
                                "已加载标签只表示阅读器中有对应材料，不代表建议内容已经核实。"),
                                style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                if (original != null) {
                    TextButton(onClick = { comparisonExpanded = !comparisonExpanded },
                        modifier = Modifier.testTag("$tagPrefix-original-toggle-$index")) {
                        Text(if (comparisonExpanded) t("Hide current chapter", "收起当前章节") else
                            t("View current reader chapter", "查看当前阅读的章节"))
                    }
                    if (comparisonExpanded) Column(Modifier.fillMaxWidth().testTag("$tagPrefix-original-comparison-$index"),
                        verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text(t("Current reader chapter · comparison only", "当前阅读的章节 · 仅供对照"),
                            style = MaterialTheme.typography.labelMedium)
                        Text(original.narration, style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.testTag("$tagPrefix-original-text-$index"))
                    }
                }
            }
        }
        proposal.questions.takeIf { it.isNotEmpty() }?.let { questions ->
            Text(t("Questions to confirm", "待确认的问题"), style = MaterialTheme.typography.titleSmall)
            questions.forEachIndexed { index, question ->
                Text("• $question", modifier = Modifier.testTag("$tagPrefix-question-$index"))
            }
        }
    }
}

private fun communityMessage(problem: LiveProblem, zh: Boolean): String = when (problem.message) {
    Message.NETWORK_UNAVAILABLE -> if (zh) "网络不可用，请检查连接后重试。" else "Network unavailable. Check the connection and retry."
    Message.TLS_ERROR -> if (zh) "安全连接失败，请稍后重试。" else "Secure connection failed. Try again later."
    Message.RATE_LIMITED -> if (zh) "请求过多，请稍后重试。" else "Too many requests. Wait before retrying."
    Message.ACCESS_DENIED, Message.CLOSED -> if (zh) "当前账号暂时无法访问这段回忆。" else "This account cannot access this memory right now."
    else -> if (zh) "暂时无法完成，请稍后重试。" else "Could not complete this request. Try again later."
}
