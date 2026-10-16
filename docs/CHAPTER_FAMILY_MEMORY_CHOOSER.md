# Add an existing family memory to a chapter

October 16 Web/API and Android phone delivery. The Web chooser source merged in
PR #30; Android chooser source merged in PR #47 and shipped in phone v65. The
phone update is published, while physical installation and family acceptance
remain open. The chooser does not enable model generation or change the schema.

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
At compact widths, editor actions scroll with the content so they do not cover
the bounded source list; the page heading stays visible. Choices retain
44-pixel touch targets. Keyboard
selection and focus return after Cancel were checked. These renders were
inspected; they use synthetic people and memories only.


## Android flow

Open a saved story, expand **Manage chapter memories / 管理本章回忆**, then tap
**Add family memory source / 添加家人回忆来源**. Choices are loaded explicitly
from the same metadata-only endpoint. The list is bounded and scrollable; More
and Retry are separate actions. An error on a later page retains earlier choices
and retries the failed page. Selected links stay visible outside the paged list.

Choosing or removing a source edits the volatile link draft. **Close choices ·
keep draft / 收起选择 · 保留草稿** closes the picker without discarding choices.
An explicitly selected source can be opened for review before saving; its
original is never loaded merely to populate the picker. **Save links / 保存关联**
uses the existing revision-bound atomic update, including its frozen exact-retry
and conflict handling. Save, chapter navigation, parent refresh/reopen and scope
changes invalidate an active picker. Candidate metadata is not persisted to
device drafts, history or server records.

Before release, Android source passed 74 focused JVM tests, compilation, lint
and QA debug builds. Three emulator journeys passed with Chinese and English at
150% text size: selection/save/reopen, paging with exact failed-page retry and
unsaved-source review, and explicit original-text/ready-transcript review. Their
rendered views were inspected after recovering an emulator System UI interruption.
These are synthetic emulator checks, not physical-device acceptance. Audio review
here shows a ready transcript; it does not automatically fetch or play the
recording.

Reader refresh now preserves a dirty link draft against its verified baseline
while blocking edits during loading or failure. Frozen uncertain saves cannot be
replaced, and a revision-conflict Reload explicitly reacquires the story. Fresh
readers clear candidate metadata and old mutation state.

Phone v65 / `0.65-chapter-memory` is signed with the original certificate and
published to the Windows HTTPS feed. All five source CI jobs passed in run
`38835026125`. Separate release verification passed configured build/lint,
embedded-field, signing-refusal, publication, native full-HTTPS, independent
Mac full-stream and Web asset checks. The exact
APK is documented in the
[v65 release record](../clients/android/docs/PHONE_V65_RELEASE_2026-10-16.md).
The physical phone has not been installed or tested, and family acceptance is
open. No server schema or model activation is part of this chooser release.

The separate reviewed chapter-proposal adoption flow into an unsaved existing
story editor is delivered in [phone v66](../clients/android/docs/PHONE_V66_RELEASE_2026-10-16.md).
Its source passed 74 focused JVM tests, build/lint and eight QA-emulator journeys
with inspected Chinese/English 150% renders. V66 signing/OTA checks are recorded
separately; physical family acceptance remains open. Search clarification shipped separately in PR #48 and is live in
API/Web source.
