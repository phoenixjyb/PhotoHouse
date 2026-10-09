package dev.photohouse.fixture

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import dev.photohouse.fixture.core.BundledFixtureRepository
import dev.photohouse.fixture.core.PhotoHouseStore

class PhotoHouseViewModel(repository: BundledFixtureRepository) : ViewModel() {
    val store = PhotoHouseStore(repository, viewModelScope)
}

class MainActivity : ComponentActivity() {
    private val model by viewModels<PhotoHouseViewModel> {
        object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                val repository = BundledFixtureRepository(
                    assets.open("fixtures.json").bufferedReader().use { it.readText() },
                    assets.open("client-scenarios.json").bufferedReader().use { it.readText() },
                    { path -> assets.open(path).use { it.readBytes() } },
                )
                return PhotoHouseViewModel(repository) as T
            }
        }
    }
    // Exposed to synthetic instrumentation to verify the real lifecycle/store wiring.
    val store get() = model.store
    override fun onCreate(savedInstanceState: Bundle?) {
        // Never restore private UI or credentials from an Android instance-state Bundle.
        super.onCreate(null)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        setContent { PhotoHouseApp(model.store) }
    }
    override fun onPause() {
        model.store.background()
        super.onPause()
    }
    override fun onResume() {
        super.onResume()
        model.store.foreground()
    }
}
