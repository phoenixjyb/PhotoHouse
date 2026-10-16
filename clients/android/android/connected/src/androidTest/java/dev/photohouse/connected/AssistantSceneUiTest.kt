package dev.photohouse.connected

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.Asset
import kotlinx.serialization.json.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.FileOutputStream

/** Generated local state only. No model, microphone, account or network is involved. */
@RunWith(AndroidJUnit4::class)
class AssistantSceneUiTest {
    @get:Rule val rule = createComposeRule()
    private val tid = "11111111-1111-4111-8111-111111111111"
    private fun state(): AssistantWorkspaceState {
        val filters=Json.parseToJsonElement("""{"people":{"ids":["301"],"match":"any"},"date":{"from":"2032-09-01","to":"2032-09-30"},"media":["image"]}""").jsonObject
        val result=AssistantTurn("results","Found",buildJsonObject{put("library_id","fictional-library")},filters,
            listOf(Asset("123","image",640,480,null,"2032-09-01","/assets/123/thumbnail?library=fictional-library")),1,false,null,
            searchVersion=3,searchInterpretation=AssistantSearchInterpretation("capture",listOf(AssistantSearchFacetSelection("301","Sample Child / 示例儿童")),emptyList(),emptyList(),null))
        val thread=AssistantWorkspaceThreadSummary(tid,"fictional-library","2032-09-01T00:00:00Z","2032-09-01T00:00:00Z","2032-10-01T00:00:00Z",1)
        return AssistantWorkspaceState(accountId="fictional",libraryId="fictional-library",generation=1,
            capabilities=AssistantWorkspaceCapabilities(1,true,true,true,true,true,searchVersion=3),sceneSearchAvailable=true,
            detail=AssistantWorkspaceThreadDetail(1,thread,emptyList()),currentTurn=AssistantWorkspaceTurn(1,tid,tid,AssistantWorkspaceRequestStatus.COMPLETED,1,true,null,result),continuationEnabled=true)
    }
    private fun editor(zh:Boolean) {
        val state=mutableStateOf(state());var sent=0;var backs=0
        rule.setContent {
            val density=LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density,1.5f)) {
                PhotoHouseTheme { Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                    AssistantSceneControls(state.value,zh,false,{state.value=state.value.copy(sceneDraft=it)},{sent++},{backs++})
                } }
            }
        }
        rule.onNodeWithTag("private-assistant-scene-composer").performScrollTo().performTextInput("孩子 flying a kite 蓝桥旁")
        rule.onNodeWithTag("private-assistant-scene-send").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("private-assistant-scene-ack").performScrollTo().performClick()
        rule.onNodeWithTag("private-assistant-scene-send").performScrollTo().assertIsEnabled().performClick()
        rule.runOnIdle { assertEquals(1,sent) }
        screenshot("scene-${if(zh) "zh" else "en"}-actions-150.png")
        rule.runOnIdle {state.value=state.value.copy(detail=state.value.detail!!.copy(thread=state.value.detail!!.thread.copy(revision=2)),
            currentTurn=state.value.currentTurn!!.copy(revision=2))}
        rule.onNodeWithTag("private-assistant-scene-send").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("private-assistant-scene-back").performScrollTo().performClick()
        rule.runOnIdle {assertEquals(1,backs)}
    }
    @Test fun chineseLargeTextControlsRequireScopeAcknowledgement()=editor(true)
    @Test fun englishLargeTextControlsRequireScopeAcknowledgement()=editor(false)
    @Test fun unresolvedConditionsCannotSubmitRetainedCards() {
        val ready=state();val current=ready.currentTurn!!;val unresolved=ready.copy(currentTurn=current.copy(result=current.result!!.copy(kind="clarification")))
        var sent=false
        rule.setContent {PhotoHouseTheme {Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            AssistantSceneControls(unresolved,true,false,{}, {sent=true},{})
        }}}
        rule.onNodeWithTag("private-assistant-scene-unready").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-scene-send").performScrollTo().assertIsNotEnabled()
        rule.runOnIdle {assertTrue(!sent)}
    }
    private fun ranking(zh:Boolean) {
        val result=state().currentTurn!!.result!!.copy(searchVersion=4,sceneRanking=AssistantSceneRanking("孩子 beside a blue bridge 放风筝",mapOf("123" to .75),1))
        rule.setContent {val density=LocalDensity.current;CompositionLocalProvider(LocalDensity provides Density(density.density,1.5f)) {
            PhotoHouseTheme {Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {AssistantSceneRankingInfo(result,zh)}}
        }}
        rule.onNodeWithTag("private-assistant-scene-ranking").assertIsDisplayed()
        rule.onNodeWithText(if(zh) "不是匹配概率" else "not a match probability",substring=true).performScrollTo().assertIsDisplayed()
        screenshot("scene-${if(zh) "zh" else "en"}-ranking-150.png")
    }
    @Test fun chineseRankingSeparatesSimilarityFromEvidence()=ranking(true)
    @Test fun englishRankingSeparatesSimilarityFromEvidence()=ranking(false)
    private fun screenshot(name:String) {
        val bitmap=rule.onRoot().captureToImage().asAndroidBitmap()
        FileOutputStream(java.io.File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,name)).use {bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it)}
    }
}
