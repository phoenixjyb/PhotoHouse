package dev.photohouse.playback

import org.junit.Assert.*
import org.junit.Test

class PlaybackProgressTest {
    @Test fun resumesExactRepresentationOnlyAndDropsFinishedClips() {
        val history = PlaybackProgress()
        history.open("account/library/asset/etag-a").record(15000, 60000)
        assertEquals(15000, history.open("account/library/asset/etag-a").positionMillis)
        assertEquals(0, history.open("account/library/asset/etag-b").positionMillis)
        assertEquals(0, history.open("other/library/asset/etag-a").positionMillis)
        history.open("account/library/asset/etag-a").record(59000, 60000)
        assertEquals(0, history.open("account/library/asset/etag-a").positionMillis)
    }
    @Test fun staleCallbacksCannotRestoreHistoryAfterClearOrClose() {
        val history = PlaybackProgress()
        val bookmark = history.open("asset")
        bookmark.record(5000, 60000)
        history.clear(); bookmark.record(6000, 60000)
        assertEquals(0, history.open("asset").positionMillis)
        val next = history.open("asset")
        next.record(7000, 60000); next.close(); next.record(8000, 60000)
        assertEquals(7000, history.open("asset").positionMillis)
    }
    @Test fun historyIsBoundedAndRejectsInvalidPlayerMeasurements() {
        val history = PlaybackProgress(2)
        listOf("a", "b", "c").forEach { history.open(it).record(5000, 60000) }
        assertEquals(0, history.open("a").positionMillis)
        history.open("b").record(-1, 60000)
        history.open("b").record(70000, 60000)
        assertEquals(5000, history.open("b").positionMillis)
    }
}
