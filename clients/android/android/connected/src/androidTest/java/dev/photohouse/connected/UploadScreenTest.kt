package dev.photohouse.connected

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import org.junit.Rule
import org.junit.Test
import dev.photohouse.connected.core.UploadReceipt
import dev.photohouse.connected.core.UploadState
import dev.photohouse.connected.core.UploadAnnotation
import dev.photohouse.connected.core.UploadAnnotationDerivation
import dev.photohouse.connected.core.UploadAnnotationPage
import dev.photohouse.connected.core.UploadAnnotationReadState
import org.junit.Assert.assertEquals

class UploadScreenTest {
    @get:Rule val compose = createComposeRule()

    @Test fun receivedStateExplainsQueueAndPromotionBoundary() {
        compose.setContent {
            UploadPanelState(
                UploadState.Succeeded(UploadReceipt("7", null, "member", "0123456789abcdef0123456789abcdef", "image", 1, 1, "a".repeat(64), 12, 5)),
                zh = false, onPick = {}, onClose = {}, onApproveNetwork = {}, onRetry = {}, onCancel = {},
            )
        }
        compose.onNodeWithTag("upload-received").assertIsDisplayed()
        compose.onNodeWithTag("upload-done").assertIsDisplayed()
    }

    @Test fun folderComposerPostsEmptyAssetIdAndSelectedText() {
        var posted: Triple<String, String, String>? = null
        compose.setContent {
            UploadAnnotationComposer(UploadAnnotationTarget("family", "a".repeat(32), ""), false, null, null,
                audioWrite = null, audioSelectionError = false,
                onDismiss = {}, onSave = { text, language, consent -> posted = Triple(text, language, consent) },
                onRetry = {}, onPickAudio = { _, _ -> }, onRetryAudio = {}, onRefresh = {})
        }
        compose.onNodeWithTag("upload-annotation-text").performTextInput("weekend garden")
        compose.onNodeWithTag("upload-annotation-save").performClick()
        compose.runOnIdle { assertEquals(Triple("weekend garden", "und", "no"), posted) }
    }

    @Test fun annotationPanelShowsOriginalAndDerivationState() {
        val annotation = UploadAnnotation("annotation", "asset", "901", "a".repeat(32), "family", "member",
            "text", "A walk after lunch", null, null, null, null, "en", "no", 1720000000,
            UploadAnnotationDerivation(1, "held", null, null, null, null, null), emptyList())
        compose.setContent {
            UploadAnnotationComposer(UploadAnnotationTarget("family", "a".repeat(32), "901"), false,
                UploadAnnotationReadState("family", "901", result = UploadAnnotationPage("family", "901", "a".repeat(32), 1, 20, 1, listOf(annotation))),
                null, audioWrite = null, audioSelectionError = false,
                onDismiss = {}, onSave = { _, _, _ -> }, onRetry = {},
                onPickAudio = { _, _ -> }, onRetryAudio = {}, onRefresh = {})
        }
        compose.onNodeWithTag("upload-annotation-original").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("upload-annotation-derivation").performScrollTo().assertIsDisplayed()
    }

    @Test fun audioAnnotationShowsLoadActionForParsedAudioItem() {
        var requested: String? = null
        val annotation = UploadAnnotation("annotation-audio", "item", "901", "a".repeat(32), "family", "member",
            "audio", null, "/upload-annotations/annotation-audio/audio?library=family&asset_id=901",
            "audio/wav", 1000, "b".repeat(64), "en", "no", 1720000000,
            UploadAnnotationDerivation(1, "held", null, null, null, null, null), emptyList())
        compose.setContent {
            UploadAnnotationComposer(UploadAnnotationTarget("family", "a".repeat(32), "901"), false,
                UploadAnnotationReadState("family", "901", result = UploadAnnotationPage("family", "901", "a".repeat(32), 1, 20, 1, listOf(annotation))),
                null, audioWrite = null, audioSelectionError = false,
                onDismiss = {}, onSave = { _, _, _ -> }, onRetry = {},
                onPickAudio = { _, _ -> }, onRetryAudio = {}, onPlayAudio = { requested = it.id }, onRefresh = {})
        }
        compose.onNodeWithTag("upload-annotation-audio-load").performScrollTo().assertIsDisplayed().performClick()
        compose.runOnIdle { assertEquals("annotation-audio", requested) }
    }
}
