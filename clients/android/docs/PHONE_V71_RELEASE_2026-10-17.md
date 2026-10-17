# Phone v71 release: library upload compatibility

Published October 17, 2026: **71 / `0.71-library-upload-fix`**. See the
[candidate contract and retry guide](PHONE_V71_CANDIDATE_2026-10-17.md).

## Source and package

PR #85 merged as `92f067dcdfcad7ee48d7ddab8cdd10f20e7ef4da`; the reviewed build
source is `d8e0612369dc39b7077ded6379e8a575c5f28193`. The merged Android tree
matches `e5073e3868e48d7ef305e52f39defc4a008c754c`. All five CI jobs passed in
run **39003962335**.

The published original-certificate APK is **11,737,464 bytes**, SHA-256
`079a753a43a9cfd7419a1f7e77e5a2069b5faf2f32117c7d5fc54e7d144a8ce5`.
Package `dev.photohouse.connected` retains the original icon and all 17 production
profile fields. Signature, alignment, unchanged DEX and icon checks passed.

## Verification and acceptance

The configured unsigned release build, 1,110 earlier full local core checks,
six signing fixtures, 15 publication fixtures, native controller parsing and
pinned-tool checks passed. Release lint was not rerun locally; CI Android lint
passed. Native UI acceptance was blocked by emulator/package-manager timeouts;
no v71 native visual pass is claimed.

Windows publication and full native/trusted HTTPS readback passed. An independent
Mac trusted HTTPS stream at **2026-10-17 05:34:54 UTC** verified the entire APK
without saving another copy. API binding and TV v30 feed remained unchanged;
this operation did not restart services or modify tasks, databases or media.

The owner subsequently reported installing v71 and completing an interrupted
batch after repeated explicit Retry taps. A read-only server audit confirmed
complete transfers and matching receipts. Those receipts were awaiting review;
arrival does not establish assignment, preview/playback readiness or family
acceptance. The repeated taps exposed queue-run recovery and feedback gaps,
tracked in the [v72 candidate](PHONE_V72_CANDIDATE_2026-10-17.md).
