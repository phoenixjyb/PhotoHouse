package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.AssistantTurn
import dev.photohouse.connected.core.AssistantWorkspaceState
import dev.photohouse.connected.core.AssistantWorkspaceWire

/** Explicit visual wording never replaces the visible server-owned hard conditions. */
@Composable
internal fun AssistantSceneControls(
    state: AssistantWorkspaceState, zh: Boolean, interactionBlocked: Boolean,
    onDraft: (String) -> Unit, onSend: () -> Unit, onBack: () -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    var acknowledged by remember(state.accountId, state.libraryId, state.generation,
        state.detail?.thread?.threadId, state.detail?.thread?.revision) { mutableStateOf(false) }
    val result = state.currentTurn?.result
    val blocked = !state.sceneReady || interactionBlocked
    Card(Modifier.fillMaxWidth().testTag("private-assistant-scene-editor")) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(t("Find a scene within these conditions", "在当前条件内按画面查找"), style = MaterialTheme.typography.titleMedium)
            Text(t("Describe actions, colors or surroundings, such as flying a kite beside a blue bridge. People, dates and other conditions below stay in place. Return to full search to change them.",
                "描述动作、颜色或环境，例如“在蓝桥旁放风筝”。下面的人物、日期和其他条件保持不变；要更改这些条件，请返回完整查找。"),
                style = MaterialTheme.typography.bodySmall)
            Column(Modifier.testTag("private-assistant-scene-scope"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (result?.kind == "results") {
                    assistantSearchInterpretationLines(result, zh).forEach { Text(it, style = MaterialTheme.typography.bodyMedium) }
                    if (result.filters?.containsKey("media") != true) Text(t("Media: photos", "媒体：照片"))
                }
            }
            if (!state.sceneReady) Text(t("First finish a photo search with resolved conditions. Clarifications, video searches and caption-description searches must be resolved through full search first.",
                "请先完成条件明确的照片查找。待确认的条件、视频查找和说明文字描述查找需要先返回完整查找处理。"),
                Modifier.testTag("private-assistant-scene-unready"), style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(value = state.sceneDraft, onValueChange = onDraft, enabled = !blocked,
                modifier = Modifier.fillMaxWidth().testTag("private-assistant-scene-composer"),
                label = { Text(t("What does the scene look like?", "想找什么样的画面？")) },
                minLines = 2, maxLines = 5,
                supportingText = { Text(t("${state.sceneDraft.toByteArray(Charsets.UTF_8).size}/512 UTF-8 bytes; use one line.",
                    "${state.sceneDraft.toByteArray(Charsets.UTF_8).size}/512 UTF-8 字节；请使用单行描述。")) })
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = acknowledged, onCheckedChange = { acknowledged = it }, enabled = !blocked,
                    modifier = Modifier.testTag("private-assistant-scene-ack"))
                Text(t("Keep these conditions; I am only adding a scene description.", "保留这些条件，我只补充画面描述。"),
                    Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
            }
            Button(onClick = { if (!blocked && acknowledged && AssistantWorkspaceWire.validSceneQuery(state.sceneDraft)) onSend() },
                enabled = !blocked && acknowledged && AssistantWorkspaceWire.validSceneQuery(state.sceneDraft),
                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("private-assistant-scene-send")) {
                Text(t("Rank photos by scene similarity", "按画面相似度排列照片"))
            }
            OutlinedButton(onClick = onBack, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                .testTag("private-assistant-scene-back")) { Text(t("Return to full search", "返回完整查找")) }
        }
    }
}

@Composable
internal fun AssistantSceneRankingInfo(result: AssistantTurn, zh: Boolean) {
    val ranking = result.sceneRanking ?: return
    fun t(en: String, cn: String) = if (zh) cn else en
    Card(Modifier.fillMaxWidth().testTag("private-assistant-scene-ranking"),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(t("Ranked by scene similarity · Check the photos", "按画面相似度排列 · 请查看确认"), style = MaterialTheme.typography.titleMedium)
            Text(t("Scene: ${ranking.query}", "画面描述：${ranking.query}"))
            assistantSearchInterpretationLines(result, zh).forEach { Text(it, style = MaterialTheme.typography.bodyMedium) }
            Text(t("Similarity is approximate ranking, not a match probability or text evidence. Showing ${result.items.size}/${ranking.candidateCount} candidate photos.",
                "相似度是近似排序，不是匹配概率或文字证据。已显示 ${result.items.size}/${ranking.candidateCount} 张候选照片。"), style = MaterialTheme.typography.bodySmall)
            if (result.hasMore) Text(t("Only the first 20 are available here. Narrow the full search to see other photos.",
                "当前只提供前 20 张，请缩小完整查找条件以查看其他照片。"), style = MaterialTheme.typography.bodySmall)
        }
    }
}
