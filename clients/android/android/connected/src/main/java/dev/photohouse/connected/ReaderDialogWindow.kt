package dev.photohouse.connected

import android.view.View
import android.view.ViewTreeObserver
import android.view.Window
import android.view.WindowManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.window.DialogWindowProvider
import androidx.core.view.WindowCompat

/** The dialog owns these temporary flags; the underlying activity is untouched. */
@Composable
internal fun ReaderDialogSystemBars(keyboardVisible: Boolean) {
    val view = LocalView.current
    val appearance = remember(view) { ReaderDialogWindowAppearance(view) }
    DisposableEffect(appearance) {
        appearance.attach()
        onDispose { appearance.close() }
    }
    LaunchedEffect(appearance, keyboardVisible) {
        // Dialog updates and keyboard transitions can reset system-bar contrast.
        withFrameNanos { }
        appearance.apply()
    }
}

private class ReaderDialogWindowAppearance(private val view: View) {
    private var window: Window? = null
    private var originalSoftInput = 0
    private var originalWidth = 0
    private var originalHeight = 0
    private var originalLightStatus = false
    private var originalLightNavigation = false
    private var closed = false
    private val applyAfterAttach = Runnable { apply() }
    private val attachListener = object : View.OnAttachStateChangeListener {
        override fun onViewAttachedToWindow(view: View) { view.post(applyAfterAttach) }
        override fun onViewDetachedFromWindow(view: View) = Unit
    }
    private val focusListener = ViewTreeObserver.OnWindowFocusChangeListener { focused ->
        if (focused) view.post(applyAfterAttach)
    }
    private var observer: ViewTreeObserver? = null

    fun attach() {
        view.addOnAttachStateChangeListener(attachListener)
        observer = view.viewTreeObserver.also { it.addOnWindowFocusChangeListener(focusListener) }
        if (view.isAttachedToWindow) apply()
        view.post(applyAfterAttach)
    }

    fun apply() {
        if (closed || !view.isAttachedToWindow) return
        val current = ((view as? DialogWindowProvider) ?: (view.parent as? DialogWindowProvider))?.window ?: return
        if (window != null && window !== current) return
        val controller = WindowCompat.getInsetsController(current, current.decorView)
        if (window == null) {
            window = current
            originalSoftInput = current.attributes.softInputMode
            originalWidth = current.attributes.width
            originalHeight = current.attributes.height
            originalLightStatus = controller.isAppearanceLightStatusBars
            originalLightNavigation = controller.isAppearanceLightNavigationBars
        }
        // Compose 1.6's dialog only explicitly sets resize below Android 12.
        // Keep the fixed header inside the visible viewport on newer versions too.
        val mode = (current.attributes.softInputMode and WindowManager.LayoutParams.SOFT_INPUT_MASK_ADJUST.inv()) or
            WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE
        if (current.attributes.softInputMode != mode) current.setSoftInputMode(mode)
        // Compose 1.6's usePlatformDefaultWidth=false measures against the physical
        // display, then writes that height back on every layout. Keep parent window
        // measurement instead so the IME can reduce the available viewport.
        if (current.attributes.width != WindowManager.LayoutParams.MATCH_PARENT ||
            current.attributes.height != WindowManager.LayoutParams.MATCH_PARENT) {
            current.setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT)
        }
        controller.isAppearanceLightStatusBars = true
        controller.isAppearanceLightNavigationBars = true
    }

    fun close() {
        closed = true
        view.removeCallbacks(applyAfterAttach)
        view.removeOnAttachStateChangeListener(attachListener)
        observer?.takeIf { it.isAlive }?.removeOnWindowFocusChangeListener(focusListener)
        window?.let { owned ->
            val controller = WindowCompat.getInsetsController(owned, owned.decorView)
            controller.isAppearanceLightStatusBars = originalLightStatus
            controller.isAppearanceLightNavigationBars = originalLightNavigation
            owned.setSoftInputMode(originalSoftInput)
            owned.setLayout(originalWidth, originalHeight)
        }
        window = null
    }
}
