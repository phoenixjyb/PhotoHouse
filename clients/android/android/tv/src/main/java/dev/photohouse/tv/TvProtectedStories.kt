package dev.photohouse.tv

import androidx.compose.runtime.Composable

/** Opaque entry point so the anonymous TV source set cannot see protected story types. */
interface TvProtectedStories {
    @Composable
    fun Content(zh: Boolean, onClose: () -> Unit)

    /** Cover and clear account-bound state when the TV app leaves the foreground. */
    fun background()
}
