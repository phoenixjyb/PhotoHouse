package dev.photohouse.stories.fixture

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import dev.photohouse.stories.StoryFixtureController

/** Debug-only, non-exported, no network or saved state; shared by phone and TV tests. */
class StoryFixtureActivity : ComponentActivity() {
    val controller = StoryFixtureController()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(null)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        val tv = intent.getBooleanExtra("synthetic_tv", false)
        controller.activate(tv = tv)
        setContent { StoryFixtureScreen(controller, tv) }
    }
    override fun onPause() { controller.clear(); super.onPause() }
    // Returning needs explicit activation; no private state is restored from a Bundle.
}
