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
