# Select search results for a story

This is a local Web/API source increment dated November 14, 2026. It does not
deploy Windows services, activate a model, change household stories, or publish
an Android build. GitHub Actions remain paused.

## Family flow

1. Submit a typed or explicitly authorized voice search in the private assistant.
2. Select individual photos and videos. The count shows the 24-frame limit.
   Selections initially keep click order across pages of the same result set;
   duplicate IDs never add a frame.
3. Open **Review selection order** to move a frame earlier or later, or remove
   it, including choices from earlier result pages. These buttons work with
   keyboard Enter/Space and have English/Chinese accessible labels. Reordering
   keeps all selected frames and creates no search or model request. Use
   **Clear selection** to start over. Unselected controls are disabled at 24.
4. Choose **Shape a story with selected frames**. A fresh current-result
   read must confirm the source and access before the editor opens with exactly
   those frames. Existing unsaved-work guards still apply.
5. Build, edit, review, and save using the existing story editor. Selecting or
   opening frames does not build, generate, save, publish, or play a story.

On the first page of a private search, **Why this match?** on a result card
prepares a question about that item. Review the question and choose **Find**.
It keeps any existing unsent draft. You can also ask “Why result 20?” or
“为什么是第20项结果？” about one of the visible results. Return to the first
page before sending a numbered follow-up. The explanation keeps the same
results and filters available for selection.

A new or refined search clears the selection, including one that needs
clarification. Switching conversations or accounts, changing libraries, losing
access, and signing out also clear it. After a refresh in the same browser tab,
reopen the same Jude conversation to resume your ordered picks for a new story
from an ordinary search. PhotoHouse keeps the result identifiers and page numbers
in tab storage and reads the current result and selected pages again to verify
each pick. Reopening waits for any outstanding paging capability check before
restoring later-page selections. If the result expired or a picked item is no
longer available, choose the frames again. Scene results, legacy results, and
picks for an open editor stay in page memory. An uncertain search uses the
existing GET-only recovery flow.

## Ordinary result pages

The existing scene page contract remains separate. Ordinary v1/v2/v3 searches
use an optional `GET /assistant/workspace/v1/result-page-capabilities?library_id=…`
with the closed response `{version:1, available:boolean, page_size:20}`. Older
servers retain their first-page behavior when this capability is unavailable.

`POST /assistant/workspace/v1/threads/{thread}/requests/{request}/result-pages`
is a read-only continuation. Its body is exactly `version`, `library_id`,
`expected_revision`, and `page`; it accepts no client-supplied filters or query.
The original search version is negotiated in `X-PhotoHouse-Search-Version` for
v2/v3, with no header for v1. It returns the bound library, thread, request,
revision, search version, binding, fingerprint, page, page size, total,
`has_more`, and normalized items, with response `version:1`.

The store requires the selected turn to be the latest request of any status and
still completed, unexpired, owned by the signed-in account, and at the expected
thread revision. The server replays its saved filters using the original search
policy, rechecks authorization/source and the unchanged stored request, and
returns no cards on a conflict. Paging invokes no language planner or encoder
and creates no conversation turn. Ordinary page requests use the existing
5,000-page request bound and 20-item page size.

Pages are a temporary view of the original result. Returning to the first
results rechecks the current saved request and conversation before enabling
another typed/voice turn. This keeps commands such as “open the first result”
bound to the result list understood by the server. Selection survives a
successful return; a failed freshness check cannot hand off stale frames.

`GET /assistant/workspace/v1/threads/{thread}/requests/{request}/current-result`
requires `library_id` and `expected_revision` query parameters and the original
search-version negotiation. It returns the existing completed-turn envelope,
with `recovered:true`, after fresh source and authorization checks and identical
latest-request guards before and after the read. It creates no turn and runs no
planner or encoder. Unlike ordinary history metadata, it refuses an older
completed result when a newer pending, failed, interrupted, or expired request
exists. The established receipt-recovery endpoint keeps its original behavior.
An older server without the new readback cannot release a story selection.

The discovery source digest covers asset media type, dimensions, duration and
capture date across the bound library. Fresh readback therefore rejects changes
to a selected frame on a later page as well as changes on the first page. The
ordinary and scene metadata-mutation regressions verify this refusal.

## Grounded clarification and measurement

The typed parser recognizes natural English openings such as “the photos where
we were celebrating indoors”. Unsupported details lead to a short clarification
about the available evidence instead of silently dropping conditions. This is
not a claim of visual recognition or real-library relevance. “只看视频” retains
the earlier person and date; “earlier / 再早一点” asks for a specific date while
retaining other filters and the currently authorized context.

Generated regressions record actual search calls: a fresh query executes one
result search, a refinement revalidates the old scope and executes its new
filtered search, and an ambiguous follow-up only revalidates the old scope.
Completed-turn recovery also revalidates the old scope without a new turn.
These authorization reads are intentional.

Legacy voice playback failure now retains its visible reply and result cards.
Private-workspace updates clear only results owned by that workspace, so pausing
after a failed audio playback does not erase a legacy search result.

The browser journey records click-to-render and pending-state timings alongside
request counts. Those measurements include the local generated ASGI bridge and
browser harness. They do not satisfy the historical semantic latency target or
measure a native service, inference provider, physical phone, or household data.

## Reproduce locally

Use the existing CPU environment and optional browser tools described in
[Development](DEVELOPMENT.md) and [Web development](WEB_DEVELOPMENT.md).
Focused suites are:

- `server/tests/security/test_assistant_result_pages.py`
- `server/tests/security/test_assistant_current_result.py`
- `server/tests/security/test_assistant_story_selection.cjs`
- `server/tests/security/test_assistant_story_selection_browser.cjs`
- `server/tests/security/test_assistant_search_browser.cjs`
- `server/tests/security/test_assistant_joint_search.py`
- `server/tests/security/test_assistant_bilingual_review_journeys.py`
- `server/tests/security/test_assistant_workspace_turn_http.py`

The browser uses disposable accounts, generated media, an intercepted
`photohouse.test` origin, and a pipe to the test API. It opens no production
origin and runs no model. Real-library relevance, provider responsiveness,
Windows delivery, and family review remain separate gates.

## November 14 local verification

The source increment starts from `269abb2e2358b8dd4f5d30668113097a473e2e34`.
Focused checks passed:

- 227 Python tests across query planning, refinement, paging, current-result
  readback, workspace storage/transport, scene recovery and closed routes.
- 120 Node tests across private/scene workspace state and voice controls/timing,
  plus the standalone selection, v3 negotiation and agent controller checks.
- Generated browser journeys: selection (7 checkpoints), bilingual search (8),
  scene recovery (9), story editor (30), and the full voice-session journey.
  Selection includes keyboard Space controls and off-page removal, a mixed
  photo/video handoff in exact click order, and logout during a held readback.
  It made zero story preview or save requests.
- Desktop and 390px phone renders at 150% text were inspected. The generated
  selection journey had no horizontal overflow or browser page errors.
- JavaScript syntax and Git whitespace checks passed.

The final generated search run measured ten completed click-to-render samples
between 60 and 289 ms, with pending feedback at 41 ms. Each submission made one
turn POST; uncertain recovery made zero additional turn POSTs. These small local
fixture samples describe UI behavior only, not model speed or real relevance.

No full repository/API/Android regression, Windows delivery, native provider
benchmark, or household acceptance was performed. The existing birthday story
is left for the owner's review.

## November 24 selection-order increment

The selection toolbar now has move-earlier, move-later and remove buttons for
each selected frame. The same controls work for a choice from a previous result
page, at the 24-frame cap, and when adding frames to an existing story. The fresh
current-result check still runs before opening or appending to the editor; an
account/library change or pending handoff prevents reordering. The original
media metadata stays attached to the selected frame.

Focused local checks passed for boundary moves, invalid/unselected IDs, the
24-frame cap, pending readback, generation changes, and the exact reordered
handoff. The generated browser journey passed 20 checkpoints, including keyboard
Space/Enter, focus at the first/last boundary, cross-page photo/video ordering,
logout during readback, and explicit story revision saving. Reordering itself
made zero API requests. Desktop, 390px at 150% text and 320px at 200% text renders
were checked; ordering controls retain at least 44px touch targets. This is local
source/browser evidence; Windows delivery and household acceptance are separate.

## November 25 generated Search-to-story journey

The generated browser starts a private Jude search, narrows the reviewed person
query by date, and asks why the first photo matched. The response cites the
reviewed person and capture-date evidence. The author picks two frames across
ordinary result pages, and the editor keeps their click order. An explicit
source choice adds a family-authored note to one chapter. The local test provider
returns a proposal for review, and the author edits and saves it. Reopening
checks the frame order, chapters, adopted wording and original note.

The journey uses disposable data and the existing in-memory provider fixture.
It checks that searching, paging and arranging frames neither generate prose
nor save a story. Household prose quality, installed clients and native provider
timings remain open. Run this path with the installed Web tools:

```sh
PH_JOIN_SELECTED_STORY=1 node server/tests/security/test_assistant_story_selection_browser.cjs
```
