package dev.photohouse.connected

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

/** No account, bearer, cookie or protected-library adapter is reachable here. */
class HomePhoneViewModel(api: HomeApi?, gateway: DiscoveryGateway? = null) : ViewModel() {
    val store = api?.let { HomeStore(it, viewModelScope) }
    val discovery = if (store != null && gateway != null) DiscoveryController(gateway, store, viewModelScope) else null
    override fun onCleared() { discovery?.background(); store?.background() }
}
class HomeActivity : ComponentActivity() {
    private val model by viewModels<HomePhoneViewModel> {
        object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                val api = runCatching {
                    // Require the private LAN override: no fallback to public DNS or account origin.
                    HttpsCatalogApi(HomeOrigin.parse(BuildConfig.PHOTOHOUSE_HOME_ORIGIN),
                        HomeLanAddress.parse(BuildConfig.PHOTOHOUSE_HOME_LAN_ADDRESS), version = 3, browseEnabled = true)
                }.getOrNull()
                val gateway = if (api != null && BuildConfig.PHOTOHOUSE_HOME_DISCOVERY_ENABLED) runCatching {
                    HttpsDiscoveryGateway(HomeOrigin.parse(BuildConfig.PHOTOHOUSE_HOME_ORIGIN),
                        HomeLanAddress.parse(BuildConfig.PHOTOHOUSE_HOME_LAN_ADDRESS), discoveryVersion = if (BuildConfig.PHOTOHOUSE_HOME_TAG_LOOKUP_ENABLED) 3 else 2,calendarEnabled=BuildConfig.PHOTOHOUSE_HOME_CALENDAR_ENABLED)
                }.getOrNull() else null
                return HomePhoneViewModel(api, gateway) as T
            }
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(null)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        window.decorView.importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        setContent { HomePhoneApp(model.store, model.discovery) { finish() } }
    }
    override fun onPause() { model.discovery?.background(); model.store?.background(); super.onPause() }
    override fun onResume() { super.onResume(); model.store?.foreground() }
}
