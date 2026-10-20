# Selected source story acceptance contract

PH-P2 freezes the first product comparison for the
[household AI plan](LOCAL_AGENT_DEVELOPMENT_PLAN.md). The task is to turn a
small explicit selection into a source-grounded, reviewed and saved story.
Compare three paths from the same unsaved selection: manual writing, existing
saved-story drafting, and proposed selected-source preparation. This contract
contains no model result, benchmark or activation claim.

## Scope and capability

The PH-A4 preparation service accepts only the closed request in the
[draft contract](SELECTED_SOURCE_STORY_DRAFT_CONTRACT.md). It receives a
host-resolved immutable snapshot after admission and returns an ephemeral
`needs_review` proposal. Its adapter has one capability: prepare narration and
questions for that exact snapshot. It has no callable search, resource browsing,
shell, file, delegation, save, share or publication tool. A general agent loop
is not required. Story/source references are resolved and reauthorized by the
application, never by accepting model-authored IDs or metadata as authority.

Keep the PH-A4 limits of six chapters/24 media, selected per-chapter sources,
64 KiB validated bundle/output, immutable chapter titles, and explicit Save.
In particular, an empty source selection means no evidence, not all evidence.
Generated wording and source attribution remain distinct. Citation membership
checks prove eligible provenance pointers, not that the prose is factually true.

## Provider contract and source implementation

The legacy narrative v1/v2 inputs require a saved story/book with positive
revision. They remain unchanged. The source implementation in
[`memory_narrative.py`](../server/backend/app/access/memory_narrative.py) adds
the explicit v3 narrative input below; it does not invent a saved story,
fabricate a revision or insert a job to prepare an unsaved draft. The isolated
[source snapshot core](../server/backend/app/access/selected_story_snapshot.py)
now authorizes and freezes its input. An isolated
[operation owner](SELECTED_SOURCE_STORY_DRAFT_CONTRACT.md#implemented-internal-operation-owner)
adds bounded retries, expiry and shared admission. Explicit provider injection
now enables app/session lifecycle wiring. Prepare/cancel HTTP v1 has an
independent default-off opt-in. The optional Web editor and
[default-off local adapter](SELECTED_SOURCE_STORY_LOCAL.md) now have source
integration. Native work ownership, model quality/locality and deployment remain
separate qualification gates.

The new internal narrative **bundle version 3** is solely
for selected-source preparation. It retains the closed v1 content fields and
adds exactly `selection_revision`. Its target is an ephemeral operation:

```json
{"type":"draft","id":"44444444-4444-4444-8444-444444444444","revision":0}
```

`id` is a canonical host-issued operation UUID; `selection_revision` is the
host's current 64-character lowercase digest. The full exact keys are
`version`, `library_id`, `target`, `selection_revision`, `language`, `title`,
`theme`, `chapters`, `sources`, `recent_turns`, `instructions`. Set `version: 3`
and require `recent_turns: []`; it does not grant conversation-history access.
Retain the existing chapter field shape and extend each v3 source with exactly
one required `source_kind` field, alongside `id`, `kind`, `text`, `asset_id`,
`author`. Apply the stricter PH-A4 counts/byte limits. No `book_editorial` field
is accepted. For an existing-story
edit, keep its real story/base revision on the application request/snapshot;
the preparation target is still ephemeral, and it grants no write authority.

Normalize trusted source kinds only for the narrative input:
`family_note` and `family_edited_caption` map to `family`; `ai_caption` maps to
`ai`. Only these three `source_kind` values are accepted in v3, with that exact
kind mapping; no transcript/contribution source is added. Send the original
`source_kind` to the adapter as well, so edited captions do not lose their
derived-source status when normalized. Keep the exact byline, source digest
and eligible media mapping in the host snapshot/citations. Never infer
attribution back from the normalized kind or supply an author when the source
service has none. Legacy v1/v2 source shapes stay unchanged.

`validate_narrative` may accept this new closed input while its output stays
version 1. Existing v1/v2 validation remains unchanged. Companion/chat calls
reject draft bundles before provider I/O, and the default private bundle
validator requires an explicit draft opt-in. The v3 structured-output schema
keeps the existing ordered narrative result, with the stricter title limit.
The provider prompt preserves each original source kind and treats an edited
caption as derived visual wording even when its normalized kind is `family`.
No saved worker target, schema, lease, retry or feature flag is changed.

V3 accepts one to six nonblank-titled chapters, one to four unique media per
chapter with no overlap, at most 24 media, and at most twelve evidence IDs per
chapter. Sources are exactly the union of selected evidence, with nonblank text
and the 48 KiB aggregate text bound; empty evidence with no sources and blank
narration remains valid. The validator does not require a shared family note's
original asset to be selected: its actual eligibility is the host source
service's responsibility. An AI or family-edited caption must name an asset in
every chapter that references it; captions cannot cross disjoint chapter media
sets. Input validation is not membership authorization.

[The synthetic v3 suite](../server/tests/security/test_selected_story_narrative.py)
exercises narrative-only admission, legacy isolation, bilingual/mixed source
kinds, output rejection and mocked provider transport. It establishes no real
model quality or locality. The separate
[snapshot suite](../server/tests/security/test_selected_story_snapshot.py)
checks actual generated-library authorization and source revalidation. Neither
core adds a route, model selection or family-facing feature. The internal
operation owner has its own synthetic lifecycle checks and no live adapter.

## Frozen fictional evidence

Use a separate generated library for each comparison arm. All people, notes
and asset IDs below are fictional; no household records are read or required.
Chapter order is `chapter-1`, `chapter-2`, with media IDs `17000017` (image)
then `23000023` (video). The chapter titles remain author-owned.

| Case label | Canonical evidence ID | Media | Kind and exact text |
| --- | --- | --- | --- |
| `family-en-plant` | `family-10000000-0000-4000-8000-000000000001` | `17000017` | Family note, byline `Synthetic Aunt`: “We planted beans together.” |
| `caption-en-can` | `caption-9101` | `23000023` | AI caption, no byline: “A blue watering can beside the raised bed.” |
| `family-zh-plant` | `family-10000000-0000-4000-8000-000000000002` | `17000017` | Family note, byline `虚构阿姨`: “我们一起种了豆子。” |
| `caption-zh-can` | `caption-9102` | `23000023` | AI caption, no byline: “菜畦旁边有一个蓝色的浇水壶。” |
| `family-en-private` | `family-10000000-0000-4000-8000-000000000003` | `17000019`, not selected | Family note: “The train arrived at six.” Never expose or cite it in these tasks. |

The first four records have revision 1 where their source type exposes a
revision; compute their digests from the actual generated canonical records.
Do not hard-code a fake selection revision or treat a test label as an asset ID.
Create family-note IDs and caption integer IDs from this canonical mapping.
Use the generated source profile that exposes current note bylines; an arm
that cannot represent those choices is unsupported, not permission to invent
attribution. Media capture dates are unset. Per-language generated copies
contain only that case's eligible caption, since current preview selects one
active caption per item; mixed cases use the caption language specified below.
The snapshot includes only per-chapter selected records, not all five rows.
The expected media are exactly the first two IDs in order, with each chapter
citing only its selected source. Source text supports beans, joint planting,
the blue can and raised bed. It does not establish a date, place, weather,
identity, kinship, emotion or an act of watering; such details cannot be
presented as recorded facts merely because they sound plausible.

| Case | Input language / output | Selected evidence and task |
| --- | --- | --- |
| P2-EN-1 | English / English | English pair; create a brief two-chapter first story |
| P2-EN-2 | English / English | English pair; preserve the edited chapter titles “Planting beans” and “The blue can”; keep narration concise |
| P2-ZH-1 | Chinese / Chinese | Chinese pair; create a brief two-chapter first story |
| P2-ZH-2 | Chinese / Chinese | Chinese pair; preserve edited titles “一起种豆子” and “蓝色浇水壶”; keep narration concise |
| P2-MIX-1 | Mixed evidence / Chinese | English planting note and Chinese can caption; prepare Chinese narration with unchanged source identity/byline |
| P2-MIX-2 | Mixed evidence / English | Chinese planting note and English can caption; prepare English narration with unchanged source identity/byline |

Freeze those six tasks before model evaluation. Independent negative cases
include: unselected and wrong-chapter citation, empty evidence, adversarial
source instructions, unknown source kinds, deleted/changed source, membership
revocation, stale selection/review, lost preparation response, lost Save response,
same request with changed digest, oversize/duplicate/extra output fields, and
scope change. Retain the [PH-A4 negative oracles](SELECTED_SOURCE_STORY_DRAFT_CONTRACT.md#acceptance-cases-and-dependencies).

## Comparable start and finish

Start with selected media/evidence, ordinary editable chapter titles and no
saved story. End with the reviewed final story saved/reopened using current
source choices and the same intended media/chapters. Each arm uses a fresh
generated copy; one arm's saved draft is not free setup for another.

In the manual arm, the author writes from the selected evidence and explicitly
saves. In the existing-drafting arm, count the required initial explicit save,
job request/wait/recovery, review, adoption into an unsaved edit and final Save.
In the PH-A4 arm, count preparation, review/edits, final Save and reopen. Any
intermediate save in the existing arm is an author action, never an implicit
model effect. If a client cannot preserve the same source selection in an arm,
report that arm as unsupported rather than broadening its evidence.

Record complete user-visible action traces with a predeclared counting rule:
count deliberate submissions, confirmations, source/chapter changes and saves;
record active writing/review/edit time separately from provider/queue waiting.
Use the same participants and counterbalance arm order. Report all six paired
case results, per-language cohorts, failures and edits. This small set supports
a bounded household decision, not population estimates or reliable p95 claims.

## Predeclared adoption gate

Every objective authorization/source/revision/recovery oracle must pass.
Every case must finish with the intended media, chapter order and reviewed
source-cited wording. A fabricated recorded event/person/date in the initial
proposal is a factual-quality failure even if the reviewer catches it. Human
source review is required; JSON/schema validity alone cannot pass this gate.

Across the six tasks, PH-A4 must reduce median hands-on seconds by at least 20%
against manual writing, must not increase median deliberate actions, and must
not worsen median hands-on time in any language cohort. Against the existing
saved-story route, it must preserve correctness and not worsen median hands-on
time or actions; show explicitly whether removing the intermediate save helps.
The same actual client/runtime/model/source/fixture pins must be recorded for
each arm. An unsupported or unavailable attempt stays in completion counts;
do not compute a favorable completed-only speed result that hides failures.

The proposed warm-generation gate is at most 30 seconds median model waiting
and no completed work run exceeding the PH-A4 60-second work deadline. Queue
wait has a separate 20-second ceiling under a future negotiated profile.
Record every cold and warm time separately; cold failures remain availability
failures. A warm-only operating claim needs qualified residency/admission, not
an assumption that a prior request kept the model loaded. Show each value
rather than derive a p95 from six samples. Missing native memory/admission,
factual quality or family/client evidence leaves adoption unqualified.

This gate authorizes no installation or deployment. A no-win result retains
the manual/existing product paths. A useful single structured generation does
not by itself justify adding an agent framework.
