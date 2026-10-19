# Private visual people review

An owner can review a small batch of existing manual catalog suggestions for an
identity already present in the selected library's `RefreshingPeopleIndex`.
Catalog suggestions can be wrong. Each face requires a visible crop and an
explicit selection, followed by a review of the selected crops and a separate
save action. No faces start selected. The parent photo opens through the
existing protected asset flow.

Use **Wrong person** to choose a saved person through the existing revision-bound
single-face assignment flow. A correction clears the batch and selections.
Confirm the refreshed face separately; correcting an assignment does not itself
record a visual confirmation. Shared or unowned identities still require the
existing ownership review and cannot be adopted through this screen.

## Three distinct decisions

1. A **catalog assignment** associates one face with a saved person. Automatic
   detections and existing manual associations are not new visual confirmation.
2. A **visual confirmation** records that the current owner explicitly reviewed
   that exact face with its current person. This writes only an opaque marker to
   the existing private account audit. It changes no face, name, vector or media.
3. **Search activation** still requires an independently prepared, source-bound
   index and an authorized deployment. Confirmation neither rewrites the index
   nor grants membership, graph access or original-media permission.

Existing approved face IDs and current confirmations are excluded from the next
batch. The queue reads at most 120 candidate rows and returns at most 12 faces,
using a descending face-ID cursor rather than an unbounded count or offset.
An empty bounded page may still have a next cursor. Only manual associations on
active assets of the selected library are candidates; automatic clusters are
never promoted or shown as confirmed identities.

## Additive owner routes

| Method and path | Purpose |
| --- | --- |
| `GET /admin/people/{person_id}/review?library=...&before=...` | Read one bounded batch; `before` is optional. |
| `POST /admin/faces/{face_id}/review?library=...` | Record one explicitly selected visual confirmation. |
| `GET /admin/faces/{face_id}/review?library=...` | Read back whether the current owner has a current confirmation. |

All three require current `library.people.manage` before provider or metadata
access. They require an explicitly configured refreshing people index whose
roster, ownership, labels and exact frozen manual assignments still match the
database. Missing or stale inputs refuse the request rather than widening the
queue to a global face directory. Cookie POSTs retain same-origin CSRF checks.
Responses use the existing private no-store headers and expose no vectors,
bounding boxes, original paths or other-library identities.

The confirmation body contains exactly four strings: `person_id`, `revision`,
`person_revision`, and `review_revision`, all taken from the current card. The
opaque review HMAC binds the current owner account, membership revision, library,
face revision and person-name revision. A changed face, name, assignment event,
membership or ownership invalidates stale decisions. Queued face writers refuse
confirmation. Repeating an unchanged confirmed decision records no duplicate
audit marker, but clients must never retry an ambiguous write automatically.

Saving multiple selected faces uses explicit individual requests. If a request
fails or its outcome is unknown, earlier confirmations may have succeeded. The
screen clears the old batch and selections and requires fresh readback before
continuing. Logout, account/library changes, stale responses and lost permission
discard the review state. No private review draft is persisted in browser storage.

## Private operator export

`server/scripts/export_visual_people_review.py` reads the existing database,
current refreshing index, an explicit selection and the reviewing owner's account
ID. It does not create a session or act as that owner. The selected owner must
still have active owner membership; global operator privilege is insufficient
and is not required in addition to family ownership.

The input selection uses the existing readiness selection shape: `schema: 1`,
`library_id`, `people` containing exact `id`/`label` pairs, and `assignments`
containing exact `id`/`asset_id`/`person_id`/`source` tuples. Include the entire
existing reviewed roster and every currently approved assignment, then add one
to twelve explicit new manual face tuples. Dropping old tuples, adding identities,
guessing IDs or including a face without a current confirmation refuses export.

```sh
python server/scripts/export_visual_people_review.py \
  --database /private/operator/catalog.sqlite \
  --library selected-library \
  --reviewed-index /private/operator/reviewed-index.json \
  --selection /private/operator/selected-faces.json \
  --reviewer-account 11111111-1111-4111-8111-111111111111 \
  --out /private/operator/new-review-export.json
```

These are fictional paths and identifiers. Bound deletion history requires both
`--deletion-journal` and `--deletion-namespace`; omitting a required binding is
refused. Inputs and output must satisfy the existing private-storage checks;
output must be a new file inside a private directory.

The export contains a base-index digest, the nested exact `selection`, and current
opaque audit evidence for each new tuple. Its status is
`requires_source_bound_preparation`. Standard output contains only counts,
digests and byte size. Keep the export private: it contains identity labels and
media identifiers. The nested selection remains input for the existing readiness
and source-bound preparation process, followed by independent review and an
authorized activation. The export itself cannot be served as an index.

## Qualification and delivery

Generated HTTP checks verify scope, permissions, current revisions, CSRF,
bounded cursors, receipt readback and that face assignments and the serving index
do not change. Browser journeys use fictional transport and generated image
fixtures; inspect Chinese/English desktop and phone renders separately.

The bilingual search journey also checks that an ambiguous request such as
`再早一点`, `a bit earlier`, or mixed `earlier一点` asks for a concrete date while
preserving all existing filters and bound results. An explicit year answer
changes only the date condition. This does not guess a time range or weaken a
person, text or media constraint.

Synthetic local latency measurements are development baselines, not Windows
service, network, model or physical Android measurements. Production schema,
models, graph permissions, uploads and tasks remain unchanged until a separately
authorized rollout. This feature needs no schema migration.
