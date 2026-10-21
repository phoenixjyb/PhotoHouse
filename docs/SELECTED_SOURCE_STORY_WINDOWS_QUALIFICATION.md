# Selected-story Windows qualification

This is an explicit, model-free rehearsal of the default-off
[owned-process story provider](SELECTED_SOURCE_STORY_PROCESS_BINDING.md). It is
separate from installation, feature activation, service control and deployment.
The ordinary CPU tests and imports never execute the native rehearsal.

## Source and execution identity

Use a source-only package built from an explicit full commit. Verify the ZIP
SHA-256, closed manifest/file list and each extracted file hash before executing
code. Retain the package, interpreter digest and report privately. The qualifier
checks its own script digest against that manifest and requires the caller's
full source commit to match. It does not fetch code or dependencies.

Run under the identity intended to execute the provider. An interactive-user
success is not SYSTEM-service qualification. Use an existing interpreter with
compatible dependencies without modifying its environment. Output must be a new
absolute directory under an existing private parent; existing output, UNC paths,
traversal, reparse aliases and nonprivate storage are refused.

```text
python -I -B scripts/qualify_selected_story.py --execute --commit <full-source-commit> --out <new-private-output-directory>
```

Without `--execute`, no native work occurs. There are no database, media, model,
provider endpoint, live task or service options. Source staging and any one-off
qualification executor are operator actions within the specific rehearsal
scope; this CLI never registers or changes scheduled tasks.

## Native synthetic cases

The [runner](../server/scripts/qualify_selected_story.py) uses the real Windows
API and a bounded outer Job, with an independent child-side proof of membership
and Job limits. Each synthetic generation uses the actual provider and its own
nested Job. The synthetic worker uses Python's standard library only and does
not call a model, listen on a socket or connect to a provider.

Cases cover disabled construction/preparation, generated narrative and exact
file exchange, invalidation of an already resumed worker, wrong-scope cleanup
refusal, running deadline expiry, preflight expiry/scope mismatch, and a real
lingering descendant after root exit. Cleanup requires native root exit plus
zero Job members and handle closure. File exchange directories must be removed
after reconciliation. Reports list only fixed case names, source/interpreter
identity, limits and remaining gates, without source words or output prose.

Limits are 2 GiB host Job memory, eight processes, at least 8 GiB free RAM, a
105-second native child wall limit and a 15-second cleanup/report allowance.
These are qualification bounds, not measured GPU or household capacity.
The outer Job kills/drains its own descendants on abnormal child completion;
no process name matching, arbitrary PID adoption or shared-service stop occurs.

The provider now checks actual Windows owner/DACL policy for its private
exchange directory and files. It checks the request file before writing source
text and the response before reading. It reuses the existing private-storage
policy; chmod alone does not establish Windows privacy. Unsafe cleanup retains
ownership/quarantine instead of recursively deleting unfamiliar contents.
Native cancellation is reported as cancellation rather than a generic worker
failure. Portable tests cover these guards and refusal behavior; they do not
substitute for this explicit native invocation.

## Package readiness and report interpretation

Alongside the native canary, verify the extracted package imports with both story
flags off and creates no provider by default. Exercise application/schema
compatibility only with generated databases in the isolated candidate. Do not
open a production database merely to run this rehearsal, infer its schema from
a stale task name, or change live configuration to make a test pass.

Before and after, compare existing service-task definition hashes, enabled
states and active launcher hash. A new, bounded, uniquely named qualification
task may be used for the intended service account when specifically authorized;
remove only that owned task after its completion and preserve its report.
Never alter an existing production task to run a canary.

A pass supports only the exact source, interpreter, account, ACL and native
cases recorded. It does not establish hard API crash/service restart recovery,
atomic executable/dependency identity, disk quota or secure erasure, complete
cross-process inference coordination, production model-worker implementation,
locality/retention, GPU/driver behavior, quality/latency or family/device
acceptance. Those remain activation/deployment gates. An inactive source package
may be a deployable candidate while real AI generation remains unqualified.
