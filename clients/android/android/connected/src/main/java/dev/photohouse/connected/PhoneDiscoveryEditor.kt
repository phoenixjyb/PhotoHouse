package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
internal fun LazyListScope.phoneDiscoveryEditor(store: ConnectedStore, state: LiveState, zh: Boolean) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val current = state.discovery ?: return
    val snapshot = current.snapshot
    val f = current.filters
    val enabled = snapshot?.enabled.orEmpty()
    fun choose(field: PhoneFacet, choice: PhoneChoice) {
        val old = when (field) { PhoneFacet.PEOPLE -> f.people; PhoneFacet.TAGS -> f.tags; PhoneFacet.PLACES -> f.places }
        val next = if (old.any { it.id == choice.id }) old.filterNot { it.id == choice.id } else old + choice
        store.updateDiscoveryFilters(when (field) { PhoneFacet.PEOPLE -> f.copy(people = next); PhoneFacet.TAGS -> f.copy(tags = next); PhoneFacet.PLACES -> f.copy(places = next) })
    }
    item {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(t("Find a memory", "寻找回忆"), style = MaterialTheme.typography.headlineMedium, fontFamily = FontFamily.Serif)
            Text(t("Bring together people, moments and places.", "从家人、时光和地点，找回珍贵瞬间。"), color = MaterialTheme.colorScheme.onSurfaceVariant)
            TextButton(onClick = { store.loadPage(1) }, modifier = Modifier.testTag("discovery-all-photos")) { Text(t("All photos", "全部照片")) }
        }
    }
    if (snapshot == null) {
        if (!state.busy) item { Button(onClick = store::openDiscovery, modifier = Modifier.testTag("discovery-reload")) { Text(t("Refresh search options", "刷新搜索选项")) } }
        return
    }
    item {
        Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(t("Family & favourites", "家人和常看"), style = MaterialTheme.typography.titleLarge)
            if (snapshot.pins.isEmpty()) Text(t("Pinned people will appear here when available.", "设置好的家人快捷入口将在这里显示。"))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                snapshot.pins.forEach { person ->
                    FilterChip(selected = f.people.any { it.id == person.id }, onClick = { choose(PhoneFacet.PEOPLE, person) }, enabled = !state.busy,
                        label = { Text((listOf(person.label) + person.aliases).distinct().joinToString(" / ")) }, modifier = Modifier.testTag("pin-${person.id}"))
                }
            }
            Button(onClick = store::applyDiscovery, enabled = !state.busy, modifier = Modifier.fillMaxWidth().testTag("discovery-quick-apply")) {
                Text(t("Find memories", "查找回忆"))
            }
            if (current.inputInvalid) Text(t("Check dates and selected filters below.", "请检查下方的日期和已选条件。"), color = MaterialTheme.colorScheme.error)
            Text(t("${snapshot.indexed} of ${snapshot.assets} memories have searchable metadata. Missing details can limit matches.",
                "${snapshot.assets} 条回忆中，${snapshot.indexed} 条有搜索资料。缺少信息可能影响搜索结果。"), style = MaterialTheme.typography.bodySmall)
            val selected = f.people.map { it.label } + f.tags.map { it.label } + f.places.map { it.label } +
                listOf(f.from.takeIf { it.isNotBlank() }, f.to.takeIf { it.isNotBlank() }).filterNotNull()
            Text(if (selected.isEmpty()) t("No filters selected", "尚未选择筛选条件")
                else t("Filters: ${selected.joinToString(" · ")}", "筛选：${selected.joinToString(" · ")}"),
                modifier = Modifier.testTag("discovery-filter-summary"), style = MaterialTheme.typography.bodySmall)
        } }
    }
    item {
        val placeCoverage = snapshot.coverage["locations"]
        val placesEnabled = "locations" in enabled
        Card(Modifier.fillMaxWidth().testTag("discovery-places-entry")) {
            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(t("Browse by place", "按地点浏览"), style = MaterialTheme.typography.titleLarge)
                if (!placesEnabled) {
                    Text(t("Places are not available in this library yet.", "此媒体库暂未提供地点筛选。"),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.testTag("discovery-places-unavailable"))
                } else if (placeCoverage == null || placeCoverage.withValues == 0) {
                    Text(t("No named places are available yet. Unnamed places are kept distinct.", "暂无已命名地点。未命名地点会明确区分。"),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.testTag("discovery-places-empty"))
                } else {
                    Text(t("${placeCoverage.withValues} memories have a named place; ${placeCoverage.withoutValues} have no named place.",
                        "${placeCoverage.withValues} 条回忆有已命名地点；${placeCoverage.withoutValues} 条没有已命名地点。"),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.testTag("discovery-places-coverage"))
                }
                OutlinedButton(onClick = { store.loadDiscoveryFacet(PhoneFacet.PLACES) },
                    enabled = !state.busy && placesEnabled,
                    modifier = Modifier.fillMaxWidth().testTag("browse-places")) {
                    Text(t("Choose a place", "选择地点"))
                }
                OutlinedTextField(
                    value = current.placeQuery,
                    onValueChange = { if (PhoneDiscoveryWire.validPlaceQuery(it)) store.updatePlaceQuery(it) },
                    label = { Text(t("Search places", "搜索地点")) },
                    supportingText = { Text(t("Example: Beijing", "例如：北京")) },
                    singleLine = true,
                    enabled = !state.busy && placesEnabled,
                    modifier = Modifier.fillMaxWidth().testTag("place-query"))
                OutlinedButton(
                    onClick = store::searchPlaces,
                    enabled = !state.busy && placesEnabled,
                    modifier = Modifier.fillMaxWidth().testTag("place-query-search")) {
                    Text(t("Search places", "搜索地点"))
                }
            }
        }
    }
    current.facetPage?.let { page ->
        item {
            Text(t("${page.facet.name.lowercase().replaceFirstChar { it.uppercase() }} choices", "${page.facet.name}选项"),
                style = MaterialTheme.typography.titleLarge, modifier = Modifier.testTag("facet-choices-heading"))
        }
        if (page.items.isEmpty()) item { Text(t("No choices available in this category.", "此类别暂无可选项。")) }
        items(page.items, key = { "choice-${page.facet.wire}-${it.id}" }) { choice ->
            val selected = when (page.facet) { PhoneFacet.PEOPLE -> f.people; PhoneFacet.TAGS -> f.tags; PhoneFacet.PLACES -> f.places }
            OutlinedCard(onClick = { choose(page.facet, choice) }, enabled = !state.busy,
                modifier = Modifier.fillMaxWidth().testTag("choice-${page.facet.wire}-${choice.id}")) {
                Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Checkbox(checked = selected.any { it.id == choice.id }, onCheckedChange = null)
                    Column(Modifier.weight(1f)) {
                        Text(choice.label, style = MaterialTheme.typography.titleMedium)
                        if (choice.aliases.isNotEmpty()) Text(choice.aliases.joinToString(" / "))
                        Text(t("${choice.count} memories", "${choice.count} 条回忆"), style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
        item { FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { store.loadDiscoveryFacet(page.facet, page.page - 1) }, enabled = !state.busy && page.page > 1,
                modifier = Modifier.testTag("facet-previous")) { Text(t("Previous choices", "上一页选项")) }
            OutlinedButton(onClick = { store.loadDiscoveryFacet(page.facet, page.page + 1) }, enabled = !state.busy && page.more && page.page < 5000,
                modifier = Modifier.testTag("facet-next")) { Text(t("More choices", "更多选项")) }
        } }
    }
    item {
        Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(t("Moment & date", "时光与日期"), style = MaterialTheme.typography.titleLarge)
            if ("caption" in enabled) OutlinedTextField(f.caption, { if (it.toByteArray(Charsets.UTF_8).size <= 512) store.updateDiscoveryFilters(f.copy(caption = it)) },
                label = { Text(t("Words in captions", "描述中的文字")) }, supportingText = { Text(t("For example: beach, birthday, a family meal", "例如：海边、生日、家人聚餐")) },
                enabled = !state.busy, modifier = Modifier.fillMaxWidth().testTag("discovery-caption"))
            if ("date" in enabled) {
                Text(t("Recorded date · YYYY-MM-DD; either end is optional", "拍摄日期 · 年-月-日；可只填开始或结束"), style = MaterialTheme.typography.bodySmall)
                var dateTarget by remember { mutableStateOf<String?>(null) }
                val datePicker = rememberDatePickerState()
                fun millis(value: String): Long? = runCatching {
                    LocalDate.parse(value).takeIf { it.year in 1900..2100 }?.atStartOfDay(ZoneOffset.UTC)?.toInstant()?.toEpochMilli()
                }.getOrNull()
                @Composable fun dateField(value: String, label: String, textTag: String, pickerTag: String, update: (String) -> Unit) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        OutlinedTextField(value, { if (it.length <= 10) update(it) }, label = { Text(label) },
                            singleLine = true, enabled = !state.busy, modifier = Modifier.weight(1f).testTag(textTag))
                        OutlinedButton(onClick = { dateTarget = textTag; datePicker.selectedDateMillis = millis(value); millis(value)?.let { datePicker.displayedMonthMillis = it } },
                            enabled = !state.busy, modifier = Modifier.testTag(pickerTag)) { Text(t("Pick", "选择")) }
                    }
                }
                dateField(f.from, t("From", "开始日期"), "discovery-from", "discovery-from-picker") { store.updateDiscoveryFilters(f.copy(from = it)) }
                dateField(f.to, t("To", "结束日期"), "discovery-to", "discovery-to-picker") { store.updateDiscoveryFilters(f.copy(to = it)) }
                if (dateTarget != null) DatePickerDialog(onDismissRequest = { dateTarget = null }, confirmButton = {
                    TextButton(onClick = {
                        datePicker.selectedDateMillis?.let { selected ->
                            val value = Instant.ofEpochMilli(selected).atZone(ZoneOffset.UTC).toLocalDate().toString()
                            if (dateTarget == "discovery-from") store.updateDiscoveryFilters(f.copy(from = value)) else store.updateDiscoveryFilters(f.copy(to = value))
                        }
                        dateTarget = null
                    }) { Text(t("Apply", "应用")) }
                }, dismissButton = { TextButton(onClick = { dateTarget = null }) { Text(t("Cancel", "取消")) } }) {
                    DatePicker(state = datePicker, showModeToggle = false)
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("image" to t("Photos", "照片"), "video" to t("Videos", "视频"), "other" to t("Other media", "其他媒体")).forEach { (key, label) ->
                    FilterChip(selected = key in f.media, onClick = { store.updateDiscoveryFilters(f.copy(media = if (key in f.media) f.media - key else f.media + key)) },
                        enabled = !state.busy, label = { Text(label) }, modifier = Modifier.testTag("discovery-media-$key"))
                }
            }
            Text(t("Leave media choices empty to include all types.", "不选媒体类型时，包含所有类型。"), style = MaterialTheme.typography.bodySmall)
        } }
    }
    item {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(t("People, tags & places", "人物、标签和地点"), style = MaterialTheme.typography.titleLarge)
            Text(t("Different filters combine together. Choose up to 20 in each group.", "不同类别的条件同时生效，每类最多选择 20 项。"), style = MaterialTheme.typography.bodySmall)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (field in PhoneFacet.entries) FilterChip(selected = current.facetPage?.facet == field,
                    onClick = { store.loadDiscoveryFacet(field) }, enabled = !state.busy && field.wire in enabled,
                    modifier = Modifier.testTag("facet-${field.wire}"), label = { Text(when (field) {
                        PhoneFacet.PEOPLE -> t("People", "人物"); PhoneFacet.TAGS -> t("Tags", "标签"); PhoneFacet.PLACES -> t("Places", "地点") }) })
            }
            for ((title, selected, field) in listOf(Triple(t("Selected people", "已选人物"), f.people, PhoneFacet.PEOPLE),
                Triple(t("Selected tags", "已选标签"), f.tags, PhoneFacet.TAGS), Triple(t("Selected places", "已选地点"), f.places, PhoneFacet.PLACES))) {
                if (selected.isNotEmpty()) {
                    Text(title, style = MaterialTheme.typography.titleSmall)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        selected.forEach { choice -> InputChip(selected = true, onClick = { choose(field, choice) }, enabled = !state.busy,
                            label = { Text("${choice.label} ×") }, modifier = Modifier.testTag("selected-${field.wire}-${choice.id}")) }
                    }
                }
            }
            if (f.people.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(false to t("Any selected person", "任一所选人物"), true to t("All selected people", "全部所选人物")).forEach { (all, label) ->
                    FilterChip(selected = f.peopleAll == all, onClick = { store.updateDiscoveryFilters(f.copy(peopleAll = all)) }, enabled = !state.busy, label = { Text(label) })
                }
            }
            if (f.tags.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(false to t("Any selected tag", "任一所选标签"), true to t("All selected tags", "全部所选标签")).forEach { (all, label) ->
                    FilterChip(selected = f.tagsAll == all, onClick = { store.updateDiscoveryFilters(f.copy(tagsAll = all)) }, enabled = !state.busy, label = { Text(label) })
                }
            }
        }
    }
    item {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(t("Themes and topics will appear once organised. Places currently use recorded regions, not a map radius.",
                "主题和话题将在整理完成后开放。地点目前按已记录的区域筛选，暂不支持地图半径。"), style = MaterialTheme.typography.bodySmall)
            if (current.inputInvalid) Text(t("Check dates and selected filters before searching.", "请检查日期和已选条件后再搜索。"), color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag("discovery-input-error"))
            Button(onClick = store::applyDiscovery, enabled = !state.busy, modifier = Modifier.fillMaxWidth().testTag("discovery-apply")) { Text(t("Find memories", "查找回忆")) }
            OutlinedButton(onClick = { store.updateDiscoveryFilters(PhoneFilters()) }, enabled = !state.busy,
                modifier = Modifier.fillMaxWidth().testTag("discovery-clear")) { Text(t("Clear filters", "清空条件")) }
        }
    }
}
