# Protected text and reviewed-person search, first slice

The release preparation adds an explicit production search-v2 source allowance
of 64 MiB, with legacy discovery still at 16 MiB. Both share the original
admission pool and retain the existing row/index/response limits. Search v2 uses
a fixed five-second per-read deadline; legacy discovery retains two seconds.
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
- `Could you show photographs taken in September 2032 containing "海边"`:
  explicit English calendar month plus the exact quoted content.
- `昨天的照片呢`: replace the date/media conditions of the previous search,
  retaining its person and content conditions.

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
caption sorts before generated-caption-only matches. Within that tier, literal
token coverage, complete phrase boundaries and shorter matching source text
provide deterministic quality ordering, followed by descending asset ID for
ties. Eligibility remains NFKC/case-folded literal substring matching. These
quality signals do not expand the candidate set or establish family relevance.
This is an explicit policy baseline without semantic or visual ranking claims.
All hard filters remain conjunctive. The ranking policy participates in source
bindings so old contexts cannot silently adopt a different result order.

## Planning and turn-local reuse

The negotiated v2 path uses `assistant_query_plan.plan_query`, a pure local
planner supplied with the authorized entity resolver's exact ID groups and the
server clock. Its internal versioned plan contains only existing filters or a
clarification reason. It cannot read databases, open providers, infer IDs, change
access, or execute mutations. V1 parsing and wire contracts remain independent.
Quoted content remains opaque; unknown modifiers, unsupported negation and
conflicting dates/media require clarification. Today/yesterday, Monday-based
weeks, calendar months/years and explicit Chinese/English dates use the supplied
server civil date. No user-time-zone inference is introduced by this increment.
Resolved names that overlap a date or media keyword (for example, `May`) also
require clarification instead of silently adding that condition. Quoted text
must fit the existing 512-byte text filter limit; a longer literal asks for a
shorter phrase without sending an invalid plan to retrieval.

Within a synchronous v2 turn, `SearchRuntime.turn_scope` reuses derived facts and
lazy text normalization only for an identical current binding. Every operation
still authenticates, reads the bounded current source/index and recomputes its
binding before using those facts. An edit, membership change or changed private
graph therefore refuses an old context. The cache is cleared on success/error
and is never reused across turns. This reduces projection work, not SQL scans;
the existing per-read budgets remain, rather than one aggregate turn deadline.
Matching and ranking check the read deadline and any supplied cancellation
callback. Existing turn transports do not supply a disconnect cancellation
callback, so disconnect cancellation is not claimed. Built-in sorting remains
cooperative with checks before/after it and within Python preparation/output
loops; it is not forcibly preempted.

The legacy text embedding helper's placeholder-vector fallback is not connected
to this path. General paraphrase understanding, cross-language semantic recall
and text-to-image retrieval still need a qualified local planner/compatible real
query encoder and measured relevance. This source increment activates none of
those models. See [readiness and relevance](SEARCH_READINESS_AND_RELEVANCE.md)
for the separate reviewed data and evaluation gates.

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
