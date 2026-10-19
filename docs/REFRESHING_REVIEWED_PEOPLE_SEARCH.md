# Reviewed people and kinship with current uploads

`RefreshingPeopleIndex` is an explicit opt-in artifact with policy
`current-library-reviewed-people-v1`. It combines a frozen reviewed roster and
exact manual face assignments with current authorized asset scope, capture dates,
media kinds and previously approved location bounds. The existing
`RefreshingPlaceIndex` contract and legacy/static index serialization remain
unchanged. No database migration or client request field changes are required.

Every read checks membership before the provider or catalog. Within the same
bounded transaction it reads only the selected library's active assets, scoped
explicitly approved face IDs and the selected person IDs owned by that library.
Unreviewed detections are excluded from the read itself, preserving the shared
row budget for current assets, coordinates and text. Names
must match their current catalog display names exactly. Reviewed aliases remain
explicit operator assertions; a nickname, matching account name, automatic
cluster, embedding or newly assigned face cannot create a reviewed identity.

The identity digest freezes ID, name and library ownership. Current catalog
revision and update timestamp also participate in the full source binding.
Bookkeeping-only changes invalidate previous contexts but allow a fresh query
with unchanged reviewed matches. Name/ownership changes, removal or modification
of any approved face assignment refuse the review, including fresh queries,
until it is explicitly rebuilt. This conservative refusal affects the whole
configured index: use the previous places-only artifact as a separately approved
fallback if review needs to be suspended, rather than silently dropping a hard
person condition.

New uploads, date changes and GPS changes refresh scope and approved region
membership in memory without writing the artifact. New manual or automatic face
rows are excluded until separately reviewed. New assets remain available to the
independent current-caption/photo-memory text adapter, date and location search.
A changed source rejects old bindings. Existing shared row, index-byte, source,
response, time, cancellation and concurrency budgets apply.

Private kinship remains a separate selected-account, library and perspective
provider. It resolves only to this current reviewed roster and exact ID+label or
unique proper-name aliases. The index grants no graph access. A missing account
binding, ambiguous identity, changed/deleted graph or revoked membership cannot
be repaired by matching display names. See [private kinship](PRIVATE_KINSHIP_SEARCH.md).

## Explicit named-parent companions

An explicit fresh request such as `find photos of Sample Child with her dad`,
`找示例儿童和她爸爸一起的照片`, or mixed Chinese/English can combine the
named person with that person's reviewed parent. The private graph must resolve
one unambiguous proper-name anchor and the asserted mother/father path; the
result requires both people in the same reviewed photo. This path uses the named
person as its anchor, even when the graph has a different selected perspective.
It never guesses a person from gender, a login name, an automatic cluster or a
bare pronoun.

The routing exception preserves the original text and consumes only recognized
identity spans. Unknown names, missing/unreviewed parents, multiple possible
anchors and extra unresolved conditions still clarify. A named companion followed
by another unscoped relative also clarifies. Selector-only nicknames cannot become
proper-name anchors. Quoted phrases remain literal text, and ordinary continuation
requests such as `find videos of them` retain their prior people filters.
Negotiated search versions 2 and 3 use the same protected resolution; this adds
no request field, response field, model call or access grant.

## Deletion history during offline preparation

Both `inspect_reviewed_people_readiness.py` and
`prepare_reviewed_people_index.py` accept paired `--deletion-journal` and
`--deletion-namespace` options. Supply the existing native journal and namespace
when the selected primary has an original-deletion marker. Omitting the guard
for a bound primary, supplying only one option, or selecting a mismatched or
stale journal refuses preparation without producing output.

The shared source boundary retains the producer's read-only SQLite authorizer
and deadline. It checks the current primary against a captured external head
before and after reading, then rechecks the ledger after closing the primary.
The operator never initializes, binds, replays or upgrades deletion history.
Unbound generated fixtures still work without either option. These checks
establish preparation evidence; activating the resulting people index or
private graph remains a separate operation.

For a bound primary, append these options to **both passes** shown below and to
the readiness command at the end of this guide:

```text
  --deletion-journal /private/operator/existing-deletions.sqlite \
  --deletion-namespace EXISTING_NAMESPACE
```

A three-person fictional HTTP journey covers Chinese, English and mixed child,
mother and father queries, all-person matches, capture-date refinement, ordinal
opening, unreviewed detections, excluded graph accounts and withdrawn/suppressed
reviewed samples. This does not claim broad real-family face coverage. A
candidate includes only its exact reviewed manual assignments, so combined
person searches may correctly return no results when no reviewed photo contains
the requested combination.

## Offline preparation

`server/scripts/prepare_reviewed_people_index.py` accepts an explicit existing
refreshing-place artifact and an explicit private review. It never installs an
artifact, modifies a database, changes configuration, creates accounts or invokes
models. The place names, aliases and bounds come unchanged from the base artifact.
The review also binds that exact base's canonical digest, preventing a different
set of bounds from reusing the same review.

The review has all fields from the existing discovery producer plus
`base_index_digest`:

```json
{
  "base_index_digest": "SHA256_OF_CANONICAL_BASE_ASDICT",
  "library_id": "LIBRARY_ID",
  "source_digest": "CURRENT_SOURCE_SHA256_AFTER_INSPECTION",
  "indexed_ids": [],
  "enabled": ["people", "date", "locations", "media"],
  "people": [{"id":"301","label":"Fictional Person","aliases":[],"allow_zero":false}],
  "pinned_ids": [],
  "assignments": [{"id":"1","asset_id":"101","person_id":"301","source":"manual"}],
  "places": [],
  "regions": [],
  "source_fields": {}
}
```

The digest strings above are placeholders. Compute `base_index_digest` using
`discovery.digest(dataclasses.asdict(discovery_index.index(base_bytes, budget.rows)))`;
it is the canonical loaded artifact digest, not a filename or arbitrary JSON
formatting hash. Inspection requires it to match the explicitly supplied base.
Use a valid 64-digit placeholder source digest for initial inspection. Only
explicitly reviewed person and manual-face IDs go into the selection; the tool
does not enumerate candidates, collect every manual row or resolve duplicate
names on the operator's behalf. Empty `indexed_ids` is allowed only during
inspection, which replaces it with the current full active scope.

Run both passes against the intended source database on its owning host. Use
private direct local paths outside Git, with a private output parent (POSIX
0700, exclusive 0600 files; on Windows separately verify owner-only ACLs):

```text
python server/scripts/prepare_reviewed_people_index.py \
  --database /private/operator/library.sqlite --library LIBRARY_ID --revision 2 \
  --base-index /private/operator/approved-places.json \
  --review /private/operator/selected-people.json \
  --inspect --out /private/operator/inspection.json
```

The inspector emits an outer `requires_explicit_review` packet. It is deliberately
neither a loadable index nor an accepted review. Inspect the exact names,
assignments, scope, source and base digests, then save its **nested `review`
member** as a separate private review file. Removing the wrapper is not identity
approval; the operator must actually review those identities and assignments.
Run the same command without `--inspect`, using that file and a new output path.
A source change between passes refuses generation. Existing files are never
overwritten. The resulting artifact round-trips through the strict production
loader; no default configuration changes enable it.

The command prints only counts and an output hash. The private output contains
IDs and aliases, so keep it private. Native resource/latency checks and judged
household relevance remain separate gates before activation. API fixture tests
cover Chinese, English and mixed people/relative/text queries, all-person matches,
upload continuity, stale catalog/face/graph contexts and account isolation.

Video capture-date repairs require a separate operator proposal and review.
Neither people-index preparation command writes capture dates.

## Read-only identity readiness inspection

Before preparing a source-bound people index, an operator can classify a small,
explicit selection without adopting any person or changing the serving gates.
`server/scripts/inspect_reviewed_people_readiness.py` accepts only the selected
person IDs and manual face IDs supplied in a private file. It does not enumerate
candidate people or faces, install an artifact, or modify the database.

The strict selection shape is:

```json
{
  "schema": 1,
  "library_id": "LIBRARY_ID",
  "people": [{"id": "PERSON_ID", "label": "CURRENTLY_REVIEWED_LABEL"}],
  "assignments": [{"id": "FACE_ID", "asset_id": "ASSET_ID",
                   "person_id": "PERSON_ID", "source": "manual"}]
}
```

Each person and face ID must be explicit, unique, and within the supplied
library. A selected person is `exact_owned` only when the owning-library row and
current display label match the selection. An unowned person with at least one
active face in this library is reported as `legacy_visible_without_owner`; that
status explains directory visibility but does not grant search admission. A
foreign-owned, hidden, absent, or changed-label record is summarized as
`name_changed_or_unavailable` without returning its current foreign label or
library ID. For visible selected legacy records only, the report may include a
single `outside_or_unmapped_faces` boolean; it contains no face or library IDs.

Assignments are checked only by their selected face IDs and only through active
assets in the selected library. They are `manual_current`, `not_manual`, or
`unavailable`; out-of-library rows are never returned. Readiness is true only
when every selected person is exactly owned with the selected label, each has at
least one selected current manual assignment, and every selected assignment is
current. This is a preparation precondition only. It does not approve a person,
repair ownership, merge clusters, or create a loadable index.

Use a private selection file (POSIX mode 0600) and a private output directory
(POSIX mode 0700; output files are exclusive mode 0600). The output path must
not already exist:

```text
python server/scripts/inspect_reviewed_people_readiness.py \
  --database /private/operator/library.sqlite \
  --library LIBRARY_ID \
  --selection /private/operator/selected-people.json \
  --out /private/operator/people-readiness.json
```

The output is a private `requires_explicit_review` inspection packet, never an
index artifact. Standard output contains only counts and hashes.

## Bounded next review batch

`inspect_people_review_candidates.py` prepares an offline proposal for people
already present in an explicit `RefreshingPeopleIndex`. It verifies their
current library ownership, exact catalog labels and every frozen approved face
assignment before selecting more candidates. It does not discover a new person
or infer an identity from a name, face embedding or automatic detection.

The first batch uses only existing manual catalog associations on active assets
in the selected library. Photos already containing an approved assignment are
excluded. Each person has at most six new photos by default (configurable from
one to twelve), in descending asset-ID order; these are review candidates, not
ranked identity predictions. A bounded extra row indicates whether more photos
remain. Duplicate manual faces in one photo stay grouped for individual review;
an excessive group refuses the operation instead of silently omitting faces.

```text
python server/scripts/inspect_people_review_candidates.py \
  --database /private/operator/library.sqlite --library LIBRARY_ID \
  --reviewed-index /private/operator/approved-people.json \
  --photos-per-person 6 --out /private/operator/new-review-batch.json
```

For a primary bound to deletion history, supply the paired existing journal and
namespace arguments described above. The approved input and new output stay in
owner-private direct local storage on the data-owning host. The output contains
private face/asset identifiers and catalog associations, but no media, original
paths, embeddings, face coordinates, account information or access tokens.
Standard output contains only counts and an output digest.

Every candidate remains explicitly unconfirmed and ineligible for search. The
packet is not accepted as an index, a readiness selection or an identity review.
Use the protected owner face-review flow to view the face crop and parent photo;
do not use the legacy face routes. An explicit visual confirmation covers only
the selected face. Recheck current source and deletion history through the
existing two-pass index preparation workflow before proposing activation. This
export neither changes catalog assignments nor installs an expanded index.

## Owner visual confirmation

The [private visual review screen](PRIVATE_PEOPLE_VISUAL_REVIEW.md) records
explicit, revision-bound confirmations separately from catalog assignments.
It excludes existing approved faces and never activates the search index.
Owner permission, current frozen identity checks and the two-pass preparation
and activation boundaries still apply.
