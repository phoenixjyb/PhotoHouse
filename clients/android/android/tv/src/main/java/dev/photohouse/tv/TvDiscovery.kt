package dev.photohouse.tv

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.dp
import dev.photohouse.home.*

/** A remote-first, capability-driven editor. No endpoint, fixture or query fallback lives here. */
@Composable internal fun TvDiscovery(
    options: DiscoveryOptions?, zh: Boolean, applied: DiscoveryDraft = DiscoveryDraft(),
    onClose: () -> Unit, onApply: ((DiscoveryDraft) -> Unit)? = null,
    loading: Boolean = false, problem: HomeError? = null, onRetry: () -> Unit = {},
    more: Set<DiscoveryField> = emptySet(), onMore: (DiscoveryField) -> Unit = {},
    tagQuery: String? = null, tagMatches: Int = 0, tagTotal: Int = 0, onFindTags: (String, Set<String>) -> Unit = { _, _ -> },
    calendarEnabled:Boolean=false,calendar:CalendarState=CalendarState(),onCalendar:(CalendarRequest)->Unit={}
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    var tagText by remember { mutableStateOf(tagQuery.orEmpty()) }
    var editing by remember { mutableStateOf(false) }
    var section by remember { mutableStateOf<DiscoveryField?>(null) }
    var draft by remember(applied) { mutableStateOf(applied) }
    var returnTag by remember { mutableStateOf("discovery-back") }
    val first = remember(editing, section) { FocusRequester() }
    val windowFocused = LocalWindowInfo.current.isWindowFocused
    val list = rememberLazyListState()
    fun back() { if (editing) { draft = applied; editing = false } else onClose() }
    BackHandler { back() }
    LaunchedEffect(editing, section, windowFocused) {
        if (!windowFocused) return@LaunchedEffect
        val banner = if (options == null || options.partialIndex || loading || problem != null) 1 else 0
        val destination = when {
            editing || returnTag == "discovery-back" -> 0
            returnTag.startsWith("quick-person-") -> 1 + banner
            returnTag == "advanced-search" -> 3 + banner
            else -> 2 + banner
        }
        list.scrollToItem(destination)
        withFrameNanos { }
        first.requestFocus()
    }
    fun open(field: DiscoveryField?, tag: String, initial: DiscoveryDraft = applied) { section = field; draft = initial; returnTag = tag; editing = true }
    val issue = draft.issue(options)
    LazyColumn(Modifier.fillMaxSize().testTag("discovery"), state = list, contentPadding = PaddingValues(bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Column(Modifier.weight(1f)) {
                    Text(if (!editing) t("Find a memory", "找到想念的那一刻") else if (section == null)
                        t("Advanced search", "高级搜索") else fieldLabel(section!!, zh), style = MaterialTheme.typography.headlineMedium)
                    Text(if (!editing) t("People, places and little moments.", "家人、远方，还有日常的小美好。") else
                        t("Combine filters to find a memory.", "组合条件，查找回忆。"), color = Muted, style = MaterialTheme.typography.bodyMedium)
                }
                TvButton(t("Back", "返回"), Modifier.testTag("discovery-back").then(
                    if (editing || returnTag == "discovery-back") Modifier.focusRequester(first) else Modifier)) { back() }
            }
        }
        if (loading || problem != null || options == null) item {
            Surface(color = Moss, shape = RoundedCornerShape(16.dp)) {
                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (loading) {
                        Text(t("Opening your library's filters…", "正在读取媒体库的筛选条件…"))
                        LinearProgressIndicator(Modifier.fillMaxWidth().testTag("discovery-loading"))
                    } else if (problem != null) {
                        Text(if (problem == HomeError.BUSY) t("Search is busy. Please try again shortly.", "搜索暂时繁忙，请稍后重试。") else
                            t("Search couldn't be loaded. Your filters have not been applied.", "暂时无法读取搜索，筛选条件尚未应用。"), modifier = Modifier.testTag("discovery-error"))
                        TvButton(t("Retry", "重试"), Modifier.testTag("retry-discovery")) { onRetry() }
                    } else {
                        Text(t("Search is being prepared", "搜索功能准备中"), style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.testTag("discovery-unavailable"))
                        Text(t("People, dates, places and tags will appear when your library makes them available. You can keep browsing your photos and videos.",
                        "媒体库准备好后，这里将显示人物、日期、地点和标签。现在可以继续浏览照片和视频。"), color = Muted)
                    }
                }
            }
        } else if (options.partialIndex) item {
            Text(t("Some library metadata is missing. Search results may be incomplete.",
                "部分媒体信息尚不完整，搜索结果可能不完整。"), color = Gold, modifier = Modifier.testTag("discovery-partial"))
        }
        if (!editing) {
            item {
                Text(t("Your people", "想念的人"), style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(8.dp))
                if (options != null && DiscoveryField.PEOPLE in options.fields && options.pinnedPeople.isNotEmpty()) {
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        options.pinnedPeople.mapNotNull { id -> options.people.find { it.id == id } }.forEach { person ->
                            DiscoveryCard(person.label, person.aliases.joinToString(" · "), false,
                                Modifier.width(184.dp).testTag("quick-person-${person.id}").then(
                                    if (returnTag == "quick-person-${person.id}") Modifier.focusRequester(first) else Modifier),
                                badge = person.label.takeIf { it.isNotEmpty() }?.let { String(Character.toChars(it.codePointAt(0))) }) {
                                val next = DiscoveryDraft(people = setOf(person.id))
                                if (onApply != null && !loading && problem == null && next.issue(options) == null) onApply(next)
                                else open(DiscoveryField.PEOPLE, "quick-person-${person.id}", next)
                            }
                        }
                    }
                } else Text(t("Family shortcuts will appear after people are linked to your library.",
                    "关联人物后，这里会显示家人的快捷入口。"), color = Muted)
            }
            item {
                Text(t("A different way to remember", "换个方式，重温回忆"), style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(8.dp))
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    for (field in listOf(DiscoveryField.PLACES, DiscoveryField.DATES, DiscoveryField.THEMES, DiscoveryField.TOPICS, DiscoveryField.TAGS)) {
                        val tag = "explore-${field.name.lowercase()}"
                        val hint = if (field == DiscoveryField.PLACES) placeEntryHint(options, zh) else fieldHint(field, zh)
                        DiscoveryCard(fieldLabel(field, zh), hint, false,
                            Modifier.width(200.dp).heightIn(min = 104.dp).testTag(tag).then(if (returnTag == tag) Modifier.focusRequester(first) else Modifier)) { open(field, tag) }
                    }
                }
            }
            item {
                TvButton(t("Advanced search", "高级搜索"), Modifier.testTag("advanced-search").then(
                    if (returnTag == "advanced-search") Modifier.focusRequester(first) else Modifier)) { open(null, "advanced-search") }
                Text(t("Combine people, dates, text, places and media type.", "组合人物、日期、文字、地点和媒体类型。"), color = Muted,
                    modifier = Modifier.padding(top = 6.dp), style = MaterialTheme.typography.bodyMedium)
            }
        } else {
            if (draft.count > 0) item {
                Text(t("${draft.count} active filters · all categories must match", "已选 ${draft.count} 类条件 · 不同类别须同时满足"),
                    color = Gold, modifier = Modifier.testTag("filter-summary"))
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (draft.text.isNotEmpty()) TvButton(t("Text ×", "文字 ×")) { draft = draft.copy(text = "") }
                    if (draft.people.isNotEmpty()) TvButton(t("People ×", "人物 ×")) { draft = draft.copy(people = emptySet()) }
                    if (draft.from.isNotEmpty() || draft.through.isNotEmpty()) TvButton(t("Dates ×", "日期 ×")) { draft = draft.copy(from = "", through = "") }
                    if (draft.themes.isNotEmpty()) TvButton(t("Themes ×", "主题 ×")) { draft = draft.copy(themes = emptySet()) }
                    if (draft.topics.isNotEmpty()) TvButton(t("Topics ×", "话题 ×")) { draft = draft.copy(topics = emptySet()) }
                    if (draft.tags.isNotEmpty()) TvButton(t("Tags ×", "标签 ×")) { draft = draft.copy(tags = emptySet()) }
                    if (draft.place != null) TvButton(t("Place ×", "地点 ×")) { draft = draft.copy(place = null) }
                    if (draft.media != null) TvButton(t("Media ×", "类型 ×")) { draft = draft.copy(media = null) }
                }
            }
            for (field in DiscoveryField.entries.filter { section == null || it == section }) item(key = field) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(fieldLabel(field, zh), style = MaterialTheme.typography.titleMedium)
                    options?.coverage?.get(field)?.let { coverage ->
                        Text(t("${coverage.withValues} items have this metadata · ${coverage.withoutValues} without a value", "${coverage.withValues} 项已有此信息 · ${coverage.withoutValues} 项暂无记录"),
                            color = Muted, style = MaterialTheme.typography.bodySmall)
                    }
                    if (options == null || field !in options.fields) {
                        Text(t("This filter is not available in your library yet.", "媒体库暂未提供此筛选条件。"), color = Muted)
                    } else when (field) {
                        DiscoveryField.TEXT -> {
                            DraftText(draft.text, t("Words in captions", "说明中的文字"), "search-text") { draft = draft.copy(text = it) }
                            Text(t("Search caption words. A name mentioned in a caption is not a confirmed person match.",
                                "搜索说明中的文字。说明中提到姓名，不代表已确认的人物关联。"), color = Muted, style = MaterialTheme.typography.bodySmall)
                        }
                        DiscoveryField.DATES -> {
                            if(calendarEnabled) TvCalendarPicker(calendar,zh,onCalendar) {from,through -> draft=draft.copy(from=from,through=through)}
                            if (options.years.isNotEmpty()) Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                options.years.forEach { year -> TvButton(year.toString(), Modifier.testTag("year-$year")) { draft = draft.year(year) } }
                            } else YearPicker(options, zh) { draft = draft.year(it) }
                            DraftText(draft.from, t("From · YYYY-MM-DD", "开始 · YYYY-MM-DD"), "date-from", 10) { draft = draft.copy(from = it) }
                            DraftText(draft.through, t("Through · YYYY-MM-DD", "截至 · YYYY-MM-DD"), "date-through", 10) { draft = draft.copy(through = it) }
                            Text(t("Dates follow the library's recorded date. Items without a date won't match a date filter.",
                                "按媒体库记录的日期查找。没有日期的内容不会匹配日期条件。"), color = Muted, style = MaterialTheme.typography.bodySmall)
                        }
                        DiscoveryField.PEOPLE -> {
                            ChoiceRow(options.people, draft.people, "person", zh) { draft = draft.copy(people = toggle(draft.people, it)) }
                            if (options.peopleAll) MatchRow(draft.peopleMatch, zh, "people-match") { draft = draft.copy(peopleMatch = it) }
                        }
                        DiscoveryField.THEMES -> ChoiceRow(options.themes, draft.themes, "theme", zh) { draft = draft.copy(themes = toggle(draft.themes, it)) }
                        DiscoveryField.TOPICS -> ChoiceRow(options.topics, draft.topics, "topic", zh) { draft = draft.copy(topics = toggle(draft.topics, it)) }
                        DiscoveryField.TAGS -> {
                            if (tagQuery != null) {
                                DraftText(tagText,t("Find a tag", "查找标签"),"tag-query",128) { tagText=it }
                                TvButton(t("Search tags", "搜索标签"),Modifier.testTag("find-tags"),enabled=!loading && tagText.trim().toByteArray(Charsets.UTF_8).size <= 128) { onFindTags(tagText,draft.tags) }
                                Text(t("$tagMatches of $tagTotal matches loaded. Selected tags stay available.", "已加载 $tagMatches / $tagTotal 个匹配标签，保留已选标签。"),color=Muted)
                            }
                            ChoiceRow(options.tags, draft.tags, "tag", zh) { draft = draft.copy(tags = toggle(draft.tags, it)) }
                            if (options.tagsAll) MatchRow(draft.tagsMatch, zh, "tags-match") { draft = draft.copy(tagsMatch = it) }
                            Text(t("Existing tags do not mean tagging is complete. Caption-derived tags and reviewed people remain separate.",
                                "已有标签不代表标注已完成。说明生成的标签与已确认的人物关联分别处理。"), color = Muted, style = MaterialTheme.typography.bodySmall)
                        }
                        DiscoveryField.PLACES -> {
                            ChoiceRow(options.places, setOfNotNull(draft.place), "place", zh) { draft = draft.copy(place = if (draft.place == it) null else it) }
                            Text(t("Only named places are shown. Unnamed places are never guessed.", "仅显示已命名地点，不推测未命名地点。"), color = Muted, style = MaterialTheme.typography.bodySmall)
                        }
                        DiscoveryField.MEDIA -> Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            for (kind in listOf(null, AssetKind.PHOTO, AssetKind.VIDEO)) {
                                val label = when (kind) { AssetKind.PHOTO -> t("Photos", "照片"); AssetKind.VIDEO -> t("Videos", "视频"); else -> t("All media", "全部") }
                                DiscoveryCard(label, "", draft.media == kind, Modifier.testTag("media-${kind?.name ?: "ALL"}")) { draft = draft.copy(media = kind) }
                            }
                        }
                    }
                    if (field in more) TvButton(t("More choices", "更多选项"), Modifier.testTag("more-${field.name}"), enabled = !loading) { onMore(field) }
                }
            }
            item {
                if (issue != null && options != null) Text(issueText(issue, zh), color = Gold, modifier = Modifier.testTag("draft-error"))
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    TvButton(t("Find memories", "查找回忆"), Modifier.testTag("apply-search"), enabled = issue == null && onApply != null && !loading && problem == null) { onApply?.invoke(draft.normalized()) }
                    TvButton(t("Clear filters", "清除条件"), Modifier.testTag("clear-search")) { draft = DiscoveryDraft() }
                    TvButton(t("Cancel", "取消"), Modifier.testTag("cancel-search")) { back() }
                }
            }
        }
    }
}

private fun toggle(ids: Set<String>, id: String) = if (id in ids) ids - id else ids + id

@Composable private fun DraftText(value: String, label: String, tag: String, limit: Int = 256, changed: (String) -> Unit) {
    OutlinedTextField(value, { if (it.length <= limit && it.none(Char::isISOControl)) changed(it) },
        Modifier.fillMaxWidth().testTag(tag), singleLine = true, label = { Text(label) }, shape = RoundedCornerShape(12.dp))
}
@Composable private fun ChoiceRow(choices: List<DiscoveryChoice>, selected: Set<String>, tag: String, zh: Boolean, choose: (String) -> Unit) {
    if (choices.isEmpty()) Text(if (zh) "暂时没有可选项。" else "No choices available yet.", color = Muted)
    else LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.testTag("choices-$tag")) {
        items(choices, key = { it.id }) { choice -> DiscoveryCard(choice.label, choiceHint(choice, zh), choice.id in selected,
            Modifier.widthIn(min = 156.dp, max = 260.dp).testTag("$tag-${choice.id}")) { choose(choice.id) } }
    }
}
@Composable private fun YearPicker(options: DiscoveryOptions, zh: Boolean, chosen: (Int) -> Unit) {
    val low = options.dateFrom?.take(4)?.toIntOrNull() ?: 1
    val high = options.dateThrough?.take(4)?.toIntOrNull() ?: 9999
    var year by remember(options.dateFrom, options.dateThrough) { mutableStateOf(java.time.LocalDate.now().year.coerceIn(low, high)) }
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        TvButton("−10", enabled = year > low) { year = (year - 10).coerceAtLeast(low) }
        TvButton("−1", enabled = year > low) { year-- }
        TvButton(if (zh) "查看 $year 年" else "Use $year", Modifier.testTag("use-year")) { chosen(year) }
        TvButton("+1", enabled = year < high) { year++ }
        TvButton("+10", enabled = year < high) { year = (year + 10).coerceAtMost(high) }
    }
}
internal fun choiceHint(choice: DiscoveryChoice, zh: Boolean): String = buildList {
    if (choice.aliases.isNotEmpty()) add(choice.aliases.joinToString(" · "))
    choice.assetCount?.let { add(if (zh) "$it 项" else "$it items") }
    choice.provenance.filterValues { it > 0 }.forEach { (source, count) ->
        val label = when (source) {
            "reviewed_assignments" -> if (zh) "已确认人物" else "Reviewed people"
            "reviewed_region" -> if (zh) "已确认地区" else "Reviewed region"
            "manual" -> if (zh) "人工" else "Manual"
            "caption" -> if (zh) "来自说明" else "Caption-derived"
            "image" -> if (zh) "来自图像" else "Image-derived"
            "caption_image" -> if (zh) "说明与图像" else "Caption/image-derived"
            "rule" -> if (zh) "规则" else "Rule-derived"
            else -> if (zh) "来源未知" else "Unknown source"
        }
        add("$label · $count")
    }
}.joinToString("\n")
@Composable private fun MatchRow(mode: MatchMode, zh: Boolean, tag: String, changed: (MatchMode) -> Unit) {
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        for (value in MatchMode.entries) DiscoveryCard(if (value == MatchMode.ANY) { if (zh) "任意一个" else "Any selected" }
            else { if (zh) "全部同时" else "All selected" }, "", mode == value, Modifier.testTag("$tag-${value.name}")) { changed(value) }
    }
}
@Composable private fun DiscoveryCard(title: String, subtitle: String, checked: Boolean, modifier: Modifier = Modifier, badge: String? = null, click: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    OutlinedButton(click, modifier.heightIn(min = 52.dp).onFocusChanged { focused = it.isFocused }.semantics { selected = checked },
        shape = RoundedCornerShape(16.dp), contentPadding = PaddingValues(16.dp),
        border = BorderStroke(if (focused) 3.dp else 1.dp, if (focused || checked) Gold else Edge),
        colors = ButtonDefaults.outlinedButtonColors(containerColor = if (focused) Gold else Moss, contentColor = if (focused) Ink else Cream)) {
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            if (badge != null) Surface(Modifier.size(40.dp).clearAndSetSemantics {}, shape = CircleShape, color = if (focused) Ink else Edge) {
                Box(contentAlignment = Alignment.Center) { Text(badge, color = Gold, style = MaterialTheme.typography.labelLarge) }
            }
            Text((if (checked) "✓  " else "") + title, style = MaterialTheme.typography.titleMedium)
            if (subtitle.isNotEmpty()) Text(subtitle, color = if (focused) Ink else Muted, style = MaterialTheme.typography.bodyMedium)
        }
    }
}
private fun fieldLabel(field: DiscoveryField, zh: Boolean): String = when (field) {
    DiscoveryField.TEXT -> if (zh) "文字" else "Caption text"
    DiscoveryField.PEOPLE -> if (zh) "人物" else "People"
    DiscoveryField.DATES -> if (zh) "日期" else "Dates"
    DiscoveryField.THEMES -> if (zh) "主题" else "Themes"
    DiscoveryField.TOPICS -> if (zh) "话题" else "Topics"
    DiscoveryField.TAGS -> if (zh) "标签" else "Tags"
    DiscoveryField.PLACES -> if (zh) "地点" else "Places"
    DiscoveryField.MEDIA -> if (zh) "媒体类型" else "Media type"
}
private fun fieldHint(field: DiscoveryField, zh: Boolean): String = when (field) {
    DiscoveryField.DATES -> if (zh) "重温那年那月" else "Return to a year or season"
    DiscoveryField.THEMES -> if (zh) "回忆里的故事" else "Stories that belong together"
    DiscoveryField.TOPICS -> if (zh) "生活里的点滴" else "The things you love"
    DiscoveryField.TAGS -> if (zh) "从细节发现回忆" else "Discover the little details"
    DiscoveryField.PLACES -> if (zh) "记忆走过的地方" else "Somewhere worth remembering"
    else -> ""
}
internal fun placeEntryHint(options: DiscoveryOptions?, zh: Boolean): String {
    if (options == null || DiscoveryField.PLACES !in options.fields) {
        return if (zh) "媒体库暂未提供地点筛选" else "Places are not available yet"
    }
    val coverage = options.coverage[DiscoveryField.PLACES]
    return if (coverage == null || coverage.withValues == 0) {
        if (zh) "暂无已命名地点；未命名地点会明确区分" else "No named places yet; unnamed places are explicit"
    } else if (zh) {
        "${coverage.withValues} 条有命名地点 · ${coverage.withoutValues} 条无命名地点"
    } else {
        "${coverage.withValues} with named places · ${coverage.withoutValues} without a named place"
    }
}
private fun issueText(issue: DraftIssue, zh: Boolean) = when (issue) {
    DraftIssue.TOO_LONG -> if (zh) "请缩短文字或减少选项（每类最多 10 项）。" else "Use shorter text or fewer choices (up to 10 per category)."
    DraftIssue.DATE_FORMAT -> if (zh) "请输入有效日期，例如 2024-02-29。" else "Enter a valid date, for example 2024-02-29."
    DraftIssue.DATE_ORDER -> if (zh) "结束日期不能早于开始日期。" else "The end date must not be before the start date."
    DraftIssue.UNKNOWN_CHOICE -> if (zh) "部分选项已不可用，请重新选择。" else "Some choices are no longer available. Select them again."
    DraftIssue.UNSUPPORTED -> if (zh) "媒体库暂不支持所选条件。" else "Your library does not support these filters yet."
}
