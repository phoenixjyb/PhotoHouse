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
unknown queries use ordinary SQL. A stable source-version change before reuse
disables the snapshot and uses live SQL. If final replay completes normally but
a supported source-version check detects a change, the runtime performs one
ordinary full fresh validation against the original binding before final owner
authorization. Unsafe path or connection identity fails closed; it never falls
back to an old SQLite handle. An exception during final validation propagates
without retry. No replay can trigger the encoder or ranking again.

This remains a local experiment, not deployment or activation evidence. Path
metadata checks do not atomically bind SQLite file descriptors and do not prove
safety against hostile out-of-band file rewrites, arbitrary VFS behavior or
unreviewed writer processes. The generated qualification database uses WAL so
its mid-encode source-mutation guard can verify a committed update from a
second connection. The guard requires a fresh readback of the changed value,
withheld cards and the existing refusal response; a lock timeout alone is not
counted as mutation evidence.

## Generated full-request profile (R127)

On local source `001a039`, one generated 23,696-eligible-row / 65-omission,
768-dimensional WAL fixture compared the same native read-only factory with
`request_source_snapshot` off and on. The provider was a fixed 418 ms
`MockTransport`; this is not a learned-model or native-Windows run. Across nine
warm English, Chinese and mixed-language pairs, mean latency was 2,369.294 ms
baseline and 2,132.612 ms candidate (9.99% lower); medians were 2,347.977 ms
and 2,024.980 ms. The candidate maximum was slower at 2,756.605 ms, 8/9 paired
samples were faster, and only 2/9 candidate samples met 2 seconds, so the
all-sample target remains unmet.

All 13 cold, warm and page-two pairs matched complete API JSON, full ranked IDs
and score bits, and per-attempt charged rows/bytes. The candidate used nine
physical source SQL reads and nine final-pass replays per request instead of 18
physical reads. Cold and page-two samples are separate from the nine-warm
summary. The recorded process passed configured setup/profile/RSS limits, but
the result does not contain exact peak RSS or separate setup/profile timings.
This modest generated result does not establish native Windows latency, family
relevance, language quality, default enablement or activation.

Correctness coverage here is generated local SQLite and synthetic account data.
No family relevance, native Windows, GPU/model-runtime, production or activation
claim is made by this experiment.
