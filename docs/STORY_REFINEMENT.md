# Saved story refinement

When automatic refinement is explicitly enabled on the Windows runtime, saving a
story with narration also queues a separate proposal in the same transaction.
The saved original and its revision history remain unchanged. A ready proposal
appears next to the original; the user reviews it and explicitly saves any
wording they want to adopt. Adopting that proposal does not immediately queue
another refinement of the same save.

Existing stories have an explicit **Refine story** action. Repeating a request
for the same story revision recovers the same job. A changed revision or changed
source invalidates the old proposal. The operation requires current library
membership and permission to edit that story. There is no background scan or
mass rewrite of previously saved stories.

The drafting instructions preserve meaning, names, dates and the family's voice.
They ask for clear transcription and punctuation errors to be corrected only
when the supplied context supports the change. Uncertain facts remain in the
original wording and become review questions. Original recordings are not
modified. This is text refinement after transcription, not a claim that an
uncertain name can be recovered from text alone.

The application passes complete chapter narration for automatic refinement,
subject to the existing 6,000-byte per-chapter and 64-KiB input limits. Other
family evidence remains bounded and labeled separately as family text,
transcript, editorial wording, AI observation or metadata. Source authorization
and fingerprints are checked before and after model work.

## Runtime and jobs

`RuntimeConfiguration.memory_auto_refinement_enabled` defaults to false. It
requires the explicitly enabled household GGUF worker and shared host admission;
it does not discover another provider or use a cloud fallback. The saved-story
packet is `saved_story_narrative_v1`, which requires the updated worker. A worker
filename alone is not deployment evidence: the release must bind its exact
source and native launch recipe.

The API owns a background queue consumer. It uses short database transactions,
runs inference outside those transactions, and starts a separately owned model
process per job. Busy or maintenance admission defers the job. Cancellation,
shutdown, timeout and failure reconcile the owned process and exchange files.
A failed job remains visible; it is not silently retried. Polling in the browser
is read-only and stops on terminal states, navigation or logout. Reopening the
story recovers its current job.

Existing-story requests use `POST /memory-stories/{story_id}/refinement` with the
current `revision`, scoped to the selected library. Readback uses the existing
story and job endpoints. These are private, no-store responses. This source
contract does not itself establish a successful Windows generation or the
quality of a particular family's draft.
