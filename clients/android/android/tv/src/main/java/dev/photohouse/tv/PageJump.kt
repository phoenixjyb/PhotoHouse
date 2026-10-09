package dev.photohouse.tv

import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogProperties

/** Remote-only page selection keeps even a large catalog reachable without typing. */
@Composable internal fun PageJump(current: Int, total: Int, zh: Boolean, dismiss: () -> Unit, go: (Int) -> Unit) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val last = ((total + 49) / 50).coerceAtLeast(1)
    var target by remember(current, last) { mutableStateOf(current.coerceIn(1, last)) }
    val steps = remember { List(6) { FocusRequester() } }
    val confirm = remember { FocusRequester() }
    val initial = if (current < last) 3 else 2
    val labels = listOf(t("First", "首页"), "−10", "−1", "+1", "+10", t("Last", "末页"))
    fun choose(index: Int) {
        target = when (index) {
            0 -> 1; 1 -> target - 10; 2 -> target - 1
            3 -> target + 1; 4 -> target + 10; else -> last
        }.coerceIn(1, last)
    }
    AlertDialog(onDismissRequest = dismiss,
        modifier = Modifier.widthIn(max = 600.dp).fillMaxWidth(),
        properties = DialogProperties(usePlatformDefaultWidth = false),
        title = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(t("Go to page", "跳转页面"))
            Text(t("Page $target of $last", "第 $target 页，共 $last 页"), Modifier.testTag("page-target"), style = MaterialTheme.typography.bodyLarge)
        } },
        text = { Column(Modifier.heightIn(max = 260.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (row in 0..1) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (column in 0..2) {
                    val i = row * 3 + column
                    val tag = when (i) { 0 -> "page-first"; 3 -> "page-plus-one"; 5 -> "page-last"; else -> "page-step-$i" }
                    TvButton(labels[i], Modifier.weight(1f).testTag(tag).focusRequester(steps[i]).focusProperties {
                        if (column > 0) left = steps[i - 1]
                        if (column < 2) right = steps[i + 1]
                        if (row > 0) up = steps[i - 3]
                        down = if (row == 0) steps[i + 3] else confirm
                    }) { choose(i) }
                }
            }
        } },
        dismissButton = { TvButton(t("Cancel", "取消")) { dismiss() } },
        confirmButton = {
            TvButton(t("Go", "跳转"), Modifier.testTag("page-go").focusRequester(confirm).focusProperties { up = steps[3] }, enabled = target != current) { go(target) }
            val focusedWindow = LocalWindowInfo.current.isWindowFocused
            LaunchedEffect(focusedWindow) {
                if (focusedWindow) { withFrameNanos { }; steps[initial].requestFocus() }
            }
        })
}
