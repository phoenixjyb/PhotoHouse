# Package a verified source snapshot

`tools/package_source.py` creates `source.zip` and `verification.json` from a
clean committed source tree. The destination must be an absolute path to a
directory that does not exist and is outside the repository. The tool does not
use the network, package Git history, sign or publish files, or perform a
privacy/legal review.

Phone and TV artifacts have separate
[release preparation requirements](ANDROID_RELEASE_PREPARATION.md); a verified
source archive does not carry private Android build profiles or signing keys.

```sh
python tools/package_source.py /absolute/path/to/new-output-directory
```

Before creating the package, the helper requires a clean Git worktree, captures
the exact `HEAD`, and runs `tools/verify_current_source.py`'s current-source
verification logic. It packages only the exact tracked path set from that
commit. It checks tracked file modes, safe and unique ZIP member paths, Git
blob and working-tree bytes, executable file modes, archive CRCs, and the
finished ZIP before exposing its verified output. The helper claims the absent destination
directory exclusively, links the verified ZIP into it, and writes
`verification.json` last as the completion marker. A destination created by
another process during packaging is preserved and causes refusal; a directory
without a valid `verification.json` is an incomplete package. Verify its
archive digest when accepting a copied package. Temporary files are kept
in a sibling staging directory and removed on refusal.

`verification.json` records the source commit, archive SHA-256, tracked-file
count and per-file Git blob/hash data. Its `imported_source_verification` field
records the ledger-covered source count separately; that number is not the ZIP
file count. The only allowed checkout/ZIP byte normalization is the declared
`text eol=crlf` for `clients/android/android/gradlew.bat`: Git stores LF while
the checked-out and packaged file uses CRLF. Other working-tree/blob byte
mismatches are refused.

Inspect package contents and complete the repository's separate privacy and
release reviews before sharing an archive. A valid source package does not
establish live-service, migration, device, model or family acceptance.
