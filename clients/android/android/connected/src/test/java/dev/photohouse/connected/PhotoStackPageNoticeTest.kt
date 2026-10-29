package dev.photohouse.connected

import dev.photohouse.connected.core.PhotoStackGroup
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PhotoStackPageNoticeTest {
    private val groups = listOf(PhotoStackGroup("1", "1", listOf("1", "2"), 2, "near_capture"))

    @Test fun pageSuggestionsExplainTemporaryChoicesAndRetainedOriginalsInBothLanguages() {
        assertEquals(
            "Similar photos on this page. Cover and separation choices reset when you refresh or change pages. All originals are kept.",
            pagePhotoStackNotice("page", groups, Words(false)),
        )
        assertEquals(
            "这是本页照片的建议分组。封面和单独显示设置只在本次查看中生效，刷新或翻页后会重置。原照片都会保留。",
            pagePhotoStackNotice("page", groups, Words(true)),
        )
    }

    @Test fun libraryOrUnknownScopeNeverGetsTheTemporaryChoiceMessage() {
        for (scope in listOf("library", null, "unsupported")) {
            for (zh in listOf(true, false)) {
                assertNull(pagePhotoStackNotice(scope, groups, Words(zh)))
            }
        }
    }

    @Test fun missingOrEmptyGroupsDoNotAdvertiseUnavailablePageChoices() {
        for (groups in listOf(null, emptyList<PhotoStackGroup>())) {
            for (zh in listOf(true, false)) {
                assertNull(pagePhotoStackNotice("page", groups, Words(zh)))
            }
        }
    }
}
