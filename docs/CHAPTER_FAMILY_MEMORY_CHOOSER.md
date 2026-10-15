# Add an existing family memory to a chapter

October 16 Web/API source following v64. This adds a manual source chooser to
saved-story editing. Android, live delivery and family acceptance are separate
following gates. It does not enable model generation or change the schema.

## Family journey

1. Open a saved story and choose **Edit story / 编辑故事**.
2. In a chapter, choose **Add family memory source / 添加家人回忆来源**.
3. Choose an accepted contribution by its original byline, type and receipt
   time. Additional pages are loaded explicitly. Cancel leaves the draft alone.
4. The chosen contribution becomes a source link in this unsaved edit. Use
   **View family memory / 查看家人回忆** to review it; original audio playback
   remains explicit. Remove an unwanted link before saving.
5. Choose **Save to library / 保存到相册库**, then reopen the story to check the
   chapter's saved link. Adding a link never automatically saves the story.

Only a library owner or the story's contributing author can choose links. The
source must belong to this story and library, be accepted, have local processing
consent and be either unbound or bound to this chapter. A chapter can link at
most 12 distinct contributions. Acceptance and a valid link do not prove the
recollection's factual accuracy. The original record's byline is attribution,
not a verified speaker/person identity.

## Metadata and save contract

The new protected read-only route is:

```text
GET /memory-community/v1/stories/{story_id}/contribution-candidates
    ?library=...&revision=...&chapter_id=chapter-N&page=1
```

It requires the existing collaboration/originals flags, healthy history
maintenance, the admitted source-reference schema, current membership, editor
permission and the complete readable media selection. Its response binds the
story, library, saved revision, chapter and page. Pages contain at most 16
eligible records, filtered before pagination. Each record contains only its
opaque ID, original byline, type, language, chapter binding, receipt timestamp
and optional recording duration. The query does not select contribution original
text/audio or derivation fields. IDs remain internal; they are not user labels.
The ordinary contribution list includes original text and is not used here.

Selection changes only the existing volatile reference map. The established
explicit-save `contribution_refs` contract stores the IDs atomically alongside
the new story revision. It rechecks contribution eligibility and story revision;
revoked consent or a changed story cannot be silently accepted. Original words,
recordings and transcripts remain in their existing source records.

The chooser refuses unverified reference state and fences stale responses and
actions by account/library, current draft/revision, editor lifetime and capture
state. A failed or malformed page leaves the draft and established links intact.
The existing failed-refresh warning, explicit original disclosure, removal and
uncertain-save recovery paths remain in use.

## Evidence and delivery

The focused backend cohort passed **66 tests**. Its synthetic checks cover
filtering, metadata-only SQL reads, pagination,
owner/author permissions, revoked membership, moved/deleted parent media,
revision/query/schema/feature guards and atomic save rejection after consent
withdrawal. The generated browser-to-ASGI/SQLite journey exercises manual
selection, save/reopen and explicit source disclosure. Browser fixtures contain
generated text/audio only. Desktop/narrow, enlarged-text and keyboard checks are
source evidence; they do not establish installed Web, phone or family acceptance.

The browser journey passed against the closed ASGI application and generated
SQLite data, including cancel/late-response fencing, exact failed-page retry,
explicit save/reopen and original disclosure. Starting Save closes an in-flight
chooser; failed-save recovery cannot strand it in a loading state. Chinese and English compact views
were rendered at an effective 260 CSS pixels (390 pixels enlarged to 150%).
At compact widths, editor header/actions scroll with the content so they do not
cover the bounded source list; choices retain 44-pixel touch targets. Keyboard
selection and focus return after Cancel were checked. These renders were
inspected; they use synthetic people and memories only.
