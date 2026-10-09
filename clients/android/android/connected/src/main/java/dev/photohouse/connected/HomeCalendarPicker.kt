package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.home.*

@Composable internal fun HomeCalendarPicker(state:CalendarState,zh:Boolean,open:(CalendarRequest)->Unit,choose:(String,String)->Unit) {
    fun t(en:String,cn:String)=if(zh) cn else en
    val page=state.page
    val grids=state.covers?.state?.collectAsState()?.value?.grids.orEmpty()
    Column(verticalArrangement=Arrangement.spacedBy(10.dp),modifier=Modifier.testTag("home-calendar")) {
        if(page==null && !state.loading && state.problem==null) {
            OutlinedButton(onClick={ open(CalendarRequest()) },modifier=Modifier.testTag("calendar-open")) { Text(t("Browse years and months","按年月浏览")) }
        }
        if(state.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
        state.problem?.let { Text(homeProblem(it,zh));OutlinedButton(onClick={ open(state.request) },modifier=Modifier.testTag("calendar-retry")) { Text(t("Retry date browsing","重试日期浏览")) } }
        if(page!=null) {
            Text(t("${page.dated} dated memories · ${page.undated} without dates","${page.dated} 项有日期 · ${page.undated} 项暂无日期"),style=MaterialTheme.typography.bodySmall)
            Text(t("Counts include all media. Your other filters apply when you find memories.","数量包含所有媒体；查找回忆时会结合其他筛选条件。"),style=MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                if(page.request.year!=null) TextButton(onClick={open(page.request.parent())},modifier=Modifier.testTag("calendar-parent")) { Text(t("Up one level","返回上一级")) }
                page.request.range()?.let { range -> TextButton(onClick={choose(range.first,range.second)},modifier=Modifier.testTag("calendar-use-period")) { Text(t("Use this ${if(page.request.month==null) "year" else "month"}",if(page.request.month==null) "选择整年" else "选择整月")) } }
            }
            Text(listOfNotNull(page.request.year?.toString(),page.request.month?.toString()).joinToString(" / ").ifEmpty { t("Through the years","时光相册") },style=MaterialTheme.typography.titleMedium)
            if(page.buckets.isEmpty()) Text(t("No dated memories here.","这段时间暂无带日期的回忆。"))
            LazyRow(horizontalArrangement=Arrangement.spacedBy(12.dp),modifier=Modifier.testTag("calendar-cards")) {
                items(page.buckets.size,key={page.buckets[it].key}) { i -> val bucket=page.buckets[i]
                    OutlinedCard(onClick={bucket.child()?.let(open) ?: choose(bucket.from,bucket.through)},modifier=Modifier.width(160.dp).testTag("calendar-${bucket.key}")) {
                        HomeThumbnail(bucket.cover?.id?.let { grids[it] },bucket.key,t("Memories","时光"))
                        Column(Modifier.padding(12.dp)) { Text(bucket.key,style=MaterialTheme.typography.titleMedium);Text(t("${bucket.count} memories","${bucket.count} 项回忆")) }
                    }
                }
            }
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                if(page.request.page>1) TextButton(onClick={open(page.request.copy(page=page.request.page-1))},modifier=Modifier.testTag("calendar-previous")) { Text(t("Previous","上一页")) }
                if(page.hasMore) TextButton(onClick={open(page.request.copy(page=page.request.page+1))},modifier=Modifier.testTag("calendar-next")) { Text(t("More years","更多年份")) }
            }
        }
    }
}
