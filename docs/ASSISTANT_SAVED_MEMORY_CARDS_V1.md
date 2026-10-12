# Private assistant saved-memory cards

Status: locally implemented discovery, explicit-command parser, result tool and
negotiated default-off backend transport, plus scoped Web card presentation.
Phone cards and reader handoff remain proposed. Typed-source reply speech is
implemented locally with a separate optional capability probe. No Windows
activation or signed client delivery is claimed.

## Existing protected foundation

`AssistantMemoryDiscovery` searches current saved story titles and chapter
narration, plus memoir titles and introductions. It uses the existing authorized
`MemoryStories.list/get` and `MemoryBooks.list/get` readers. Those readers scope
by the authenticated account's current library membership, filter missing,
moved, deleted or unreadable parents before pagination, and hydrate current
story evidence and memoir children. The discovery layer returns frozen
references with `kind`, `id`, current numeric `revision`, a SHA-256
`source_revision`, title and a bounded plain-text excerpt. It searches saved
family text only; it does not search source captions, annotations, provider
output or media bytes.

The search is a literal, case-insensitive substring match. `%`, `_` and `\\` have
no wildcard meaning. Queries are trimmed, limited to 160 Unicode code points
and 320 UTF-8 bytes. Excerpts are limited to 240 code points. A search examines
at most 256 available story and memoir candidates and returns at most 12 cards;
if more candidates would make the scan incomplete, it fails closed. The scan
uses a `PRAGMA data_version` guard because list pages and detail reads use
separate authorized transactions. A concurrent commit makes the scan return a
conflict. A concurrent change after the final check remains an ordinary
read-return race; the reader handoff always performs a fresh protected GET.

The foundation also has a revision-bound `read_reference` operation. It returns
existing authorized reader data only when the numeric and source revisions still
match, with a final commit-drift guard. That reader payload is request-owned
mutable data; references and search-page metadata are frozen.

`assistant_memory_intent.py` implements the explicit prefix and literal-phrase
rules below. `assistant_saved_memory_tool.py` produces fresh card projections,
existing strict stored summaries and typed reference projections. It does not
persist them or execute a reader handoff.

The domain foundation has no persistence or model call. Its focused security
suite exercises authorization, withdrawal, source drift, literal matching,
revision binding and bounded results. The protected private-turn transport now
uses its outputs only after explicit client negotiation.

## Negotiated default-off extension

The runtime flag `assistant_saved_memory_cards_enabled` defaults to `false`.
Admission requires the existing assistant, healthy private workspace, enabled
memory collaboration and healthy memory retention. The request still requires
the current account-owned thread and `library.read` membership. The flag is
discovered through a separate optional feature probe:
`GET /assistant/workspace/v1/saved-memory-capabilities?library_id=...`.
It returns exactly `{version: 1, available: <boolean>}` under current library
authorization. Updated clients treat a missing/unavailable probe as false,
without disabling ordinary private history or media turns. Keep the existing
capabilities response unchanged: older SDKs reject unknown capability fields.
The feature probe reports true only when the assistant turn engine,
private store and saved story/memoir readers are all available for this
request's library.

The Web client checks this separate probe after the ordinary private workspace
loads. Missing, disabled or malformed probes preserve the legacy request body;
access denial clears private state. New account/library generations, base
capability loss and a newer feature probe fence late card responses. Fresh cards
are immutable plain-text projections and bypass media hydration. They have no
open button or stored actionable context. The phone SDK has not adopted this
extension yet. Qualified source and generated-browser evidence are recorded in
[Development](DEVELOPMENT.md); they do not prove live or family acceptance.

The existing turn request remains byte-for-byte unchanged unless a capable
client opts in. Extend its strict body with one optional field:

```json
{
  "library_id": "example-library",
  "request_id": "11111111-1111-4111-8111-111111111111",
  "expected_revision": 3,
  "text": "找回忆 野餐",
  "accepts": ["saved_memory_cards_v1"]
}
```

`accepts` is omitted by legacy clients. When present it must be the unique
single-element array shown above for a new request, and the capability must
currently be true. An existing matching request is recovered before applying
new negotiation or current feature availability.
The existing 1024-byte input, 20 KiB JSON and three-second request bounds
remain. The POST request ID and parent receipt correlation keep their current
idempotency and scope rules. No client context, source ID, revision, card,
excerpt, effect or result is accepted.

Negotiation is not a new idempotency-key component in this slice: the current
`begin_turn` replay key is account/library/request ID, with thread ID, input text
and expected revision checked for conflict; it does not fingerprint `accepts`.
Replaying the same request ID, text, thread and expected revision with changed
or omitted `accepts` follows the existing stored status and remains GET-safe.
It never recomputes the turn or upgrades a prior result into fresh cards. Do not
add an undocumented schema fingerprint field. A new request ID is required for
a new opted-in search.

Only an opted-in turn uses saved-memory commands. Keep this first version
deterministic and explicit so ordinary photo search keeps its current behavior:

| Locale | Command form | Search phrase |
| --- | --- | --- |
| Chinese | `找回忆<phrase>` or `找回忆 <phrase>`; `搜索故事<phrase>` or `搜索故事 <phrase>`; `找回忆册<phrase>` or `找回忆册 <phrase>` | Trimmed remainder |
| English | `find saved story <phrase>`, `search saved memories for <phrase>`, `find memoir <phrase>` | Trimmed remainder |

Chinese prefix matching accepts ASR output with no separating space (for
example, `找回忆野餐`); a space after the prefix is optional. `搜索故事` selects
story matches, `找回忆册` selects memoir matches, and the generic `找回忆`
command searches both kinds. English commands select the corresponding kind in
the same way. Apply the kind filter before the 256-candidate completeness limit
and before ranking/display limits. An empty phrase receives a clarification.
Trim outer whitespace. For an unquoted phrase, normalize terminal spoken
punctuation only (for example a final `。`, `！`, `？`, `.`, `!` or `?`) before
literal search; do not remove punctuation from inside the phrase. If the whole
phrase is explicitly quoted with matching straight or curly quotation marks,
remove only the enclosing pair and preserve all inner punctuation and
metacharacters literally, including a terminal punctuation character. An
unrecognized request follows the existing deterministic media assistant. There
is no LLM, semantic ranking, remote lookup, memory generation, save, edit,
delete, share or automatic effect in this slice.

## Fresh response shape

An opted-in saved-memory command returns the existing private turn envelope and
an extended result. Existing result fields remain present; only this negotiated
branch adds `memory_cards` and admits `kind: "memory_cards"`:

```json
{
  "version": 1,
  "kind": "memory_cards",
  "reply": "找到 1 段已保存回忆。选择卡片可在现有阅读器中打开。",
  "context": {
    "kind": "saved_memory",
    "library_id": "example-library",
    "source_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "references": [
      {
        "kind": "story",
        "id": "22222222-2222-4222-8222-222222222222",
        "revision": "2",
        "source_revision": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
      }
    ]
  },
  "filters": null,
  "items": [],
  "total": 1,
  "has_more": false,
  "effect": null,
  "memory_cards": [
    {
      "kind": "story",
      "id": "22222222-2222-4222-8222-222222222222",
      "revision": "2",
      "source_revision": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "title": "A day by the lake",
      "excerpt": "We packed lunch and walked down to the water."
    }
  ]
}
```

`total` is the count of all authorized literal matches within the complete
256-candidate scan, before the 12-card display limit. `memory_cards` and
`references` contain the first at most 12 ordered matches; those references
exactly match the displayed `(kind, id, revision, source_revision)` bindings.
`has_more` is true exactly when `total` exceeds the number of displayed cards.
For example, 21 full matches produce `total: 21`, 12 cards, and
`has_more: true`. There is no cursor or paging in this version; ask the user to
refine the phrase to narrow results. The foundation exposes this immutable
page metadata through a `search_page` result while retaining `search()` as a
tuple-returning compatibility wrapper. `context.kind` distinguishes this source
set from the existing media context, whose exact shape and meaning stay
unchanged. The saved-memory context is descriptive and revision-bound; the
client never sends it back as authority. `effect` is always null. A card is a
reference, not a navigation command.

Card limits are: 12 cards, unique `(kind, id)` pairs, UUIDv4 IDs, canonical
positive decimal revisions no larger than `2^63-2`, lowercase 64-character
SHA-256 source revisions, titles at most 640 UTF-8 bytes / 640 code points,
excerpts at most 240 code points / 960 UTF-8 bytes, and at most 240 KiB for the
whole response, matching the current private workspace response budget. The
saved-story parent title has no explicit source length bound, while chapter
titles are bounded to 640 UTF-8 bytes and 160 code points and memoir titles to
512 UTF-8 bytes. The card limit is therefore a wire bound, not a source
guarantee: never truncate, omit, or alter an oversized saved title. Fail the
whole card response closed and report a safe unavailable outcome if any matched
title exceeds the card bound. Existing saved data remains readable by its
current reader. A zero-match response has the same shape with empty `references`
and `memory_cards`, `total: 0`, `has_more: false` and a localized no-match reply.
It never fabricates an excerpt or source.

For a story, `source_revision` binds the authorized story ID, its current numeric
revision and its current selection/evidence revision. For a memoir, it binds the
memoir ID and revision plus the ordered child story IDs, revisions and current
selection/evidence revisions. The reader refuses a child revision that changes
while it hydrates the memoir. Membership, owner scope and current media/evidence
availability are checked again at every read.

## Stored turns, history and recovery

Keep the persisted private-turn result summary in its current strict v1 media
grammar. For a saved-memory turn, store a safe summary with `context: null`, no
media `items`, `total: 0`, `has_more: false`, `effect: null`, and the exact same
short server-owned `reply` shown with the fresh cards. The reply must not depend
on card titles or excerpts. Future source-validated speech can therefore use
exactly the reply the user saw. Store no title, excerpt, narration, opening
or `saved_memory` context in private assistant storage.

Pass the current typed IDs and source digests through the existing
`complete_turn(..., cards=...)` slot using its already-supported `story` and
`memoir` reference kinds. Use the source digest for the opaque 64-character
reference binding fields; the numeric reader revision remains on the fresh
response. Existing private history projects those references only as type/count
placeholders with `actionable: false`. It reveals no IDs, excerpts, evidence,
reader links or source hashes.

GET recovery and POST idempotency replay return only the stored safe summary,
with the existing `recovered: true`, no memory cards or saved-memory context,
and no effect. The client presents a separate recovered-status notice while
keeping the stored `reply` as the same server-owned text from the fresh turn.
They do not re-run the search, speech, navigation or listener. An uncertain
client preserves its draft and can explicitly submit a new search after
reviewing the recovered status. Opening an existing thread or paging history
never hydrates saved-memory cards.

Because the saved-memory summary has `context: null`, successful completion
also deletes any previous media `thread_context` for that thread using the
existing `complete_turn` behavior. The memory result has no media `effect`; a
previous media result such as “open first” cannot be carried forward or
executed by this turn. Pure voice ordinal navigation such as “open the first
memory card” remains out of scope: there is no persisted typed memory context
for recovery to authorize that action.

No isolated assistant-store schema-v3 migration is needed for this first
extension only if cards remain an ephemeral explicit reader slice: it adds no
columns or tables, keeps `thread_context` media-only, uses the already-supported
`story` / `memoir` exchange reference kinds, and persists only the existing
legacy result-summary shape and opaque typed references. Schema-v2 stores and
older readers therefore continue to handle threads, exchanges, preferences and
turn recovery without parsing a new stored result kind. If a later design
chooses to persist excerpts or typed saved-memory context for rehydration, it
must separately specify an explicit offline schema-version migration, backup
and rollback path; it must not silently widen the current v2 JSON grammar.

## Reader handoff

Only a fresh card response displays an explicit **Open saved story** or **Open
memoir** control. Clicking it ends the current automatic voice progression and
calls a client handoff callback bound to the same authenticated account,
library, foreground generation and parent turn/card ordinal. The client sends
no title, excerpt, source digest or source revision as authority. The proposed
protected revision-bound handoff service resolves the card from that completed
turn's stored `story` / `memoir` reference, checks current library membership,
hydrates through the authorized current reader, recomputes the source digest,
and returns reader data only on an exact digest match. It applies the discovery
`PRAGMA data_version` drift guard through the completed read. For memoirs it
must include current child selection/evidence revisions; the existing memoir
GET's numeric parent revision alone is insufficient. If this exact handoff
service is not implemented, card opening remains disabled; a client GET that
checks only an ID and numeric revision is not safe. A stale source digest,
moved/deleted child, membership change or changed scope aborts the handoff and
requires a fresh search or reader refresh. No card click invokes the private
turn endpoint or a write endpoint.

One proposed route shape is
`GET /assistant/workspace/v1/threads/{thread_id}/requests/{turn_id}/memory-cards/{ordinal}?library_id=...`.
The ordinal is zero-based and indexes the ordered typed references stored on
that completed exchange; it is not a source ID. The server checks the completed
turn and current account/library membership, resolves only a stored `story` or
`memoir` reference, and obtains the full reader projection through the existing
authorized reader service. It recomputes the same source digest and checks
`PRAGMA data_version` before returning the reader projection. Missing, foreign,
or withdrawn references use the existing hidden-not-found behavior; changed
source digest or snapshot drift returns conflict. The client sends no revision
or digest, so it cannot widen the set of readable objects.

Android has protected reader APIs, but the current private assistant panel only
exposes an asset-open callback. `openSavedMemoryStory` also expects a summary in
the saved-story shelf; `openMemoryBook` expects a book summary in the book shelf.
The integration therefore needs a scope-guarded central handoff method that
fetches the exact current reference through the existing repository and opens
the existing reader state. Web has the protected memory endpoints, but its
private assistant result renderer presents media and saved-memory cards, while its
Web reader handoff for memoirs is not wired. Its assistant can display saved
memory cards, but still needs the explicit protected callback to open a reader.

Voice speaks only the short server-owned reply under the existing private
receipt rules. A separate optional
`GET /assistant/workspace/v1/saved-memory-speech-capabilities?library_id=...`
returns exactly `{version: 1, available: <boolean>}`. Missing or disabled speech
capability preserves cards while disabling their playback. The original card
probe and base capability shapes stay unchanged.

The speech route loads this completed turn's stored typed references, requires
the exchange and turn revisions to match, and rehydrates them through current
authorized readers before and after TTS. Stored digest fields are not numeric
reader revisions: the reader obtains its current numeric revision separately
and verifies it together with the stored source digest. Mixed/unknown references,
duplicates and malformed bindings are refused. One `data_version` guard covers
the whole multi-reference validation pass. The request-local memory-group
setting is propagated to all readers. Current feature, retention, membership,
thread and speech dependency checks are repeated before returning bytes.
TTS receives only the persisted generic reply, never card text or reader payload.
A failed post-synthesis check finalizes the receipt as failed
and returns no audio bytes. It does not read excerpts aloud
automatically. A fresh voice response can return to listen only after playback
completion. Recovered turns pause before speech, navigation, or listening. A
card's explicit open control ends the foreground voice progression before
entering the reader.

## Compatibility and staged acceptance

Keep current `/assistant/v1/*` request and response shapes untouched. Do not
return `kind: "memory_cards"`, `context.kind: "saved_memory"` or
`memory_cards` to a private-turn request without the exact `accepts` opt-in.
Default the runtime flag off. Existing strict v1 request bodies and response
objects remain exact when the opt-in is absent. Updated phone and Web decoders
accept the extension only when both the current feature probe and request opt-in are
true; unknown fields, card types, duplicate IDs, malformed revisions and
oversized excerpts fail closed.

Qualification proceeds in separate gates:

1. **Foundation:** existing focused security tests for literal lookup, current
   scope, withdrawal, source drift, child revision conflicts and bounded scan.
2. **Backend domain:** parser dispatch, exact card/context grammar, response
   budget at 240 KiB, oversized-title fail-closed behavior, zero writes,
   deterministic order, no source-caption matching, no provider/LLM calls and no
   outbound sockets.
3. **Private store / HTTP:** capability defaults false; old bodies preserve the
   exact v1 projection; only opted-in turns return fresh card references; card
   digests land in existing exchange references; GET recovery and thread/history
   reads expose only safe text and type/count placeholders; successful memory
   completion clears prior media thread context; same-ID replay with changed
   `accepts` follows stored status without recomputation or fresh cards.
4. **Kotlin and Web wire:** strict capability negotiation and result parsing;
   accepted/rejected malformed card contracts; exactly one turn POST; no retry
   or source navigation on recovery; no automatic speech from history; scope,
   generation, cancellation and reader-revision races; recovered-status notice
   separate from the unchanged stored reply.
5. **UI preview / simulator:** localized story/memoir cards, excerpt bounds,
   explicit handoff button, stale-reference message, narrow-screen and large-text
   behavior, keyboard/accessibility, and voice stop-before-reader behavior.
   Keep voice ordinal navigation unavailable. Test reader handoff against changed
   story evidence and changed memoir child evidence. Saved-memory reply speech
   remains disabled until references are source-validated before and after TTS.
6. **Runtime and delivery:** synthetic no-provider qualification first. The
   operator must separately enable the flag only after store health, memory
   retention health and API gates pass. Served Windows rollout, signing,
   installation and family/device acceptance each require their own evidence
   and authority; local tests do not establish them.
