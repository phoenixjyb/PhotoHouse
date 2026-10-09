package dev.photohouse.connected

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*
import kotlinx.coroutines.launch

/** A book proposal is read independently; it never replaces a saved child story. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun MemoryBookNarrativePanel(
    store: ConnectedStore, reading: MemoryBooksReading, draft: MemoryBookNarrativeStoreState, zh: Boolean,
) {
    val book = reading.selectedBook ?: return
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    fun finishTyping() { focus.clearFocus(); keyboard?.hide() }
    val live by store.state.collectAsState()
    val edition by store.memoryBookEditionState.collectAsState()
    val editorial by store.memoryBookEditorialState.collectAsState()
    val dictationStore by store.memoryBookNarrativeDictationState.collectAsState()
    val emptyDictationState = remember { kotlinx.coroutines.flow.MutableStateFlow(MemoryDictationState()) }
    val dictationFlow = dictationStore?.state ?: emptyDictationState
    val dictationState by dictationFlow.collectAsState()
    val companionDictationFlow = reading.companion?.dictation?.state ?: emptyDictationState
    val companionDictationState by companionDictationFlow.collectAsState()
    fun t(en: String, cn: String) = if (zh) cn else en
    val activeJob = draft.job?.state in setOf("queued", "running")
    val ownVoiceUnfinished = dictationState.loading || dictationState.recording || dictationState.transcribing ||
        dictationState.transcript != null
    val otherBusy = edition.hasUnfinishedWork || live.busy || reading.readerBusy || reading.companion?.let {
        it.busy || it.pendingTurn != null || it.pendingConversation != null || it.job?.state in setOf("queued", "running")
    } == true || ownVoiceUnfinished || companionDictationState.let { it.loading || it.recording || it.transcribing } ||
        editorial.status in setOf(MemoryBookEditorialStoreStatus.SAVING, MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN)
    val frozen = draft.busy || draft.pendingRequest != null || activeJob || otherBusy
    var wording by remember(live.session?.account_id, live.generation, reading.library, book.id, book.revision) {
        mutableStateOf(draft.instructions)
    }
    var rejected by remember(live.session?.account_id, live.generation, reading.library, book.id, book.revision) { mutableStateOf(false) }
    var dictationOpenRejected by remember(live.session?.account_id, live.generation, reading.library, book.id, book.revision) { mutableStateOf(false) }
    var dictationInsertRejected by remember(live.session?.account_id, live.generation, reading.library, book.id, book.revision) { mutableStateOf(false) }
    var formExpanded by remember(live.session?.account_id, live.generation, reading.library, book.id, book.revision) { mutableStateOf(false) }
    var formRejected by remember(live.session?.account_id, live.generation, reading.library, book.id, book.revision) { mutableStateOf(false) }
    LaunchedEffect(draft.instructions) { if (!rejected) wording = draft.instructions }
    Column(Modifier.fillMaxWidth().testTag("memory-book-narrative-panel"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(t("A connected account of your family memories", "把家人的回忆连成完整叙事"),
            style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif)
        Text(t("Check the saved chapters first. AI suggestions stay separate from the memoir and its stories until you review them.",
            "先检查已保存的篇章。AI 建议会单独展示，供你逐章核对；回忆册与原故事保持原样。"),
            style = MaterialTheme.typography.bodySmall)
        OutlinedButton(onClick = { finishTyping(); formExpanded = !formExpanded }, enabled = !frozen,
            modifier = Modifier.fillMaxWidth().testTag("memory-book-narrative-form-open")) {
            Text(if (draft.form == MemoryBookNarrativeForm.EXISTING) t("Storytelling form (optional)", "讲述方式（可选）")
                else t("Storytelling form · ", "讲述方式 · ") + memoirFormTitle(draft.form, zh))
        }
        if (formExpanded) {
            Text(t("This guides your next draft. Your family's original words stay separate.",
                "用于下一次整理，家人的原话会单独保留。"), style = MaterialTheme.typography.bodySmall)
            MemoryBookNarrativeForm.entries.forEach { form ->
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)
                    .toggleable(value = draft.form == form, role = Role.RadioButton, enabled = !frozen,
                        onValueChange = {
                            finishTyping()
                            val accepted = store.chooseMemoryBookNarrativeForm(form)
                            formRejected = !accepted
                            if (accepted) formExpanded = false
                        }).testTag("memory-book-narrative-form-${form.name.lowercase()}"),
                    verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(selected = draft.form == form, onClick = null, enabled = !frozen)
                    Column(Modifier.weight(1f).padding(vertical = 8.dp)) {
                        Text(memoirFormTitle(form, zh), style = MaterialTheme.typography.titleSmall)
                        Text(memoirFormHelp(form, zh), style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
        if (formRejected) Text(t("The instructions are too long for this form. Shorten them, then choose a form again. Your current form and complete draft are kept.",
            "整理要求太长，请缩短后重新选择讲述方式。当前方式和完整文字已保留。"),
            color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("memory-book-narrative-form-error")
                .semantics { liveRegion = LiveRegionMode.Polite })
        OutlinedTextField(value = wording, onValueChange = {
            wording = it; rejected = !store.updateMemoryBookNarrativeInstructions(it)
        }, enabled = !frozen, minLines = 2, maxLines = 5,
            label = { Text(t("Your instructions", "整理要求")) },
            placeholder = { Text(t("Keep family accounts attributed, connect the chapters, and ask about uncertain details.",
                "保留家人的讲述归属，连接各篇章，遇到不确定的细节先提出问题。")) },
            isError = rejected,
            supportingText = if (rejected) ({ Text(t("The complete wording is kept here. Shorten it before requesting a draft.",
                "完整文字已保留在这里，请缩短后再生成建议。"), modifier = Modifier.testTag("memory-book-narrative-input-error")
                .semantics { liveRegion = LiveRegionMode.Polite }) }) else null,
            modifier = Modifier.fillMaxWidth().testTag("memory-book-narrative-instructions"))
        if (dictationStore == null && store.assistantEnabled) {
            OutlinedButton(onClick = {
                finishTyping()
                dictationOpenRejected = !store.openMemoryBookNarrativeDictation()
            }, enabled = !frozen && store.assistantEnabled && !rejected && wording == draft.instructions,
                modifier = Modifier.fillMaxWidth().testTag("memory-book-narrative-voice-open")) {
                Text(t("Dictate arranging instructions", "口述整理要求"))
            }
            if (dictationOpenRejected) Text(
                t("Voice instructions are unavailable for this memoir right now. You can keep typing below.",
                    "当前无法使用语音整理要求，你仍可继续输入文字。"),
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag("memory-book-narrative-dictation-open-error")
                    .semantics { liveRegion = LiveRegionMode.Polite },
            )
        } else if (dictationStore != null) {
            TextButton(onClick = {
                store.clearMemoryBookNarrativeDictation()
                dictationInsertRejected = false
                dictationOpenRejected = false
            }, modifier = Modifier.testTag("memory-book-narrative-voice-close")) {
                Text(if (ownVoiceUnfinished) t("Discard this dictation", "放弃这段口述")
                    else t("Close voice instructions", "关闭语音整理要求"))
            }
            MemoryDictationInput(
                store = dictationStore!!,
                zh = zh,
                onInsert = {
                    val inserted = !rejected && wording == draft.instructions &&
                        store.insertMemoryBookNarrativeDictation()
                    dictationInsertRejected = !inserted
                    if (inserted) {
                        rejected = false
                        store.clearMemoryBookNarrativeDictation()
                        finishTyping()
                    }
                },
                purpose = MemoryDictationPurpose.MEMOIR_INSTRUCTIONS,
                insertRejected = dictationInsertRejected,
                insertEnabled = !rejected && wording == draft.instructions,
            )
        }
        Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)
            .toggleable(value = draft.editorialContext, role = Role.Checkbox, enabled = !frozen,
                onValueChange = store::chooseMemoryBookNarrativeEditorialContext)
            .testTag("memory-book-narrative-editorial-context"), verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = draft.editorialContext, onCheckedChange = null, enabled = !frozen)
            Text(t("Include the saved opening and transitions", "结合已保存的开篇与章节过渡"), Modifier.weight(1f))
        }
        OutlinedButton(onClick = { finishTyping(); store.checkMemoryBookNarrativePlan() }, enabled = !frozen,
            modifier = Modifier.testTag("memory-book-narrative-check")) { Text(t("Check available chapters", "检查可整理的篇章")) }
        if (draft.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (draft.status != MemoryBookNarrativeStatus.IDLE) Text(bookNarrativeStatus(draft.status, zh),
            modifier = Modifier.testTag("memory-book-narrative-status").semantics { liveRegion = LiveRegionMode.Polite })
        draft.failure?.let { Text(bookNarrativeFailure(it, zh), color = MaterialTheme.colorScheme.error,
            modifier = Modifier.testTag("memory-book-narrative-failure").semantics { liveRegion = LiveRegionMode.Polite }) }
        draft.plan?.let { plan ->
            Text(t("${englishCount(plan.storyCount, "story", "stories")} · ${englishCount(plan.chapterCount, "chapter", "chapters")} · ${englishCount(plan.distinctItemCount, "distinct moment", "distinct moments")}",
                "${plan.storyCount} 个故事 · ${plan.chapterCount} 个篇章 · ${plan.distinctItemCount} 个不同片段"),
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("memory-book-narrative-plan"))
            val planScope = listOf(live.session?.account_id, live.generation, reading.library,
                book.id, book.revision, book.stories.map { it.id to it.revision }, draft.editorialContext)
            val planMatches = plan.targetId == book.id && plan.revision == book.revision &&
                plan.sections.map { it.id to it.revision } == book.stories.map { it.id to it.revision } &&
                (plan.contextProfile == "memoir_editorial_v1") == draft.editorialContext
            if (plan.whole.state == "smaller_scope_required") Text(t(
                "This memoir is too large for one draft. You can still read each saved story below.",
                "整本回忆录超过单次整理范围。仍可在下方逐篇阅读已保存的故事。"),
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("memory-book-plan-whole-smaller"))
            MemoryBookPlanSections(plan.sections, listOf(planScope, plan),
                enabled = !frozen && planMatches, zh = zh, onOpen = { section ->
                    val current = store.state.value
                    val currentReading = current.memoryBooks
                    val currentBook = currentReading?.selectedBook
                    val currentDraft = store.memoryBookNarrativeState.value
                    val currentScope = listOf(current.session?.account_id, current.generation,
                        currentReading?.library, currentBook?.id, currentBook?.revision,
                        currentBook?.stories?.map { it.id to it.revision }, currentDraft.editorialContext)
                    val currentVoice = store.memoryBookNarrativeDictationState.value?.state?.value
                    val currentCompanionVoice = currentReading?.companion?.dictation?.state?.value
                    val currentEditorial = store.memoryBookEditorialState.value
                    val currentOtherBusy = current.busy || currentReading?.readerBusy != false ||
                        currentReading.companion?.let { it.busy || it.pendingTurn != null ||
                            it.pendingConversation != null || it.job?.state in setOf("queued", "running") } == true ||
                        currentVoice?.let { it.loading || it.recording || it.transcribing || it.transcript != null } == true ||
                        currentCompanionVoice?.let { it.loading || it.recording || it.transcribing } == true ||
                        currentEditorial.status in setOf(MemoryBookEditorialStoreStatus.SAVING, MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN)
                    if (!frozen && !currentOtherBusy && planMatches && currentScope == planScope &&
                        currentDraft.plan === plan && !currentDraft.busy && currentDraft.pendingRequest == null &&
                        currentDraft.job?.state !in setOf("queued", "running") &&
                        currentReading?.readerBusy == false && plan.sections.any { it == section }) {
                        val storyIndex = currentBook?.stories?.indexOfFirst {
                            it.id == section.id && it.revision == section.revision
                        } ?: -1
                        if (storyIndex >= 0) {
                            finishTyping()
                            store.loadMemoryBookStory(storyIndex)
                        }
                    }
                })
        }
        if (reading.capabilities?.generationEnabled != true) Text(t("AI drafting is not enabled for this library.",
            "这个相册尚未开放 AI 整理建议。"), style = MaterialTheme.typography.bodySmall)
        Button(onClick = { finishTyping(); store.requestMemoryBookNarrative() }, enabled = !frozen && !rejected && !formRejected && wording == draft.instructions &&
            draft.job == null && book.canEdit && reading.capabilities?.generationEnabled == true && draft.plan?.let {
                it.canEdit && it.whole.canDraft && it.whole.state == "within_limits"
            } == true,
            modifier = Modifier.testTag("memory-book-narrative-request")) { Text(t("Prepare a reviewable memoir draft", "生成整本待核对建议")) }
        if (draft.pendingRequest != null && draft.failure != null) OutlinedButton(onClick = store::retryMemoryBookNarrative,
            enabled = !draft.busy && !otherBusy, modifier = Modifier.testTag("memory-book-narrative-retry")) {
            Text(t("Retry the same request", "重试这次请求"))
        }
        if (activeJob) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = store::refreshMemoryBookNarrative, enabled = !draft.busy && !otherBusy,
                    modifier = Modifier.testTag("memory-book-narrative-refresh")) { Text(t("Check progress", "查看进度")) }
                TextButton(onClick = store::cancelMemoryBookNarrative, enabled = !draft.busy && !otherBusy,
                    modifier = Modifier.testTag("memory-book-narrative-cancel")) { Text(t("Cancel request", "取消请求")) }
            }
        }
        draft.proposal?.let { proposal ->
            val reviewScope = listOf(live.session?.account_id, live.generation, reading.library,
                book.id, book.revision, book.stories.map { it.id to it.revision }, draft.job?.id)
            val latestReviewScope by rememberUpdatedState(reviewScope)
            val navigationScope = rememberCoroutineScope()
            val reviewStart = remember(reviewScope) { BringIntoViewRequester() }
            var selected by remember(reviewScope) { mutableIntStateOf(0) }
            fun selectDraftChapter(next: Int) {
                if (next !in proposal.chapters.indices || draft.busy || otherBusy) return
                selected = next
                navigationScope.launch {
                    withFrameNanos { }
                    if (latestReviewScope == reviewScope) reviewStart.bringIntoView()
                }
            }
            val index = selected.coerceIn(0, proposal.chapters.lastIndex)
            val chapter = proposal.chapters[index]
            Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = MaterialTheme.shapes.large,
                modifier = Modifier.fillMaxWidth().testTag("memory-book-narrative-review")) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(t("AI suggestion · Not applied", "AI 建议 · 尚未应用"), style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary, modifier = Modifier.bringIntoViewRequester(reviewStart).testTag("memory-book-narrative-review-only"))
                    Text(proposal.title, style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif)
                    MemoryBookNarrativeDirectory(proposal.chapters, selected, reviewScope,
                        enabled = !draft.busy && !otherBusy, zh = zh, onSelect = ::selectDraftChapter)
                    Text(t("Chapter ${index + 1} of ${proposal.chapters.size}", "篇章 ${index + 1}/${proposal.chapters.size}"),
                        modifier = Modifier.testTag("memory-book-narrative-chapter-position"))
                    Text(chapter.storyTitle, style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.testTag("memory-book-narrative-story-label"))
                    Text(chapter.chapterTitle, style = MaterialTheme.typography.labelLarge,
                        modifier = Modifier.testTag("memory-book-narrative-chapter-label"))
                    Text(chapter.narration, style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.testTag("memory-book-narrative-prose"))
                    Text(if (chapter.citationCount == 0) t("No citations are attached to this passage. Check the original accounts before using it.",
                        "这段建议尚未附上引用，使用前请核对原始讲述。") else
                        t("${englishCount(chapter.citationCount, "cited source", "cited sources")}. Check the original story and family accounts before using this passage.",
                            "引用了 ${chapter.citationCount} 条资料。使用前请核对原故事与家人的讲述。"),
                        style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("memory-book-narrative-citations"))
                    ChapterReadAloud(chapter.narration, book.language,
                        listOf("memoir-proposal", live.session?.account_id, live.generation, reading.library,
                            book.id, book.revision, draft.job?.id, chapter.id, chapter.narration), zh,
                        enabled = chapter.narration.isNotBlank() && !draft.busy)
                    TextButton(onClick = {
                        val storyIndex = book.stories.indexOfFirst { it.id == chapter.storyId && it.revision == chapter.storyRevision }
                        if (storyIndex >= 0) store.loadMemoryBookStory(storyIndex)
                    }, enabled = !reading.readerBusy && book.stories.any { it.id == chapter.storyId && it.revision == chapter.storyRevision },
                        modifier = Modifier.testTag("memory-book-narrative-open-story")) { Text(t("Open the original story", "打开原故事核对")) }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        OutlinedButton(onClick = { selectDraftChapter(index - 1) }, enabled = !draft.busy && !otherBusy && index > 0,
                            modifier = Modifier.testTag("memory-book-narrative-previous")) { Text(t("Previous", "上一篇")) }
                        OutlinedButton(onClick = { selectDraftChapter(index + 1) }, enabled = !draft.busy && !otherBusy && index < proposal.chapters.lastIndex,
                            modifier = Modifier.testTag("memory-book-narrative-next")) { Text(t("Next", "下一篇")) }
                    }
                    if (proposal.questions.isNotEmpty()) {
                        Text(t("Questions to ask the family", "还想问问家人"), style = MaterialTheme.typography.titleMedium)
                        proposal.questions.forEach { Text("• $it", modifier = Modifier.testTag("memory-book-narrative-question")) }
                    }
                }
            }
        }
        MemoryBookEditionPanel(store, reading, zh, enabled = !draft.busy && !otherBusy)
    }
}

private fun englishCount(count: Int, singular: String, plural: String): String =
    "$count ${if (count == 1) singular else plural}"

private fun memoirFormTitle(form: MemoryBookNarrativeForm, zh: Boolean): String = when (form) {
    MemoryBookNarrativeForm.EXISTING -> if (zh) "保持原有讲述" else "Keep the existing voice"
    MemoryBookNarrativeForm.CHRONICLE -> if (zh) "忠实纪事" else "Family chronicle"
    MemoryBookNarrativeForm.ESSAY -> if (zh) "家庭散文" else "Reflective essay"
    MemoryBookNarrativeForm.LONG_MEMOIR -> if (zh) "长篇回忆录" else "Connected memoir"
}

private fun memoirFormHelp(form: MemoryBookNarrativeForm, zh: Boolean): String = when (form) {
    MemoryBookNarrativeForm.EXISTING -> if (zh) "按已有篇章和你写下的要求整理。" else "Arrange the saved chapters using your instructions."
    MemoryBookNarrativeForm.CHRONICLE -> if (zh) "沿已有时间线讲述，未知日期先问家人。" else "Follow known events; ask the family about uncertain dates."
    MemoryBookNarrativeForm.ESSAY -> if (zh) "温暖地回望，保留家人的真实说法。" else "Reflect warmly while keeping each person's account intact."
    MemoryBookNarrativeForm.LONG_MEMOIR -> if (zh) "用开篇、衔接和回望连起各篇章。" else "Connect the chapters with an opening, transitions and reflection."
}

private fun bookNarrativeStatus(status: MemoryBookNarrativeStatus, zh: Boolean): String = when (status) {
    MemoryBookNarrativeStatus.IDLE -> ""
    MemoryBookNarrativeStatus.CHECKING_PLAN -> if (zh) "正在检查已保存的篇章…" else "Checking the saved chapters…"
    MemoryBookNarrativeStatus.PLAN_READY -> if (zh) "篇章已检查，可以由你确认生成建议。" else "The chapters are checked. You can choose to request a draft."
    MemoryBookNarrativeStatus.SMALLER_SCOPE -> if (zh) "整本内容超过本次处理范围，请缩小回忆册，或分别整理各个故事。整理要求已保留。" else "This memoir exceeds the current scope. Use a smaller memoir or arrange individual stories. Your instructions are kept."
    MemoryBookNarrativeStatus.VIEW_ONLY -> if (zh) "可以查看篇章；整理整本建议需要编辑权限。" else "You can view the chapters. Drafting the whole memoir requires edit permission."
    MemoryBookNarrativeStatus.PLAN_FAILED -> if (zh) "未能完成篇章检查，整理要求已保留。" else "The chapter check could not finish. Your instructions are kept."
    MemoryBookNarrativeStatus.QUEUING -> if (zh) "正在提交整理请求…" else "Submitting the draft request…"
    MemoryBookNarrativeStatus.RETRY_REQUIRED -> if (zh) "请求尚未确认，请重试同一份请求，整理要求已保留。" else "The request is unconfirmed. Retry the same request; your instructions are kept."
    MemoryBookNarrativeStatus.QUEUED -> if (zh) "整理建议已排队。" else "The draft is queued."
    MemoryBookNarrativeStatus.RUNNING -> if (zh) "正在整理整本回忆册。" else "Arranging the memoir draft."
    MemoryBookNarrativeStatus.REVIEW_READY -> if (zh) "建议已准备好，请逐章核对。" else "The suggestion is ready for chapter review."
    MemoryBookNarrativeStatus.DRAFT_FAILED -> if (zh) "本次整理未完成，原故事保持原样。" else "The draft could not finish. The original stories are unchanged."
    MemoryBookNarrativeStatus.DRAFT_STALE -> if (zh) "回忆册或来源已变化，这份建议不再适用于当前内容。" else "The memoir or sources changed. This suggestion no longer matches the current content."
    MemoryBookNarrativeStatus.DRAFT_CANCELLED -> if (zh) "整理请求已取消。" else "The draft request was cancelled."
}

private fun bookNarrativeFailure(failure: MemoryBookNarrativeFailure, zh: Boolean): String = when (failure) {
    MemoryBookNarrativeFailure.NETWORK -> if (zh) "当前离线，请联网后重试。" else "Offline. Reconnect before retrying."
    MemoryBookNarrativeFailure.TLS -> if (zh) "未能建立安全连接，请检查服务地址。" else "A secure connection could not be established. Check the service address."
    MemoryBookNarrativeFailure.SERVICE_UNAVAILABLE -> if (zh) "服务暂不可用，请稍后重试。" else "The service is unavailable. Try again later."
    MemoryBookNarrativeFailure.RATE_LIMITED -> if (zh) "请求较多，请稍后重试。" else "Too many requests. Try again later."
    MemoryBookNarrativeFailure.SCOPE_CHANGED -> if (zh) "内容版本已变化，请重新打开并核对回忆册。" else "The content changed. Reopen and review the memoir."
    MemoryBookNarrativeFailure.TOO_LARGE -> if (zh) "内容超过本次处理范围，请缩小范围。" else "The content exceeds the current processing scope. Reduce it."
    MemoryBookNarrativeFailure.INVALID_RESPONSE -> if (zh) "收到的建议与当前篇章不匹配，未显示建议文字。" else "The response does not match the current chapters. Its suggested text is hidden."
    MemoryBookNarrativeFailure.INVALID_REQUEST -> if (zh) "未能提交这份请求，请核对整理要求与篇章。" else "The request could not be submitted. Check the instructions and chapters."
    MemoryBookNarrativeFailure.UNKNOWN -> if (zh) "暂时无法确认处理结果，整理要求已保留。" else "The result is unconfirmed. Your instructions are kept."
}
