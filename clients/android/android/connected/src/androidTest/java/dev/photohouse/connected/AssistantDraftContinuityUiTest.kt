package dev.photohouse.connected

import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** In-memory composer continuity through the real ConnectedApp conversation-panel route. */
@RunWith(AndroidJUnit4::class)
class AssistantDraftContinuityUiTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    @After fun stop() { scope.cancel() }

    private class PhotoApi : PhotoHouseApi by GeneratedMemoirReaderApi() {
        override val protectedNativeV2Enabled = false
        override val assistantEnabled = true
        var accountId = "synthetic-account-a"
        var submittedTurns = 0
        var transcriptCalls = 0

        override suspend fun session(token: Bearer) = Session(accountId, "+12025550123", listOf(
            Membership(LIBRARY, "approved", "viewer", 1, null, 0, true),
            Membership(OTHER_LIBRARY, "approved", "viewer", 1, null, 0, true),
        ))

        override suspend fun gallery(token: Bearer, library: String, page: Int) =
            Gallery(library, page, 50, 0, false, emptyList())

        override suspend fun assistantCapabilities(token: Bearer, library: String) =
            AssistantCapabilities(true, true, true, true, 30)

        override suspend fun assistantTurn(token: Bearer, library: String, text: String,
                                           context: kotlinx.serialization.json.JsonObject?): AssistantTurn {
            submittedTurns++
            return AssistantTurn("text", "Synthetic reply", null, null, emptyList(), 0, false, null)
        }

        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray): AssistantTranscript {
            transcriptCalls++
            return AssistantTranscript("Synthetic transcript", "en")
        }

        companion object {
            const val LIBRARY = "synthetic-library"
            const val OTHER_LIBRARY = "other-library"
        }
    }

    private class WorkspaceApi : AssistantWorkspaceApi {
        override val assistantWorkspaceEnabled = true
        var threadRevision = 1L
        var submittedTurns = 0

        private fun summary(id: String, library: String) = AssistantWorkspaceThreadSummary(
            id, library, "2026-10-14T00:00:00Z", "2026-10-15T00:00:00Z",
            "2026-11-14T00:00:00Z", threadRevision, exchangeCount = 0, label = "Synthetic thread",
        )

        override suspend fun capabilities(token: Bearer, library: String) = AssistantWorkspaceCapabilities(
            version = 1, available = true, threads = true, preferences = false,
            preferencesApplied = false, serverOwnedTurns = true, threadLabels = true,
        )

        override suspend fun listThreads(token: Bearer, library: String) =
            AssistantWorkspaceThreadList(1, listOf(summary(THREAD_ID, library), summary(OTHER_THREAD_ID, library)))

        override suspend fun readThread(token: Bearer, library: String, threadId: String) =
            AssistantWorkspaceThreadDetail(1, summary(threadId, library), emptyList())

        override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                        expectedRevision: Long, text: String): AssistantWorkspaceTurn {
            submittedTurns++
            throw AssertionError("This continuity journey must not submit a turn")
        }

        companion object {
            const val THREAD_ID = "123e4567-e89b-42d3-a456-426614174001"
            const val OTHER_THREAD_ID = "123e4567-e89b-42d3-a456-426614174002"
        }
    }

    private class NoCapturePlatform : AssistantVoiceSessionPlatform {
        var captureCalls = 0
        override suspend fun capture(maxSeconds: Int): ByteArray? { captureCalls++; return null }
        override suspend fun playSpeech(audio: ProtectedAnnotationAudio): Boolean = false
        override fun stopAudio() = Unit
        override fun finishCapture() = Unit
    }

    private data class Installed(val store: ConnectedStore, val platform: NoCapturePlatform)

    private fun install(api: PhotoApi, workspace: WorkspaceApi): Installed {
        val store = ConnectedStore(api, scope, assistantWorkspaceApi = workspace)
        val platform = NoCapturePlatform()
        val platformFactory = AssistantVoicePlatformFactory { _, _ -> platform }
        rule.runOnUiThread {
            rule.activity.setContent {
                CompositionLocalProvider(LocalAssistantVoicePlatformFactory provides platformFactory) {
                    ConnectedApp(store, initialLanguage = "en")
                }
            }
            store.authenticate("+12025550123", "synthetic-password-only")
        }
        rule.waitUntil(5_000) { store.state.value.library == PhotoApi.LIBRARY }
        rule.waitForIdle()
        rule.onNodeWithTag("connected-screen").performScrollToNode(hasTestTag("open-assistant"))
        rule.onNodeWithTag("open-assistant").performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("assistant-text").assertIsDisplayed(); true }.getOrDefault(false) }
        rule.waitForIdle()
        return Installed(store, platform)
    }

    private fun openAndReturnFromThreads() {
        rule.onNodeWithTag("assistant-private-conversations").performClick()
        rule.onNodeWithTag("private-assistant-dismiss").assertIsDisplayed().performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("assistant-text").assertIsDisplayed(); true }.getOrDefault(false) }
        rule.waitForIdle()
    }

    private fun assertDraft(expected: String) {
        val editableText = rule.onNodeWithTag("assistant-text").fetchSemanticsNode()
            .config[SemanticsProperties.EditableText].text
        assertEquals("composer draft", expected, editableText)
    }

    @Test fun typedAndSuggestedDraftsSurvivePrivateConversationRoundTripsWithoutSendingOrRecording() {
        val api = PhotoApi()
        val workspace = WorkspaceApi()
        val installed = install(api, workspace)

        rule.onNodeWithTag("assistant-text").performTextInput("Find a quiet family walk")
        openAndReturnFromThreads()
        assertDraft("Find a quiet family walk")

        rule.onNodeWithTag("assistant-suggestion-0").performClick()
        assertDraft("Find videos from last year")
        openAndReturnFromThreads()
        assertDraft("Find videos from last year")

        assertEquals("navigation never sends a text turn", 0, api.submittedTurns)
        assertEquals("navigation never starts transcription", 0, api.transcriptCalls)
        assertEquals("navigation never sends a private workspace turn", 0, workspace.submittedTurns)
        assertEquals("navigation never starts microphone capture", 0, installed.platform.captureCalls)

        rule.onNodeWithTag("assistant-back").performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("open-assistant").assertIsDisplayed(); true }.getOrDefault(false) }
        rule.onNodeWithTag("connected-screen").performScrollToNode(hasTestTag("open-assistant"))
        rule.onNodeWithTag("open-assistant").performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("assistant-text").assertIsDisplayed(); true }.getOrDefault(false) }
        assertDraft("")
    }

    @Test fun accountAndLibraryChangesClearTheCompositionLocalDraft() {
        val api = PhotoApi()
        val workspace = WorkspaceApi()
        val store = install(api, workspace).store
        rule.onNodeWithTag("assistant-text").performTextInput("Keep this only in this account and library")

        store.selectLibrary(PhotoApi.OTHER_LIBRARY)
        rule.waitUntil(5_000) { store.state.value.library == PhotoApi.OTHER_LIBRARY }
        rule.waitForIdle()
        rule.onNodeWithTag("open-assistant").performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("assistant-text").assertIsDisplayed(); true }.getOrDefault(false) }
        assertDraft("")

        api.accountId = "synthetic-account-b"
        store.logout()
        rule.waitUntil(5_000) { store.state.value.session == null }
        store.authenticate("+12025550123", "synthetic-password-only")
        rule.waitUntil(5_000) { store.state.value.session?.account_id == "synthetic-account-b" &&
            store.state.value.library == PhotoApi.LIBRARY }
        rule.waitForIdle()
        rule.onNodeWithTag("open-assistant").performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("assistant-text").assertIsDisplayed(); true }.getOrDefault(false) }
        assertDraft("")
        assertFalse(store.state.value.covered)
    }

    @Test fun activatingAnotherPrivateThreadClearsDraftButSameThreadRevisionChangeDoesNot() {
        val api = PhotoApi()
        val workspace = WorkspaceApi()
        install(api, workspace)

        rule.onNodeWithTag("assistant-private-conversations").performClick()
        rule.onNodeWithTag("private-assistant-thread-${WorkspaceApi.THREAD_ID}").performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("private-assistant-continue-text").assertIsDisplayed(); true }.getOrDefault(false) }
        rule.onNodeWithTag("private-assistant-continue-text").performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("assistant-text").assertIsDisplayed(); true }.getOrDefault(false) }
        rule.onNodeWithTag("assistant-text").performTextInput("Do not carry this into another thread")
        rule.onNodeWithTag("assistant-private-conversations").performClick()
        rule.onNodeWithTag("private-assistant-thread-${WorkspaceApi.OTHER_THREAD_ID}").performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("private-assistant-continue-text").assertIsDisplayed(); true }.getOrDefault(false) }
        rule.onNodeWithTag("private-assistant-continue-text").performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("assistant-text").assertIsDisplayed(); true }.getOrDefault(false) }
        assertDraft("")

        rule.onNodeWithTag("assistant-text").performTextInput("Keep this in the selected thread")
        rule.onNodeWithTag("assistant-private-conversations").performClick()
        workspace.threadRevision = 2L
        rule.onNodeWithTag("private-assistant-thread-${WorkspaceApi.OTHER_THREAD_ID}").performClick()
        rule.onNodeWithTag("private-assistant-dismiss").performClick()
        rule.waitUntil(5_000) { runCatching { rule.onNodeWithTag("assistant-text").assertIsDisplayed(); true }.getOrDefault(false) }
        assertDraft("Keep this in the selected thread")
    }
}
