# Android batch upload validation and restart recovery

Following source, October 16, 2026. These changes are not included in the
published phone v68 APK. A later signed package and physical phone acceptance
are separate delivery gates.

## Review before starting

The file picker can return files that PhotoHouse cannot use: unsupported types,
unavailable provider content, unknown size, or a selection beyond the batch
limits. A skipped-only selection used to offer Start and then throw on an empty
queue submission. A valid selection could also exceed the queue's remaining
capacity and throw. The review now explains the reason and disables Start when
there is no admissible batch. Discard remains available; failed validation keeps
the existing queue unchanged.

The queue exposes a read-only `enqueueIssue` result and rechecks it at enqueue.
A typed rejection handles a queue or destination change between review and tap.
The UI keeps the reviewed selection on rejection and displays fixed localized
text, without exposing arbitrary exception text or starting a transfer.
Account/session generation changes clear the reviewed selection and network
confirmation; selections must not carry across accounts or stale destinations.

A stale Start button cannot acknowledge metered data consent. If connectivity
changes after rendering or while the destination chooser is open, the final
start gate returns to visible network review. Only an explicit tap on the
rendered warning/Continue step acknowledges that review; a later Start begins
work. Unknown connectivity requires the same review. The destination dialog
cannot grant network approval.

The supported formats and limits remain unchanged:

- Direct photo: JPEG/PNG, up to 25 MiB.
- Resumable batch: JPEG/PNG up to 256 MiB per image; MP4/MOV up to 16 GiB per video.
- At most 100 unfinished queue items, including earlier queued files.
- At most 64 GiB per new batch; bounded chunks and server media validation remain.

These are intake constraints, not decode or playback acceptance. HEIC and other
formats are not silently converted. The app shows the batch format/size limits
on the review card.

## Restoring an interrupted transfer

An on-disk `uploading` record is restored as `paused`. Its transfer ID, digest,
committed offset, destination and other metadata are preserved. Restore does
not read source bytes, hash files or contact the server. The user explicitly
resumes; the existing remote-offset/completion checks reconcile progress before
sending further data. Other terminal/cancellation states retain their contracts.

## Incident diagnosis and acceptance

A received upload, library approval, background preparation and gallery
visibility are distinct stages. Check accepted transfer/receipt metadata first.
If there is no new accepted session, inspect client selection/preparation,
access, request validation and connectivity before changing worker queues.
Do not infer a processing fault from the presence of older failed task records.

Core regression cases cover empty/invalid selections, combined queue capacity,
per-file/batch bounds and restore without work. Synthetic native review fixtures
cover empty, capacity-blocked and ready states in Chinese and English at 150%
text size. These source/fixture checks cannot establish the cause of a reported
incident without its client/error/time, or prove real device upload acceptance.
No server schema, service, media, upload policy or retention change is included.
