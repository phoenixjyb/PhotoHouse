# Video source recovery planning

[`plan_bad_video_recovery.py`](../server/scripts/plan_bad_video_recovery.py)
classifies a sanitized checkpoint
snapshot and prints a path-free recovery plan. It is a read-only planner. It
does not open media, databases, providers, or network connections, and it does
not write, retry, transcode, or promote assets.

For example, from the repository root:

```sh
printf '{"rows":[{"id":1,"reason":"source_empty","source_size":0}]}\n' \
  | python server/scripts/plan_bad_video_recovery.py
```

The focused generated test is
[`test_bad_video_recovery.py`](../server/tests/security/test_bad_video_recovery.py).

## Bounded input

The input is one UTF-8 JSON object with exactly one `rows` array. Each row may
contain only `id`, `reason`, `source_size`, and optional `header_hex`. IDs and
sizes must be nonnegative signed 64-bit integers (IDs must be positive), and
`header_hex` may describe at most the first 64 bytes. The planner accepts at
most 5,000 rows and 1 MiB of JSON. Duplicate object keys and nonstandard JSON
numbers are rejected. CLI errors are fixed strings and do not echo a filename,
row, or parser detail.

Allowed reason values are `source_empty`, `preparation_failed`, and
`source_decode_failed`. Snapshots should contain only asset IDs, those
reason codes, byte counts, and a bounded file-header sample. Do not include
filenames, directories, account or library identifiers, captions, or original media.

## Recovery meaning

- A zero-byte original cannot be reconstructed from its current bytes. Locate
  an independent original or backup and verify its identity against a trusted
  receipt before preparing a fresh derived copy.
- An AppleDouble sidecar is container metadata, not a truncated video. Keep
  its row for review and inspect the separately cataloged video counterpart;
  never rename or transcode the sidecar as video.
- A recorded full-decode failure requires an independent original first. If no
  original is available, any salvage experiment is a separate review that must
  write to a fresh candidate and pass strict full-decode and playback checks.
- A preparation failure or suspiciously small source needs independent-source
  and container review. Do not assume the current bytes can produce a playable
  video.

Failure rows remain evidence. A partial output is not a ready asset, and this
planner does not authorize retries, state resets, or promotion. Recovery must
not silently retry already-ready rows or replace originals with derived files.

## Source provenance

The portable classifier was imported from legacy commit
`84b772831c102b96280e3e7423647ff4787794d9`,
`scripts/plan_bad_video_recovery.py`, SHA-256
`8ca6446de26b92c9259e076b77957a396b5f5b4d5de62b157d3488df60e0309f`.
The monorepo copy preserves its classifications and adds bounded strict JSON
intake, duplicate-key rejection, numeric/row limits, and privacy-safe CLI
errors.
