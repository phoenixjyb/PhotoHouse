# Upload review and the original-deletion journal

## Failure boundary

A resumable completion commits the incoming asset, receipt and completed transfer
before attempting automatic approval. If the approval callback cannot open its
database context, the client may see a temporary error even though the file has
arrived. A later transfer GET can truthfully confirm receipt without assignment.

A collaboration database bound to an external original-deletion journal must not
be opened by omitting that journal. Reconstructing a path-only `ExistingDatabase`
in upload review or promotion apply loses the active runtime context and must
fail closed. Owner policy being enabled does not bypass that requirement.

## Repair contract

Carry the configured connection's journal and other connection settings into
review readers/writers and the promotion apply boundary. A missing or stale
journal must still refuse a bound primary. Preserve the existing operation,
plan digest, operator, audience, membership and policy revision checks. This
requires no schema migration and does not enable an inference provider.

Receipt, automatic/manual approval, library assignment and media preparation
remain separate outcomes. Do not turn transfer GET/history refresh into a write,
retry finalization blindly, disable the journal guard, or clear a completed
transfer in order to trigger approval again.

## Previously received items

The source repair restores correctly configured future review operations. Existing
incoming receipts require a fresh explicit owner review or separately approved,
bounded recovery. That recovery must recheck current operator/owner/member access,
destination, policy, immutable source identity and journal head before moving a
file, assigning it or releasing its existing tasks. Policy changes do not silently
approve older uploads; do not create duplicate originals or retry failed jobs.

## Qualification and delivery

Use generated media and a temporary journal-bound database to cover the automatic
resumable path and explicit review. Prove that missing/mismatched/stale journals
still reject access and preserve files, mappings and task state. Local source and
synthetic checks do not prove a Windows deployment or actual family acceptance.
A live API switch and recovery of existing receipts require their own authority.

### Local candidate evidence — October 17, 2026

- The new three-case synthetic HTTP suite passes for resumable automatic approval,
  explicit manual approval and library transfer with a bound journal. It also
  verifies a non-default connection timeout survives review, refused apply leaves
  source bytes/tasks/mappings/receipts unchanged, and missing/mismatched/stale
  journal context still fails closed.
- The eight affected existing suites passed 134 tests and 56 subtests: upload
  auto approval, upload review/retry, promotion/transfer, library organization,
  original-deletion integration and runtime adapter.
- The new suite is included in the ordinary API check profile. All fixtures use
  temporary databases and generated media. This candidate has not been deployed.
- The offline `scripts/provision_access.py` caller still supplies no journal;
  its default context remains unavailable on a bound database. It does not
  discover private runtime settings implicitly.

Run the new regression alone with the existing test environment:

```sh
PYTHONPATH=server/backend:server/tests/security python -m unittest \
  discover -s server/tests/security -p test_upload_original_deletion_journal.py
```

## Accept now, process later

A reviewed offline promotion may explicitly set `release_starters=False`. It
archives and assigns the selected upload as one transaction, leaves every task
state untouched, and persists `processing_deferred: true` in its receipt. The
ordinary default still releases existing held starters. An idempotent replay of
a deferred receipt never starts those jobs, even if the caller uses that default.
This option adds no HTTP surface, schema migration or automatic scheduler.

A later processing request must separately recheck the exact accepted receipt,
current owner/library access and held task identities before releasing only those
starters. Do not reset completed/failed tasks or reupload accepted source files.

### Explicit processing release

`upload_processing.release_deferred_upload_starters` accepts the original sealed
promotion envelope, its persisted deferred receipt, the configured database
factory and exact reviewed held-task rows. In one writer transaction it rechecks
current owner/operator and uploader membership, active assignment and cancellation
state. It releases only that unchanged selection and records a separate immutable
release receipt. It preserves the original promotion receipt, journal guard and
completed/failed results. Duplicate releases fail closed.

No HTTP or startup hook invokes this helper. A user must explicitly request the
processing operation; accepting or replaying an upload does not grant it. Expose
received, accepted-but-held, queued, processing, failed and ready as distinct states
in the following server/client status slice. Queue release alone is not proof
that a worker ran, a preview exists or an inference result is available.

## Processing worker follow-through

An explicit release has been qualified locally and with nine native Windows
synthetic cases, then applied once to the previously accepted batch. The separate
release receipt and unchanged promotion receipt were independently observed.
Existing CPU and face workers were started after preflight and task-definition
checks; the image-vector worker was already running. No API switch, migration or
scheduled-task definition change was part of that operation.

The portable caption lane is still a gap. The retained legacy caption launcher
has an older schema allowlist, claims the broad caption queue and requires other
writers to be fenced. Starting it alongside approved-upload workers would violate
that contract. A replacement must accept an exact released task selection, retain
the configured journal on every claim/write, recheck upload/library assignment,
preserve edited captions, and enforce provider/resource limits. Do not claim
captions are prepared just because their tasks were released.

A failed task is retained evidence. Verify derived files independently, distinguish
transient publication failures from damaged sources, and record any bounded repair
without silently resetting a finished or failed job.

### Windows CPU worker lifetime budget

The approved CPU lane used to construct `WindowsJob` for every hash/decode child.
That helper joins the calling process to the Job; closing its handle does not
remove the process from the nested Job chain. A native synthetic reproduction
succeeded 99 times and refused the 100th join with Windows error 50. Three child
launches per media task explain a batch failing after 33 successful tasks even
when its next original decodes normally. The old `filesystem_io` task label alone
cannot distinguish this resource-supervision failure from actual disk trouble.

The source fix binds one verified 1,536 MiB Job to an executing CPU worker and
checks that same PID-bound envelope before each child launch. It retains the
8 GiB available-memory floor, child resource monitor and process priority.
Preflight remains inert and a Windows child cannot launch without the envelope.
Closing/clearing the envelope happens on worker exit, including errors. Run the
worker once per process; this is not a reusable in-process service API.

Twenty scoped tests cover real generated-media processing plus shared budget,
missing/changed budget, PID mismatch, low memory, launch failure and cleanup.
Native repeated-child qualification and rollout remain separate gates. Existing
worker payloads are immutable; a source commit does not patch a running worker.
