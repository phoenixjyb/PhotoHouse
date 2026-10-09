# Approved worker terminal diagnostics

The CPU, image embedding, video embedding and face pipeline entry points report
terminal failures as one sanitized JSON object on stderr with exit code `2`.
Successful stdout and the existing private inference-child exit behavior remain
unchanged. The video preparation entry point retains its existing separate
`startup` / `worker_loop` diagnostics and exit code `1`.

## Report contract

CPU and embedding reports preserve the existing fields and add a fixed phase
and failure identifier:

```json
{"worker":"refused-or-interrupted","inspect_task_state":true,"phase":"worker_entry","failure":"unsupported_schema"}
```

The face pipeline preserves its existing report shape with a sanitized reason:

```json
{"face_pipeline":"refused","phase":"worker_entry","reason":"worker_lock_busy"}
```

`worker_entry` covers argument parsing and exceptions that escape the worker
body, including a polling-loop failure. It does not claim the failure occurred
during startup. Handled item failures still use their existing queue error,
retry and approval rules; these terminal reports do not replace task records.

The shared standard-library classifier lives in
`scripts/home_preparation_resources.py`. Known refusal messages and resource
codes map to fixed identifiers. SQLite busy/locked classification uses the
numeric primary error code, including extended codes. Permission errors,
missing files, other I/O failures and interruption have separate identifiers.
Unknown refusals report `refused`; unknown exceptions report
`unexpected_failure`. Reports never copy arbitrary exception messages,
arguments, tracebacks, paths, model output, GPU identities or database rows.

## Diagnose an installed worker

1. Record the task action, selected interpreter, immutable worker package and
   actual schema identity privately. A task name or package schema label does
   not establish which source/database ran.
2. Separate static file/hash checks, read-only metadata, provider execution and
   queue processing. A supported schema does not prove successful imports or
   actual processing. A prior nonzero scheduler result does not explain its cause.
3. CPU default preflight reads its selected database and queue metadata without
   processing tasks. Video preparation default preflight checks its selected
   database, paths and media executable locations. Embedding default preflight
   can launch a model/provider child and take a lock; it is not a metadata-only
   diagnostic. The face pipeline hashes models and uses resource/provider
   checks. Review each installed revision before invoking a preflight.
4. Before an execution diagnostic, prepare an exact source/configuration pin,
   exclusive private report destination, process/log/resource limits and owned
   descendant cleanup. Obtain authority for that concrete Windows operation.
5. Preserve failed tasks and older logs. A successful `--once` run with an empty
   queue establishes that run's result only. It does not prove media processing,
   recover a polling service or arrange its future schedule.

Installing the changed source also requires a new verified package and launcher
pins; editing a deployed immutable payload would invalidate its guard. This
source contract does not start tasks, alter a database or enable inference.

## Source checks

`tests/security/test_approved_worker_failure_reports.py` runs in the ordinary
CPU API profile. Its generated CLI cases replace worker bodies with failures;
they cover sanitized parser/terminal reports, imported refusal types, numeric
SQLite errors, resource guards, interruption and unchanged child routing.
They establish source behavior, not native Windows or installed-task acceptance.

See [worker packaging](APPROVED_UPLOAD_PROCESSING_V37.md) and
[maintenance](../../../docs/MAINTAINING.md) for the separate delivery gates.
