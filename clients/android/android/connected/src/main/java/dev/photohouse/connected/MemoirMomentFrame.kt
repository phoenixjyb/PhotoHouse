package dev.photohouse.connected

import android.graphics.BitmapFactory
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

@Composable
internal fun MemoirMomentFrame(
    position: Int,
    count: Int,
    kind: String,
    bytes: ByteArray?,
    selected: Boolean,
    busy: Boolean,
    unavailable: Boolean,
    zh: Boolean,
    onSelect: () -> Unit,
    assetId: String,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val kindLabel = when (kind) {
        "video" -> t("Video", "视频")
        "image" -> t("Photo", "照片")
        else -> t("Media", "媒体")
    }
    val bitmap = remember(bytes) {
        bytes?.let { encoded ->
            runCatching { BitmapFactory.decodeByteArray(encoded, 0, encoded.size)?.asImageBitmap() }.getOrNull()
        }
    }
    val accessibleLabel = buildString {
        append(if (zh) "片段 $position/$count" else "Moment $position of $count")
        if (selected) append(if (zh) "，当前" else ", current")
        append(if (zh) "，$kindLabel" else ", $kindLabel")
        when {
            busy -> append(if (zh) "，加载中" else ", loading")
            unavailable -> append(if (zh) "，不可用" else ", unavailable")
            bitmap == null -> append(if (zh) "，预览尚未加载" else ", preview not loaded")
        }
    }
    Card(
        modifier = Modifier.width(MOMENT_CARD_WIDTH)
            .selectable(selected = selected, enabled = !busy, role = Role.RadioButton, onClick = onSelect)
            .semantics(mergeDescendants = true) { contentDescription = accessibleLabel }
            .testTag("memory-book-frame-$assetId"),
        colors = CardDefaults.cardColors(
            containerColor = if (selected) MaterialTheme.colorScheme.secondaryContainer
            else MaterialTheme.colorScheme.surfaceContainerLow,
        ),
        border = BorderStroke(
            if (selected) 2.dp else 1.dp,
            if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
        ),
    ) {
        Column {
            Box(Modifier.fillMaxWidth().height(MOMENT_THUMBNAIL_HEIGHT), contentAlignment = Alignment.Center) {
                if (bitmap != null) {
                    Image(bitmap, contentDescription = null, modifier = Modifier.fillMaxWidth().height(MOMENT_THUMBNAIL_HEIGHT),
                        contentScale = ContentScale.Crop)
                } else {
                    Text(
                        when {
                            busy -> t("Loading", "加载中")
                            unavailable -> t("Unavailable", "不可用")
                            else -> t("Not loaded", "尚未加载")
                        },
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
            // Reserve the same label line on every frame. A badge over the thumbnail
            // can obscure fallback text or the photo itself at larger font sizes.
            Text(
                if (selected) t("Current", "当前") else "",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
                minLines = 1,
                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            )
            Text(
                "$position / $count · $kindLabel",
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(horizontal = 6.dp, vertical = 6.dp),
            )
        }
    }
}

private val MOMENT_CARD_WIDTH = 104.dp
private val MOMENT_THUMBNAIL_HEIGHT = 68.dp
