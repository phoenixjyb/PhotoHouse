# Backend and Web tests

Use explicit profiles from the **PhotoHouse repository root**, after the
[development setup](../../docs/DEVELOPMENT.md#cpu-quick-start):

```sh
.venv/bin/python tools/check.py api
.venv/bin/python tools/check.py memory
.venv/bin/python tools/check.py windows-cpu
```

The dispatcher selects current generated tests in `server/tests/security/`,
uses [`config/pytest.ini`](../../config/pytest.ini), sets backend import paths,
and isolates the run from historical inference fixtures with `--noconftest`.
The API profile also runs the generated no-listener demo. No family database,
GPU, model weights or deployed provider is required.

## Focused checks

For one known contract, from the repository root:

```sh
PYTHONPATH=server/backend .venv/bin/python -m pytest --noconftest -c config/pytest.ini server/tests/security/test_assistant_memory_actions.py
```

`server/tests/ui/` holds pure Node UI/controller tests. Generated browser journeys
also live under `server/tests/security/` as `.cjs` files; follow
[Web development](../../docs/WEB_DEVELOPMENT.md) for existing Node/Playwright tools
and exact profiles. Android checks belong in the [client subtree](../../clients/android/README.md).

Source tests, emulator/browser fixtures, native package qualification, live service
checks and physical/family acceptance are separate. Provider/GPU experiments need
explicit installed dependencies, weights, resource budgets and synthetic fixtures;
do not infer them from a generic test filename or run them as part of CPU setup.
Dated counts and acceptance receipts remain in [Development](../../docs/DEVELOPMENT.md),
with current delivery/gates summarized in [Project Status](../../docs/PROJECT_STATUS.md).
