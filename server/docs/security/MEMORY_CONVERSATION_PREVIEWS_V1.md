# Memory conversation previews v1

The protected conversation list can include a short preview of the first
retained user message when the caller explicitly requests
`GET /memory-community/v1/conversations?...&preview=1`. Without that query
parameter, the response keeps its legacy item shape (`id`, `created_at`, and
`expires_at`). Other preview values and duplicate query keys are rejected by the
existing strict query parser.

The preview is derived at read time from the earliest retained user turn. It is
not stored separately, does not invoke a provider, and does not request turn
history. The query remains scoped to the authorized actor, library, current
story or book, unexpired conversations, and the existing eight-item list bound.
An empty thread or invalid historical text produces an empty preview. Valid
text has Unicode whitespace collapsed to single ASCII spaces, is limited to 80
Unicode code points, and is trimmed after clipping so the preview never ends
with a separator. The UI
does not infer a first-message label from the most recently accepted message;
it may populate a blank label from a server-read turn only when that turn has
sequence 1.

The Web UI requests the opt-in field, checks its type, length, and control
characters, and assigns it through `textContent` as part of the native select
option. It retains the ordinal/date label for blank previews. If an older
server rejects the optional query with HTTP 400, the UI makes one legacy list
request and displays the ordinal/date label. It does not make a separate turn
request to build a preview; the ordinary current-thread history read can fill a
blank label only when sequence 1 is present.

Qualification uses synthetic records only. Tests cover the unchanged legacy
shape, opt-in validation, first-turn ordering, empty threads, Unicode bounds,
text-only display, rejection of malformed response text, language switching,
same-target thread selection, draft recovery, and the stale-scope fence before
legacy fallback. No runtime, provider, storage schema, or family data changes
are part of this contract.
