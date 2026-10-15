# Private story drafts: save and resume

This increment adds explicit **Save draft / Resume / Delete draft** for a new
story on Web and phone. It is device-local, not cross-device synchronization or
publication. It needs no server schema migration or model activation.

## Ownership and storage

- One bounded draft per configured origin, account and library; no other scope
  may list, decrypt, overwrite or resume it. At most twenty scope slots, each
  bounded to 128 KiB. Refuse excess capacity instead of evicting another draft.
- Saving is explicit. Store authored title/wording, ordered asset IDs, chapter
  structure, selected source IDs, original selection revision and guide mode.
  Never store tokens, recordings, pending dictation, thumbnails, source prose,
  generated suggestions or a server preview wholesale.
- Web uses IndexedDB with a non-extractable AES-GCM key, unique IV and exact
  origin/account/library authenticated data. Android uses AndroidKeyStore and
  an atomic encrypted file in no-backup storage. This protects stored bytes;
  it does not protect an unlocked device or a compromised application origin.
- Drafts remain until explicitly deleted or successfully published. Browser
  site-data clearing or app removal may also remove them. A failed read/decrypt
  must show an error, not claim that no draft exists or silently discard prose.
- Signing out or switching library removes in-memory prose and fences pending
  operations. Stored drafts remain isolated and require a fresh signed-in scope
  to resume. They do not grant access to withdrawn media or libraries.

## Explicit save and resume

Saving is unavailable during recording, transcript review, IME composition,
source refresh, uncertain publication or another operation. This first slice
does not persist edits to an already saved story. Replacing the existing slot
requires an explicit confirmation, unless continuing the same local draft.

Resume first rechecks current creation permission and requests a fresh outline
for **all** saved asset IDs. No old evidence prose, thumbnail or permission flag
is revived. Preserve authored words and grouping; retain only source IDs still
valid for the same chapter. Compare selection revisions and reset publication
review. Changed sources require renewed explicit review. Failure or scope change
leaves encrypted storage intact and does not reveal stale prose in another scope.
No recording, inference or publication starts automatically.

## Uncertain publication

For a durably saved draft, before sending Save story, atomically checkpoint its
exact frozen request and mutation ID. A persistence error stops dispatch. After
restart, resume presents explicit **Check/retry this save** using that same body
and ID, rebound to the current authorized session. It must never silently turn
an uncertain request into a fresh create. A successful response removes the
matching record; failures keep it. A changed/newer local record must not be
deleted by a late completion from an older operation.

This is an encrypted recovery journal for an explicitly saved local draft, not
automatic persistence of every editor or a separate source of story truth.

## Acceptance and delivery

Qualify process/page recreation, exact wording/order, changed/revoked sources,
account/library separation, corrupt storage and quota failure, explicit deletion,
byte-identical uncertain retry, stale completion ownership, dictation/IME guards
and Chinese/English narrow/large-text controls. Tests use generated media and
fake speech. Source checks do not establish deployment, a signed APK, live model
quality or family/device acceptance.

### Focused local commands

Run the Web storage and full draft journey with the existing browser tools:

```sh
node server/tests/security/test_story_draft_store.cjs
PH_BROWSER_PYTHON="$PWD/.venv/bin/python" node server/tests/security/test_story_draft_resume_browser.cjs
python -m unittest tools.tests.test_android_emulator_test
```

Android JVM/store checks are in `StoryDraftRecordCodecTest` and
`StoryWorkspaceStoreTest`; Keystore/atomic storage checks are in
`KeystoreStoryDraftPersistenceTest`. Use the explicit QA emulator runner described
in [development](DEVELOPMENT.md#explicit-emulator-instrumentation), never a broad
connected task when a real family phone is attached.
