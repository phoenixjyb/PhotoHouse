# Android OTA publication guard v1

`scripts/publish_android_update.py` publishes a signed phone or TV APK to an
explicit update root. Each invocation now takes one shared exclusive lock for
that root before it reads either channel pointer. Phone and TV publishers use
the same lock, so cooperating versions serialize even when they update different
channels.

## Lock behavior

The lock filename is `.android-update-publish.lock`. Acquisition uses exclusive
file creation and waits up to one second. If the lock remains present, the
publisher refuses with a busy error. It never deletes a preexisting lock based
on age, owner metadata, or apparent process status. A process that exits
unexpectedly can leave a stale lock; clearing one requires separate manual
inspection. A successful invocation removes only the lock file whose identity
and random token match its own.

This coordinates invocations of publisher versions that honor this lock. It is
not a filesystem transaction or universal compare-and-swap: direct writers and
older publisher copies can bypass the lock. The publisher snapshots both
channel pointers under the lock and rechecks them immediately before replacing
the selected pointer, which refuses changes observed during the operation. A
bypass writer can still race between that final read and atomic replacement.

## Reviewed pointer expectations

The Python API accepts two keyword-only expectations:

- `expected_current_pointer_sha256`: the selected channel pointer digest the
  operation reviewed.
- `expected_other_pointer_sha256`: the untouched channel pointer digest the
  operation reviewed.

Each accepts a lowercase SHA-256 digest to pin an existing pointer or explicit
`None` to assert that the pointer is absent. Omit an argument only for legacy
callers that do not carry a preapproved pointer snapshot. When supplied, both
expectations are checked while the root lock is held before any content-addressed
APK copy, and checked again immediately before pointer replacement. The current
pointer must still advance to a higher version with the same package and signer.

The CLI equivalents are `--expected-current-pointer-sha256` or
`--expect-current-pointer-absent`, and `--expected-other-pointer-sha256` or
`--expect-other-pointer-absent`. Each pair is mutually exclusive. Supplying a
wrong digest, asserting absence for an existing file, or asserting a digest for
a missing file refuses before writing. A failure before pointer replacement
leaves both channel pointers as observed by the publisher unchanged. The
content-addressed APK file may remain if it was copied before a last-moment
pointer drift was detected; it is not advertised unless the pointer is
replaced.

## Rollback and authorization boundaries

This function does not implement a rollback or downgrade. Its increasing
version check rejects a lower or equal package version. A separately reviewed
rollback operation must preserve the prior pointer bytes and compare the
current pointer digest with the exact just-published digest under the same
serialization mechanism before restoring anything. A stale comparison must
refuse and leave current pointers untouched.

The publisher is a standalone operation and is not installed or called by API
startup. A caller's operation-specific authorization can cover the intended
signing, private staging, phone-only pointer update, required read-only
preflight/readback, and any explicitly scoped rollback eligibility together.
The helper does not create or authenticate that authority; it only accepts the
explicit feed-root, APK, channel, signer and optional pointer expectations.
Read-only checks that are part of the authorized operation do not require a
second confirmation from this utility.

Tests in `tests/security/test_android_updates.py` cover same-root competing
phone/TV publishers, bounded refusal on an existing foreign lock, owned-lock
cleanup after success and errors, first publication with explicit absent
pointers, expected current/other pointer mismatches, pointer drift during an
attempt, phone publication preserving TV bytes, and stale rollback comparisons.
All added publisher tests use temporary directories, synthetic APK bytes and
mocked APK metadata; they do not contact a feed or Windows host.
