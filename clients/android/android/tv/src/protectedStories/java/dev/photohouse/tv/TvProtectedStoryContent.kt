package dev.photohouse.tv

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import kotlinx.coroutines.flow.StateFlow

enum class TvStoryApprovalStage { SIGN_IN, LIBRARIES, STORIES, REVIEW, APPLIED, SAVED, UNCERTAIN, ERROR }

enum class TvStoryApprovalIssue {
    SIGN_IN_FAILED, ACCESS_ENDED, LOAD_FAILED, SUGGESTION_CHANGED, SAVE_FAILED, CONFLICT,
}

data class TvStoryApprovalLibrary(val id: String, val title: String)

data class TvStoryApprovalStory(
    val id: String,
    val title: String,
    val revision: Long,
    val chapterCount: Int,
)

data class TvStoryApprovalChapter(
    val id: String,
    val title: String,
    val originalText: String,
    val suggestedText: String?,
    val changed: Boolean,
)

data class TvStoryApprovalUiState(
    val stage: TvStoryApprovalStage = TvStoryApprovalStage.SIGN_IN,
    val busy: Boolean = false,
    val issue: TvStoryApprovalIssue? = null,
    val libraries: List<TvStoryApprovalLibrary> = emptyList(),
    val stories: List<TvStoryApprovalStory> = emptyList(),
    val page: Int = 1,
    val hasMore: Boolean = false,
    val currentStory: TvStoryApprovalStory? = null,
    val currentChapters: List<TvStoryApprovalChapter> = emptyList(),
    val focusedChapterId: String? = null,
    val dirty: Boolean = false,
    val writeStarted: Boolean = false,
    val canStart: Boolean = false,
    val canRefresh: Boolean = false,
    val canApply: Boolean = false,
    val unlinkedSourceCount: Int = 0,
    val questions: List<String> = emptyList(),
)

sealed interface TvStoryApprovalAction {
    class SignIn(val phone: String, val password: String) : TvStoryApprovalAction
    data class ChooseLibrary(val id: String) : TvStoryApprovalAction
    data class LoadStories(val page: Int) : TvStoryApprovalAction
    data class OpenStory(val id: String) : TvStoryApprovalAction
    data object RefreshCurrent : TvStoryApprovalAction
    data object StartCurrent : TvStoryApprovalAction
    data object ApplyProposal : TvStoryApprovalAction
    data object Save : TvStoryApprovalAction
    data object RetrySave : TvStoryApprovalAction
    data object DiscardApplied : TvStoryApprovalAction
    data object SignOut : TvStoryApprovalAction
    data object Cancel : TvStoryApprovalAction
}

interface TvStoryApprovalController {
    val state: StateFlow<TvStoryApprovalUiState>
    fun dispatch(action: TvStoryApprovalAction)
}

@Composable
fun TvProtectedStoryContent(
    controller: TvStoryApprovalController,
    zh: Boolean,
    onClose: () -> Unit,
) {
    val state by controller.state.collectAsState()
    var phone by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmDiscard by remember { mutableStateOf(false) }
    var confirmUncertainClose by remember { mutableStateOf(false) }
    var privateScreenCovered by remember { mutableStateOf(false) }
    var applyPressed by remember { mutableStateOf(false) }
    var savePressed by remember { mutableStateOf(false) }
    val chapterFocus = remember { FocusRequester() }
    val saveFocus = remember { FocusRequester() }
    val stageFocus = remember { FocusRequester() }
    val lifecycleOwner = LocalLifecycleOwner.current
    fun t(en: String, cn: String) = if (zh) cn else en

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_PAUSE, Lifecycle.Event.ON_STOP -> {
                    privateScreenCovered = true
                    phone = ""
                    password = ""
                    confirmDiscard = false
                    confirmUncertainClose = false
                }
                Lifecycle.Event.ON_RESUME -> privateScreenCovered = false
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    val focusedChapter = state.currentChapters.firstOrNull { it.id == state.focusedChapterId }
        ?: state.currentChapters.firstOrNull { it.changed }
    val issueMessage = when (state.issue) {
        TvStoryApprovalIssue.SIGN_IN_FAILED -> t("Sign-in failed. Check the account details and try again.", "登录失败，请检查账户信息后重试。")
        TvStoryApprovalIssue.ACCESS_ENDED -> t("Library access ended. Sign in again.", "相册库访问已结束，请重新登录。")
        TvStoryApprovalIssue.LOAD_FAILED -> t("Stories could not load. Retry when ready.", "故事暂时无法加载，请重试。")
        TvStoryApprovalIssue.SUGGESTION_CHANGED -> t("This story changed. Refresh it before applying the suggestion.", "故事内容已变化，请刷新后再应用建议。")
        TvStoryApprovalIssue.SAVE_FAILED -> t("Save failed. Your draft is still available.", "保存失败，草稿仍可继续处理。")
        TvStoryApprovalIssue.CONFLICT -> t("This story changed elsewhere. Refresh and review the current version.", "故事已在其他位置更改，请刷新并核对最新版本。")
        null -> null
    }
    LaunchedEffect(state.stage, state.focusedChapterId, focusedChapter?.id) {
        if (state.stage == TvStoryApprovalStage.APPLIED && focusedChapter != null) {
            withFrameNanos { }
            runCatching { chapterFocus.requestFocus() }
        }
    }
    LaunchedEffect(state.stage, state.busy) {
        if (state.stage != TvStoryApprovalStage.APPLIED && !state.busy) {
            withFrameNanos { }
            runCatching { stageFocus.requestFocus() }
        }
    }
    LaunchedEffect(state.stage, state.busy, state.issue) {
        if (!state.busy && state.stage != TvStoryApprovalStage.UNCERTAIN) {
            applyPressed = false
            savePressed = false
        }
    }
    fun leave() {
        controller.dispatch(TvStoryApprovalAction.Cancel)
        onClose()
    }
    BackHandler {
        if (state.stage == TvStoryApprovalStage.APPLIED && state.dirty && (state.writeStarted || state.busy)) {
            confirmUncertainClose = true
        } else if (state.stage == TvStoryApprovalStage.APPLIED && state.dirty) {
            confirmDiscard = true
        } else if (state.stage == TvStoryApprovalStage.UNCERTAIN) {
            confirmUncertainClose = true
        } else leave()
    }

    MaterialTheme(colorScheme = darkColorScheme(primary = Gold, background = Ink, surface = Ink, onSurface = Cream)) {
        Column(Modifier.fillMaxSize().testTag("protected-story-content"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (privateScreenCovered) {
                Text(t("Private story content is covered.", "私人故事内容已隐藏。"),
                    Modifier.testTag("story-private-covered"), style = MaterialTheme.typography.headlineMedium)
            } else {
            issueMessage?.let { message ->
                Surface(Modifier.fillMaxWidth().testTag("story-message"), color = Moss,
                    shape = RoundedCornerShape(10.dp), border = BorderStroke(1.dp, Edge)) {
                    Text(message, Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                        style = MaterialTheme.typography.bodyLarge, color = Cream)
                }
            }
            when (state.stage) {
                TvStoryApprovalStage.SIGN_IN -> SignInStage(
                    zh, state.busy, phone, password, stageFocus,
                    onPhone = { phone = it }, onPassword = { password = it },
                    onSignIn = {
                        val enteredPhone = phone.trim()
                        val enteredPassword = password
                        password = ""
                        controller.dispatch(TvStoryApprovalAction.SignIn(enteredPhone, enteredPassword))
                    }, onCancel = ::leave,
                )
                TvStoryApprovalStage.LIBRARIES -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).testTag("story-libraries"),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(t("Choose a family library", "选择家庭相册库"), style = MaterialTheme.typography.headlineSmall)
                    state.libraries.forEach { library ->
                        TvButton(library.title, Modifier.fillMaxWidth().heightInTv()
                            .then(if (library == state.libraries.firstOrNull()) Modifier.focusRequester(stageFocus) else Modifier)
                            .testTag("story-library-${library.id}"),
                            enabled = !state.busy) { controller.dispatch(TvStoryApprovalAction.ChooseLibrary(library.id)) }
                    }
                    TvButton(t("Sign out", "退出登录"), Modifier.then(if (state.libraries.isEmpty()) Modifier.focusRequester(stageFocus) else Modifier)
                        .testTag("story-sign-out"), enabled = !state.busy) {
                        controller.dispatch(TvStoryApprovalAction.SignOut)
                    }
                }
                TvStoryApprovalStage.STORIES -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).testTag("story-list"),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(t("Stories in this library", "此相册库中的故事"), style = MaterialTheme.typography.headlineSmall)
                    if (state.stories.isEmpty() && !state.busy) Text(t("No stories on this page.", "此页暂无故事。"), style = MaterialTheme.typography.bodyLarge)
                    state.stories.forEach { story ->
                        TvButton("${story.title} · ${story.chapterCount} ${t("chapters", "章")}",
                            Modifier.fillMaxWidth().heightInTv()
                                .then(if (story == state.stories.firstOrNull()) Modifier.focusRequester(stageFocus) else Modifier)
                                .testTag("story-open-${story.id}"), enabled = !state.busy) {
                            controller.dispatch(TvStoryApprovalAction.OpenStory(story.id))
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        TvButton(t("Previous page", "上一页"),
                            Modifier.then(if (state.stories.isEmpty() && state.page > 1) Modifier.focusRequester(stageFocus) else Modifier).testTag("stories-previous"),
                            enabled = !state.busy && state.page > 1) {
                            controller.dispatch(TvStoryApprovalAction.LoadStories(state.page - 1))
                        }
                        Text(t("Page ${state.page}", "第 ${state.page} 页"), style = MaterialTheme.typography.titleMedium)
                        TvButton(t("Next page", "下一页"), Modifier.then(if (state.stories.isEmpty() && state.page == 1) Modifier.focusRequester(stageFocus) else Modifier).testTag("stories-next"),
                            enabled = !state.busy && state.hasMore) {
                            controller.dispatch(TvStoryApprovalAction.LoadStories(state.page + 1))
                        }
                    }
                    TvButton(t("Sign out", "退出登录"), Modifier.then(if (state.stories.isEmpty()) Modifier.focusRequester(stageFocus) else Modifier)
                        .testTag("story-sign-out"), enabled = !state.busy) {
                        controller.dispatch(TvStoryApprovalAction.SignOut)
                    }
                }
                TvStoryApprovalStage.REVIEW -> ReviewStage(
                    state = state, zh = zh, stageFocus = stageFocus,
                    onStart = { controller.dispatch(TvStoryApprovalAction.StartCurrent) },
                    onRefresh = { controller.dispatch(TvStoryApprovalAction.RefreshCurrent) },
                    onApply = {
                        if (!applyPressed) {
                            applyPressed = true
                            controller.dispatch(TvStoryApprovalAction.ApplyProposal)
                        }
                    },
                    onStories = { controller.dispatch(TvStoryApprovalAction.LoadStories(state.page)) },
                    onSignOut = { controller.dispatch(TvStoryApprovalAction.SignOut) },
                )
                TvStoryApprovalStage.APPLIED -> Column(Modifier.fillMaxSize().testTag("story-applied-draft"),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(t("Applied to draft", "已带入草稿"), Modifier.testTag("applied-to-draft"),
                        style = MaterialTheme.typography.headlineSmall, color = Gold)
                    if (state.unlinkedSourceCount > 0) {
                        Text(t("${state.unlinkedSourceCount} source links still need review.", "仍有 ${state.unlinkedSourceCount} 个素材关联需要核对。"),
                            Modifier.testTag("unlinked-source-warning"), style = MaterialTheme.typography.bodyLarge, color = Gold)
                    }
                    val target = focusedChapter
                    if (target != null) {
                        val scroll = rememberScrollState()
                        Column(Modifier.weight(1f).fillMaxWidth()
                            .focusRequester(chapterFocus).focusProperties { down = saveFocus }
                            .remoteReadingPane(scroll).testTag("applied-chapter-focus")) {
                            Column(Modifier.verticalScroll(scroll).padding(12.dp).testTag("applied-chapter-${target.id}"),
                                verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                Text(target.title.ifBlank { t("Changed chapter", "已修改章节") },
                                    style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
                                Text(t("Original", "原文"), style = MaterialTheme.typography.titleLarge, color = Gold)
                                Text(target.originalText, style = MaterialTheme.typography.bodyLarge, lineHeight = MaterialTheme.typography.bodyLarge.lineHeight)
                                Spacer(Modifier.height(4.dp))
                                Text(t("Suggested", "建议稿"), style = MaterialTheme.typography.titleLarge, color = Gold)
                                Text(target.suggestedText.orEmpty(), style = MaterialTheme.typography.bodyLarge, lineHeight = MaterialTheme.typography.bodyLarge.lineHeight,
                                    modifier = Modifier.testTag("chapter-suggested-${target.id}"))
                            }
                        }
                    } else {
                        Text(t("No changed chapter was returned for review.", "没有可供核对的修改章节。"),
                            Modifier.testTag("no-changed-chapter"), style = MaterialTheme.typography.bodyLarge)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        TvButton(t("Save to library", "保存到相册库"), Modifier.focusRequester(saveFocus)
                            .focusProperties { up = chapterFocus }.testTag("story-save-to-library"),
                            enabled = state.dirty && !state.busy && !state.writeStarted && !savePressed && target != null) {
                            savePressed = true
                            controller.dispatch(TvStoryApprovalAction.Save)
                        }
                        TvButton(t("Discard edits", "放弃修改"), Modifier.testTag("story-discard-edits"),
                            enabled = !state.busy && !state.writeStarted) { confirmDiscard = true }
                    }
                }
                TvStoryApprovalStage.SAVED -> Column(Modifier.fillMaxSize().testTag("story-saved"), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text(t("Saved to library", "已保存到相册库"), style = MaterialTheme.typography.headlineMedium, color = Gold)
                    TvButton(t("Back to stories", "返回故事列表"), Modifier.focusRequester(stageFocus).testTag("story-saved-back")) {
                        controller.dispatch(TvStoryApprovalAction.LoadStories(state.page))
                    }
                    TvButton(t("Close", "关闭"), Modifier.testTag("story-saved-close"), onClick = ::leave)
                }
                TvStoryApprovalStage.UNCERTAIN -> Column(Modifier.fillMaxSize().testTag("story-save-uncertain"), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text(t("Save not confirmed", "保存结果尚未确认"), style = MaterialTheme.typography.headlineMedium, color = Gold)
                    Text(t("Retry the same save to confirm its result.", "请重试同一保存请求以确认结果。"), style = MaterialTheme.typography.bodyLarge)
                    TvButton(t("Retry same save", "重试同一保存"), Modifier.focusRequester(stageFocus).testTag("story-save-retry"), enabled = !state.busy) {
                        controller.dispatch(TvStoryApprovalAction.RetrySave)
                    }
                    TvButton(t("Close", "关闭"), Modifier.testTag("story-uncertain-close"), onClick = { confirmUncertainClose = true })
                }
                TvStoryApprovalStage.ERROR -> Column(Modifier.fillMaxSize().testTag("story-error"), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text(t("Story review unavailable", "暂时无法审核故事"), style = MaterialTheme.typography.headlineMedium)
                    TvButton(t("Retry", "重试"), Modifier.focusRequester(stageFocus).testTag("story-error-retry")) {
                        controller.dispatch(TvStoryApprovalAction.LoadStories(state.page))
                    }
                    TvButton(t("Close", "关闭"), Modifier.testTag("story-error-close"), onClick = ::leave)
                }
            }
            }
        }
    }
    if (confirmDiscard) AlertDialog(
        onDismissRequest = { confirmDiscard = false },
        title = { Text(t("Discard these draft changes?", "放弃这些草稿修改？")) },
        text = { Text(t("The applied chapter will not be saved to the library.", "带入的章节不会保存到相册库。")) },
        confirmButton = {
            TvButton(t("Discard changes", "放弃修改"), Modifier.testTag("story-discard-confirm")) {
                confirmDiscard = false
                controller.dispatch(TvStoryApprovalAction.DiscardApplied)
                leave()
            }
        },
        dismissButton = {
            TvButton(t("Keep reviewing", "继续审核"), Modifier.testTag("story-discard-cancel")) { confirmDiscard = false }
        },
    )
    if (confirmUncertainClose) AlertDialog(
        onDismissRequest = { confirmUncertainClose = false },
        title = { Text(t("Close with an unconfirmed save?", "保存结果尚未确认，仍要关闭？")) },
        text = { Text(t("The save may already have completed. Closing clears this TV session's retry request; keep the screen open to retry the same save.",
            "保存可能已经完成。关闭会清除本次电视会话中的重试请求；留在此页可重试同一保存。")) },
        confirmButton = {
            TvButton(t("Close anyway", "仍要关闭"), Modifier.testTag("story-uncertain-close-confirm")) {
                confirmUncertainClose = false
                leave()
            }
        },
        dismissButton = {
            TvButton(t("Keep open", "继续保留"), Modifier.testTag("story-uncertain-close-cancel")) { confirmUncertainClose = false }
        },
    )
}

@Composable
private fun SignInStage(
    zh: Boolean,
    busy: Boolean,
    phone: String,
    password: String,
    firstFocus: FocusRequester,
    onPhone: (String) -> Unit,
    onPassword: (String) -> Unit,
    onSignIn: () -> Unit,
    onCancel: () -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val fieldColors = TextFieldDefaults.colors(
        focusedTextColor = Cream,
        unfocusedTextColor = Cream,
        focusedContainerColor = Moss,
        unfocusedContainerColor = Moss,
    )
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).testTag("story-sign-in"),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(t("Sign in to review family stories", "登录后审核家庭故事"), style = MaterialTheme.typography.headlineSmall)
        TextField(phone, onPhone, Modifier.fillMaxWidth().focusRequester(firstFocus).testTag("story-phone"), singleLine = true,
            label = { Text(t("Phone", "手机号")) }, enabled = !busy,
            colors = fieldColors)
        TextField(password, onPassword, Modifier.fillMaxWidth().testTag("story-password"), singleLine = true,
            label = { Text(t("Password", "密码")) }, visualTransformation = PasswordVisualTransformation(), enabled = !busy,
            colors = fieldColors)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            TvButton(t("Sign in", "登录"), Modifier.testTag("story-sign-in-submit"), enabled = !busy && phone.isNotBlank() && password.isNotBlank(), onClick = onSignIn)
            TvButton(t("Cancel", "取消"), Modifier.testTag("story-sign-in-cancel"), enabled = !busy, onClick = onCancel)
        }
        Text(t("This TV session is temporary and ends when you leave the app.", "此电视登录仅用于当前前台会话，离开应用后结束。"),
            style = MaterialTheme.typography.bodyMedium, color = Muted)
    }
}

@Composable
private fun ReviewStage(
    state: TvStoryApprovalUiState,
    zh: Boolean,
    stageFocus: FocusRequester,
    onStart: () -> Unit,
    onRefresh: () -> Unit,
    onApply: () -> Unit,
    onStories: () -> Unit,
    onSignOut: () -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val story = state.currentStory
    val scroll = rememberScrollState()
    val textFocus = remember { FocusRequester() }
    val chapters = state.currentChapters.withIndex()
    val changed = chapters.filter { it.value.changed }
    Column(Modifier.fillMaxSize().testTag("story-review-current"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(story?.title.orEmpty(), style = MaterialTheme.typography.headlineSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Column(Modifier.weight(1f).fillMaxWidth().focusRequester(textFocus).focusProperties { down = stageFocus }
            .remoteReadingPane(scroll).verticalScroll(scroll).padding(8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            (changed.ifEmpty { chapters.toList() }).forEach { (index, chapter) ->
                Surface(Modifier.fillMaxWidth().testTag("review-chapter-${chapter.id}"), color = Moss,
                    shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, if (chapter.changed) Gold else Edge)) {
                    Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("${t("Chapter", "第")} ${index + 1} · ${chapter.title.ifBlank { t("Untitled", "未命名") }}",
                            style = MaterialTheme.typography.titleLarge)
                        val suggested = chapter.suggestedText
                        if (suggested != null) ReviewTextPair(chapter.originalText, suggested, zh)
                        else Text(chapter.originalText, style = MaterialTheme.typography.bodyLarge)
                    }
                }
            }
            if (state.questions.isNotEmpty()) {
                Text(t("Questions to review", "待核对问题"), style = MaterialTheme.typography.titleLarge, color = Gold)
                state.questions.forEach { Text(it, style = MaterialTheme.typography.bodyLarge) }
            }
        }
        if (state.unlinkedSourceCount > 0) Text(t("${state.unlinkedSourceCount} source links need review.", "有 ${state.unlinkedSourceCount} 个素材关联需要核对。"),
            Modifier.testTag("unlinked-source-warning"), style = MaterialTheme.typography.bodyLarge, color = Gold)
        Row(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            if (state.canStart) TvButton(t("Refine this story", "整理这个故事"),
                Modifier.focusRequester(stageFocus).testTag("story-start-review"), enabled = !state.busy, onClick = onStart)
            if (!state.canStart && state.canRefresh) TvButton(t("Refresh", "刷新"),
                Modifier.then(if (state.canApply) Modifier else Modifier.focusRequester(stageFocus)).testTag("story-refresh"),
                enabled = !state.busy, onClick = onRefresh)
            TvButton(t("Apply reviewed changes", "应用已审核修改"),
                Modifier.then(if (state.canApply) Modifier.focusRequester(stageFocus) else Modifier)
                    .focusProperties { up = textFocus }.testTag("story-apply-proposal"),
                enabled = state.canApply && !state.busy, onClick = onApply)
            TvButton(t("Stories", "故事列表"), Modifier.then(if (!state.canStart && !state.canRefresh && !state.canApply) Modifier.focusRequester(stageFocus) else Modifier)
                .testTag("story-review-list"), enabled = !state.busy, onClick = onStories)
            TvButton(t("Sign out", "退出登录"), Modifier.testTag("story-review-sign-out"), enabled = !state.busy, onClick = onSignOut)
        }
    }
}

@Composable
private fun Modifier.remoteReadingPane(scroll: ScrollState): Modifier {
    val scrollStep = with(LocalDensity.current) { 96.dp.toPx() }
    var focused by remember { mutableStateOf(false) }
    return this.onFocusChanged { focused = it.isFocused }
        .onPreviewKeyEvent { event ->
            if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
            when (event.key) {
                Key.DirectionDown -> scroll.canScrollForward && scroll.dispatchRawDelta(scrollStep) != 0f
                Key.DirectionUp -> scroll.canScrollBackward && scroll.dispatchRawDelta(-scrollStep) != 0f
                else -> false
            }
        }
        .focusable()
        .border(1.dp, if (focused) Gold else Edge, RoundedCornerShape(10.dp))
}

@Composable
private fun ReviewTextPair(original: String, suggested: String, zh: Boolean) {
    fun t(en: String, cn: String) = if (zh) cn else en
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth >= 900.dp) {
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(t("Original", "原文"), style = MaterialTheme.typography.titleMedium, color = Gold)
                    Text(original, style = MaterialTheme.typography.bodyLarge, lineHeight = MaterialTheme.typography.bodyLarge.lineHeight)
                }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(t("Suggested", "建议稿"), style = MaterialTheme.typography.titleMedium, color = Gold)
                    Text(suggested, style = MaterialTheme.typography.bodyLarge, lineHeight = MaterialTheme.typography.bodyLarge.lineHeight)
                }
            }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(t("Original", "原文"), style = MaterialTheme.typography.titleMedium, color = Gold)
                Text(original, style = MaterialTheme.typography.bodyLarge, lineHeight = MaterialTheme.typography.bodyLarge.lineHeight)
                Text(t("Suggested", "建议稿"), style = MaterialTheme.typography.titleMedium, color = Gold)
                Text(suggested, style = MaterialTheme.typography.bodyLarge, lineHeight = MaterialTheme.typography.bodyLarge.lineHeight)
            }
        }
    }
}

private fun Modifier.heightInTv() = this.heightIn(min = 60.dp)
