# CI template

The candidate workflow runs the same CPU API/generated-demo and unconfigured
Android commands as local development. It does not sign, install, publish, start
models or connect to a household service. It uses read-only repository permission
and does not persist checkout credentials.

Action commits are pinned in `ci-action-pins.json`, resolved from their official
repository tags. See the upstream [checkout](https://github.com/actions/checkout),
[Python](https://github.com/actions/setup-python) and
[Java](https://github.com/actions/setup-java) documentation.

This is a prepared template. No hosted run has occurred yet. Local acceptance
and hosted CI are reported separately.

The Android job always runs the read-only unit-report inventory after its build
step. It prints only module/count summaries, including missing reports and
failures, errors or skipped cases. It does not print test output or launch a
build. A readable inventory does not establish a fresh execution or bind a
report to a source revision; the preceding Gradle step supplies the job's build
result. Locally, reports can be old or filtered, so keep the actual command and
source pin with any acceptance claim.
