package dev.photohouse.tv

import android.os.Bundle
import android.view.View
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import dev.photohouse.home.*

class TvViewModel(api: HomeApi?, gateway: DiscoveryGateway? = null) : ViewModel() {
    val store = api?.let { HomeStore(it, viewModelScope) }
    val discovery = if (store != null && gateway != null) DiscoveryController(gateway, store, viewModelScope) else null
}
class MainActivity : ComponentActivity() {
    private val model by viewModels<TvViewModel> {
        object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                val api = runCatching {
                    val origin = HomeOrigin.parse(BuildConfig.PHOTOHOUSE_ORIGIN)
                    when (BuildConfig.PHOTOHOUSE_CATALOG_VERSION) {
                        1 -> if (BuildConfig.PHOTOHOUSE_LAN_ADDRESS.isEmpty()) HttpsHomeApi(origin)
                            else HttpsHomeApi(origin, HomeLanAddress.parse(BuildConfig.PHOTOHOUSE_LAN_ADDRESS))
                        2, 3 -> if (BuildConfig.PHOTOHOUSE_LAN_ADDRESS.isEmpty()) HttpsCatalogApi(origin, version = BuildConfig.PHOTOHOUSE_CATALOG_VERSION, browseEnabled = BuildConfig.PHOTOHOUSE_BROWSE_ENABLED)
                            else HttpsCatalogApi(origin, HomeLanAddress.parse(BuildConfig.PHOTOHOUSE_LAN_ADDRESS), BuildConfig.PHOTOHOUSE_CATALOG_VERSION, BuildConfig.PHOTOHOUSE_BROWSE_ENABLED)
                        else -> error("Unsupported catalog")
                    }
                }.getOrNull()
                val gateway = if (api != null && BuildConfig.PHOTOHOUSE_DISCOVERY_ENABLED) runCatching {
                    val origin = HomeOrigin.parse(BuildConfig.PHOTOHOUSE_ORIGIN)
                    if (BuildConfig.PHOTOHOUSE_LAN_ADDRESS.isEmpty()) HttpsDiscoveryGateway(origin, discoveryVersion = if (BuildConfig.PHOTOHOUSE_CATALOG_VERSION == 3) { if (BuildConfig.PHOTOHOUSE_HOME_TAG_LOOKUP_ENABLED) 3 else 2 } else 1,calendarEnabled=BuildConfig.PHOTOHOUSE_HOME_CALENDAR_ENABLED)
                    else HttpsDiscoveryGateway(origin, HomeLanAddress.parse(BuildConfig.PHOTOHOUSE_LAN_ADDRESS), if (BuildConfig.PHOTOHOUSE_CATALOG_VERSION == 3) { if (BuildConfig.PHOTOHOUSE_HOME_TAG_LOOKUP_ENABLED) 3 else 2 } else 1,calendarEnabled=BuildConfig.PHOTOHOUSE_HOME_CALENDAR_ENABLED)
                }.getOrNull() else null
                return TvViewModel(api, gateway) as T
            }
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(null)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        window.decorView.importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        setContent { TvApp(model.store, model.discovery) }
    }
    override fun onPause() { model.discovery?.background(); model.store?.background(); super.onPause() }
    override fun onResume() { super.onResume(); model.store?.foreground() }
}
