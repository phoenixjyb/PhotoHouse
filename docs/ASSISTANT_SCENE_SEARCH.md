# Gated conversation scene search

This feature connects the explicit [semantic image search
pilot](SEMANTIC_SEARCH_PILOT.md) to the private assistant workspace. It is a
separately negotiated, server-owned v4 turn, not a new default language planner.
Ordinary Web and Android search continues to negotiate v1–v3 and rejects
unsolicited v4 contexts or semantic scores. The Web client separately probes
scene availability and provides an explicit scene-search flow. Android has no
scene controls yet. The runtime switch remains default off; no live model
activation is included.

## Scope and explicit opt-in

An ordinary v2 or v3 search first establishes the desired people, capture
dates, tags, locations, media and literal caption/photo-memory conditions.
A subsequent scene turn takes those conditions from the current server-owned
thread revision. It accepts visual wording separately; it never derives a
person, kinship relationship, date or access permission from that wording.
Changes to hard conditions require a complete ordinary search first.
The immediately preceding completed turn at that revision must contain resolved
results. Retained results underneath a clarification do not authorize ignoring
its unresolved conditions. This admission check and lease acquisition share
one store transaction; rejected attempts leave the clarification intact.

Scene ranking supports photos only. A missing media condition becomes
`["image"]` as part of this explicit photo-search action. An existing video,
other or mixed-media condition is refused rather than narrowed silently.
Existing v3 `descriptive` caption conditions and explicit singleton asset
lookups are also refused: neither can be discarded or treated as an
unrestricted photo search. An empty hard-filter result invokes no encoder.

The application must be constructed with an explicit matching
`SemanticSearchRuntime`, a healthy private workspace and
`assistant_semantic_search_enabled=True`. The new switch defaults to false
and requires `assistant_enabled=True`. No bootstrap/configuration adapter,
model installation, vector migration or provider discovery is added.

An authenticated client can probe the separate optional endpoint:

```http
GET /assistant/workspace/v1/scene-search-capabilities?library_id=example-library
Authorization: Bearer <current-session-token>
```

```json
{"version":1,"available":true,"search_version":4,"media":["image"]}
```

Availability means the explicit runtime and workspace are configured; it does
not attest to useful model relevance or complete vector coverage for every
possible scope. The old capability response remains unchanged.

After an ordinary search at revision 1, a client explicitly submits:

```http
POST /assistant/workspace/v1/threads/<thread-uuid>/turns
Authorization: Bearer <current-session-token>
X-PhotoHouse-Search-Version: 4
Content-Type: application/json
```

```json
{
  "library_id":"example-library",
  "request_id":"<new-request-uuid>",
  "expected_revision":1,
  "text":"a child flying a kite beside a blue bridge",
  "accepts":["scene_search_v1"]
}
```

`text` is the exact visual description, bounded to 512 UTF-8 bytes with no
control characters. English, Chinese and mixed input use the same contract;
these source checks do not establish any encoder's language quality. The
client cannot supply filters, context, scores or ranking snapshots. Saved-memory
actions and speech are not combined with a scene turn. The stateless assistant
and speech endpoints reject v4.

## Result and recovery

The result has `version:4`, `kind:"results"`, `effect:null`, protected asset
cards with finite `semantic_score` values, the preserved hard `filters`, their
reviewed-label `interpretation`, and the pilot's `semantic` descriptor. Cosine
similarity ranks the complete eligible image cohort; it is not a probability,
identity/date fact or literal-caption match reason. There is no calibrated
relevance cutoff, so a low-scoring candidate can appear. Results explicitly
require review. The first page has at most 20 cards and the eligible cohort at
most 512 images; no later-page scene API is added here.

The source-bound v4 `context` retains the scene query, its original v2/v3
scope, and only the first page's scores alongside the usual visible IDs. The
private store validates this closed bounded structure and persists it with the
existing lease, revision, TTL and request-id rules. No embedding vector is
stored in the conversation or returned to clients. No schema migration is
needed. Server-owned scores are trusted store data, like the saved reply;
no HTTP endpoint accepts a caller-provided trusted ranking.

GET of the existing request resource, with the same v4 header, and an exact
POST retry both recover the saved order without encoding the query again.
Recovery rechecks the original authorized search scope, current source binding,
the pinned joint-space identity, all eligible vector manifests and file
checksums, and the current membership. It also checks the source again after
retrieval. A corrupt eligible vector outside the first page still refuses the
entire result. Foreign, hidden and hard-filtered-out vector files are never
read. These checks share a cooperative elapsed-time allowance across phases;
they do not promise interruption of a synchronous phase before its own timeout.

Source, scope, membership or identity changes withhold stale cards; there is
no lexical fallback. Recovered turns never replay open effects. Legacy clients
cannot recover a v4 result as ordinary results or refine away its semantic
state. They can still read non-actionable history and start a complete new
ordinary search; the latter deliberately leaves the old scene behind.

## Web scene-search flow

The private assistant probes the optional scene endpoint after ordinary workspace
capabilities. An unavailable/malformed/404 probe leaves ordinary search usable.
An older API may refuse unknown routes with 403: the client rechecks ordinary
capabilities before treating that as an unavailable feature. A true base denial
revokes the scoped state and drafts. Racing probes cannot restore older readiness.

Inside a selected conversation, **Find a scene within these conditions** shows
reviewed person/date/place/tag/literal-text conditions and the explicit photo
scope. It enables submission only after the current completed result has resolved
v2/v3/v4 conditions, with no pending request, descriptive caption condition,
video/mixed scope, recording or voice session. A clarification retaining older
cards is not ready. The user acknowledges that the shown conditions stay in
place and supplies a separate single-line scene description. The UTF-8 byte
counter enforces the server's 512-byte limit. Unsent ordinary and scene drafts
stay separate. In the assistant dialog, opening the scene editor temporarily hides
the ordinary composer; **Return to full search** restores it and keyboard focus.
Abandoning a scene request never places its visual wording in the
ordinary composer.

Only that action sends v4 and `accepts:["scene_search_v1"]`. Its validator
requires the original scope, exact query, next revision, closed scene context,
ordered finite bounded scores, matching card IDs, complete-coverage descriptor,
image media and null effects. Normal v1–v3 validation remains closed. Approximate
ranking and the original scene text appear separately from factual match
reasons; scores are not rendered as percentages. At most 20 candidates appear,
with narrowing guidance when more exist. Scene results expose no reply speech
or automatic viewer action. A complete new ordinary search exits scene mode.

A lost POST keeps its original UUID/revision/text and v4 recovery header, even
if capabilities subsequently change. Recovery is GET-only and never resends. Definitive HTTP 400/409 refusals clear
the local pending marker, keep the scene draft, withhold old cards and offer
history refresh or a complete new search; an unaccepted UUID cannot strand the
thread in endless recovery. Transport/invalid-response failures remain uncertain.
After a fresh successful scene probe, history GETs use the v4 reader, which can
also rehydrate earlier v1–v3 results under their original binding policy. A saved
scene read does not seed speech or effects. A failed history read clears old
cards before revalidation; no stale scene cards remain after artifact refusal.
Account/library/lock changes clear both drafts and prevent late completions.

The generated scene browser journey uses synthetic identities, two-dimensional
vectors and a mock encoder in a disposable SQLite fixture. It disables the
encoder after a lost response to exercise recovery and reopening, damages an
artifact to check stale-card concealment, and renders Chinese/English enlarged
phone and desktop layouts. These checks establish the UI/transport behavior;
they do not establish natural-scene model quality.

## Remaining delivery gates

The generated HTTP/vector tests establish routing, hard-condition composition,
scope and artifact refusal, first-page recovery, and zero encoder calls on
replay. Client tests establish that existing v3 validators remain usable and
reject the unmodeled v4 extension. These are source checks with fictional
vectors and a mock encoder, not natural-scene relevance, native GPU or family
acceptance.

Android scene-search controls, meaningful English/Chinese/mixed natural-scene
pair qualification, complete immutable-vector coverage, native resource
qualification and explicit runtime activation remain separate work. The
[pair measurement guide](SEMANTIC_PAIR_QUALIFICATION.md) distinguishes the
existing generated shape canary from those relevance requirements.
