package dev.photohouse.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.AssistantWorkspaceError
import dev.photohouse.connected.core.AssistantWorkspacePreference
import dev.photohouse.connected.core.AssistantWorkspaceRequestStatus
import dev.photohouse.connected.core.AssistantWorkspaceState
import java.time.Instant

/** Local UI for the opt-in, account-private conversation workspace. */
@Composable
@OptIn(ExperimentalLayoutApi::class)
internal fun PrivateAssistantPanel(
    state: AssistantWorkspaceState,
    zh: Boolean,
    onNew: () -> Unit,
    onRefresh: () -> Unit,
    onOpenThread: (String, Long) -> Unit,
    onDraft: (String) -> Unit,
    onSend: () -> Unit,
    onRecover: () -> Unit,
    onReconcileCreation: (() -> Unit)? = null,
    onDelete: (String, Long) -> Unit,
    onSetLocale: (String?) -> Unit,
    onDismiss: () -> Unit,
    onOpenAsset: (String) -> Unit = {},
    onAbandonPending: ((String, String, Long) -> Unit)? = null,
    onContinueVoice: ((String, Long) -> Unit)? = null,
    onContinueText: ((String, Long) -> Unit)? = null,
    onLoadOlder: ((String, Long, Long) -> Unit)? = null,
    onReloadHistory: ((String, Long) -> Unit)? = null,
    onOpenSavedMemoryCard: (Int) -> Unit = {},
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val capabilities = state.capabilities
    val historyReady = capabilities?.let { it.available && it.threads } == true
    val ready = historyReady && capabilities?.serverOwnedTurns == true
    val pending = state.pendingTurn != null
    val scopeAvailable = state.accountId != null && state.libraryId != null
    val controlsEnabled = historyReady && !state.busy && !pending && state.pendingCreationId == null && scopeAvailable
    val draftBytes = state.draft.toByteArray(Charsets.UTF_8).size
    val draftValid = state.draft.isNotBlank() && draftBytes in 1..1024
    val detail = state.detail
    val currentTurn = state.currentTurn
    val keyboard = LocalSoftwareKeyboardController.current
    val focusManager = LocalFocusManager.current
    var showDeleteDialog by remember(state.accountId, state.libraryId, state.generation, detail?.thread?.threadId) {
        mutableStateOf(false)
    }
    var deleteAcknowledged by remember(state.accountId, state.libraryId, state.generation, detail?.thread?.threadId) {
        mutableStateOf(false)
    }
    var deleteTarget by remember(state.accountId, state.libraryId, state.generation, detail?.thread?.threadId) {
        mutableStateOf<Pair<String, Long>?>(null)
    }
    var showAbandonDialog by remember(state.accountId, state.libraryId, state.generation, state.pendingTurn?.requestId) {
        mutableStateOf(false)
    }
    var abandonAcknowledged by remember(state.accountId, state.libraryId, state.generation, state.pendingTurn?.requestId) {
        mutableStateOf(false)
    }
    var preservedPendingQuestion by remember(state.accountId, state.libraryId, state.generation) { mutableStateOf<String?>(null) }
    var preservedLocalDraft by remember(state.accountId, state.libraryId, state.generation) { mutableStateOf<String?>(null) }
    var managementExpanded by remember(state.accountId, state.libraryId, state.generation, detail?.thread?.threadId) {
        mutableStateOf(detail == null)
    }
    val managementForcedOpen = detail == null || state.pendingCreationId != null || pending || state.uncertain ||
        state.error != null || showDeleteDialog || showAbandonDialog || preservedPendingQuestion != null ||
        preservedLocalDraft != null
    val managementVisible = managementExpanded || managementForcedOpen
    val send: () -> Unit = {
        if (controlsEnabled && ready && state.continuationEnabled && draftValid) {
            keyboard?.hide()
            focusManager.clearFocus()
            onSend()
        }
    }

    BoxWithConstraints(Modifier.fillMaxSize().safeDrawingPadding()) {
        val compact = maxHeight < 640.dp
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .imePadding().padding(horizontal = 16.dp, vertical = if (compact) 8.dp else 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(t("Private conversations", "私人对话"), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-dismiss")) {
                    Text(t("Back to assistant", "返回助手"))
                }
            }
            Text(
                t("Account-private history · Text and status expire after 30 days; audio is temporary.",
                    "账号私有记录 · 文本和状态保留 30 天；音频仅临时处理。"),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.testTag("private-assistant-retention"),
            )

            if (detail != null) {
                Card(
                    modifier = Modifier.fillMaxWidth().testTag("private-assistant-current-summary"),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
                ) {
                    Row(
                        Modifier.fillMaxWidth().padding(start = 12.dp, top = 4.dp, bottom = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Column(Modifier.weight(1f).padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(t("Current conversation", "当前对话"), style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(detail.thread.label ?: t("Private conversation", "私人对话"),
                                style = MaterialTheme.typography.bodyMedium)
                            if (state.historyRefreshRequired) {
                                Text(t("Refresh needed", "需要刷新记录"), style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.tertiary,
                                    modifier = Modifier.testTag("private-assistant-refresh-needed"))
                            } else {
                                Text(t("${detail.thread.exchangeCount} exchanges", "${detail.thread.exchangeCount} 轮对话"),
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        OutlinedButton(
                            onClick = { managementExpanded = !managementExpanded },
                            enabled = historyReady && !managementForcedOpen,
                            modifier = Modifier.padding(end = 8.dp).heightIn(min = 48.dp)
                                .semantics { stateDescription = if (managementVisible) t("Expanded", "已展开") else t("Collapsed", "已收起") }
                                .testTag("private-assistant-manage-toggle"),
                        ) {
                            Text(if (managementVisible) t("Back to conversation", "返回对话")
                                else t("Manage conversations", "管理对话"))
                        }
                    }
                }
            }

            when {
                capabilities == null -> {
                    Text(t("Private conversations are not available yet. Check availability to continue.", "私人对话暂不可用。请检查当前状态后继续。"),
                        style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("private-assistant-unavailable"))
                    OutlinedButton(onClick = onRefresh, enabled = !state.busy && scopeAvailable,
                        modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-refresh")) {
                        Text(if (state.busy) t("Checking…", "正在检查…") else t("Check availability", "检查可用状态"))
                    }
                }
                !historyReady -> {
                    Text(t("Private server-owned conversations are unavailable for this library.", "此资料库暂未开放由服务器管理的私人对话。"),
                        style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("private-assistant-unavailable"))
                    OutlinedButton(onClick = onRefresh, enabled = !state.busy && scopeAvailable,
                        modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-refresh")) { Text(t("Retry", "重试")) }
                }
                else -> {
                    if (!ready) Text(t("Search is temporarily unavailable. Your saved conversations are still readable.",
                        "检索暂不可用，仍可查看已保存的对话。"), style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("private-assistant-search-unavailable"))
                    if (managementVisible) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = { if (state.pendingCreationId != null) onReconcileCreation?.invoke() else onNew() },
                            enabled = scopeAvailable && !state.busy && !pending,
                            modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("private-assistant-new"),
                        ) {
                            Text(if (state.pendingCreationId != null) t("Check creation status", "检查创建状态")
                                else t("New conversation", "新建对话"))
                        }
                        OutlinedButton(
                            onClick = onRefresh, enabled = scopeAvailable && !state.busy,
                            modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-refresh"),
                        ) { Text(t("Refresh", "刷新")) }
                    }

                    if (state.pendingCreationId != null) {
                        Text(t("A conversation creation may still be completing. Check the same request before starting another.",
                            "对话创建可能仍在完成中。请先检查同一请求，再开始其他操作。"),
                            color = MaterialTheme.colorScheme.tertiary, style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.testTag("private-assistant-pending-creation"))
                        OutlinedButton(
                            onClick = onNew,
                            enabled = scopeAvailable && !state.busy && !pending,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                .testTag("private-assistant-retry-creation"),
                        ) {
                            Text(t("Retry creation with the same ID", "使用相同 ID 重试创建"))
                        }
                    }

                    if (preservedPendingQuestion != null || preservedLocalDraft != null) {
                        Card(
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
                            modifier = Modifier.fillMaxWidth().testTag("private-assistant-abandoned-request"),
                        ) {
                            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text(t("Kept on this phone · not resubmitted", "已保留在此手机 · 未重新发送"),
                                    style = MaterialTheme.typography.titleSmall,
                                    color = MaterialTheme.colorScheme.onSecondaryContainer)
                                preservedPendingQuestion?.let { question ->
                                    Text(t("Previous question", "上一条问题"), style = MaterialTheme.typography.labelMedium)
                                    Text(question, style = MaterialTheme.typography.bodyMedium)
                                    OutlinedButton(
                                        onClick = { onDraft(question) },
                                        enabled = scopeAvailable && !state.busy,
                                        modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-restore-question"),
                                    ) { Text(t("Use previous question as a draft", "将上一条问题放入草稿")) }
                                }
                                preservedLocalDraft?.takeIf { it.isNotEmpty() }?.let { localDraft ->
                                    Text(t("Unsent draft", "未发送的草稿"), style = MaterialTheme.typography.labelMedium)
                                    Text(localDraft, style = MaterialTheme.typography.bodyMedium)
                                    OutlinedButton(
                                        onClick = { onDraft(localDraft) },
                                        enabled = scopeAvailable && !state.busy,
                                        modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-restore-draft"),
                                    ) { Text(t("Restore unsent draft", "恢复未发送草稿")) }
                                }
                            }
                        }
                    }

                    val availableThreads = state.threads?.threads.orEmpty()
                    if (availableThreads.isNotEmpty()) {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.testTag("private-assistant-thread-list")) {
                            Text(t("Your conversations", "你的对话"), style = MaterialTheme.typography.titleMedium)
                            availableThreads.forEach { thread ->
                                val selected = state.detail?.thread?.threadId == thread.threadId
                                OutlinedButton(
                                    onClick = { onOpenThread(thread.threadId, thread.revision) },
                                    enabled = scopeAvailable && !state.busy && !pending,
                                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                        .testTag("private-assistant-thread-${thread.threadId}"),
                                ) {
                                    Text(
                                        text = buildString {
                                            append(if (selected) "• " else "")
                                            append(thread.label ?: t("Conversation", "对话"))
                                            if (!state.historyRefreshRequired) {
                                                append(" · ")
                                                append(thread.exchangeCount)
                                                append(t(" exchanges · ", " 轮 · "))
                                                append(displayPrivateDate(thread.updatedAt))
                                            }
                                        },
                                        style = MaterialTheme.typography.bodyMedium,
                                    )
                                }
                            }
                        }
                    } else {
                        Text(t("No saved conversations in this library yet.", "此资料库中还没有保存的对话。"),
                            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    }

                    if (detail != null) {
                        FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            Text(t("Conversation history", "对话记录"), style = MaterialTheme.typography.titleMedium,
                                modifier = Modifier.testTag("private-assistant-history-heading"))
                            if (managementVisible) TextButton(
                                onClick = {
                                    deleteTarget = detail.thread.threadId to detail.thread.revision
                                    showDeleteDialog = true
                                    deleteAcknowledged = false
                                },
                                enabled = !state.busy && !pending,
                                modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-delete"),
                            ) { Text(t("Delete conversation", "删除对话"), color = MaterialTheme.colorScheme.error) }
                        }
                        if ((onContinueVoice != null || onContinueText != null) && ready && state.continuationEnabled &&
                            state.pendingTurn == null && !state.busy && scopeAvailable) {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                if (onContinueText != null) OutlinedButton(
                                    onClick = { onContinueText(detail.thread.threadId, detail.thread.revision) },
                                    modifier = Modifier.weight(1f).heightIn(min = 48.dp)
                                        .testTag("private-assistant-continue-text"),
                                ) {
                                    Text(t("Continue chatting", "继续聊天"))
                                }
                                if (onContinueVoice != null) OutlinedButton(
                                    onClick = { onContinueVoice(detail.thread.threadId, detail.thread.revision) },
                                    modifier = Modifier.weight(1f).heightIn(min = 48.dp)
                                        .testTag("private-assistant-continue-voice"),
                                ) {
                                    Text(t("Continue with voice in this conversation", "在这个对话中语音聊"))
                                }
                            }
                        }
                        if (state.historyRefreshRequired) {
                            Text(t("This conversation has changed. Reload its history before continuing.", "对话已有更新，请重新加载记录后继续。"),
                                style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("private-assistant-history-changed"))
                            onReloadHistory?.let { reload -> OutlinedButton(
                                onClick = { reload(detail.thread.threadId, detail.thread.revision) },
                                enabled = !state.busy && !pending, modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-history-reload"),
                            ) { Text(t("Reload history", "重新加载记录")) } }
                        } else if (detail.hasOlderExchanges) {
                            val before = detail.exchanges.firstOrNull()?.revision
                            if (capabilities.historyPaging && before != null && onLoadOlder != null) {
                                OutlinedButton(onClick = { onLoadOlder(detail.thread.threadId, detail.thread.revision, before) },
                                    enabled = !state.busy && !pending && state.pendingCreationId == null,
                                    modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-history-older")) {
                                    Text(t("Read earlier messages", "查看更早消息"))
                                }
                            } else Text(t("Showing recent complete messages. Earlier history is not available on this server.",
                                "正在显示最近的完整消息；此服务器暂不支持查看更早记录。"),
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.testTag("private-assistant-history-older"))
                        }
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("private-assistant-history")) {
                            detail.exchanges.forEachIndexed { index, exchange ->
                                Card(
                                    modifier = Modifier.fillMaxWidth().testTag("private-assistant-exchange-$index"),
                                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
                                ) {
                                    Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                        if (!state.historyRefreshRequired) Text(displayPrivateDate(exchange.createdAt),
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        Text(t("You", "你"), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                                        Text(exchange.inputText, style = MaterialTheme.typography.bodyLarge)
                                        Text(t("Assistant", "助手"), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.tertiary)
                                        Text(exchange.reply, style = MaterialTheme.typography.bodyLarge)
                                        if (exchange.cards.isNotEmpty()) {
                                            Text(exchange.cards.joinToString(" · ") { card ->
                                                "${workspaceCardLabel(card.type, zh)}: ${card.count}"
                                            }, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        }
                                    }
                                }
                            }
                        }

                        currentTurn?.takeIf { it.status == AssistantWorkspaceRequestStatus.COMPLETED }?.result?.let { result ->
                            if (currentTurn.recovered.not() && result.memoryCards.isNotEmpty()) {
                                Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("private-assistant-memory-cards")) {
                                    Text(t("Saved memories", "已保存的回忆"), style = MaterialTheme.typography.titleSmall)
                                    result.memoryCards.forEachIndexed { ordinal, card ->
                                        Card(Modifier.fillMaxWidth().testTag("private-assistant-memory-card-$ordinal"),
                                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
                                            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                                Text(card.title, style = MaterialTheme.typography.titleMedium)
                                                Text(card.excerpt, style = MaterialTheme.typography.bodyLarge)
                                                OutlinedButton(
                                                    onClick = { onOpenSavedMemoryCard(ordinal) },
                                                    enabled = scopeAvailable && !state.busy && state.pendingTurn == null &&
                                                        state.savedMemoryReaderAvailable && state.memoryReaderOrdinal != ordinal,
                                                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                                        .testTag("private-assistant-open-memory-$ordinal"),
                                                ) {
                                                    Text(if (card.kind == "story") t("Open saved story", "打开已保存故事")
                                                        else t("Open memoir", "打开回忆录"))
                                                }
                                                if (state.memoryReaderOrdinal == ordinal) Text(
                                                    t("Opening…", "正在打开…"), style = MaterialTheme.typography.bodySmall,
                                                    modifier = Modifier.testTag("private-assistant-memory-opening-$ordinal"))
                                                if (state.memoryReaderErrorOrdinal == ordinal && state.memoryReaderHandoff == null) {
                                                    Text(t("Could not open this memory. Retry from this card.", "无法打开这段回忆。请从此卡片重试。"),
                                                        style = MaterialTheme.typography.bodySmall,
                                                        color = MaterialTheme.colorScheme.error,
                                                        modifier = Modifier.testTag("private-assistant-memory-error-$ordinal"))
                                                    TextButton(onClick = { onOpenSavedMemoryCard(ordinal) },
                                                        enabled = scopeAvailable && !state.busy && state.pendingTurn == null,
                                                        modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-memory-retry-$ordinal")) {
                                                        Text(t("Retry", "重试"))
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            if (result.items.isNotEmpty()) {
                                Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.testTag("private-assistant-grounded-results")) {
                                    Text(t("Available results · open only when you choose", "可查看的结果 · 仅在你选择时打开"),
                                        style = MaterialTheme.typography.titleSmall)
                                    result.items.forEach { asset ->
                                        OutlinedButton(
                                            onClick = { onOpenAsset(asset.id) },
                                            enabled = scopeAvailable && !state.busy,
                                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                                .testTag("private-assistant-open-asset-${asset.id}"),
                                        ) {
                                            Text(
                                                listOfNotNull(asset.taken_at ?: asset.date_hint?.value,
                                                    if(asset.kind == "video") t("Video", "视频") else t("Photo", "照片"))
                                                    .joinToString(" · "),
                                            )
                                        }
                                    }
                                }
                            }
                        }

                        if (state.uncertain && state.pendingTurn != null) {
                            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                                modifier = Modifier.fillMaxWidth().testTag("private-assistant-uncertain")) {
                                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(t("The last response is uncertain. Check its saved status before continuing; this only reads the existing request.",
                                        "上一条回复状态不确定。请先查询已保存的状态再继续；此操作只读取现有请求。"),
                                        style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onErrorContainer)
                                    Button(onClick = onRecover, enabled = scopeAvailable && !state.busy,
                                        modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-recover")) {
                                        Text(if (state.busy) t("Checking…", "正在查询…") else t("Check saved status", "查询已保存状态"))
                                    }
                                    if (onAbandonPending != null) {
                                        OutlinedButton(
                                            onClick = { showAbandonDialog = true; abandonAcknowledged = false },
                                            enabled = scopeAvailable && !state.busy,
                                            modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-abandon-pending"),
                                        ) {
                                            Text(t("Leave this request and start a new conversation", "放下这次请求，开始新对话"))
                                        }
                                    }
                                }
                            }
                        }

                        state.error?.let { error ->
                            Text(workspaceErrorText(error, zh), color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("private-assistant-error"))
                        }

                        if (managementVisible) {
                        val localeSupported = capabilities.preferences && capabilities.preferencesApplied &&
                            "locale" in capabilities.appliedPreferences &&
                            state.unsupportedPreferences.contains(AssistantWorkspacePreference.LOCALE).not()
                        if (localeSupported && state.preferences != null) {
                            Column(verticalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.testTag("private-assistant-locale")) {
                                Text(t("Reply language", "回复语言"), style = MaterialTheme.typography.titleSmall)
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    listOf(null to t("Follow request language", "跟随请求语言"), "zh" to "中文", "en" to "English").forEach { (locale, label) ->
                                        val selected = state.preferences?.locale == locale
                                        if (selected) Button(onClick = {}, enabled = false, modifier = Modifier.heightIn(min = 48.dp)) { Text(label) }
                                        else OutlinedButton(onClick = { onSetLocale(locale) }, enabled = controlsEnabled,
                                            modifier = Modifier.heightIn(min = 48.dp)) { Text(label) }
                                    }
                                }
                            }
                        }
                        val unsupported = state.unsupportedPreferences.filter { it != AssistantWorkspacePreference.LOCALE }
                        if (unsupported.isNotEmpty()) Text(
                            t("Other saved response preferences are not applied in this client.", "此客户端不会应用其他已保存的回复偏好。"),
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.testTag("private-assistant-unsupported-preferences"),
                        )
                        }

                        val currentTurnState = state.currentTurn?.status
                        if (currentTurnState == AssistantWorkspaceRequestStatus.FAILED || currentTurnState == AssistantWorkspaceRequestStatus.INTERRUPTED) {
                            Text(
                                if (currentTurnState == AssistantWorkspaceRequestStatus.FAILED) t("The server could not complete that response.", "服务器未能完成这次回复。")
                                else t("That response was interrupted. Refresh the conversation before trying again.", "这次回复已中断。请刷新对话后再试。"),
                                color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }

                    if (detail == null) {
                        Text(t("Choose a saved conversation or start a new one. Each conversation is private to your account and library.",
                            "选择已有对话或开始新对话。每段对话仅属于你的账号和资料库。"),
                            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    } else {
                        OutlinedTextField(
                            value = state.draft,
                            onValueChange = onDraft,
                            enabled = ready && scopeAvailable && !state.busy,
                            modifier = Modifier.fillMaxWidth().testTag("private-assistant-composer"),
                            label = { Text(t("Your message", "输入消息")) },
                            supportingText = {
                                Text(
                                    if (draftBytes > 1024) {
                                        t("Message is too long. Shorten it before sending.", "内容太长，请缩短后发送。")
                                    } else {
                                        t("Write your question; you can edit it before sending.", "写下问题，发送前可以修改。")
                                    },
                                )
                            },
                            minLines = if (compact) 2 else 3,
                            maxLines = 7,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                            keyboardActions = KeyboardActions(onSend = { send() }),
                        )
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween) {
                            TextButton(onClick = { onRefresh() }, enabled = scopeAvailable && !state.busy,
                                modifier = Modifier.heightIn(min = 48.dp)) { Text(t("Refresh history", "刷新记录")) }
                            Button(onClick = send, enabled = controlsEnabled && ready && state.continuationEnabled && draftValid,
                                modifier = Modifier.heightIn(min = 48.dp).testTag("private-assistant-send")) {
                                Text(if (state.busy) t("Sending…", "正在发送…") else t("Send", "发送"))
                            }
                        }

                    }
                }
            }
        }
    }

    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false; deleteAcknowledged = false },
            title = { Text(t("Delete this conversation?", "删除这段对话？")) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(t("This removes the saved text and references for this conversation. This action cannot be undone.",
                        "这会删除此对话保存的文本和引用，且无法撤销。"))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = deleteAcknowledged, onCheckedChange = { deleteAcknowledged = it },
                            modifier = Modifier.testTag("private-assistant-delete-ack"))
                        Text(t("I understand this conversation will be deleted.", "我了解这段对话将被删除。"),
                            modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    }
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val target = deleteTarget
                        showDeleteDialog = false
                        deleteAcknowledged = false
                        deleteTarget = null
                        if (target != null) onDelete(target.first, target.second)
                    },
                    enabled = deleteAcknowledged && !state.busy && state.pendingTurn == null,
                    modifier = Modifier.testTag("private-assistant-delete-confirm"),
                ) { Text(t("Delete permanently", "永久删除"), color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false; deleteAcknowledged = false },
                    modifier = Modifier.testTag("private-assistant-delete-cancel")) { Text(t("Cancel", "取消")) }
            },
            modifier = Modifier.testTag("private-assistant-delete-dialog"),
        )
    }

    if (showAbandonDialog && state.pendingTurn != null && onAbandonPending != null) {
        AlertDialog(
            onDismissRequest = { showAbandonDialog = false; abandonAcknowledged = false },
            title = { Text(t("Leave this uncertain request?", "放下这次状态不确定的请求？")) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(t(
                        "The server may still complete the previous request. Its submitted question and your unsent draft will remain available on this phone, and nothing will be sent again automatically. This does not delete the saved conversation or write a family memory.",
                        "服务器仍可能完成上一条请求。已提交的问题和未发送草稿会保留在此手机，不会自动再次发送。此操作不会删除已保存的对话，也不会写入家庭回忆。",
                    ))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = abandonAcknowledged,
                            onCheckedChange = { abandonAcknowledged = it },
                            modifier = Modifier.testTag("private-assistant-abandon-ack"),
                        )
                        Text(t("I understand the previous request may still complete.", "我了解上一条请求仍可能完成。"),
                            modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    }
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val pendingTurn = state.pendingTurn
                        if (pendingTurn == null) return@TextButton
                        preservedPendingQuestion = pendingTurn.text
                        preservedLocalDraft = state.draft
                        showAbandonDialog = false
                        abandonAcknowledged = false
                        val renderedRevision = state.detail?.thread?.revision
                        if (renderedRevision != null) {
                            onAbandonPending(pendingTurn.threadId, pendingTurn.requestId, renderedRevision)
                        }
                    },
                    enabled = abandonAcknowledged && !state.busy && state.pendingTurn != null,
                    modifier = Modifier.testTag("private-assistant-abandon-confirm"),
                ) { Text(t("Leave request", "放下请求")) }
            },
            dismissButton = {
                TextButton(onClick = { showAbandonDialog = false; abandonAcknowledged = false },
                    modifier = Modifier.testTag("private-assistant-abandon-cancel")) { Text(t("Keep checking", "继续查询")) }
            },
            modifier = Modifier.testTag("private-assistant-abandon-dialog"),
        )
    }
}

private fun displayPrivateDate(value: String): String = runCatching {
    Instant.parse(value).toString().replace('T', ' ').removeSuffix("Z").take(16)
}.getOrElse { value.take(32) }

private fun workspaceCardLabel(type: String, zh: Boolean): String = when (type) {
    "asset" -> if (zh) "照片或视频" else "media"
    "person" -> if (zh) "人物" else "people"
    "location" -> if (zh) "地点" else "places"
    "tag" -> if (zh) "标签" else "tags"
    else -> type.take(32)
}

private fun workspaceErrorText(error: AssistantWorkspaceError, zh: Boolean): String = when (error) {
    AssistantWorkspaceError.UNAVAILABLE -> if (zh) "私人对话当前不可用。" else "Private conversations are currently unavailable."
    AssistantWorkspaceError.ACCESS_DENIED -> if (zh) "资料库访问权限已改变。" else "Library access has changed."
    AssistantWorkspaceError.INVALID_REQUEST -> if (zh) "无法处理此操作，请检查输入后重试。" else "This action could not be processed. Check the input and try again."
    AssistantWorkspaceError.CONTEXT_CHANGED -> if (zh) "对话上下文已改变，请刷新后继续。" else "The conversation context changed. Refresh before continuing."
    AssistantWorkspaceError.NETWORK -> if (zh) "网络暂不可用。" else "The network is temporarily unavailable."
    AssistantWorkspaceError.INVALID_RESPONSE -> if (zh) "服务器返回的内容无法验证。" else "The server response could not be verified."
    AssistantWorkspaceError.TURN_FAILED -> if (zh) "服务器未能完成这次回复。" else "The server could not complete this response."
    AssistantWorkspaceError.TURN_INTERRUPTED -> if (zh) "这次回复处理中断。" else "This response was interrupted."
    AssistantWorkspaceError.UNKNOWN -> if (zh) "操作未完成。" else "The action did not complete."
}
