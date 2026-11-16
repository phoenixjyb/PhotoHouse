package dev.photohouse.tv

import android.graphics.Bitmap
import android.graphics.Canvas
import android.os.SystemClock
import android.view.KeyEvent
import androidx.activity.compose.setContent
import androidx.compose.runtime.Composable
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performSemanticsAction
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class TvStoryApprovalUiTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val input = InstrumentationRegistry.getInstrumentation()

    @Before fun remoteInput() { input.setInTouchMode(false) }

    @Test fun dpadAppliesChapterTwoToDraftWithoutWritingUntilExplicitSave() {
        val controller = GeneratedStoryApprovalController()
        val protectedStories = object : TvProtectedStories {
            @Composable
            override fun Content(zh: Boolean, onClose: () -> Unit) = TvProtectedStoryContent(controller, zh, onClose)
            override fun background() = controller.dispatch(TvStoryApprovalAction.Cancel)
        }
        rule.runOnUiThread {
            rule.activity.setContent {
                TvApp(null, initialLanguage = "en", protectedStories = protectedStories)
            }
        }
        rule.onNodeWithTag("story-review-entry").performSemanticsAction(SemanticsActions.RequestFocus).assertIsFocused()
        key(KeyEvent.KEYCODE_DPAD_CENTER)

        // The review route focuses its available primary action for the TV remote.
        rule.onNodeWithTag("story-apply-proposal").assertIsDisplayed().assertIsFocused()
        key(KeyEvent.KEYCODE_DPAD_CENTER)

        captureAppliedState()
        assertEquals(TvStoryApprovalStage.APPLIED, controller.state.value.stage)
        rule.onNodeWithTag("applied-to-draft").assertIsDisplayed()
        rule.onNodeWithTag("applied-chapter-chapter-2").assertIsDisplayed()
        rule.onNodeWithTag("chapter-suggested-chapter-2").assertIsDisplayed()
        rule.onNodeWithTag("story-save-to-library").assertIsDisplayed()
        assertEquals("Apply only changes the in-memory draft", 0, controller.libraryWrites)
        rule.onNodeWithTag("applied-chapter-focus").assertIsFocused()

        key(KeyEvent.KEYCODE_DPAD_DOWN)
        rule.onNodeWithTag("story-save-to-library").assertIsFocused()
        key(KeyEvent.KEYCODE_DPAD_CENTER)
        assertEquals("Only the explicit Save to library action writes", 1, controller.libraryWrites)
    }

    private fun key(code: Int) {
        // Dispatch to the test activity so a system launcher dialog cannot intercept the remote.
        rule.runOnUiThread {
            val pressedAt = SystemClock.uptimeMillis()
            rule.activity.dispatchKeyEvent(KeyEvent(pressedAt, pressedAt, KeyEvent.ACTION_DOWN, code, 0))
            rule.activity.dispatchKeyEvent(KeyEvent(pressedAt, SystemClock.uptimeMillis(), KeyEvent.ACTION_UP, code, 0))
        }
        rule.waitForIdle()
    }

    private fun captureAppliedState() {
        rule.waitForIdle()
        rule.runOnUiThread {
            val view = rule.activity.window.decorView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            File(rule.activity.cacheDir, "tv-story-approval-applied-chapter2.png").outputStream().use {
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
            }
            bitmap.recycle()
        }
    }
}

/** Generated-only state seam: never constructs an API client or contacts a server. */
private class GeneratedStoryApprovalController : TvStoryApprovalController {
    private val mutableState = MutableStateFlow(
        TvStoryApprovalUiState(
            stage = TvStoryApprovalStage.REVIEW,
            currentStory = TvStoryApprovalStory("story-1", "A quiet afternoon", revision = 4, chapterCount = 2),
            currentChapters = listOf(
                TvStoryApprovalChapter("chapter-1", "Before", "We arrived early.", "We arrived early.", changed = false),
                TvStoryApprovalChapter("chapter-2", "At the table", "We sat together.", "We shared a long, happy lunch.", changed = true),
            ),
            canApply = true,
            canRefresh = true,
        ),
    )
    override val state: StateFlow<TvStoryApprovalUiState> = mutableState
    var libraryWrites: Int = 0
        private set

    override fun dispatch(action: TvStoryApprovalAction) {
        when (action) {
            TvStoryApprovalAction.ApplyProposal -> mutableState.value = mutableState.value.copy(
                stage = TvStoryApprovalStage.APPLIED,
                focusedChapterId = "chapter-2",
                dirty = true,
            )
            TvStoryApprovalAction.Save -> {
                libraryWrites++
                mutableState.value = mutableState.value.copy(stage = TvStoryApprovalStage.SAVED, writeStarted = true)
            }
            TvStoryApprovalAction.Cancel,
            TvStoryApprovalAction.DiscardApplied,
            TvStoryApprovalAction.RefreshCurrent,
            TvStoryApprovalAction.RetrySave,
            TvStoryApprovalAction.SignOut,
            TvStoryApprovalAction.StartCurrent -> Unit
            is TvStoryApprovalAction.ChooseLibrary,
            is TvStoryApprovalAction.LoadStories,
            is TvStoryApprovalAction.OpenStory,
            is TvStoryApprovalAction.SignIn -> Unit
        }
    }
}
