# Family-note voices in story and memoir context

## Reader and assistant behavior

An asset-family note's voluntary byline now reaches both its explicit original
source detail and the current story/memoir model context. Distinct notes retain
their own labels. AI captions and existing editorial narration do not inherit
a nearby family note's speaker. A blank label remains unattributed.

This is a user-supplied display label, not proof of an account identity,
relationship or event. Account IDs and the stored author account are not added
to model sources. The existing prompt rules still require supported wording,
distinguish transcripts from authored words, preserve disagreements and reserve
direct quotes for attributed verbatim family text. No semantic output verifier
or real model-quality acceptance is introduced here.

## Current scope and freshness

The source context builder resolves the same current note UUID, library, asset,
revision and undeleted state inside its caller's authorization transaction.
It validates the entire label against the existing 256-byte text/control rules.
Only notes already selected as current chapter evidence can supply a label;
another library's note cannot be selected merely by sharing an asset.

The complete label is included in the dependency fingerprint. Changes invalidate
queued/ready results and saved-edition reads, including an out-of-band label
change without an ordinary note revision increment. The worker freshly hydrates
labels before inference and rechecks them afterward; a concurrent change discards
the result. Queue controls contain no copied note words or speaker labels.

No response keys, schema, migration, generation permissions, retention policy,
audio handling, model adapter or feature defaults change. The existing model
source `author` field carries the display label. Previously prepared results
whose note fingerprint lacks the new attribution dependency become stale and
require a new explicit drafting request. C2 remains default-off.

## Local qualification

Five affected source suites passed 65 tests / 31 subtests: jobs, processing,
editorial context, editions and source service. The final worker privacy
assertion passed again separately after decoding its stored control JSON before
checking it. Overlapping reruns are not additional unique test coverage.

Synthetic cases verify two different note voices reaching the narrator, blank
labels, a same-revision label change hiding a ready result, a change during
inference discarding output, no copied words/labels in queue controls, wrong
library exclusion, and a saved edition withholding original material after its
label changes. The matching source/API, narrative, reference and editorial HTTP
qualification passed separately: seven affected source/API/narrative/reference/
migration suites, 63 tests / 44 subtests. A stale b1-only migration assertion
was corrected to verify the starting revision, complete schema and persisted
reference rows are unchanged after a refused downgrade. This is a test fix;
the migration transaction implementation is unchanged.

Provider doubles run outside the database transaction. These checks do not
establish coherent real narration, voice recognition, audible playback, a live
Windows deployment or household use. The implementation adds no source-erasure
ownership proof or physical deletion behavior.

## Source map

- Context and dependency fingerprint: [memory_jobs.py](../backend/app/access/memory_jobs.py)
- Explicit originals: [memory_book_edition_sources.py](../backend/app/access/memory_book_edition_sources.py)
- Narrative source contract and prompt rules: [memory_narrative.py](../backend/app/access/memory_narrative.py)
- Worker recheck: [memory_processing.py](../backend/app/access/memory_processing.py)
