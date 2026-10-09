# Runtime configuration

The generated demo creates a temporary SQLite catalog and geometric pictures;
it does not read a configured installation. Run it before selecting real storage.

For a real deployment construct `app.access.runtime.RuntimeConfiguration` with
explicit database, HTTPS origin, original roots and derived root. Storage must
already be prepared and migrated. Upload, assistant, source-memory and generation
features each require explicit opt-in. Original-memory intake also requires a
separate bound deletion journal and a tested paired restore. Never obtain these
values by discovering another installation or committing a workstation `.env`.

The ordinary application entry point starts closed. Public UI code may be served
while authenticated media routes remain unavailable until configuration is valid.
Windows scheduled-task, GPU and release operator profiles need independent
qualification; the CPU demo does not claim those profiles work on every host.
