package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class ConnectedStoreFamilyTagTest {
    private val asset = Asset("301", "image", 640, 480, null, "2026-09-24", "/assets/301/thumbnail?library=family")
    private fun membership(id: String) = Membership(id, "approved", "viewer", 1, null, 0, true)

    @Test fun protectedCatalogAndScopedAssetsNavigateAndClearOnBackground() = runTest {
        val api = FamilyApi()
        val store = ConnectedStore(api, backgroundScope, now = { 0L })
        store.authenticate("+12025550123", "password"); runCurrent()
        assertEquals("family", store.state.value.library)
        store.openFamilyTags("garden"); runCurrent()
        assertEquals("garden", api.lastQuery)
        assertEquals("picnic", store.state.value.familyTags?.result?.items?.single()?.name)
        store.openFamilyTag("picnic", page = 2); runCurrent()
        assertEquals("family", api.lastAssetLibrary)
        assertEquals("picnic", api.lastAssetTag)
        assertEquals(2, store.state.value.familyTags?.assetPage)
        assertEquals(1, store.state.value.familyTags?.page)
        assertEquals("301", store.state.value.gallery?.items?.single()?.id)
        assertEquals(2, store.state.value.gallery?.page)
        assertNotNull(store.state.value.previews["301"])
        store.openAsset(store.state.value.gallery!!.items.single()); runCurrent()
        assertEquals("picnic", store.state.value.familyTags?.selectedTag)
        store.backToPhotos(); runCurrent()
        assertEquals("301", store.state.value.gallery?.items?.single()?.id)
        assertEquals(2, store.state.value.gallery?.page)
        assertEquals(2, api.lastAssetPage)
        store.openMedia(store.state.value.gallery!!.items.single()); runCurrent()
        assertTrue(store.state.value.viewingOriginal)
        store.closeOriginalPhoto()
        assertEquals("picnic", store.state.value.familyTags?.selectedTag)
        store.backToPhotos(); runCurrent()
        assertEquals(2, store.state.value.gallery?.page)
        store.backToFamilyTags(); runCurrent()
        assertNull(store.state.value.familyTags?.selectedTag)
        assertEquals(1, store.state.value.familyTags?.page)
        store.background()
        assertNull(store.state.value.familyTags)
        assertNull(store.state.value.gallery)
        assertTrue(store.state.value.previews.isEmpty())
        store.logout()
        assertNull(store.state.value.familyTags)
    }

    @Test fun disabledFeatureAndDeniedCatalogDoNotShowPrivateTags() = runTest {
        val disabledApi = FamilyApi().apply { familyTagsEnabled = false }
        val disabledStore = ConnectedStore(disabledApi, backgroundScope, now = { 0L })
        disabledStore.authenticate("+12025550123", "password"); runCurrent()
        disabledStore.openFamilyTags()
        assertEquals(0, disabledApi.catalogReads)
        assertNull(disabledStore.state.value.familyTags)

        val deniedApi = FamilyApi().apply { catalogFailure = ApiFailure(FailureKind.HTTP, 403) }
        val deniedStore = ConnectedStore(deniedApi, backgroundScope, now = { 0L })
        deniedStore.authenticate("+12025550123", "password"); runCurrent()
        deniedStore.openFamilyTags(); runCurrent()
        assertEquals(Message.CLOSED, deniedStore.state.value.problem?.message)
        assertNull(deniedStore.state.value.familyTags)
    }

    private inner class FamilyApi : PhotoHouseApi {
        override val protectedNativeV2Enabled = true
        override var familyTagsEnabled = true
        var catalogReads = 0
        var lastQuery = ""
        var lastAssetLibrary: String? = null
        var lastAssetTag: String? = null
        var lastAssetPage: Int? = null
        var catalogFailure: ApiFailure? = null
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("account-family", phone_login = "+12025550123", memberships = listOf(membership("family"), membership("second")))
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 25, 1, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, asset)
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset) = byteArrayOf(1, 2, 3)
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 3, byteArrayOf())
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf(1)
        override suspend fun familyTags(token: Bearer, library: String, page: Int, query: String): FamilyTagsPage {
            catalogReads++; lastQuery = query; catalogFailure?.let { throw it }
            return FamilyTagsPage(library, page, FamilyTagsWire.PAGE_SIZE, 1, listOf(FamilyTagChoice("picnic", 1)))
        }
        override suspend fun familyTagAssets(token: Bearer, library: String, tag: String, page: Int): Gallery {
            lastAssetLibrary = library; lastAssetTag = tag; lastAssetPage = page
            return Gallery(library, page, FamilyTagsWire.PAGE_SIZE, 26, false, listOf(asset))
        }
    }
}
