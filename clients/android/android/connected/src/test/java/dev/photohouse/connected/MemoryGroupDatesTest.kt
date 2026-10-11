package dev.photohouse.connected

import org.junit.Assert.*
import org.junit.Test

class MemoryGroupDatesTest {
    @Test fun recordedWallDateAndOffsetStayTogetherWithoutPhoneTimezoneConversion() {
        assertEquals("2026年1月1日 · 00:30 · UTC+08:00", memoryGroupRecordedDate("2026-01-01T00:30:00+08:00", true))
        assertEquals("1 Jan 2026 · 00:30 · UTC+08:00", memoryGroupRecordedDate("2026-01-01 00:30:00+0800", false))
        assertEquals("1 Jan 2026 · 00:30 · UTC", memoryGroupRecordedDate("2026-01-01T00:30:00Z", false))
        assertEquals("2026年1月1日", memoryGroupRecordedDate("2026-01-01", true))
        assertEquals("1 Jan 2026 · 10:00", memoryGroupRecordedDate("2026-01-01T10:00:00", false))
    }
    @Test fun invalidOrMissingMetadataDoesNotInventADate() {
        for (value in listOf(null, "", "0000-01-01", "2026-02-30", "2026-01-01T25:00:00", "filename_20260101"))
            assertNull(memoryGroupRecordedDate(value, true))
    }
}
