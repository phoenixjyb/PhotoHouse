# Inspect a fixed API source package

The portable [`inspect_api_package.py`](../tools/inspect_api_package.py) checks
one source-only ZIP against an explicit local Git commit and independently
reviewed SHA-256. It reads only; it does not extract or execute the package,
install dependencies, open a database, invoke a model or change a service.

Run it from the reviewed source revision corresponding to the package. The
[package builder](../server/scripts/build_staging_package.py) owns the exact
allowlist, regular source blob checks, member sizes and expanded-size limit.
The inspector first compares the local builder bytes with that commit before
loading its verified maintenance helper. A modified local builder is refused
before execution. It reconstructs the canonical ZIP from immutable local blobs
and compares every byte, including the manifest and ZIP metadata. Older packages
whose source closure differs require their corresponding reviewed verifier.

```sh
.venv/bin/python tools/inspect_api_package.py \
  --archive /absolute/private/api-source.zip \
  --commit FULL_40_CHARACTER_COMMIT \
  --sha256 FULL_64_CHARACTER_SHA256 \
  --git /absolute/reviewed/git \
  --git-sha256 FULL_64_CHARACTER_GIT_BINARY_SHA256
```

The archive must be a direct, privately readable regular file: no symlink,
reparse point, alternate directory link or hard link. Its size is bounded to
32 MiB. Stable open-handle and pathname identities are checked, and the bytes
are reread after local Git traversal. Restoring a Windows modification time
cannot conceal a changed same-size input. No file permissions are changed.
The Git executable has its own reviewed absolute path and SHA-256; ambient
`PATH` cannot choose a different binary. Its stable identity and bytes are
rechecked. Local Git reads ignore repository overrides, replacement refs and
user/global configuration and disallow lazy object fetching, with a 30-second
overall traversal budget and bounded
command output. They
perform no network or authenticated Git operation.

The JSON result contains the source commit, archive hash/size, file count and
explicit read-only boundaries. Refusal output has a fixed safe reason code and omits archive paths, file
content, unknown exception messages and subprocess errors. Neither a package manifest nor a self-consistent changed
source hash can substitute for the exact committed blobs.

## What a pass establishes

A pass establishes package/source identity only. It is not synthetic execution,
native Windows qualification, configuration/admission readiness, a stopped-writer
backup, deployment, HTTPS readback, an APK signature or family acceptance.
Current source can be dirty with unrelated development because the selected
immutable commit is read directly; this is not permission to package dirty work.
The builder still constructs packages from explicit committed source only.

The generated inspector cohort uses miniature local Git repositories and
mutation cases, not household configuration or runtime data:

```sh
.venv/bin/python -m unittest tools.tests.test_inspect_api_package -q
```

The initial twenty-six cases cover exact identity, dirty worktree separation,
changed source with matching manifest hashes, extra/traversal/duplicate ZIP
members, repacked metadata, private paths, hard links, file replacement,
permissions, modified builder refusal, explicit Git identity, fake ambient Git,
Git overrides/replacement refs, missing promised blobs, bounded traversal/output and content-free
CLI output, including malformed arguments. Native Windows ACL/handle behavior remains a separate acceptance
check; shared private-file helpers already refuse unqualified platforms.

Git must support its [no-lazy-fetch option](https://git-scm.com/docs/git).
An older binary that refuses that option fails inspection before reading objects;
the tool does not fall back to a potentially networked object read.
