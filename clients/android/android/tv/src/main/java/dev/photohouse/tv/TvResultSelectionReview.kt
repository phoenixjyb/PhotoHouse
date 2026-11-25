package dev.photohouse.tv

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.home.AssetKind
import dev.photohouse.home.HomeAsset

@Composable
internal fun TvResultSelectionReview(
    assets: List<HomeAsset>,
    valid: Boolean,
    zh: Boolean,
    onDismiss: () -> Unit,
    onRemove: (Int) -> Unit,
    onOpen: (HomeAsset) -> Unit,
    onClear: () -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val hasOpenTarget = valid && assets.isNotEmpty()
    val focusTarget = remember(hasOpenTarget, assets.firstOrNull()?.id) { FocusRequester() }
    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier.testTag("selection-review"),
        title = { Text(t("Review selected moments", "检查已选回忆")) },
        text = {
            if (!valid) {
                Text(t("These results are no longer available on this page. Close this review and search again.",
                    "此页搜索结果已失效。请关闭此页并重新搜索。"), Modifier.testTag("selection-stale"))
            } else if (assets.isEmpty()) {
                Text(t("No moments selected yet.", "还没有选择回忆。"), Modifier.testTag("selection-empty"))
            } else {
                FocusReviewAction(focusTarget)
                Column(
                    Modifier.fillMaxWidth().heightIn(max = 360.dp).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    assets.forEachIndexed { index, asset ->
                        Column(Modifier.fillMaxWidth().testTag("selection-item-${asset.id}"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("${index + 1}. ${asset.caption.ifBlank { t("Moment ${asset.id}", "回忆 ${asset.id}") }}",
                                Modifier.testTag("selection-label-${asset.id}"))
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                TvButton(
                                    if (asset.kind == AssetKind.VIDEO) t("Watch", "观看") else t("Open photo", "打开照片"),
                                    Modifier.weight(1f).heightIn(min = 48.dp)
                                        .then(if (index == 0 && hasOpenTarget) Modifier.focusRequester(focusTarget) else Modifier)
                                        .testTag("selection-open-${asset.id}"),
                                    onClick = { onOpen(asset) },
                                )
                                TvButton(
                                    t("Remove", "移除"),
                                    Modifier.weight(1f).heightIn(min = 48.dp).testTag("selection-remove-${asset.id}"),
                                    onClick = { onRemove(asset.id) },
                                )
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            if (!hasOpenTarget) FocusReviewAction(focusTarget)
            TvButton(t("Keep choosing", "继续选择"), Modifier
                .then(if (!hasOpenTarget) Modifier.focusRequester(focusTarget) else Modifier)
                .testTag("selection-review-close"), onClick = onDismiss)
        },
        dismissButton = {
            TvButton(t("Clear all", "全部清除"), Modifier.padding(end = 8.dp).testTag("selection-review-clear"), onClick = onClear)
        },
    )
}

@Composable
private fun FocusReviewAction(requester: FocusRequester) {
    val focused = LocalWindowInfo.current.isWindowFocused
    LaunchedEffect(focused, requester) {
        if (focused) {
            withFrameNanos { }
            requester.requestFocus()
        }
    }
}
