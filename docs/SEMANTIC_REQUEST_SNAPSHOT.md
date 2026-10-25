# Request-local semantic source snapshot experiment

The semantic runtime has an experimental `request_source_snapshot` option.
It defaults to `false`; the regular application path and qualification report
shape remain unchanged unless an explicit caller opts in. The generated
qualification harness uses a dedicated exact native SQLite factory for its
private temporary database only.

When enabled, the first complete source projection still comes from live SQL.
The request may reuse only those exact immutable rows during its final no-op
source validation, on the same read-only connection, if the source identity,
SQLite environment and data version remain stable. It stores no rows between
requests. Membership, source/index bindings, eligibility policy and omitted
cohort, source hashes, vector checks, budgets and cancellation checks remain
fresh. Replayed rows are detached tuples and are charged again against the
current request's row and byte limits.

The native factory uses a direct regular file in `mode=ro`, `query_only=1`,
`foreign_keys=ON`, `trusted_schema=OFF`, and `read_uncommitted=0`. It rejects
attached/TEMP state, virtual or generated tables, changed connection
environment, unsupported journal mode, unsafe path identity and same-connection
writes. Only fixed source SQL templates and exact string arguments are eligible;
unknown queries use ordinary SQL. A source change before reuse disables the
snapshot and uses live SQL. A change detected after final replay causes one
ordinary full fresh validation against the original binding before final owner
authorization. No replay can trigger the encoder or ranking again.

This remains a local experiment, not deployment or activation evidence. Path
metadata checks do not atomically bind SQLite file descriptors and do not prove
safety against hostile out-of-band file rewrites, arbitrary VFS behavior or
unreviewed writer processes. The generated qualification database uses WAL so
its mid-encode source-mutation guard can verify a committed update from a
second connection. The guard requires a fresh readback of the changed value,
withheld cards and the existing refusal response; a lock timeout alone is not
counted as mutation evidence.

Correctness coverage here is generated local SQLite and synthetic account data.
No family relevance, native Windows, GPU/model-runtime, production, latency or
activation claim is made by this experiment.
