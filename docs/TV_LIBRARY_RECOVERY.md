# TV library-directory recovery

The TV keeps named libraries separate from media browsing filters. A library
directory request can fail while the current page of media is still available.
That failure keeps the page and selection visible, disables the old library
choices, and presents a localized recovery message above the featured media.
The message and Retry action have their own row outside the scrolling toolbar.

## Explicit retry

“重试媒体库” / “Retry libraries” reloads the current page through the existing
HomeStore operation. It keeps the selected library, media type, availability
filter and page number. It does not silently choose All libraries or issue an
automatic retry. The service still validates the selection on every request.
Detached library controls recheck the latest directory and current store before
changing a selection.

After a repeated directory failure, remote focus returns to Retry. After a
successful refresh, focus returns to the selected library if it still exists
in the current catalog. A disconnected or replaced store cannot receive the
old control's callback.

## Qualification and delivery

The generated emulator journey exercises successful browsing, two directory
failures, disabled stale controls, explicit remote retries, preserved filters,
and Chinese/English 150% text. Visibility checks compare full versus visible
bounds against the display window, including the recovery message and button.
In compact landscape with text at 150% or larger, the decorative featured
image is omitted so the library controls and photo grid remain usable. The
fixture requires at least 120 dp of grid viewport and navigates from the
recovered selected library to a visible photo and its viewer using the remote.
See [development evidence](DEVELOPMENT.md) for completed checks.

The changed source is TV v30. Signing, OTA publication, installation on an
Android TV/projector and household viewing remain separate delivery gates.
The client uses the existing Home TV access policy; service recovery has its
own operation gate.
