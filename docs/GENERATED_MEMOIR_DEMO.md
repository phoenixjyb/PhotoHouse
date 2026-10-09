# Generated family story and memoir demo

Run the demo from the repository root after setting up the documented CPU demo
dependencies:

```sh
python examples/generated-demo/check_demo.py
```

It applies the real migrations to a new temporary SQLite database and draws two
geometric JPEGs. A fictional owner creates two stories. A fictional member adds
and consents to one text contribution per story; the owner accepts them and
links each accepted contribution to its saved story. The owner then saves an
ordered memoir with synthetic opening references and a hand-written transition
that cites the second story's contribution.

The demo reads the saved editorial sidecar back, removes a child story's
contribution reference, and confirms that the member can still read the original
contribution. It then restores the link and current memoir text, changes the
child story revision, and verifies that the API reports `source_changed` without
returning the old editorial prose.

Every story narration and editorial passage in this flow is explicitly marked
as synthetic demo text. The app is configured with memory generation disabled;
the demo does not call ASR, a model, or a provider. It uses no real recording,
family text, persistent database, household endpoint, listening server, network
connection, or child process. The temporary database and generated images are
removed when the command exits. A passing run verifies this local API journey
only; it is not a family writing evaluation or live-service qualification.
