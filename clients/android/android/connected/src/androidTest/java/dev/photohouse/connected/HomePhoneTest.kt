package dev.photohouse.connected

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.home.*
import kotlinx.coroutines.*
import org.junit.*
import org.junit.Assert.*
import java.io.ByteArrayOutputStream
import java.io.File

class HomePhoneTest {
    @get:Rule val rule = createAndroidComposeRule<HomeActivity>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var store: HomeStore
    private val picture: ByteArray by lazy {
        val b = Bitmap.createBitmap(640,480,Bitmap.Config.ARGB_8888)
        val c = Canvas(b); val p = Paint(Paint.ANTI_ALIAS_FLAG)
        c.drawColor(0xffe8dfc9.toInt()); p.color=0xffdec486.toInt(); c.drawCircle(465f,100f,55f,p)
        p.color=0xff879b7a.toInt(); c.drawOval(-100f,260f,820f,730f,p)
        p.color=0xff436454.toInt(); c.drawOval(-100f,350f,780f,700f,p)
        val bytes=ByteArrayOutputStream().use { b.compress(Bitmap.CompressFormat.JPEG,90,it);it.toByteArray() };b.recycle();bytes
    }
    private val movies by lazy { InstrumentationRegistry.getInstrumentation().context.assets.open("synthetic-long-video.mp4").use { it.readBytes() } }
    private val requests=mutableListOf<Pair<Int,BrowseSelection>>()
    private var lastReader: HomeVideoReader?=null
    private var badVideo=false
    private fun api() = object : HomeApi {
        override val catalogVersion=3
        override val browseEnabled=true
        override suspend fun feed(page:Int):HomeFeed=error("Selection required")
        override suspend fun feed(page:Int, revision:Int?, selection:BrowseSelection):HomeFeed {
            requests += page to selection
            val all=listOf(
                HomeAsset(400,"Still preparing / 准备中",null,null,AssetKind.VIDEO),
                HomeAsset(300,"A quiet afternoon / 午后时光",Preview(640,480,picture.size,"","grid"),Preview(640,480,picture.size,"","display"), original=HomeOriginal("image/jpeg",picture.size,640,480,"original")),
                HomeAsset(200,"A moment together / 相聚时刻",Preview(640,480,picture.size,"","grid"),null,AssetKind.VIDEO,HomeVideo(320,240,65000,movies.size.toLong(),"","video",null)),
                HomeAsset(100,"Warm evening / 温暖的傍晚",Preview(640,480,picture.size,"","grid"),Preview(640,480,picture.size,"","display")))
            val matching=all.filter { selection.media==BrowseMedia.ALL || it.kind==if(selection.media==BrowseMedia.PHOTOS) AssetKind.PHOTO else AssetKind.VIDEO }
            val filtered=(if(selection.availability==Availability.READY) matching.filter { it.deliveryReady() } else matching).let { if(selection.order==BrowseOrder.READY_FIRST) it.sortedByDescending { a->a.deliveryReady() } else it }
            return HomeFeed(8,"synthetic","Our home",page,2,filtered.size,page*2<filtered.size,filtered.drop((page-1)*2).take(2),3,BrowseCounts(matching.count { it.deliveryReady() },matching.size))
        }
        override suspend fun preview(asset:HomeAsset,variant:Variant,revision:Int)=picture
        override suspend fun original(asset:HomeAsset,revision:Int)=picture
        override fun video(asset:HomeAsset,revision:Int,failed:(Exception)->Unit):HomeVideoSource = HomeVideoReader(movies.size.toLong(),262144,
            { start,size -> if(badVideo) ByteArray(size) else movies.copyOfRange(start.toInt(),start.toInt()+size) },failed).also { lastReader=it }
    }
    private fun start() { store=HomeStore(api(),scope);rule.runOnUiThread { rule.activity.setContent { HomePhoneApp(store, initialZh = false) {} };store.foreground() };rule.waitUntil { store.state.value.feed!=null } }
    private fun clickTag(tag:String) {
        if (rule.onAllNodesWithTag("home-gallery").fetchSemanticsNodes().isNotEmpty())
            rule.onNodeWithTag("home-gallery").performScrollToNode(hasTestTag(tag))
        rule.onNodeWithTag(tag).performScrollTo().performClick()
    }
    private fun click(text:String) { rule.onNodeWithText(text).performScrollTo().performClick() }
    @After fun stop() { if(::store.isInitialized) rule.runOnUiThread { store.background() };scope.cancel() }
    @Test fun homeDefaultsToChineseAndCanSwitchToEnglish() {
        store=HomeStore(api(),scope)
        rule.runOnUiThread { rule.activity.setContent { HomePhoneApp(store) {} };store.foreground() }
        rule.waitUntil { store.state.value.feed!=null }
        rule.onNodeWithTag("home-language").assertTextEquals("English")
        snapshot("home-phone-default-zh.png")
        clickTag("home-language")
        rule.onNodeWithTag("home-language").assertTextEquals("简体中文")
    }
    @Test fun homeFiltersPagingPhotoAndOriginalKeepTouchControlsAndCaptions() {
        start()
        clickTag("home-ready-first");rule.onNodeWithTag("home-ready-first").assertIsSelected()
        rule.waitUntil { store.state.value.feed?.items?.firstOrNull()?.id==300 }
        if (rule.activity.resources.configuration.fontScale >= 1.5f)
            rule.onNodeWithTag("home-gallery").performScrollToNode(hasTestTag("home-asset-300"))
        rule.waitUntil(10000) { rule.onAllNodesWithTag("home-thumbnail", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
        snapshot("home-phone-en.png")
        clickTag("home-ready-only");rule.onNodeWithTag("home-ready-only").assertIsSelected()
        clickTag("home-media-photo");rule.waitUntil { store.state.value.feed?.total==2 }
        clickTag("home-language");snapshot("home-phone-zh.png")
        rule.onNodeWithTag("home-ready-only").assertTextContains("仅显示已就绪",substring=true)
        clickTag("home-language")
        clickTag("home-asset-300")
        rule.waitUntil(10000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size==1 }
        if (rule.onAllNodesWithTag("photo-exit-fullscreen").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("photo-exit-fullscreen").performClick()
        click("Zoom in");rule.onNodeWithTag("photo-zoom").assertTextEquals("150%")
        click("Original quality");rule.waitUntil { store.state.value.originalQuality }
        click("Full screen");rule.onNodeWithTag("photo-exit-fullscreen").performClick()
        click("Close photo")
        clickTag("home-media-all");clickTag("home-ready-only")
        clickTag("home-page");rule.onNodeWithTag("phone-page-input").performTextReplacement("2");rule.onNodeWithTag("phone-page-go").performClick()
        rule.waitUntil { store.state.value.feed?.page==2 }
        assertEquals(2,requests.last().first)
        clickTag("home-media-video");rule.waitUntil { store.state.value.feed?.page==1 && store.state.value.feed?.total==2 }
        assertEquals(BrowseMedia.VIDEOS,requests.last().second.media)
        rule.runOnUiThread { store.background() }
        rule.onNodeWithTag("home-covered").assertIsDisplayed()
        assertTrue(store.state.value.grids.isEmpty());assertNull(store.state.value.feed)
    }
    @Test fun videoStreamsSeeksAndFailureStaysVisibleUntilRetry() {
        start();clickTag("home-media-video");clickTag("home-ready-only")
        clickTag("home-asset-200")
        rule.waitUntil(15000) { rule.onAllNodesWithText("Play").fetchSemanticsNodes().any { it.config.contains(androidx.compose.ui.semantics.SemanticsProperties.Disabled).not() } }
        click("Play");click("Full screen");rule.onNodeWithTag("video-exit-fullscreen").performClick()
        assertFalse(lastReader!!.isClosed)
        click("Pause");click("Forward 10s");click("Close video")
        assertTrue(lastReader!!.isClosed)
        badVideo=true;clickTag("home-video-retry")
        rule.waitUntil(15000) { store.state.value.videoFailed }
        rule.onNodeWithTag("home-media-error").assertExists()
        assertNotNull(store.state.value.asset);assertTrue(lastReader!!.isClosed)
        snapshot("home-phone-video-error.png")
        badVideo=false;clickTag("home-video-retry")
        rule.waitUntil(15000) { rule.onAllNodesWithText("Play").fetchSemanticsNodes().any { it.config.contains(androidx.compose.ui.semantics.SemanticsProperties.Disabled).not() } }
        rule.runOnUiThread { store.background() }
        assertTrue(lastReader!!.isClosed);rule.onNodeWithTag("home-covered").assertIsDisplayed()
    }
    @Test fun deniedHomeStaysHomeAndClearsMediaWithoutOpeningAccount() {
        val denied=object:HomeApi {
            override suspend fun feed(page:Int):HomeFeed=throw HomeFailure(HomeError.DENIED)
            override suspend fun preview(asset:HomeAsset,variant:Variant,revision:Int):ByteArray?=error("Denied must not read")
        }
        store=HomeStore(denied,scope)
        rule.runOnUiThread { rule.activity.setContent { HomePhoneApp(store, initialZh = false) {} };store.foreground() }
        rule.waitUntil { store.state.value.problem==HomeError.DENIED }
        rule.onNodeWithTag("home-error").assertExists()
        assertNull(store.state.value.feed);assertNull(store.state.value.video)
        rule.onNodeWithText("Password").assertDoesNotExist()
    }
    private fun snapshot(name:String) {
        rule.waitForIdle()
        rule.runOnUiThread { val view=rule.activity.window.decorView;val b=Bitmap.createBitmap(view.width,view.height,Bitmap.Config.ARGB_8888)
            view.draw(Canvas(b));File(rule.activity.filesDir,name).outputStream().use { b.compress(Bitmap.CompressFormat.PNG,100,it) };b.recycle() }
    }
}
