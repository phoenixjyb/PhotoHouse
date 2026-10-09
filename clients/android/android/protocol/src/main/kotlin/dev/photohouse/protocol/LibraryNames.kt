package dev.photohouse.protocol

/** Presentation-only names for known protected libraries; IDs remain the wire identity. */
object LibraryNames {
    private data class Name(val english: String, val chinese: String)

    private val known = mapOf(
        "yanbo-work" to Name("Yanbo’s Work", "砚波的工作"),
        "documents" to Name("Documents", "文档"),
        "chuan-work" to Name("Chuan’s Work", "曹川的工作"),
        "scenery" to Name("Scenery", "风景"),
        "concerts" to Name("Concerts", "音乐会"),
        "home-renovation" to Name("Home Renovation", "装修"),
        "expense-receipts" to Name("Expense Receipts", "报销单"),
        "family-a" to Name("Family", "家庭"),
        "family" to Name("Family", "家庭"),
    )

    fun english(id: String): String = known[id]?.english ?: id
    fun chinese(id: String): String = known[id]?.chinese ?: id
    fun display(id: String, chinese: Boolean): String = if (chinese) chinese(id) else english(id)
}
