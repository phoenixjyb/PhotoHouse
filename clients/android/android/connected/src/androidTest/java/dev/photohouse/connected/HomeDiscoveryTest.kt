package dev.photohouse.connected

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import dev.photohouse.home.*
import kotlinx.coroutines.*
import org.junit.*
import org.junit.Assert.*
import java.io.File

class HomeDiscoveryTest {
    @get:Rule val rule=createAndroidComposeRule<HomeActivity>()
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
    private lateinit var browse:HomeStore
    private lateinit var discovery:DiscoveryController
    private val queries=mutableListOf<DiscoveryDraft>()
    private var unavailable=false
    private var denied=false
    private fun api(search:Boolean)=object:HomeApi {
        override val catalogVersion=3
        override suspend fun feed(page:Int):HomeFeed {
            if(search && denied) throw HomeFailure(HomeError.DENIED)
            val id=if(search) 20+page else 10
            return HomeFeed(8,"synthetic","Our home",page,1,if(search) 2 else 1,search && page==1,listOf(HomeAsset(id,"A quiet afternoon / 午后时光",null,null)),3)
        }
        override suspend fun preview(asset:HomeAsset,variant:Variant,revision:Int):ByteArray?=null
    }
    private fun start() {
        browse=HomeStore(api(false),scope)
        val gateway=object:DiscoveryGateway {
            override val calendarEnabled=true
            override suspend fun calendar(snapshot:DiscoverySnapshot,request:CalendarRequest):CalendarPage {
                val key=when(request.level) {"year"->"2026";"month"->"2026-02";else->"2026-02-03"}
                val from=when(request.level) {"year"->"2026-01-01";"month"->"2026-02-01";else->key}
                val through=when(request.level) {"year"->"2026-12-31";"month"->"2026-02-28";else->key}
                return CalendarPage(request,1,false,12,2,listOf(CalendarBucket(key,from,through,12,null)))
            }
            override fun calendarCovers(snapshot:DiscoverySnapshot,page:CalendarPage)=api(false)
            override suspend fun load():DiscoverySnapshot {
                if(unavailable) throw HomeFailure(HomeError.OFFLINE)
                return DiscoverySnapshot(9,8,"synthetic","Our home",DiscoveryOptions(
                    setOf(DiscoveryField.PEOPLE,DiscoveryField.TEXT,DiscoveryField.DATES,DiscoveryField.TAGS,DiscoveryField.MEDIA),
                    people=listOf(DiscoveryChoice("201","Sample Adult / 示例成人"),DiscoveryChoice("202","Sample Child / 示例儿童",listOf("Sample Child","示例儿童"))),
                    tags=listOf(DiscoveryChoice("301","Park / 公园")),peopleAll=true,tagsAll=true,pinnedPeople=listOf("202","201"),partialIndex=true),tagQuery="",tagMatches=setOf("301"),facetTotals=mapOf(DiscoveryField.TAGS to 6002))
            }
            override suspend fun findTags(snapshot:DiscoverySnapshot,query:String,selected:Set<String>):DiscoverySnapshot {
                val matches=if(query=="湖") listOf(DiscoveryChoice("8999","Lake / 湖")) else listOf(DiscoveryChoice("301","Park / 公园"))
                return snapshot.copy(tagQuery=query,tagMatches=matches.map { it.id }.toSet(),facetTotals=mapOf(DiscoveryField.TAGS to matches.size),
                    options=snapshot.options.copy(tags=(snapshot.options.tags.filter { it.id in selected }+matches).distinctBy { it.id }))
            }
            override suspend fun more(snapshot:DiscoverySnapshot,field:DiscoveryField)=snapshot
            override fun results(snapshot:DiscoverySnapshot,draft:DiscoveryDraft):HomeApi { queries+=draft;return api(true) }
        }
        discovery=DiscoveryController(gateway,browse,scope)
        rule.runOnUiThread { rule.activity.setContent { HomePhoneApp(browse,discovery, initialZh = false) {} };browse.foreground() }
        rule.waitUntil { browse.state.value.feed!=null }
    }
    private fun tag(name:String) {
        val parent=if(rule.onAllNodesWithTag("home-search-editor").fetchSemanticsNodes().isNotEmpty()) "home-search-editor" else "home-gallery"
        rule.onNodeWithTag(parent).performScrollToNode(hasTestTag(name))
        rule.onNodeWithTag(name).performClick()
    }
    private fun input(name:String,value:String) {
        rule.onNodeWithTag("home-search-editor").performScrollToNode(hasTestTag(name))
        rule.onNodeWithTag(name).performTextReplacement(value)
    }
    @After fun stop() { if(::discovery.isInitialized) rule.runOnUiThread { discovery.background();browse.background() };scope.cancel() }
    @Test fun quickPersonResultsPageAndClearStayInsideHome() {
        start();tag("home-explore");rule.waitUntil { discovery.state.value.snapshot!=null }
        tag("home-quick-person-202");rule.waitUntil { discovery.state.value.results?.state?.value?.feed!=null }
        assertEquals(setOf("202"),queries.single().people)
        rule.onNodeWithTag("home-search-summary").assertExists();rule.onNodeWithTag("home-ready-only").assertDoesNotExist()
        tag("home-next");rule.waitUntil { discovery.state.value.results?.state?.value?.feed?.page==2 }
        tag("home-clear-search");rule.waitUntil { discovery.state.value.results==null && browse.state.value.feed!=null }
        rule.onNodeWithTag("home-asset-10").assertExists();rule.onNodeWithText("Password").assertDoesNotExist()
    }
    @Test fun combinedDraftValidatesAndChineseEditorRenders() {
        start();tag("home-language");tag("home-explore");rule.waitUntil { discovery.state.value.snapshot!=null }
        rule.waitForIdle();snapshot("home-search-zh.png")
        input("home-search-from","2026-13-01")
        rule.onNodeWithTag("home-search-editor").performScrollToNode(hasTestTag("home-search-apply"));rule.onNodeWithTag("home-search-apply").assertIsNotEnabled()
        input("home-search-from","2026-01-01");input("home-search-through","2026-12-31");input("home-search-text","park")
        tag("home-choice-people-201");tag("home-choice-tags-301");tag("home-search-apply")
        rule.waitUntil { queries.size==1 }
        val q=queries.single();assertEquals("park",q.text);assertEquals("2026-01-01",q.from);assertEquals(setOf("201"),q.people);assertEquals(setOf("301"),q.tags)
    }
    @Test fun retryAndDeniedResultsNeverBroadenOrOpenAccount() {
        unavailable=true;start();tag("home-explore");rule.waitUntil { discovery.state.value.problem==HomeError.OFFLINE }
        assertTrue(queries.isEmpty());rule.onNodeWithTag("home-search-editor").assertExists()
        unavailable=false;tag("home-search-retry");rule.waitUntil { discovery.state.value.snapshot!=null }
        denied=true;tag("home-quick-person-202")
        rule.waitUntil { browse.state.value.problem==HomeError.DENIED }
        assertNull(discovery.state.value.results);assertNull(browse.state.value.feed)
        rule.onNodeWithText("Password").assertDoesNotExist()
        rule.runOnUiThread { discovery.background();browse.background() }
        rule.onNodeWithTag("home-covered").assertExists()
    }
    @Test fun tagLookupRetainsSelectionAcrossQueriesAndAppliesBoth() {
        start();tag("home-language");tag("home-explore");rule.waitUntil { discovery.state.value.snapshot!=null }
        tag("home-choice-tags-301");input("home-tag-query","湖");tag("home-find-tags")
        rule.waitUntil { discovery.state.value.snapshot?.tagQuery=="湖" }
        tag("home-choice-tags-8999")
        input("home-tag-query","");tag("home-find-tags")
        rule.waitUntil { discovery.state.value.snapshot?.tagQuery=="" }
        rule.onNodeWithTag("home-search-editor").performScrollToNode(hasTestTag("home-tag-query"));snapshot("home-tags-zh.png")
        tag("home-search-apply");rule.waitUntil { queries.size==1 }
        assertEquals(setOf("301","8999"),queries.single().tags)
    }
    @Test fun visualCalendarSelectsDayAndKeepsChosenPerson() {
        start();tag("home-language");tag("home-explore");rule.waitUntil {discovery.state.value.snapshot!=null}
        tag("home-choice-people-201");tag("calendar-open")
        rule.waitUntil {discovery.state.value.calendar.page?.request==CalendarRequest()}
        tag("calendar-2026");rule.waitUntil {discovery.state.value.calendar.page?.request==CalendarRequest(2026)}
        tag("calendar-2026-02");rule.waitUntil {discovery.state.value.calendar.page?.request==CalendarRequest(2026,2)}
        rule.onNodeWithTag("home-search-editor").performScrollToNode(hasTestTag("calendar-2026-02-03"));snapshot("home-calendar-zh.png")
        tag("calendar-2026-02-03");tag("home-search-apply");rule.waitUntil {queries.size==1}
        assertEquals("2026-02-03",queries.single().from);assertEquals("2026-02-03",queries.single().through)
        assertEquals(setOf("201"),queries.single().people)
    }
    private fun snapshot(name:String) { rule.runOnUiThread {
        val view=rule.activity.window.decorView;val b=Bitmap.createBitmap(view.width,view.height,Bitmap.Config.ARGB_8888)
        view.draw(Canvas(b));File(rule.activity.filesDir,name).outputStream().use { b.compress(Bitmap.CompressFormat.PNG,100,it) };b.recycle()
    } }
}
