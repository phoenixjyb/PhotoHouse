package dev.photohouse.connected

import android.graphics.Bitmap
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import kotlinx.coroutines.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Chosen names and narrator edits only; all identities and content are synthetic. */
@RunWith(AndroidJUnit4::class)
class StoryAttributionUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun finish() { scope.cancel() }

    @Test fun chineseCreationPrefillsNameAndExplicitClearSurvivesReview() = journey(true, "")
    @Test fun englishCreationPrefillsNameAndNarratorOverrideSurvivesReopen() = journey(false, "Grandma")

    private fun journey(zh: Boolean, narrator: String) {
        var saved: ProtectedStory? = null
        fun editor(initial: ProtectedStory? = null) = ProtectedStoryEditorStore(scope, "42", initial,
            save = { mutation ->
                ProtectedStory("10000000-0000-0000-0000-000000000001", "42", mutation.draft.title,
                    mutation.draft.text, mutation.draft.language, mutation.draft.byline,
                    "synthetic-server-author", 1, 100, 100, true, true).also { saved = it }
            }, reload = { saved }, onSaved = {}, onDenied = {}, defaultByline = "爸爸 / Dad")
        val create = editor()
        var visible by mutableStateOf(create)
        rule.setContent { ProtectedStoryEditorDialog(visible, onDismiss = {}, zh = zh) }
        rule.onNodeWithTag("story-editor-title").performScrollTo()
            .assertTextContains(if (zh) "标题（可选）" else "Title (optional)")
        rule.onNodeWithTag("story-editor-byline").performScrollTo().assertTextContains("爸爸 / Dad")
            .assertTextContains(if (zh) "署名（可选）" else "Byline (optional)")
        capture(if (zh) "automatic-attribution-zh.png" else "automatic-attribution-en.png")
        rule.onNodeWithTag("story-editor-byline").performTextReplacement(narrator)
        rule.onNodeWithTag("story-editor-text").performScrollTo().performTextInput("合成的一天。 A synthetic day.")
        rule.onNodeWithTag("story-editor-review").performScrollTo().performClick()
        assertEquals(narrator, create.state.value.mutation!!.draft.byline)
        rule.onNodeWithTag("story-editor-confirm").performScrollTo().performClick()
        rule.waitUntil(5000) { create.state.value.phase == StoryEditorPhase.SAVED }
        assertEquals(narrator, saved!!.byline)
        assertEquals("synthetic-server-author", saved!!.authorId)
        val edit = editor(saved)
        rule.runOnIdle { create.close(); visible = edit }
        assertEquals(narrator, edit.state.value.draft.byline)
        rule.onNodeWithTag("story-editor-byline").performScrollTo().assertIsDisplayed()
        capture(if (zh) "preserved-empty-byline-zh.png" else "preserved-narrator-en.png")
        rule.runOnIdle { edit.close() }
    }

    private fun capture(name: String) {
        rule.waitForIdle()
        val bitmap = rule.onNodeWithTag("protected-story-editor").captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        File(context.filesDir, name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
}
