# Android whole memoir draft review core

## Contract

`MemoryBookNarrativeStore` coordinates an explicitly requested, read-only book plan and an explicitly queued whole memoir draft. The editorial-context choice defaults to `false`; it is frozen into `MemoryNarrativeRequest` when queued. A retry reuses that exact request and mutation ID. The store never silently falls back to basic mode, resends on its own, or writes proposed narration into the book or child stories.

Before queueing, the saved plan must match the current book revision and the ordered child story IDs and revisions. Queueing also requires a within-limits plan, book edit permission, and whole-book draft permission. Viewer plans remain readable. Oversized plans retain the user's instructions and explain that a smaller scope is needed.

An uncertain transport failure keeps the exact request available for an explicit retry. A definite `409` or `422` clears that frozen request and invalidates the plan; the instructions and context choice remain, and the user must explicitly check a fresh plan before another queue attempt. A stale job response never exposes a proposal.

Every awaited result is fenced to the account/credential reference, library, generation, book ID and revision, ordered child revisions, and caller-provided reader epoch. A changed scope clears held state and drops late results. The public state contains no account identity or bearer credential. Ready output is mapped only to the exact flattened chapter IDs and labels in the frozen plan. Opaque source IDs are validated and discarded; only citation counts are exposed for an honest review. The proposal is not applied automatically.

`clear()` drops local instructions, plan, request, job, and proposal and cancels the current local continuation. `cancelKnownJob()` is an explicit server action for a known queued/running job; no job is cancelled automatically on scope changes. Authentication denial clears the coordinator state.

## Local evidence

The focused JVM test class `MemoryBookNarrativeStoreTest` uses a synthetic API and synthetic saved-book plan. It covers default-off request semantics, explicit plan and queue, multi-story chapter mapping, citation-ID removal, oversized/view-only refusal, exact uncertain retry, definite conflict/size rejection and explicit recheck, stale-job suppression, malformed chapter mapping, and late plan/job fencing. This is local synthetic evidence only; it does not establish provider, Windows, device, or family-data acceptance.

Run from `android/` with the repository's cached JDK/Gradle dependencies:

```sh
./gradlew --offline --no-daemon --max-workers=2 :live-core:test --tests '*MemoryBookNarrativeStoreTest'
```
