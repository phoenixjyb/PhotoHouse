# API/CPU overlay qualification — October 18, 2026

## Scope and runtime reconciliation

The upload-journal repair and fixed installed CPU worker remain delivery
candidates. The general API repair was not activated by the earlier one-time
[caption operation](CAPTION_PROVIDER_RECOVERY_2026-10-18.md).

Before staging the new offline candidate, preservation checks detected an API
action change. Read-only reconciliation confirmed the current base and invitation
overlay plus a separate discovery-latency overlay at `6d5063c`. Non-action task
settings and the other checked tasks/file pins matched. The first transport
attempt stopped before creating its Windows stage. Its claim and logs remain.
The same approved immutable offline package was then staged, with preservation
checks updated to include the observed current API. No running API was replaced.

A future upload-journal candidate must preserve that discovery change as well as
the invitation overlay. A generic source ZIP or the previous private base is not
a drop-in replacement for the current live application.

## Native R3 result

The fixed 262-file offline package passed its extraction/hash checks. It contains
source, test code and the documented half-second generated MP4 pattern; it
contains no family media, production database, private runtime configuration,
model weights or credentials.

The explicit Windows Job-proof startup canary passed before fixture databases
were opened: flags `0x2208`, 2 GiB memory and eight processes, with an 8 GiB
available-RAM floor. API and CPU fixture execution are serial, capped at five
minutes and two minutes respectively.

The API child ran 129 synthetic tests in 49.7 seconds; 20 failed. All failures
came from the resumable-upload cohort. Its shared `UploadTests` fixture patched
`socket.socket.bind` and `connect` unconditionally. This masked the outer
socket guard, preventing Windows asyncio from constructing its internal
`socketpair`. The failure occurred while creating the ASGI test portal and does
not establish a failure in the production upload handler.

Execution stopped on that failed cohort. The separate three-test `a0` cohort
and CPU phase were not reached. The package is **not natively qualified** for an
API or installed-worker rollout. Earlier CPU qualification and caption evidence
retain their original scopes; they cannot be relabelled as this run's success.

## Fixture repair and durable gate

Use the existing `install_no_external_sockets()` fixture guard for upload tests,
while retaining subprocess and shell denial. Only the creating thread's
stdlib-internal, temporary loopback socketpair is allowed; ordinary loopback,
remote endpoints and application listeners remain denied.

A focused regression forces CPython's Windows socketpair fallback on every host,
then exercises an upload request through the actual shared fixture. It must also
prove ordinary network access and subprocess use remain blocked. Include that
regression in both API and Windows CPU profiles, and the resumable cohort in the
API profile, so a Linux-only green suite cannot conceal this Windows fixture
failure again.

Post-failure readback matched nine task definitions/states and eleven file pins,
including the observed newer API and both OTA pointers. An independent trusted
HTTPS request returned 200 for the Web UI; this is anonymous availability, not
a signed-in family test.

The corrected source passed 65 upload/resumable/retry/history tests and 16
subtests locally. The updated Windows CPU check profile passed 96 tests and 66
subtests on the source Mac, and 13 check-profile tests passed. These are portable
checks, not a new native Windows qualification. Its forced-fallback regression
now exercises a successful
synthetic upload and receipt, not merely an unavailable-service response.
The corrected test source and next candidate require their own native checks. Preserve
the consumed native claim, failure log and old package. Do not modify the
already-staged files or rerun the failed operation. A newly fixed Windows package
needs a fresh private stage and operation authority. No service switch, queue
reset, migration, APK publication or model activation is part of this repair.

## Native R4 result and Windows upload contention

The corrected 263-file R4 package was approved after all five CI jobs succeeded
at review head `9b9dfae`. Its transferred hashes and explicit Job-proof startup
canary passed. The native API child ran all 130 tests in 59.7 seconds: 129 passed,
and one failed. The previously failing socketpair cohort now runs successfully.

The remaining failure is `test_same_transfer_busy_lock_refuses_without_waiting`:
a concurrent request to the same synthetic transfer returned 503 instead of
retryable 429. Windows CRT nonblocking byte-range locking reports `EACCES` for a
locking violation; the existing implementation catches only `BlockingIOError`.
See [Microsoft's `_locking` return values](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/locking?view=msvc-170).
The repair must classify contention only at lock acquisition, preserve unrelated
storage/permission failures, and always close the descriptor. Exceptions raised
inside the protected upload operation must not be relabelled as contention.

R4 stopped before the separate three-test `a0` cohort and CPU phase. It is **not
natively qualified**. Its operation claim, package and failure log are retained;
do not replay it or overwrite its staged files. Post-failure readback matched all
nine task bindings and eleven file pins, including both OTA pointers. A separate
trusted HTTPS request returned 200 for the Web UI. No production database,
family media, model, service, task or OTA change occurred.

A subsequent candidate must preserve the current invitation and discovery
optimizations and add the Windows contention repair to the three journal files.
Its complete extracted artifact, regression tests and native qualification are
separate gates before a live API or CPU-worker switch.

The source repair normalizes Windows CRT lock contention at acquisition only,
keeps other I/O errors intact, and closes the descriptor even if unlock fails.
Portable regressions cover the CRT busy errno, unrelated storage failures,
protected-body error propagation, descriptor closure and subsequent retry. The
unchanged real same-transfer HTTP test is now also in the Windows CPU CI profile,
so this platform-specific contract is checked before another native package trial.

Portable checks after the lock repair passed 67 upload-related tests; the updated
Windows CPU profile passed 118 tests and 66 subtests on the source Mac, and 13
check-profile tests passed. These results do not replace native Windows package
qualification.
