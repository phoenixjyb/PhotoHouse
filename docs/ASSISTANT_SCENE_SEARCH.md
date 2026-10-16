# Gated conversation scene search

This backend increment connects the explicit [semantic image search
pilot](SEMANTIC_SEARCH_PILOT.md) to the private assistant workspace. It is a
separately negotiated, server-owned v4 turn, not a new default language planner.
The existing Web and Android clients continue to negotiate v1–v3 and reject
unsolicited v4 contexts or semantic scores. There is no scene-search UI or
live model activation in this increment.

## Scope and explicit opt-in

An ordinary v2 or v3 search first establishes the desired people, capture
dates, tags, locations, media and literal caption/photo-memory conditions.
A subsequent scene turn takes those conditions from the current server-owned
thread revision. It accepts visual wording separately; it never derives a
person, kinship relationship, date or access permission from that wording.
Changes to hard conditions require a complete ordinary search first.

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

## Remaining delivery gates

The generated HTTP/vector tests establish routing, hard-condition composition,
scope and artifact refusal, first-page recovery, and zero encoder calls on
replay. Client tests establish that existing v3 validators remain usable and
reject the unmodeled v4 extension. These are source checks with fictional
vectors and a mock encoder, not natural-scene relevance, native GPU or family
acceptance.

A client scene-search flow, meaningful English/Chinese/mixed natural-scene
pair qualification, complete immutable-vector coverage, native resource
qualification and explicit runtime activation remain separate work. The
[pair measurement guide](SEMANTIC_PAIR_QUALIFICATION.md) distinguishes the
existing generated shape canary from those relevance requirements.
