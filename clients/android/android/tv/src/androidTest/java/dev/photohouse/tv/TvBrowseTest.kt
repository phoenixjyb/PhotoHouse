package dev.photohouse.tv

import android.view.KeyEvent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.test.platform.app.InstrumentationRegistry
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

class TvBrowseTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
    @After fun finish() { scope.cancel() }
    @Test fun selectorsRenderCountsFilterGloballyAndKeepAnEmptyResultRecoverable() {
        val preview=androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().context.assets.open("home-8x8.jpg").use { it.readBytes() }
        val all=listOf(HomeAsset(300,"Waiting for preparation / 准备中",null,null,AssetKind.VIDEO),
            HomeAsset(102,"A quiet afternoon / 午后时光",Preview(8,8,preview.size,"","grid"),Preview(8,8,preview.size,"","display")))
        val api=object:HomeApi {
            override val catalogVersion=3; override val browseEnabled=true
            override suspend fun collections()=HomeCollections(9,listOf(
                HomeCollection("family","Family",2,1,1), HomeCollection("trips","Trips",0,0,0),
                HomeCollection("kids","Kids",0,0,0), HomeCollection("home","Home",0,0,0),
                HomeCollection("grandparents","Grandparents",0,0,0), HomeCollection("shared","Shared",0,0,0)))
            override suspend fun feed(page:Int):HomeFeed=error("Selection required")
            override suspend fun feed(page:Int,revision:Int?,selection:BrowseSelection):HomeFeed {
                val selected=if(selection.collectionId==null || selection.collectionId=="family") all else emptyList()
                val matching=selected.filter { selection.media==BrowseMedia.ALL || it.kind==if(selection.media==BrowseMedia.PHOTOS) AssetKind.PHOTO else AssetKind.VIDEO }
                val ready=matching.count { it.deliveryReady() }
                val items=(if(selection.availability==Availability.READY) matching.filter { it.deliveryReady() } else matching).let {
                    if(selection.order==BrowseOrder.READY_FIRST) it.sortedByDescending { a->a.deliveryReady() } else it
                }
                return HomeFeed(9,"synthetic","Our home / 我们的家",1,50,items.size,false,items,3,BrowseCounts(ready,matching.size))
            }
            override suspend fun preview(asset:HomeAsset,variant:Variant,revision:Int)=preview
        }
        val store=HomeStore(api,scope)
        rule.runOnUiThread { rule.activity.setContent { TvApp(store) };store.foreground() }
        rule.waitUntil { store.state.value.collections?.collections?.size == 6 }
        rule.onNodeWithTag("browse-all").assertTextContains("全部",substring=true)
        rule.showAction("language")
        rule.onNodeWithTag("language").performClick()
        rule.onNodeWithTag("browse-all").assertTextContains("All",substring=true)
        rule.onNodeWithTag("collection-family").assertTextContains("Family",substring=true)
        rule.onNodeWithTag("collection-trips").assertTextContains("0",substring=true)
        rule.onNodeWithTag("ready-first").performScrollTo().performSemanticsAction(SemanticsActions.RequestFocus)
        rule.onNodeWithTag("ready-first").assertIsFocused()
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.onNodeWithTag("ready-first").assertIsSelected()
        rule.waitUntil { store.state.value.feed?.items?.firstOrNull()?.id==102 }
        rule.onNodeWithTag("ready-only").performScrollTo().performClick()
        rule.onNodeWithTag("ready-only").assertIsSelected()
        rule.onNodeWithTag("asset-300").assertDoesNotExist()
        rule.onNodeWithTag("asset-102").assertExists()
        val toolbarBounds = rule.onNodeWithTag("gallery-toolbar").getUnclippedBoundsInRoot()
        assertTrue((toolbarBounds.bottom - toolbarBounds.top).value <= 56f)
        val rowTop = rule.onNodeWithTag("browse-all").getUnclippedBoundsInRoot().top.value
        for (tag in listOf("browse-photo", "browse-video", "ready-only", "ready-first", "gallery-more")) {
            assertEquals(rowTop, rule.onNodeWithTag(tag).getUnclippedBoundsInRoot().top.value, 1f)
        }
        snapshot("ready-browse-en.png")
        rule.showAction("language")
        rule.onNodeWithTag("language").performClick()
        rule.onNodeWithTag("ready-only").assertTextContains("仅已就绪",substring=true)
        snapshot("ready-browse-zh.png")
        rule.onNodeWithTag("collection-trips").performScrollTo().performClick()
        rule.waitUntil { store.state.value.feed?.total==0 }
        rule.onNodeWithTag("gallery-empty-title").assertTextContains("暂无已就绪内容",substring=true)
        rule.onNodeWithTag("collection-all").performScrollTo().performClick()
        rule.onNodeWithTag("browse-all").performScrollTo().performClick()
        rule.waitUntil { store.state.value.feed?.total==1 }
        rule.onNodeWithTag("browse-video").performScrollTo().performClick()
        rule.waitUntil { store.state.value.feed?.total==0 }
        rule.onNodeWithTag("gallery-empty").assertExists()
        rule.onNodeWithTag("grid").assertDoesNotExist()
        rule.onNodeWithText("暂无已就绪内容。可显示全部，或在发布更多媒体后刷新。").assertExists()
        rule.onNodeWithTag("ready-only").performScrollTo().performClick()
        rule.onNodeWithTag("asset-300").assertExists()
        rule.runOnUiThread { store.background() }
        rule.onNodeWithTag("covered").assertExists()
    }

    @Test fun remoteLibraryChoiceRestoresVisibleFocusAfterLoadAndKeepsEmptyLibraryRecoverable() {
        val preview=InstrumentationRegistry.getInstrumentation().context.assets.open("home-8x8.jpg").use { it.readBytes() }
        val photo=HomeAsset(102,"A quiet afternoon",Preview(8,8,preview.size,"","grid"),Preview(8,8,preview.size,"","display"))
        val video=HomeAsset(300,"Waiting for preparation",null,null,AssetKind.VIDEO)
        val collections=HomeCollections(9,listOf(
            HomeCollection("family","Family",2,1,1), HomeCollection("trips","Trips",0,0,0),
            HomeCollection("kids","Kids",0,0,0), HomeCollection("home","Home",0,0,0),
            HomeCollection("grandparents","Grandparents",0,0,0), HomeCollection("shared","Shared",0,0,0)))
        val api=object:HomeApi {
            override val catalogVersion=3; override val browseEnabled=true
            var sharedRequestGate:CompletableDeferred<Unit>?=null
            override suspend fun collections()=collections
            override suspend fun feed(page:Int):HomeFeed=error("Selection required")
            override suspend fun feed(page:Int,revision:Int?,selection:BrowseSelection):HomeFeed {
                if(selection.collectionId=="shared") {
                    val gate=sharedRequestGate
                    sharedRequestGate=null
                    gate?.await()
                }
                val selected=if(selection.collectionId==null || selection.collectionId=="family") listOf(video,photo) else emptyList()
                val matching=selected.filter { selection.media==BrowseMedia.ALL || it.kind==if(selection.media==BrowseMedia.PHOTOS) AssetKind.PHOTO else AssetKind.VIDEO }
                val items=if(selection.availability==Availability.READY) matching.filter { it.deliveryReady() } else matching
                return HomeFeed(9,"synthetic","Our home",page,50,items.size,false,items,3,BrowseCounts(items.count { it.deliveryReady() },matching.size))
            }
            override suspend fun preview(asset:HomeAsset,variant:Variant,revision:Int)=preview
        }
        val store=HomeStore(api,scope)
        rule.runOnUiThread { rule.activity.setContent { TvApp(store) };store.foreground() }
        rule.waitUntil { store.state.value.feed?.items?.isNotEmpty()==true && store.state.value.collections?.collections?.size==6 }

        val gate=CompletableDeferred<Unit>()
        rule.runOnUiThread { api.sharedRequestGate=gate }
        rule.onNodeWithTag("collection-shared").performScrollTo().performSemanticsAction(SemanticsActions.RequestFocus)
        rule.onNodeWithTag("collection-shared").assertIsFocused()
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.waitUntil { store.state.value.busy && store.state.value.feed==null }
        rule.onNodeWithTag("tv-loading-status").assertExists()
        gate.complete(Unit)
        rule.waitUntil { store.state.value.feed!=null && !store.state.value.busy && store.selection.collectionId=="shared" }
        rule.onNodeWithTag("collection-shared").assertIsDisplayed().assertIsSelected().assertIsFocused()
        rule.onNodeWithTag("gallery-empty").assertExists()
        snapshot("tv-library-selected-${rule.activity.resources.configuration.fontScale}.png")

        repeat(6) { InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_LEFT) }
        rule.onNodeWithTag("collection-all").assertIsDisplayed().assertIsFocused()
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.waitUntil { store.selection.collectionId==null && store.state.value.feed?.items?.any { it.id==102 }==true && !store.state.value.busy }
        rule.onNodeWithTag("collection-all").assertIsDisplayed().assertIsSelected().assertIsFocused()

        repeat(8) { InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_RIGHT) }
        rule.onNodeWithTag("browse-photo").assertIsDisplayed().assertIsFocused()
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.waitUntil { store.selection.media==BrowseMedia.PHOTOS && store.state.value.feed?.items?.any { it.id==102 }==true && !store.state.value.busy }
        rule.onNodeWithTag("collection-all").assertIsNotFocused()
        rule.onNodeWithTag("featured-asset-102").assertIsDisplayed()
        rule.onNodeWithText("打开照片").assertIsDisplayed()
        snapshot("tv-library-photos-${rule.activity.resources.configuration.fontScale}.png")
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_DOWN)
        rule.onNodeWithTag("asset-102").assertIsFocused()
        rule.onNodeWithTag("gallery-overview").assertDoesNotExist()
        val gridViewportBounds=rule.onNodeWithTag("grid-viewport").fetchSemanticsNode().boundsInRoot
        val focusedAssetBounds=rule.onNodeWithTag("asset-102").fetchSemanticsNode().boundsInRoot
        assertTrue("Focused grid card starts inside the grid viewport",focusedAssetBounds.top>=gridViewportBounds.top)
        assertTrue("Focused grid card ends inside the grid viewport",focusedAssetBounds.bottom<=gridViewportBounds.bottom)
        snapshot("tv-library-asset-focus-${rule.activity.resources.configuration.fontScale}.png")
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_UP)
        val toolbarTags=listOf("collection-all","collection-family","collection-trips","collection-kids","collection-home","collection-grandparents","collection-shared",
            "browse-all","browse-photo","browse-video","ready-only","ready-first","gallery-more")
        val focusedToolbarTag=toolbarTags.firstOrNull { tag ->
            runCatching { rule.onNodeWithTag(tag).assertIsFocused() }.isSuccess
        }
        assertNotNull("DPAD up returns focus to a toolbar control",focusedToolbarTag)
        rule.onNodeWithTag("gallery-overview").assertIsDisplayed()
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_DOWN)
        rule.onNodeWithTag("asset-102").assertIsFocused()
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.waitUntil { store.state.value.asset?.id == 102 }
        rule.onNodeWithTag("viewer").assertExists()
        rule.runOnUiThread { store.background() }
    }
    private fun snapshot(name:String) {
        rule.waitForIdle()
        rule.runOnUiThread {
            val view=rule.activity.window.decorView
            val bitmap=Bitmap.createBitmap(view.width,view.height,Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap));File(rule.activity.filesDir,name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) };bitmap.recycle()
        }
    }
}
