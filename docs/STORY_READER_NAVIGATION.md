# Story reader navigation

The Web and phone readers keep a selected media frame inside a selected story
chapter. Selection changes the current preview; it does not start video,
narration, microphone capture, story saving or a model request.

## Web filmstrip

Each chapter shows protected preview thumbnails with visible frame numbers and
a video marker. Controls have at least 44 px targets, localized position labels,
selected semantics and a live current-frame notice. A failed thumbnail leaves
its frame selectable. The existing outline groups up to 24 selected media into
chapters of at most four frames; this change preserves that contract.

Clicking or using arrow keys reveals the selected control inside the horizontal
strip. It does not scroll the page or reader dialog. Language changes preserve
focus and strip position. Detached controls are bound to their rendered draft,
chapter and access generation, so they cannot act on a replacement reader.
Late preview errors and detached video controls likewise recheck the current
reader and DOM attachment before changing the stage or opening media.
Signing out clears the controls and live position notice.

## Phone reader

The selected frame is bound to current account, library, access generation,
story revision, chapter identity and ordered eligible media. A changed scope or
media cohort resets selection to the first current frame. Preview bytes are
shown only for a current story item. Explicit frame, chapter and open-media
callbacks recheck the current reader before acting.

The strip exposes selected semantics and a localized position label. Chapter
count has its own line; equally sized Previous/Next buttons retain 48 dp
minimum targets at enlarged text. This avoids placing three competing labels
in one narrow row.

The phone can now offer [Continue reading](PHONE_STORY_READING_CONTINUITY.md)
after a process restart and a fresh authorized detail read. Its encrypted record
contains only location identifiers and revision metadata. The matching location
is an offer; restoring it and opening its original media remain separate actions.

## Explicit memoir narration continuation

After local Web speech finishes a chapter, a memoir reader can offer **Read next
chapter aloud / 继续朗读下一章** when that same story has another chapter. The
button advances and starts speech only on an explicit click. It does not cross
to a different story, fetch source audio, invoke a provider or start recording.
Manual navigation, replay, stopping, reader replacement and scope changes
invalidate the old action. Active capture or an unfinished dictation helper
refuses continuation. The current reader, book revision, ordered child list and
exact story/chapter snapshot must still match.

Source `ce2467c` passed 24 generated memoir browser checkpoint groups and the
complete 19-suite Web profile. Chinese and English 390 px/150% renders were
visually inspected. Browser speech uses an installed local voice; the synthetic
speech adapter does not qualify a household device's voice or audio quality.

The phone also has separate [memoir reading continuity](PHONE_MEMOIR_READING_CONTINUITY.md),
with fresh parent/child authorization before a location is offered and explicit
Continue or Start over. Story and memoir records have separate encryption domains.

## Manual memoir story boundaries

Web source `074d096` labels a cross-story step **Next story / 下一则故事** or
**Previous story / 上一则故事**. Within a story, the chapter labels remain.
Moving to another story freshly reauthorizes the book before the child; the
new heading receives focus. Previous, Next and Contents callbacks check their
attached controls and rendered account/library/book/ordered-child/story/chapter
snapshot before stopping speech or changing the reading pane. An old close
event cannot stop a replacement reader's narration.

The 24-checkpoint memoir journey and final complete 19-suite profile passed.
The first full profile timed out opening the workspace after a saved story's
Edit action. Two isolated workspace runs and the final full run passed without
source or test changes; that first failure's cause remains unknown. Both
English/Chinese 390 px/150% story-boundary controls were inspected.

## Original memoir contents and media cards

The phone original reader has a collapsed **Contents / 目录** panel. Opening it
uses the book's already loaded story summaries and the current story's chapters;
it does not fetch every child or original media. An explicit story choice uses
the normal fresh parent/child read. A chapter choice uses the loaded current
story. Current rows are marked and disabled so tapping them does not reset the
reading position. Previous/Next controls remain available.

Manual phone controls retain the exact rendered account, generation, library,
reader instance, book revision, ordered child revisions, chapter, page and
selected moment. A detached control cannot move the replacement reader or write
its bookmark. Opening media checks this scope both before and after the leave
confirmation. Numbered media cards expose their selected state to accessibility
services; a dedicated current-label line keeps failed-preview text readable at
150% text size. Choosing a card changes only the preview selection.

The Web original memoir reader numbers photos and videos within each chapter,
using those positions in alternative text, open controls and visible captions.
Date captions still identify the recorded capture-date source. Captions scale
with text size; two-item mobile chapters give both captions a full-width row.
Late preview errors and old open-media callbacks check their attached control
and exact rendered story/chapter before fetching a fallback, changing the DOM,
closing the reader or stopping replacement speech.

## Evidence and delivery

Generated browser journeys cover keyboard navigation, narrow bilingual renders,
one/two-frame chapters, failed thumbnails, detached controls and logout. Phone
instrumentation uses generated adapters on an API 36 emulator; its source and
render results remain separate from a signed APK, OTA, installed phone or TV.
See [development evidence](DEVELOPMENT.md) for the exact checks.

This reader work does not change the TV application or its anonymous LAN access
policy. Original playback, contribution review and story/memoir conversation
controls retain their existing explicit actions.
