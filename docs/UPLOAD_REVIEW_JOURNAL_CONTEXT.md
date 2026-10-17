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
