package dev.photohouse.tv

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.home.*

@Composable internal fun TvCalendarPicker(state:CalendarState,zh:Boolean,open:(CalendarRequest)->Unit,choose:(String,String)->Unit) {
    fun t(en:String,cn:String)=if(zh) cn else en
    val page=state.page
    val grids=state.covers?.state?.collectAsState()?.value?.grids.orEmpty()
    val first=remember { FocusRequester() }
    LaunchedEffect(page) { if(page!=null && page.buckets.isNotEmpty()) { withFrameNanos { };first.requestFocus() } }
    Column(verticalArrangement=Arrangement.spacedBy(10.dp),modifier=Modifier.testTag("tv-calendar")) {
        if(page==null && !state.loading && state.problem==null) TvButton(t("Browse years and months","按年月浏览"),Modifier.testTag("calendar-open")) {open(CalendarRequest())}
        if(state.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
        state.problem?.let { Text(t("Date browsing is unavailable. Please retry.","日期浏览暂不可用，请重试。"));TvButton(t("Retry","重试"),Modifier.testTag("calendar-retry")) {open(state.request)} }
        if(page!=null) {
            Text(t("${page.dated} dated memories · ${page.undated} without dates","${page.dated} 项有日期 · ${page.undated} 项暂无日期"),color=Muted)
            Text(t("Counts include all media; other filters apply when you find memories.","数量包含所有媒体；查找回忆时会结合其他筛选条件。"),color=Muted,style=MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                if(page.request.year!=null) TvButton(t("Up one level","返回上一级"),Modifier.testTag("calendar-parent")) {open(page.request.parent())}
                page.request.range()?.let {range -> TvButton(t("Use this period","选择这段时间"),Modifier.testTag("calendar-use-period")) {choose(range.first,range.second)} }
            }
            Text(listOfNotNull(page.request.year?.toString(),page.request.month?.toString()).joinToString(" / ").ifEmpty {t("Through the years","时光相册")},style=MaterialTheme.typography.titleMedium)
            if(page.buckets.isEmpty()) Text(t("No dated memories here.","这段时间暂无带日期的回忆。"))
            LazyRow(horizontalArrangement=Arrangement.spacedBy(12.dp),modifier=Modifier.testTag("calendar-cards")) {
                items(page.buckets.size,key={page.buckets[it].key}) { i -> val bucket=page.buckets[i];var focused by remember {mutableStateOf(false)}
                    OutlinedCard(onClick={bucket.child()?.let(open) ?: choose(bucket.from,bucket.through)},
                        modifier=Modifier.width(190.dp).then(if(i==0) Modifier.focusRequester(first) else Modifier).onFocusChanged {focused=it.isFocused}.testTag("calendar-${bucket.key}"),
                        border=BorderStroke(if(focused) 3.dp else 1.dp,if(focused) Gold else Muted)) {
                        TvImage(bucket.cover?.id?.let {grids[it]},bucket.key,Modifier.fillMaxWidth().height(105.dp),missing=t("Memories","时光"),maxPixels=1_048_576)
                        Column(Modifier.padding(12.dp)) { Text(bucket.key,style=MaterialTheme.typography.titleMedium);Text(t("${bucket.count} memories","${bucket.count} 项回忆")) }
                    }
                }
            }
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                if(page.request.page>1) TvButton(t("Previous","上一页"),Modifier.testTag("calendar-previous")) {open(page.request.copy(page=page.request.page-1))}
                if(page.hasMore) TvButton(t("More years","更多年份"),Modifier.testTag("calendar-next")) {open(page.request.copy(page=page.request.page+1))}
            }
        }
    }
}
