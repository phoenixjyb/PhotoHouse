package dev.photohouse.fixture.core

import dev.photohouse.protocol.LibraryNames
import org.junit.Assert.assertEquals
import org.junit.Test

class LibraryNamesTest {
    @Test fun knownLibrariesHaveBilingualPresentationNames() {
        assertEquals("Yanbo’s Work", LibraryNames.english("yanbo-work"))
        assertEquals("砚波的工作", LibraryNames.chinese("yanbo-work"))
        assertEquals("Documents", LibraryNames.display("documents", false))
        assertEquals("文档", LibraryNames.display("documents", true))
        assertEquals("家庭", LibraryNames.display("family-a", true))
        assertEquals("Family", LibraryNames.display("family", false))
        assertEquals("Home Renovation", LibraryNames.english("home-renovation"))
        assertEquals("装修", LibraryNames.chinese("home-renovation"))
        assertEquals("Expense Receipts", LibraryNames.english("expense-receipts"))
        assertEquals("报销单", LibraryNames.chinese("expense-receipts"))
    }

    @Test fun unknownIdsRemainUnchanged() {
        assertEquals("synthetic-library", LibraryNames.english("synthetic-library"))
        assertEquals("synthetic-library", LibraryNames.chinese("synthetic-library"))
        assertEquals("synthetic-library", LibraryNames.display("synthetic-library", false))
    }
}
