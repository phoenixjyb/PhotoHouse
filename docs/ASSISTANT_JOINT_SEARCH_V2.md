# Protected text and reviewed-person search, first slice

The release preparation adds an explicit production search-v2 source allowance
of 64 MiB, with legacy discovery still at 16 MiB. Both share the original
admission pool and retain the existing row/deadline/index/response limits.
Superseded captions are excluded from the independent current-text fallback
before loading it. See [readiness and resource limits](SEARCH_READINESS_AND_RELEVANCE.md).

October 15 source increment, following the [search handoff](NEXT_SESSION_SEARCH_REDESIGN_2026-10-15.md).
This is a locally runnable API path, not a Windows deployment or a Web/phone
feature activation. New story creation remains deferred.

## Contract and compatibility

Send `X-PhotoHouse-Search-Version: 2` to the existing
`GET /assistant/v1/capabilities`, `POST /assistant/v1/turns` and
`POST /assistant/v1/speech` endpoints. Turns/capabilities then identify their
response as version 2. Other header values except absent/1 are refused.
The private workspace now negotiates the same search contract on capabilities,
turn creation, request recovery and reply speech. Its outer envelope remains
version 1. Existing clients send no new header and retain the version-1 shape.

The internal `SearchPlan(version=2)` accepts existing discovery hard filters
(`media`, `date`, reviewed `people` with `any`/`all`, `locations`, `tags`, and
literal `caption`) plus a separate literal `text` phrase. Date basis is still
`capture`; neither filenames nor receipt times become capture dates. The current
context shape is retained, with a separate source-bound opaque binding and
fingerprint. Downgrading a v2 context or using it in another session/library
requires refresh; context never grants access.

Examples using fictional reviewed names:

- `找包含“海边”的照片`: literal text in current captions or saved photo memories.
- `找示例儿童在海边玩的照片`: reviewed person AND literal 海边 AND image.
- `找示例儿童和示例成人一起的照片`: both reviewed identities on the same asset.
- `find photos containing "family at park"`: preserve the complete quoted phrase.
- `只看去年九月的`: refine the current query after source/context revalidation.

Quoted text is content, not an identity hint. Two-character Chinese and NFKC /
case-folded mixed-language matching work without an FTS tokenizer. Unquoted
scene parsing supports `在…玩/游玩` and a short explicit noun-scene list,
including `在海边的照片`; the scene remains a literal text condition. Arbitrary
unmatched details, unknown/ambiguous names, unconfigured personal kinship mappings and
unsupported negation require clarification; there is no model or cloud fallback.
This is a lexical baseline, not general semantic understanding.

An optional [private kinship provider](PRIVATE_KINSHIP_SEARCH.md) now adds
selected-account, library and explicit-perspective relationship resolution.
It joins only current reviewed identities; household graph data stays outside
source and a local draft does not enable the running service.

## Source adapters and lifecycle

`AssistantSearchReads` extends the protected discovery reader. It first validates
membership, current source/index scope and reviewed assignments with the original
policy. It then reads a separate request-time projection in that same SQLite
transaction and shared row/byte/time/concurrency budget:

| Source | Admission | Revision binding |
| --- | --- | --- |
| Current caption | Existing `current_caption` unique/edited precedence; superseded and ambiguous captions excluded | Current row digest, including text/edit flags |
| Saved photo memory | `access_stories.deleted=0`, matching child library AND current active parent mapping | ID, revision, current title/text, author, updated time |
| Person | Explicit reviewed names/aliases plus reviewed manual face assignments | Existing validated index and current scoped source digest |

The adapter includes only the original index's `indexed_ids` in text matches.
No media, database, embeddings or persistent full-text cache is copied. Reusing
`Stories.search`'s child/parent scope is deliberate; calling that separate paged
endpoint and intersecting results outside its transaction would break freshness
and ranking. Upload annotation/transcript sources and saved multi-image
stories/memoirs are deferred rather than conflated with photo notes.
Private assistant conversations/journals, revisions, withdrawn notes and raw
face clusters are never retrieval sources.

The original `RefreshingPlaceIndex` remains strictly date/locations/media. The
independent text adapter does not alter that artifact or make any person usable
without a reviewed roster/assignment. Static reviewed artifacts still reject
changed dependencies until rebuilt; refreshing location artifacts keep their
original scope/region refresh and independently bind current text. Source changes
invalidate a previous context even when its result order would stay unchanged.
New queries can use current photo-note text; withdrawn/deleted sources disappear.
Permission, source movement and asset state checks remain mandatory.

An oversized/slow projection fails closed through the shared budget. There is
no claim that scanning an actual household library fits that budget; bounded
private readiness/latency qualification precedes any activation. A rebuildable
incremental projection remains an option after measuring this baseline.

## Ordering and explanation

Assets are deduplicated before pagination. A matching photo memory or edited
caption sorts before generated-caption-only matches, then descending asset ID
provides deterministic ties. This is an explicit policy baseline without semantic
or visual ranking claims. All hard filters remain conjunctive.

Version-2 cards with text/person/date evidence add `match_reasons`; media-only
cards may omit it. Text reasons identify `photo_memory`,
`edited_caption` or `generated_caption`, `source_id` and current `revision`;
reviewed-person reasons identify the confirmed person ID, and capture-date reasons
identify the recorded day. No original prose is copied into context or the reply.
Clients label generated evidence as generated; no semantic confidence or truth
judgment is implied.

## Private workspace and client experience

Web and phone probe `/assistant/workspace/v1/capabilities` with the v2 header.
Only an explicit unsupported HTTP 400 permits a legacy capability retry. A
submitted turn is never retried or silently downgraded. A healthy negotiated
response retains the normal version-1 workspace fields and adds:

```json
{"search":{"version":2,"date_basis":"capture","perspective":null}}
```

An unavailable, stale or busy search source withholds turn admission while
leaving owned conversation history and preferences available. It does not force
the whole private workspace offline or silently retry a legacy search.

For a currently allowed private graph, `perspective` is instead a bounded object
with one `label`. This authenticated, library-scoped presentation does not expose
the graph, its relationships, aliases, allowlist or file location. The chosen
center appears before submission; results also identify their own perspective.

Header 2 is admitted only on workspace capabilities, `POST threads/{id}/turns`,
`GET threads/{id}/requests/{id}`, and `POST .../requests/{id}/speech`. Thread
management, preferences and saved-memory endpoints keep their existing contracts.
Negotiating saved-memory cards alongside search does not change media results
into saved-memory results: saved-memory cards remain their separate version-1
contract.

Every nested version-2 result adds `interpretation`: `date_basis: "capture"`,
`perspective`, and `people`, `tags`, `locations` arrays of `{id,label}` exactly
matching the selected filter IDs in order. Initial clarifications have null
filters and empty selections. Version-2 contexts carry `search_version: 2`;
labels and reasons are never stored in context. Cards carry at most 64 reasons.
Clients validate the whole result before presenting any of it, render labels as
plain text, show whether all or any people are required, and distinguish saved
photo memories, edited captions and AI-generated captions.

Durable summaries retain the original search version, filters and opaque source
binding, without interpretation labels or card evidence. Recovery rehydrates
those from current authorized sources using the original engine. A v2 client
can recover a legacy result as version 1; a legacy client cannot read or speak a
version-2 result. A fresh explicit search may leave a different-version context,
while refinements and ordinal opens require refresh rather than reinterpretation.
Recovered requests never replay an open effect or become fresh speech sources.
Source, membership and private graph changes still invalidate the result set;
reply synthesis checks those dependencies before and after generation.

This JSON extension requires the matching server for v2-created conversation
state. A rollback to older code must account for those threads; no production
workspace upgrade or rollback has been exercised by local fixtures.

## Checks and remaining gates

The generated joint-search suite is in `tools/check.py api`. Run it directly:

```sh
.venv/bin/python -m unittest discover -s server/tests/security -p 'test_assistant_joint_search.py'
```

Also run the conversational/HTTP/workspace suites and affected discovery/index
suites, source-ledger verification and the API profile. The new runtime module
is in the fixed API source allowlist. Record final observed results in the
[project status](PROJECT_STATUS.md); source checks do not qualify native Windows,
models, hosted CI, installed clients or family relevance.

Implementation `b7d605b` passes the 19-test focused suite and the complete local
API profile: 1,519 tests / 939 subchecks, including isolated source-package
imports, plus the generated no-listener demo. The private receipt binds the
same start/end commit and source input hash. Two earlier intentionally stopped
profiles remain incomplete records. Source-ledger verification, 119 local
documentation link targets and the affected discovery/index suites also passed.
No Web/Android profile or native/model/runtime/real-family acceptance is claimed.

The integrated source slice connects Web/phone/private workspace, visible
interpretations and evidence, and recovery. Its current validation is recorded in
the project status. Next are real-library identity/index admission and relevance
measurement, explicit video date-basis handling, and local understanding/ranking.
No real date backfill, reviewed-index preparation, deployment, signing or
publication is part of this source increment.
