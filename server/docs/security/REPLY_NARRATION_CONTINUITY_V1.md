# Reply narration continuity

October 5, 2026. Web source improvement; not yet served on the household API.

After an explicit **Read reply aloud**, a reply offers **Pause reading**, then
**Resume reading**, alongside **Stop reading**. Chinese labels are 朗读回复、
暂停朗读、继续朗读 and 停止朗读. Resume continues the current installed-local
speech utterance; it does not submit a chat turn, fetch audio, repeat the reply
or start another model request. Original recordings remain a separate control.

The existing reply text and local-voice limits remain in force. Controls bind
to the mounted, authorized reply that owns the current narrator. Stop,
recording, reader/thread changes, backgrounding and disposal terminate that
ownership. An old Resume callback cannot restart terminated speech or control
a newer narrator. A native pause/resume exception cancels this narrator and
leaves the complete visible reply available for reading. Pausing does not
enable automatic listening, sending or narration of the next reply.

## Local evidence

- `node tests/security/test_story_narration_ui.cjs` passed: Chinese/English
  labels, same-chunk continuation, bounded full reply text, Stop while paused,
  stale-control ownership, denied scope and a synthetic native pause failure.
- `node tests/security/test_memory_community_browser.cjs` passed all **16**
  recorded checkpoints through protected ASGI and synthetic SQLite/media.
  It also checks no request on Pause/Resume and microphone ownership after
  cancelling a paused reply. There were no browser errors, external requests
  or recorded failures.
- The Chinese paused-controls render at 390 px and 150% text was inspected.
  Controls wrap within the reply. English labels have deterministic VM evidence;
  no new English browser render is claimed.

The browser uses a deterministic speech engine. Installed voice quality,
audible playback and physical-device behavior remain separate acceptance checks.
No schema, retention, provider, Windows service or APK change is included.
