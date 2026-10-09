package dev.photohouse.connected

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.home.*

/** Memory-only touch editor; identity labels and choices come from the reviewed server index. */
@OptIn(ExperimentalLayoutApi::class)
@Composable internal fun HomeDiscoveryEditor(state: DiscoveryState, zh: Boolean, close: () -> Unit,
    retry: () -> Unit, more: (DiscoveryField) -> Unit, apply: (DiscoveryDraft) -> Unit, findTags: (String, Set<String>) -> Unit = { _, _ -> }, calendarEnabled:Boolean=false,onCalendar:(CalendarRequest)->Unit={}) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val snapshot = state.snapshot
    val options = snapshot?.options
    var draft by remember { mutableStateOf(state.query ?: DiscoveryDraft()) }
    var tagText by remember { mutableStateOf(snapshot?.tagQuery.orEmpty()) }
    val ready = options != null && !state.loading && state.problem == null
    fun toggle(values: Set<String>, id: String) = if (id in values) values - id else values + id
    LazyColumn(Modifier.fillMaxSize().safeDrawingPadding().testTag("home-search-editor"), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item {
            TextButton(onClick = close, modifier = Modifier.testTag("home-search-back")) { Text(t("Back to album", "返回相册")) }
            Text(t("Find a memory", "寻找一段回忆"), style = MaterialTheme.typography.headlineLarge)
            Text(t("People, places and moments together.", "从人物、地点和时光，找回那些片刻。"))
        }
        if (state.loading) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        state.problem?.let { error -> item {
            Text(homeProblem(error, zh), color = MaterialTheme.colorScheme.error)
            OutlinedButton(onClick = retry, modifier = Modifier.testTag("home-search-retry")) { Text(t("Retry search options", "重试搜索选项")) }
        } }
        if (options != null) {
            if (options.partialIndex) item { Text(t("Some memories have missing metadata. Results may be incomplete.", "部分回忆的信息尚未完善，搜索结果可能不完整。")) }
            if (DiscoveryField.PLACES in options.fields) item {
                val coverage = options.coverage[DiscoveryField.PLACES]
                Card(Modifier.fillMaxWidth().testTag("home-places-entry")) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(t("Browse by place", "按地点浏览"), style = MaterialTheme.typography.titleMedium)
                        Text(if (coverage == null || coverage.withValues == 0)
                            t("No named places yet; unnamed places are explicit.", "暂无已命名地点；未命名地点会明确区分。")
                        else t("${coverage.withValues} memories have named places; ${coverage.withoutValues} have no named place.",
                            "${coverage.withValues} 条回忆有已命名地点；${coverage.withoutValues} 条没有已命名地点。"),
                            style = MaterialTheme.typography.bodySmall)
                    }
                }
            } else item {
                Text(t("Places are not available in this library yet.", "此媒体库暂未提供地点筛选。"),
                    modifier = Modifier.testTag("home-places-unavailable"), style = MaterialTheme.typography.bodySmall)
            }
            if (DiscoveryField.PEOPLE in options.fields && options.pinnedPeople.isNotEmpty()) item {
                Text(t("Your people", "想念的人"), style = MaterialTheme.typography.titleMedium)
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    options.pinnedPeople.mapNotNull { id -> options.people.find { it.id == id } }.forEach { p ->
                        SuggestionChip(onClick = { apply(DiscoveryDraft(people = setOf(p.id))) }, enabled = ready, label = { Text(p.label) }, modifier = Modifier.testTag("home-quick-person-${p.id}"))
                    }
                }
            }
            if (DiscoveryField.TEXT in options.fields) item {
                OutlinedTextField(draft.text, { draft = draft.copy(text = it) }, enabled = ready, label = { Text(t("Words in captions", "说明中的文字")) }, modifier = Modifier.fillMaxWidth().testTag("home-search-text"))
            }
            if (DiscoveryField.DATES in options.fields) item {
                if(calendarEnabled) HomeCalendarPicker(state.calendar,zh,onCalendar) { from,through -> draft=draft.copy(from=from,through=through) }
                OutlinedTextField(draft.from, { draft = draft.copy(from = it.take(10)) }, enabled = ready, singleLine = true, label = { Text(t("From · YYYY-MM-DD", "开始 · YYYY-MM-DD")) }, modifier = Modifier.fillMaxWidth().testTag("home-search-from"))
                OutlinedTextField(draft.through, { draft = draft.copy(through = it.take(10)) }, enabled = ready, singleLine = true, label = { Text(t("Through · YYYY-MM-DD", "截至 · YYYY-MM-DD")) }, modifier = Modifier.fillMaxWidth().testTag("home-search-through"))
            }
            for ((field, choices) in listOf(DiscoveryField.PEOPLE to options.people, DiscoveryField.TAGS to options.tags, DiscoveryField.PLACES to options.places)) {
                if (field !in options.fields) continue
                item { Text(when(field) { DiscoveryField.PEOPLE -> t("People", "人物"); DiscoveryField.TAGS -> t("Tags", "标签"); else -> t("Places", "地点") }, style = MaterialTheme.typography.titleMedium) }
                if (field == DiscoveryField.TAGS && snapshot?.tagQuery != null) item {
                    OutlinedTextField(tagText, { if (it.toByteArray(Charsets.UTF_8).size <= 128 && it.none { c -> c < ' ' }) tagText = it },
                        enabled=ready, singleLine=true, label={ Text(t("Find a tag", "查找标签")) }, modifier=Modifier.fillMaxWidth().testTag("home-tag-query"))
                    OutlinedButton(onClick={ findTags(tagText,draft.tags) },enabled=ready,modifier=Modifier.testTag("home-find-tags")) { Text(t("Search tags", "搜索标签")) }
                    Text(t("${snapshot.tagMatches.size} of ${snapshot.facetTotals[DiscoveryField.TAGS] ?: 0} matches loaded. Selected tags stay available.",
                        "已加载 ${snapshot.tagMatches.size} / ${snapshot.facetTotals[DiscoveryField.TAGS] ?: 0} 个匹配标签，保留已选标签。"),style=MaterialTheme.typography.bodySmall)
                }
                items(choices.size, key = { "${field.name}-${choices[it].id}" }) { i ->
                    val p = choices[i]
                    val selected = when(field) { DiscoveryField.PEOPLE -> p.id in draft.people; DiscoveryField.TAGS -> p.id in draft.tags; else -> p.id == draft.place }
                    OutlinedCard(onClick = { draft = when(field) {
                        DiscoveryField.PEOPLE -> draft.copy(people = toggle(draft.people, p.id))
                        DiscoveryField.TAGS -> draft.copy(tags = toggle(draft.tags, p.id))
                        else -> draft.copy(place = if (selected) null else p.id)
                    } }, enabled = ready, modifier = Modifier.fillMaxWidth().testTag("home-choice-${field.name.lowercase()}-${p.id}")) {
                        Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Checkbox(selected, onCheckedChange = null)
                            Column(Modifier.weight(1f)) { Text(p.label); if (p.aliases.isNotEmpty()) Text(p.aliases.joinToString(" / "), style = MaterialTheme.typography.bodySmall) }
                        }
                    }
                }
                if (field == DiscoveryField.PEOPLE && options.peopleAll || field == DiscoveryField.TAGS && options.tagsAll) item {
                    val mode = if (field == DiscoveryField.PEOPLE) draft.peopleMatch else draft.tagsMatch
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { MatchMode.entries.forEach { m ->
                        FilterChip(mode == m, { draft = if (field == DiscoveryField.PEOPLE) draft.copy(peopleMatch = m) else draft.copy(tagsMatch = m) }, enabled = ready, label = { Text(if (m == MatchMode.ANY) t("Match any", "符合任一") else t("Match all", "全部符合")) })
                    } }
                }
                if (field in snapshot!!.nextPages) item { TextButton(onClick = { more(field) }, enabled = ready) { Text(t("More choices", "更多选项")) } }
            }
            if (DiscoveryField.MEDIA in options.fields) item {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (kind in listOf(null, AssetKind.PHOTO, AssetKind.VIDEO)) FilterChip(draft.media == kind, { draft = draft.copy(media = kind) }, enabled = ready,
                        label = { Text(when(kind) { AssetKind.PHOTO -> t("Photos", "照片"); AssetKind.VIDEO -> t("Videos", "视频"); else -> t("All media", "全部媒体") }) })
                }
            }
            item {
                val issue = draft.issue(options)
                if (issue != null) Text(t("Check dates, text length and selected filters.", "请检查日期、文字长度和已选条件。"), modifier = Modifier.testTag("home-search-invalid"), color = MaterialTheme.colorScheme.error)
                Text(t("All filter categories must match. Places use named regions.", "不同类别的条件须同时满足。地点按已命名区域筛选。"), style = MaterialTheme.typography.bodySmall)
                Button(onClick = { apply(draft) }, enabled = ready && issue == null, modifier = Modifier.fillMaxWidth().testTag("home-search-apply")) { Text(t("Find memories", "查找回忆")) }
                TextButton(onClick = { draft = DiscoveryDraft() }, enabled = ready, modifier = Modifier.testTag("home-search-reset")) { Text(t("Clear filters", "清空条件")) }
            }
        }
    }
}
