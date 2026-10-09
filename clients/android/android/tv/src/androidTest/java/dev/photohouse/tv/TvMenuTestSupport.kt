package dev.photohouse.tv

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.ComposeContentTestRule

internal fun ComposeContentTestRule.showAction(tag: String) {
    if (onAllNodesWithTag(tag).fetchSemanticsNodes().isEmpty()) {
        onNodeWithTag("gallery-more").performScrollTo().performClick()
    }
}
