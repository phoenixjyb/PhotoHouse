# Journal-guarded person ownership repair

The offline `plan-person-repair`, `validate`, `review`, `apply`, and `receipt`
commands can take an explicit original-deletion journal path and namespace. The
options are paired and are accepted only by these command names:

```text
--original-deletion-journal ABSOLUTE_PRIVATE_JOURNAL_PATH
--original-deletion-namespace CANONICAL_NAMESPACE_UUID
```

The CLI only reads and verifies this journal. It never initializes, appends to,
upgrades, or replays it, and it does not discover a path from runtime settings.
When a primary database is bound to a deletion journal, omitting the pair does
not bypass the database guard. Supplying only one option, a mismatched namespace,
or the pair to another command is refused.

For a bound repair, pass the same explicit journal pair to each step. First plan
the exact selected person and sorted asset IDs, then validate that plan. Review
it against a separate fresh backup. Because this guard also verifies the restored
primary marker, `review` requires a new `--restore-out` path. `apply` repeats the
review and therefore also requires its own new, non-existing `--restore-out`
path. Do not reuse the review output path. Carry the exact reviewed plan digest,
review digest, authority reference, restore reference, and all-writers-stopped
assertion through the existing operator workflow. `receipt` takes the journal
pair and checks the matched receipt’s operation before returning it.

The journal path, file identity, namespace, and verified head are included in the
local cross-command review digest, but not printed in the CLI report. If the
journal file or head changes between review and apply, review must be repeated.
Restore verification compares the SQLite backup and restored copy; it is not a
disaster-recovery qualification. The operator still owns actual writer shutdown,
backup creation, restore readiness, authority, and rollback procedures.

Repair is whole-asset ownership work: the reviewed plan must enumerate the exact
suppressed, unmapped asset references for one already-visible person and confirm
that the change will not unlock another affected identity. Apply inserts only
the selected asset-to-library and person-to-library ownership rows. It preserves
the selected assets’ suppressed state, face detections and manual assignments,
embeddings, media, and task rows. It does not approve face assignments, merge
people, grant original-media access, change memberships, activate reviewed search
or kinship, or establish sharing outside the selected library’s existing
audience.

An unsealed proposal, source-copy result, preparation reference, or successful
synthetic test is not approval to apply. For each person, obtain independent
review of provenance, the whole-asset audience effect, and the maintenance window;
then create and review a fresh sealed plan and backup. After one person’s repair,
the database snapshot has changed: recalculate and review the next person’s
exact remaining assets, then use a fresh plan and backup. Never reuse a previous
person’s asset selection or treat the journal pair as a substitute for operation
authority.
