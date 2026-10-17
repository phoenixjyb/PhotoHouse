# Phone v71 candidate: library upload response compatibility

Version **71 / `0.71-library-upload-fix`** is reserved for this repair.
The last published version remains [v70](PHONE_V70_RELEASE_2026-10-17.md).
This is source qualification, not a publication or real-upload acceptance record.

## Defect and repair

The server returns `destination_library_id` on library-targeted resumable upload
responses. A completion response can also include `approval_state` and
`library_id`. The old phone parser required exactly six targetless fields, so
it rejected a valid library-targeted create response before saving the transfer
identifier or sending chunks. The screen then displayed only “上传中断”.

The parser now accepts these specific optional fields and validates their types,
states and approval/library relationship. Unknown and duplicate fields still
fail. The HTTPS create adapter and queue check that every response belongs to
the originally selected library, including chunk/conflict/recovery/cancel paths.
Completed GET responses without approval metadata remain valid; approval and
preparation are still checked separately through existing history.

Failed uploads store a content-free classification and show a Chinese/English
explanation for response, network, login/access, source, size/format and server
failures. Arbitrary legacy messages are never rendered. Retry remains explicit
and preserves request/batch identity and committed progress; restoration does
not automatically upload files. There is no database, API, worker or model
change in this candidate.

## Device and runtime evidence

USB read-only inspection confirmed the Samsung runs v70. Its available recent
app logs contain no detailed upload failure. The source defect above is
reproducible. After direct SSH closed, the existing trusted relay enabled a
read-only audit at 04:42 UTC: seven new library-targeted sessions were created
around 02:53 UTC and all had zero committed bytes. There were no new completed
receipts. That matches rejection of a successful creation response before any
chunk is sent; no raw request/response capture is available. The live API binding
and phone v70 / TV v30 manifests were verified. No transfer, receipt or service
was modified.

## Trial after approved delivery

1. Update without uninstalling, then confirm v71 in Settings.
2. Open 添加内容 → 导入进度. Keep the existing interrupted batch.
3. Check server status first, then explicitly retry one interrupted item.
   Do not select the whole folder again merely to restart its failed queue.
4. Confirm committed bytes advance and a received/library status appears.
   Refresh server history; awaiting owner review is a valid separate state.
5. Verify the asset in its library, then check its preview and video playback
   separately. Receipt and library assignment do not prove media preparation.
6. If it fails, report the new explanation and approximate time. Do not send
   passwords or private media. Missing file access may need a later picker action.

Signing, Windows staging/publication, full download verification and a physical
upload trial are separate delivery gates.
