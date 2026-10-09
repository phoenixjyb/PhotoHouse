# Saved memoir source inspector — Web

The saved-edition reader now has an explicit, edition-bound source inspector.
It works from the saved edition shelf and does not require the reader to own
the private ready job or have edition-writing permission. The inspector uses
the protected source routes defined in
[`MEMOIR_EDITION_SOURCES_V1.md`](security/MEMOIR_EDITION_SOURCES_V1.md).

## Reader behavior

- Opening a saved edition loads its current manuscript only. It does not load
  source text or audio. The reader chooses **Review this edition’s source
  materials** to request a metadata-only catalog, paged at 16 entries.
- Catalog entries describe origin and material kind. They do not expose words,
  bylines, URLs or audio bytes. A separate **Inspect material** action loads one
  source currently bound to the selected edition. Chapter citations can open
  their selected source IDs through the same explicit detail action. The
  client checks origin-specific selector structure, exact book-introduction
  binding and saved-chapter child binding against the current ordered children.
- Details show current stored text or transcript separately from the exact
  prompt excerpt used for this edition. Bounded text includes a notice that it
  is only a partial display. AI captions and ASR transcripts are labeled as
  derived material; family-edited captions, family originals, memoir direction
  and saved chapter wording keep separate labels.
- An original recording has its own explicit load button. The reader validates
  the returned WAV and size, creates a local object URL, and shows a manual
  controls-only player. It does not autoplay. Fresh reads and scope changes
  abort pending requests, stop the player, clear material and revoke the URL.
- After an explicit source read, focus and viewport move to the returned
  material heading, or to the final changed/unavailable notice. The handoff is
  scope-fenced and yields if focus moved during the request, an editor is
  focused, IME composition is active, or recording is underway.
- A changed or invalidated source clears both the source inspector and parent
  manuscript. Failed and malformed reads clear the affected prior material;
  no cache or unbound legacy route is used as a fallback. Account, library,
  book and ordered child-revision changes fence late results. Shelf cleanup is
  scoped to its own speech controls and leaves private proposal speech DOM
  intact.

## Verification

The focused browser test is `tests/security/test_memory_book_edition_sources_browser.cjs`
with its no-listener ASGI fixture `tests/security/memory_book_edition_sources_browser_bridge.py`.
It uses a temporary synthetic SQLite library and generated WAV bytes. The
Chromium journey passed with two save requests carrying the same uncertain
retry payload, zero browser errors and zero external requests. It checked:

- no source-detail or audio request on shelf open or catalog open;
- all six catalog origins, the 16-item first page and a second metadata page;
- explicit source detail for AI and family-edited captions and an ASR-backed
  recording, including separate current text and prompt excerpt labels and the
  voluntary asset-note byline;
- active-element and viewport checks for successful detail, failed and changed
  notices without test-driven scrolling, plus focus preservation when a
  connected synthetic private-editor sentinel is focused during a delayed read;
- explicit audio load, no playback start, a `controls` player with `autoplay`
  false and `preload=none`, and object-URL revocation on a fresh edition read;
- originals-gate refusal, unavailable reads, malformed metadata/detail,
  short current pages incorrectly marked `has_more`, `source_changed` clearing
  on both detail and page 2, valid empty current-page metadata, and source
  invalidation hiding the manuscript;
- late detail fencing across account/library and book/child revision changes;
- pending editor DOM retention during shelf refresh, IME navigation guard,
  uncertain-save identity/payload retry, and no generation during retry;
- Chinese and English source views at 390 CSS pixels, with selected source
  metadata and prose raised to 150% of their pre-write computed font sizes and
  no horizontal overflow.

Run with existing local tools (no package or browser download):

```sh
PH_BROWSER_PYTHON=/path/to/python \
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright-core \
PH_BROWSER_EXECUTABLE=/path/to/chromium \
PH_BROWSER_ARTIFACTS=/path/to/artifact-directory \
node tests/security/test_memory_book_edition_sources_browser.cjs
```

Reviewed browser screenshots are written to the configured artifact directory:

- `sources-zh-current-readable-390px-text150.png`
- `sources-en-current-readable-390px-text150.png`
- `sources-zh-detail-viewport-390px-text150.png`
- `sources-en-detail-viewport-390px-text150.png`

The fixture uses synthetic material only. This is source and browser evidence,
not family-device listening, production route, Windows service or media-store
acceptance. The C2 routes remain default-off unless explicitly enabled; the
existing native physical-purge and paired-restore activation gate still applies.
This UI does not activate C2, change retention, create saved drafts, or call a
model.
