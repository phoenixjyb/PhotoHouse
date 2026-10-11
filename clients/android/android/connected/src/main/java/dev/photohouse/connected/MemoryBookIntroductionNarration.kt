package dev.photohouse.connected

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/** Exact rendered memoir location for transient introduction speech. */
internal data class MemoryBookIntroductionNarrationScope(
    val accountId: String,
    val generation: Long,
    val libraryId: String,
    val readerScopeId: Long,
    val bookId: String,
    val bookRevision: Long,
    val orderedChildren: List<Pair<String, Long>>,
    val storyIndex: Int?,
    val storyId: String?,
    val storyRevision: Long?,
    val chapterIndex: Int?,
    val chapterId: String?,
    val framePage: Int,
    val selectedAssetId: String?,
    val introduction: String,
    val language: String,
)

@Composable
internal fun MemoryBookIntroductionNarration(
    scope: MemoryBookIntroductionNarrationScope,
    zh: Boolean,
    enabled: Boolean,
) {
    if (scope.introduction.isBlank()) return
    Column(
        Modifier.fillMaxWidth().testTag("memory-book-introduction-narration"),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        ChapterReadAloud(
            text = scope.introduction,
            language = scope.language,
            scopeKey = scope,
            zh = zh,
            enabled = enabled,
            labels = ChapterReadAloudLabels(
                read = if (zh) "朗读开篇" else "Read introduction aloud",
                pause = if (zh) "暂停朗读" else "Pause introduction",
                resume = if (zh) "继续朗读" else "Resume introduction",
                stop = if (zh) "停止朗读" else "Stop introduction",
                done = if (zh) "开篇朗读完毕。" else "Introduction finished.",
                tagPrefix = "memory-book-introduction-narration",
            ),
        )
    }
}
