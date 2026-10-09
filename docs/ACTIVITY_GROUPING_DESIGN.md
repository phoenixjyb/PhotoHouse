# Activity grouping from family stories and visual similarity

**Status:** design proposal; no visual similarity route or provider activation is
claimed here.

## Goal and boundary

Offer a family an explicit, reviewable list of visually similar **photo**
candidates while they assemble a grouped story. A family-authored story already
selected by the user is the context anchor. Visual similarity may help find
nearby photos; it does not prove that photos depict the same activity.

Keep the current same-capture-day lookup as its own discovery method. A matching
recorded day is a date fact, not an activity fact. Visual results must not be
merged into that result set or inherit its `same_recorded_capture_day` reason.
Neither route may infer an event date from a filename or upload time, identify a
person, label an activity, or add media without an explicit family action.

The proposal does not introduce a model call. Existing originals and family
story text remain separate from derived vectors and candidate suggestions. A
candidate is temporary review material. It joins a draft only after the user
presses the existing add action; the ordinary preview reloads current evidence,
and saving remains an explicit existing story action.

## What exists today

- [`story_workspace.py`](../server/backend/app/access/story_workspace.py)
  implements `POST /story-workspace/related-media`. It authorizes `library.read`,
  checks every seed is an active image or video mapped to the requested
  library, and looks up active photos/videos whose recorded `assets.taken_at`
  day matches. It bounds a request to 24 seeds, 80 inspected candidate rows,
  20 returned items and 256 KiB. It reads no pixels, embeddings, captions or
  story prose, and makes no writes or inference.
- The Web and phone pickers are explicit: opening them does not fetch
  candidates, and each result requires an add action. The response marks
  `needs_review`; selected-media changes reload the ordinary preview. See
  [`STORY_RELATED_MEDIA_V1.md`](../server/docs/security/STORY_RELATED_MEDIA_V1.md).
- [`access_stories`](../server/backend/app/access/story_schema.py) stores
  family-authored notes attached to one asset at a time, with author, library,
  current revision and revision history. It is not a multi-asset activity
  grouping. Story preview reads current notes for selected assets and keeps
  them distinct from AI captions. [`stories.py`](../server/backend/app/access/stories.py)
  provides literal, bounded text search; it is not semantic vector retrieval.
- [`Embedding`](../server/backend/app/db.py) records `asset_id`, modality,
  model, dimension, storage path, vector checksum, device and optional model
  version. It has no library key and no preprocessing or checkpoint identity
  column. The asset-to-library map supplies current membership and must be
  joined for every candidate query.
- [`run_approved_image_embed_worker.py`](../server/scripts/run_approved_image_embed_worker.py)
  creates image vectors in a bounded child using an explicit local checkpoint
  and records a model name/version and vector checksum. It does not establish
  that current library assets have vectors or that old rows match a current
  preprocessing identity. [`run_approved_video_embed_worker.py`](../server/scripts/run_approved_video_embed_worker.py)
  writes video vectors to derived files without a comparable per-vector
  metadata row; video is therefore outside the initial visual lookup.
- [`vector_index.py`](../server/backend/app/vector_index.py) contains a global
  asset-ID index and loaders that read all image embedding rows. Searching it
  and filtering the top results afterward is not acceptable for a protected
  library query: out-of-library vectors can crowd out eligible candidates, and
  identifiers are retrieved before scope is enforced.
- The model catalog requires vector-space identity to include model and
  preprocessing identity; matching dimensions alone is insufficient. The
  example image, video and text bindings are disabled. `model_binding.py`
  has no visual-candidate projection target. Text embeddings remain a legacy
  path, and strict image-worker inference explicitly does not provide text
  embeddings. No live database coverage, private Windows installation, or
  runtime readiness is established by this source review.

## Candidate contract if the feature is built

Use a new visual-candidate route or a separately versioned request mode. Do
not change the existing same-day route's meaning or response reason. The new
path stays default-off and is unavailable unless a later, explicit feature
projection and private Windows runtime configuration provide a qualified
image-vector identity. This design does not add that projection or enable a
provider.

For every lookup:

1. Require the existing `library.read` authorization in the request's current
   transaction. Resolve every selected seed as active and mapped to that
   library before reading candidate records.
2. Limit visual seeds and returned candidates to 24 and 20, respectively.
   Restrict the initial modality to images. A video seed may remain in the
   manual story selection, but it cannot be a visual query seed or a visual
   candidate in this version.
3. Build the allowed candidate ID set from active image assets joined to
   `access_asset_libraries` for the requested library. Exclude seeds and
   require an embedding for each candidate. Apply that membership filter
   before any vector scoring or top-K operation. Never query the global index
   and post-filter it.
4. Require one exact vector-space identity across all query and candidate
   vectors. Bind it to model artifact/checkpoint digest, preprocessing digest,
   vector-space ID, dimension, normalization and model version. Validate vector
   length, finite values, nonzero norm and checksum before scoring. Missing,
   unversioned, corrupt or mixed-space vectors fail closed for the lookup; do
   not mix them, infer compatibility from dimension, or fall back to a stub,
   text model or live inference request.
5. Rank only the preauthorized candidate set by cosine similarity to the
   selected photo seeds. For multiple seeds, use each candidate's best
   individual seed match rather than averaging unrelated selected photos into
   one synthetic event vector. Exclude seed IDs and make tie order stable.
6. Return ordinary protected asset fields and a review marker such as
   `match_reason: "visual_similarity"`, `needs_review: true`, and the matching
   selected seed ID. Do not return vectors, filesystem paths, model identity,
   family text or a semantic/activity label. The existing preview can load
   current family evidence after the user adds a candidate.
7. Keep originals and family-authored text unchanged. Do not create an
   accepted group, save a title, change a story, or enqueue derived work as a
   side effect of lookup.

Candidate work needs a strict resource ceiling as well as a response ceiling.
The existing 24-seed and 20-result limits are a useful UI ceiling, not a
complete search-cost bound: the global index cannot safely supply scoped top-K.
Until a library-partitioned retrieval plan is qualified, refuse a lookup whose
authorized, compatible candidate cohort exceeds a fixed scoring budget. Do not
silently truncate an ID-ordered prefix and describe its results as the nearest
matches in the whole library. Establish the production scoring budget from
offline synthetic performance and Windows resource evidence before exposing a
complete-library result claim.

## Smallest meaningful next implementation

Implement only the pure, offline ranker in
[`visual_candidates.py`](../server/backend/app/access/visual_candidates.py)
and synthetic contract tests. Its immutable input consists of a bounded
authorization snapshot, explicit seed and candidate IDs, complete seed and
candidate vector records, and one expected vector-space identity. The snapshot
is a caller assertion, not an authorization mechanism: a later route must build
it from active photo IDs after its current library authorization and candidate
filter. The ranker refuses foreign or incomplete ID sets before inspecting or
scoring vectors.

The source-only contract fixes the limits at 24 seeds, 512 candidates, 4,096
dimensions and 20 results. Every vector must match all of the expected artifact
SHA-256, preprocessing SHA-256, vector-space ID, model version, dimension and
`unit_l2` normalization fields. Every record also carries a checksum over a
dimension-prefixed, big-endian IEEE-754 float32 representation; nonfinite,
zero, non-unit, wrong-shape and checksum-mismatched vectors refuse the entire
cohort. This is a canonical component checksum, distinct from the existing
`.npy` container/file hash: a future loader must qualify the stored file hash
before decoding, then separately verify this checksum over the decoded
float32 components. The accepted unit-norm tolerance is only for validating
stored values; scoring normalizes the validated canonical components first so
small norm differences cannot change cosine ranking. If one asset appears in
both the seed and candidate cohorts, both records must have the same exact
identity and component checksum. The authorization snapshot accepts only
bounded built-in finite containers (`set`, `frozenset`, `list` or `tuple`),
and rejects lazy or custom iterables without consuming them. Ranking uses
cosine similarity to each seed independently, keeps the best seed for each
candidate, breaks ties deterministically, and excludes all seed IDs. The
result contains IDs only, not a score or an activity label.

This helper must not open files, a database, a model, a network connection or a
private provider. A missing or mixed identity returns one fixed unavailable
result, never partial rankings. These source-level semantics neither read
actual embedding rows nor prove that an installed vector artifact matches the
expected identity.

The ranker is meaningful because it settles the scoring and refusal semantics
with testable inputs while leaving the current route untouched. It does **not**
provide an online feature, show real candidate coverage, validate actual
artifact provenance, or establish Windows capacity. A later integration slice
must separately add private identity propagation and library-filtered vector
loading, then prove no-write and cross-library behavior against synthetic
SQLite fixtures before any owner considers enabling the feature.

Suggested focused tests for that source-only slice:

- exact cosine order, deterministic tie order, seed exclusion and best-per-seed
  ranking using synthetic vectors;
- rejection of an unauthorized ID supplied as a seed or candidate, and proof
  that a high-scoring foreign-library vector cannot change the eligible top-K;
- refusal for missing/mismatched space identity, mixed versions, wrong
  dimension, non-finite values, zero vectors, checksum mismatch and candidate
  cohort over budget;
- bounded output, fixed unavailable response, ID-only results, and no storage,
  provider, model or network calls. The ranker accepts only a caller-declared
  photo cohort and cannot itself prove the media MIME type;
- a no-write snapshot around an authorized synthetic database query when route
  integration is later proposed.

## Explicitly deferred

This design does not call an LLM to interpret family prose. A future
story-text-plus-image ranking path needs an independently qualified text
embedding implementation in the same declared vector space; current legacy
text embedding and title-generation integrations do not satisfy that contract.
Video candidates need persisted model, preprocessing and frame-sampling
identity before they can share image ranking. Any activity name, date, person
identity or saved grouping remains a family decision based on their review,
not a similarity-score conclusion.
