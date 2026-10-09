package dev.photohouse.home

import org.junit.Assert.*
import org.junit.Test

class VideoNavigationTest {
    @Test fun videoNavigationSkipsPhotosAndUnpreparedVideosWithoutWrapping() {
        fun video(id: Int) = HomeAsset(id, "", null, null, AssetKind.VIDEO, HomeVideo(10,10,60000,100,"a".repeat(64),"/synthetic",null))
        val items = listOf(video(1), HomeAsset(2,"",null,null), HomeAsset(3,"",null,null,AssetKind.VIDEO), video(4))
        val state = HomeState(feed = HomeFeed(1,"synthetic","",1,4,4,false,items), selected = 1)
        assertEquals(4,state.adjacentVideo(1)?.id)
        assertNull(state.adjacentVideo(-1))
        assertNull(state.adjacentVideo(2))
        assertEquals(1,state.copy(selected=4).adjacentVideo(-1)?.id)
    }
}
