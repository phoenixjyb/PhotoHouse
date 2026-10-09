# Memoir source chooser v1

Source/UI candidate, October 5, 2026. The memoir editor provides local search and
bounded paging when a story has many eligible citation sources. This changes how
the existing source catalog is browsed; it does not change the citation API,
save body, source order, or server limits.

## Chooser behavior

Each opening or transition chooser searches only the already-loaded catalog
metadata: saved story title, chapter label, and recall ordinal. Typing, paging,
and clearing a filter never fetch contribution details or audio. At most 12
eligible source rows appear on a page. The chooser reports the visible range,
number of filter matches, total eligible sources, total selected references, and
selected references currently outside the view. Its clear-filter, previous, and
next controls have Chinese and English labels.

Selections remain in the in-memory draft while hidden by a search or page. A
selected source missing from the current eligible catalog remains in a separate
visible, removable list regardless of the active filter or page. The existing
limit remains 12 selected references per section and 96 across the memoir. Only
an explicit checkbox change removes a saved selection.

While a save or uncertain retry is pending, newly rendered checkboxes remain
disabled. Their change handlers also refuse forced events. Browsing another page
cannot change the frozen request; a retry sends the same serialized body.

Changing the chooser filter/page clears any inspected source panel, aborts and
fences held detail/audio responses, pauses and removes a loaded player, and
revokes its object URL. Account/library changes discard the scoped chooser state;
locale changes reset the local filter and page. The visible byline is labeled as
submitted contribution text and does not establish the contributor's account
identity. Audio remains a separate user action labeled “Load original
recording”; playback does not autoplay.

## Evidence

The source is in `backend/app/ui/access/memory-community.js`, with presentation
in `backend/app/ui/access/styles.css`. The synthetic Chromium journey and bridge
are `tests/security/test_memory_book_editorial_browser.cjs` and
`tests/security/memory_book_editorial_browser_bridge.py`.

The expanded fixture supplies 24 eligible sources across two saved stories. The
journey covers 12-row paging, title/chapter/recall-label search, zero-match and
clear-filter behavior, selections across pages, save and reload of the selected
references, unavailable-reference removal, locale/scope resets, stale held
inspection fencing during paging and filtering, and no eager detail/audio
requests. It also checks the submitted byline label and renders the large chooser
in Chinese and English at 390 px with 150% zoom. This is local synthetic source
evidence only; it does not establish Windows installation, live service,
provider, or physical-device acceptance.
