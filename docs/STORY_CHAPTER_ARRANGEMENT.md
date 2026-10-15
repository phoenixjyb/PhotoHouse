# Arrange a new story's chapters

A new story with reviewed source choices can split a chapter into two parts or
combine neighboring chapters. This gives one day's related photos and videos
an activity-based outline before the author saves it.

## User actions

Enable chapter source review, then open **Arrange chapters / 整理篇章**. Choose
where to split the current chapter, or merge it with the next chapter. Both
clients preserve the selected media order. A story has up to six chapters, each
with one to four moments. Saved-story editing retains its existing grouping.

Splitting keeps the current title and words in the first part. The second part
starts with the same title and no chapter prose. A selected source remains in
the first part that contains an eligible item; a source eligible for both parts
is retained once, in the first part. Original notes and recordings are unchanged.

Merging preserves both paragraphs and the unique selected sources. Different
titles are joined; identical titles are retained once. If the combined title,
words or source list would exceed a limit, the change is refused before any
chapter is modified. The author can shorten the text or adjust sources and retry.

After a successful arrangement, the phone review checkbox is cleared. Both
clients invalidate old title suggestions and retain an unsaved draft for review.
Recording, recognition review and uncertain saves must finish before arranging
chapters. Close an open phone dictation panel before changing its chapter.
Arrangement never submits a story,
starts recording, copies an original memory or requests model generation.

## Contracts and recovery

The existing `chapter_sources_v1` create contract accepts the actual ordered
chapter layout. Legacy creates keep their deterministic four-item grouping.
There is no new route or migration. Title assistance receives the actual chapter
assets and source choices. A submitted save freezes those groups, sources and
words for an identical retry.

Both clients' source-conflict refresh keeps a valid manual grouping and its
authored words. It refreshes item evidence and the selection revision, removes
selections no longer eligible and requires another review. A failed refresh
retains the unfinished draft. The [Web recovery flow](WEB_STORY_SOURCE_REFRESH.md)
keeps the text fields mounted during refresh, then asks for an explicit source
review confirmation before another save.

## Evidence and delivery

Local generated-data checks cover media order, chapter renumbering, split source
allocation, merge limits, stale controls, title invalidation, immutable save
retry, legacy refusal and phone source refresh. Browser and emulator render
results are recorded separately from Windows service availability, signed APKs,
OTA and family acceptance.
