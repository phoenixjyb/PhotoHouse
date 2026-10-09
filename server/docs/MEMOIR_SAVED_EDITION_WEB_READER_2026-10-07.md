# Saved memoir editions in the Web reader

The memoir reader exposes a saved edition shelf to authorized book readers,
including members who cannot edit the book. It is independent of generation
availability, a ready generation job, and the private draft editor.

The shelf reads the edition capability first. When editions are enabled, it
requests the metadata-only list in pages of eight. List entries contain status,
creation date and identity only; opening an entry makes a fresh detail request.
The reader clears previously displayed prose before that request and keeps no
fallback copy if the request fails or reports changed or invalidated sources.

Current detail prose must pass the bounded manuscript decoder and its chapter
IDs must cover the current ordered book children as contiguous
`<story-id>-chapter-1..6` sequences. This client check confirms chapter scope;
the server remains authoritative for fresh source provenance. Changed or
invalidated entries must carry null manuscript content.

The shelf is outside the generation/editor panel so list and detail refreshes do
not replace a pending editor or its DOM identity. Account, library, book and
revision changes invalidate outstanding shelf responses. The reader does not
generate, play, record, save, or persist drafts automatically.

Saved detail uses labels for saved chapters and a saved AI manuscript awaiting
review. It does not reuse proposal labels that could make durable saved text look
like a new draft or verified fact. Chapter audio uses the real story-workspace
speech adapter in its saved-edition mode. A reader must explicitly start it; it
speaks only the visible chapter text with an available local voice, and does not
start automatically. A fresh detail read, invalidation read or locale rerender
disposes only shelf speech controls, leaving sibling private proposal and chat
speech controls intact.

Browser verification uses the synthetic ASGI bridge and Chromium. It is source
and UI evidence only. The focused reader fixture checks exact prose playback,
manual start, local voice selection, cancellation on fresh and invalidation
reads, shelf-only disposal, and chapter directory targets alongside a sibling
proposal speech control. It also checks Chinese and English shelf rendering and
actual computed text at 1.5× in a 390px viewport. These checks do not establish
Windows runtime, GPU, phone, or family acceptance.

C2 remains default-off. UI source and synthetic browser checks do not authorize
activation; enabling it remains gated on native source-purge behavior and
backup/restore verification for the owning deployment.
