package dev.photohouse.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.isSpecified

internal enum class ReaderTextSizePreset(val scale: Float, internal val tag: String) {
    SMALLER(0.9f, "smaller"),
    DEFAULT(1.0f, "default"),
    LARGER(1.25f, "larger"),
}

/** Scales a prose style while keeping Android's current system font scale in effect. */
internal fun readerProseStyle(style: TextStyle, preset: ReaderTextSizePreset): TextStyle =
    style.copy(
        fontSize = if (style.fontSize.isSpecified) style.fontSize * preset.scale else style.fontSize,
        lineHeight = if (style.lineHeight.isSpecified) style.lineHeight * preset.scale else style.lineHeight,
    )

@Composable
internal fun ReaderTextSizeControls(
    selected: ReaderTextSizePreset,
    zh: Boolean,
    tagPrefix: String,
    onSelect: (ReaderTextSizePreset) -> Unit,
    modifier: Modifier = Modifier,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val options = listOf(
        Triple(ReaderTextSizePreset.SMALLER, t("Smaller", "较小"), t("Smaller reading text", "较小字号阅读文字")),
        Triple(ReaderTextSizePreset.DEFAULT, t("Default", "标准"), t("Default reading text", "标准字号阅读文字")),
        Triple(ReaderTextSizePreset.LARGER, t("Larger", "较大"), t("Larger reading text", "较大字号阅读文字")),
    )
    Column(modifier.fillMaxWidth().testTag("$tagPrefix-controls"), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(t("Reading size", "阅读字号"), style = MaterialTheme.typography.labelLarge)
        Row(Modifier.fillMaxWidth().selectableGroup(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            options.forEach { (preset, label, accessibleLabel) ->
                FilterChip(
                    selected = selected == preset,
                    onClick = { onSelect(preset) },
                    label = { Text(label, maxLines = 1) },
                    modifier = Modifier.weight(1f).heightIn(min = 48.dp)
                        .testTag("$tagPrefix-${preset.tag}")
                        .semantics { contentDescription = accessibleLabel },
                )
            }
        }
    }
}
