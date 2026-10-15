# Private assistant Windows qualification

The source-only candidate includes `server/scripts/qualify_private_assistant.py`.
It creates invented media metadata and captions, an a0 main database, a separate
schema-v2 conversation store and an assistant receipt journal. It opens no real
database or family media, starts no listener and substitutes in-process TTS.
The current eight checks cover generated discovery, owned turn recovery,
saved-reply speech receipts, negotiated story/memoir cards with legacy recovery,
saved-memory source drift during synthesis, paged history, actor separation and
fixed retention. Earlier immutable qualification candidates retain their own
six-case source pin; updating this script does not update their approved scope.

## Execution identity and private storage

Run native qualification with the identity that will open the private store in
production. A successful interactive-user check does not qualify a SYSTEM API.
Windows private-storage validation checks the real owner and DACL: SYSTEM and
local Administrators are allowed, along with the current caller. An explicit ACE
for the interactive user is therefore refused when the caller is SYSTEM.

For a SYSTEM service, the generated data parent must have an owner and DACL
accepted under SYSTEM, without an unrelated user ACE. Do not provision a live
store as an interactive user and assume that granting SYSTEM access is enough.
The same rule applies to later authorized store initialization or upgrade.
The validator never changes an ACL itself. Preserve existing stores until a
separately prepared and approved provisioning operation can validate them.

## Bounds and ownership

The Windows CLI admits a suspended child into a Job before resuming it. The
child has a 900-second wall limit, 2 GiB Job memory limit, four-process limit and
8 GiB free-RAM admission floor. Application/database dependencies load inside
that child; the supervising wrapper uses standard-library and private-path
checks. Interpreter startup and the lightweight supervisor are outside the
child's memory limit and need their own enclosing wall limit.

A prepared native operation should bind the source ZIP and every extracted
file, recheck them under the execution identity before running, and record the
installed runtime used. It does not install dependencies or prove that the
installed environment is an immutable dependency-lock reconstruction.

If a temporary scheduled task is needed to obtain SYSTEM identity, it must have
a unique name, no boot or recurring trigger, an enclosing time limit and an
exact recorded definition. Capture existing PhotoHouse task definitions before
the operation and check that they remain unchanged. Cleanup can remove only the
owned, unchanged, non-running temporary task. A failed check remains a failed
check even when cleanup succeeds; retain its generated failure evidence.

Staging, registration, execution and owned-task cleanup require authorization
for this operation. A synthetic pass does not authorize live store creation,
schema changes, provider calls, API switching, APK publication or family access.

## Acceptance record

Keep the immutable source/package identity, installed interpreter/runtime
fingerprint, execution identity, native report, bounds and task-cleanup receipt
together in private operator evidence. The public repository contains portable
source and synthetic checks, not household task definitions or paths.

The October 13 local source passed its eight-case qualification on macOS. Native
Windows qualification, live private-store provisioning and served
voice behavior remain separate delivery gates.
