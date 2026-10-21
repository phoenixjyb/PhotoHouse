# Explicit local semantic search pilot

The separately gated [conversation scene-search Web flow and backend](ASSISTANT_SCENE_SEARCH.md)
now reuses this runtime for server-owned workspace v4 turns and model-free
first-page recovery. Existing clients and the default application remain on
their original search behavior; client integration and runtime activation are
still separate gates.

This source-only pilot provides a separate protected text-to-image API. The
ordinary assistant v1/v2 continues to use its existing literal text contract.
No local model, service, image-vector preparation, schema migration, private
configuration, Web control or Android feature is activated by importing or
deploying these source files. The [local provider implementation](LOCAL_SEMANTIC_TEXT_PROVIDER.md)
has an explicit probe/serve path; its native installation, qualification and
measured relevance remain separate delivery gates.

## Search behavior

`POST /libraries/{library_id}/semantic-search/v1/query` is mounted only when
`create_app` receives a matching `SemanticSearchRuntime`. Its access/discovery
objects must be the same objects explicitly supplied to the application.
The default application has no semantic route. The reviewed HTTP boundary
binds the opt-in method, path template and endpoint identity.

Required JSON fields are `query` (a scene description, at most 512 UTF-8 bytes)
and `filters` (the existing structured search-v2 hard filters). Optional fields
are `binding`, `fingerprint`, `page` and `page_size` (1–20, default 20).
Authentication, approved library membership and cookie CSRF rules apply before
the request body, metadata, vector files or encoder can be read. Query-string
credentials are refused. Bodies, responses, database reads, vector dimensions,
files and concurrency remain bounded.

For example, a synthetic caller may submit:

```json
{
  "query": "children flying a kite",
  "filters": {
    "people": {"ids": ["301", "302"], "match": "all"},
    "date": {"from": "2032-09-01", "to": "2032-09-30"}
  },
  "page_size": 10
}
```

The API does not infer identities or date filters from `query`. The query is
the semantic scene description; callers must supply intended hard conditions
separately. Natural-language planning and client UI integration remain
separate work. The gated conversation backend reuses server-owned hard
conditions instead. This distinction prevents an unqualified model from silently
replacing a reviewed person or date restriction.

The pilot searches images only. An omitted media filter becomes `['image']`
and is included in the response's `filters`; an explicit video/other/mixed
media request is invalid. People, dates, locations, tags and optional literal
`text` remain joint hard constraints using the existing authorized discovery
implementation. Ranking never expands the eligible set or relaxes a condition.
Unknown capture dates stay excluded by a date constraint.

All eligible images are ranked before pagination. More than 512 eligible
images, a missing/stale/duplicate vector, an invalid schema, a changed source
hash, a malformed vector or an encoder failure refuses the entire search.
No eligible image is silently skipped to produce an apparently complete top-k.
An empty hard-filter result returns no items without invoking the encoder.
Foreign-library, hidden and hard-filtered-out vector files are never read.

Results include the existing protected asset cards plus `semantic_score` and
an explicit `semantic` descriptor (`text_to_image`, `cosine`, candidate count,
complete eligible coverage, `needs_review: true`). Scores express relative
cosine similarity, not probability, identity recognition or factual certainty.
There is no inferred relevance threshold: low-scoring images can still appear.
No vector components, original prose, local paths or model qualification
documents are returned. Existing text/person/date match reasons retain their
original meanings; a semantic score is not presented as literal text evidence.

The opaque binding covers the exact query, reviewed metadata, current image
source hashes, immutable vector manifests and joint-space configuration.
Page sizes and filters participate in the fingerprint. Membership and source
binding are rechecked in a fresh transaction after encoding, so concurrent
revocation or a source edit withholds stale cards. After initial authorization,
retrieval/source rechecks and provider work share one elapsed-time allowance;
HTTP admission and body receipt have separate bounds. Checks are
cooperative; a synchronous provider socket operation can wait for its phase
timeout before the next deadline/cancellation check. No provider cancellation
acknowledgement is claimed.

## Explicit encoder qualification

`JointSpaceBinding` records exact image and text `VectorSpaceIdentity` values
and a SHA-256 digest of an operator-reviewed qualification record. Dimensions,
normalization and the named joint space must agree. Artifact/preprocessing
hashes and model versions may differ between the two modalities, but are pinned
separately. Equal dimensions alone do not authorize comparison. This typed
attestation records an operator decision; constructing it does not independently
prove that a model pair has been measured or has useful multilingual recall.

The image side reuses the existing immutable `image_vector_artifacts` schema
and bounded NPY loader. No legacy in-memory/FAISS index or placeholder-vector
helper is consulted. Preparing compatible artifacts is an explicit separate
operation, not a side effect of search.

`LocalSemanticEncoder` accepts only an explicit loopback HTTP URL ending in
`/v1/encode-text`, with an explicit port. It disables environment proxies and
redirects. The standalone local provider requires a separately configured
`bearer_token`, sent only as an Authorization header. Its JSON request has exactly:

```json
{"version": 1, "binding_sha256": "<joint binding digest>", "query": "<exact query>"}
```

The local service must return exactly `version`, `binding_sha256`,
`query_sha256` (SHA-256 of the exact query's UTF-8 bytes), `vector` and
`checksum_sha256`. The checksum uses the existing canonical float32 vector
checksum. The vector must be finite, unit L2, dimensionally correct and belong
to the pinned text identity. Responses require strict UTF-8 JSON with unique
keys, no nonfinite numbers, no compression, a 64 KiB body limit and at most a
two-second configured timeout. Raw query text is sent only to this explicitly
selected local service, without account IDs, graph/roster contents, captions,
memories, asset IDs or library tokens. There is no provider discovery, fallback,
cross-request vector cache or model download.

## Qualification evidence and remaining gates

Generated tests exercise nonliteral vector ranking, hard-filter composition,
scope and body admission, complete coverage refusal, source/identity/checksum
validation, query-bound paging, aggregate deadlines, cancellation, concurrent
revocation/source edits and the unchanged closed default application. These
tests use synthetic vectors and HTTP mock transport. They establish source
behavior, not model quality, GPU operation or family acceptance.

Before a live pilot: install and qualify the local encoder service, qualify its
exact text/image pair and language coverage, prepare compatible immutable image
artifacts, verify the native runtime and resource bounds, and measure relevance
against reviewed examples. Runtime configuration/client wiring and deployment
remain separate explicit work. No family account or face binding is inferred
or activated by this pilot.

The optional [reviewed scene-query provider](REVIEWED_SCENE_PROVIDER.md) composes
an exact private mapping with an existing qualified encoder under a distinct
binding. It preserves original request identity and rejects unlisted inputs.
Its source support does not change these default-off or qualification gates.

The optional [provider-only readiness check](SEMANTIC_PROVIDER_READINESS.md) tests
an already running direct/library 768-dimensional responder with one synthetic
request and an externally pinned private configuration. It leaves the provider
protocol and model recipes unchanged. This does not replace native process
ownership, lifecycle/recovery, index refresh/retirement, relevance or activation
authority.
