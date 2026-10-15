# Experimental oral-history qualification

`server/scripts/qualify_oral_history.py --out <absolute-private-directory>` runs a
source-only qualification using generated content. The destination must not exist
and its existing parent must be a direct private local directory. The command
accepts no database, source-audio, provider, network, or service arguments.

The runner uses the existing generated a0 account/library seed helper. It installs
the oral-history tables only in that new fixture database, binds a fresh V3
deletion journal, and performs the guarded V3-to-V4 journal upgrade before it
creates a recording. It then exercises an ordered short section followed by an
exact 20-second canonical PCM section, exact retries and changed-payload conflicts,
and receipt/audio verification across primary close/reopen boundaries,
author-only access, retained-source withdrawal with a content-free ledger binding,
stale-prefix refusal and reviewed journal replay, and corrupt-source refusal.
The next source increment also verifies a populated synthetic V3 legacy history
survives upgrade with the same records, digest and primary marker, and verifies
a journal-committed withdrawal after primary rollback and connection reopen.
Ordinary access must refuse that unreplayed state; reviewed replay restores the
exact withdrawal retry without reviving the recording.
The raw WAV bytes remain only in the private generated SQLite database; temporary
SQLite backups stay inside the same output directory and are removed before
success. The runner creates no standalone audio export and includes no source bytes
in the report. This is not an erasure qualification: the fixture deliberately
retains its source section after withdrawal.

On Windows, the run is confined to the existing native bounded child helper with
a 300-second wall limit, 2 GiB memory cap, eight-process limit, and 8 GiB minimum
free-memory threshold. The child receives a clean environment without dotenv,
user-site packages, bytecode, provider settings, or network configuration. Other
platforms run the same synthetic path directly for local source qualification.

The JSON report contains only case/group booleans, accepted-before-restore counts,
and actual final restored-fixture counts.
It sets `experimental_fixture_schema=true` and explicitly reports production
admission, transport, and erasure as unavailable. A pass qualifies these generated
source contracts only. It does not admit production data, expose an HTTP route,
qualify production schema rollout, approve a worker, or qualify live restoration.

## Qualification revisions

The frozen v59 archive at `816b9b5` retains its original four groups / ten cases.
The next v60 source appends a fifth two-case group; its report has **five groups /
twelve cases**, with the original case order and four group counts preserved.
Accepted-before-restore and final fixture counts remain unchanged. Forty-nine
focused qualification/intake/withdrawal tests passed locally. A successful run
retains only the two main fixture databases and its content-free report; the
separate legacy-upgrade scratch databases and SQLite sidecars are removed.

Any future native operation must pin the matching runner, archive and revised
report contract. The prepared v59 native controller deliberately still expects
four groups / ten cases and must not qualify this later source by accident.
