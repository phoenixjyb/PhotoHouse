"""Explicit existing-SQLite adapter; no environment discovery or import-time I/O.

Deployment wiring must deliberately construct RuntimeConfiguration. Importing the
default app never imports this module or enables these connections. This module
never migrates, bootstraps, maps assets, opens listeners or starts workers.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import stat
import time

from .media import MediaRuntime
from .transport import AccessRuntime
from .memory_book_edition_schema import EDITION_REVISION, EDITION_TABLE, SOURCES_TABLE
from .family_note_identity_schema import IDENTITY_REVISION, IDENTITY_TABLES

REQUIRED_REVISION = 'a0c9d2e4f817'
EDITORIAL_REVISION = 'b1d7e4a9c230'
EDITION_REVISIONS = frozenset({EDITION_REVISION, IDENTITY_REVISION})
EDITORIAL_REVISIONS = frozenset({EDITORIAL_REVISION, *EDITION_REVISIONS})
SOURCE_REFERENCE_REVISIONS = frozenset({REQUIRED_REVISION, *EDITORIAL_REVISIONS})
COLLABORATION_REVISIONS = frozenset({'f7c3a9d2e614', *SOURCE_REFERENCE_REVISIONS})
COMPATIBLE_REVISIONS = {'d4a7e3c9b821', 'e6b2f8a1c903', *COLLABORATION_REVISIONS}
REQUIRED_TABLES = frozenset({
    'assets', 'captions', 'face_detections', 'access_accounts', 'access_sessions',
    'access_operators', 'access_libraries', 'access_memberships', 'access_invitations',
    'access_asset_libraries', 'access_audit', 'access_admission_key', 'access_attempts',
    'access_kdf_slot', 'access_provisioning_receipts', 'access_stories', 'access_story_revisions',
    'access_person_libraries', 'access_album_libraries', 'access_uploads', 'access_upload_transfers',
    'access_upload_auto_policies', 'access_upload_annotations',
    'access_annotation_derivations', 'access_annotation_tag_proposals',
    'access_memory_stories', 'access_memory_revisions',
    'access_memory_contributions', 'access_memory_contribution_derivations',
    'access_memory_books', 'access_memory_book_revisions', 'access_memory_conversations',
    'access_memory_jobs', 'access_memory_turns',
    'access_original_deletion_state',
    'access_memory_contribution_refs',
    'access_memory_book_editorial', 'access_memory_book_editorial_refs',
    EDITION_TABLE, SOURCES_TABLE, *IDENTITY_TABLES,
})


def required_tables_for_revision(revision):
    """Return the runtime table contract for one already-supported revision."""
    if type(revision) is not str or revision not in COMPATIBLE_REVISIONS:
        raise ValueError('Unsupported schema revision')
    required_tables = REQUIRED_TABLES
    if revision != IDENTITY_REVISION:
        required_tables = required_tables - IDENTITY_TABLES
    if revision not in EDITION_REVISIONS:
        required_tables = required_tables - {EDITION_TABLE, SOURCES_TABLE}
    if revision not in EDITORIAL_REVISIONS:
        required_tables = required_tables - {'access_memory_book_editorial', 'access_memory_book_editorial_refs'}
    if revision not in SOURCE_REFERENCE_REVISIONS:
        required_tables = required_tables - {'access_memory_contribution_refs'}
    if revision not in COLLABORATION_REVISIONS:
        required_tables = required_tables - {'access_memory_contributions',
            'access_memory_contribution_derivations', 'access_memory_books',
            'access_memory_book_revisions', 'access_memory_conversations',
            'access_memory_jobs', 'access_memory_turns', 'access_original_deletion_state'}
    if revision == 'd4a7e3c9b821':
        required_tables = required_tables - {'access_memory_stories', 'access_memory_revisions'}
    return required_tables


class RuntimeUnavailable(RuntimeError):
    """Generic configuration/storage refusal; never includes a path or SQL value."""


class AccessConnection(sqlite3.Connection):
    """Carries the explicitly configured deletion guard into domain services."""
    original_deletions = None


@dataclass(frozen=True)
class ExistingDatabase:
    path: Path
    timeout: float = 3.0
    read_only: bool = False
    original_deletions: object = None

    def __post_init__(self):
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ValueError('An explicit absolute database Path is required')
        if type(self.read_only) is not bool:
            raise ValueError('Explicit read-only flag required')
        if type(self.timeout) not in (int, float) or not 0 < self.timeout <= 10:
            raise ValueError('Database timeout must be between zero and ten seconds')

    @contextmanager
    def __call__(self):
        connection = None
        try:
            # SQLite mode=rw is essential: a typo must not create an empty DB.
            # Require a directly selected regular file; no symlink discovery.
            before = self.path.lstat()
            if not stat.S_ISREG(before.st_mode) or self.path.resolve(strict=True) != self.path:
                raise RuntimeUnavailable('Access unavailable')
            connection = sqlite3.connect(self.path.as_uri() + ('?mode=ro' if self.read_only else '?mode=rw'), uri=True, timeout=self.timeout, factory=AccessConnection)
            connection.original_deletions = self.original_deletions
            after = self.path.lstat()
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise RuntimeUnavailable('Access unavailable')
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            if self.read_only:
                connection.execute('PRAGMA query_only=ON')
            if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
                raise RuntimeUnavailable('Access unavailable')
            versions = connection.execute('SELECT version_num FROM alembic_version').fetchall()
            if len(versions) != 1 or versions[0][0] not in COMPATIBLE_REVISIONS:
                raise RuntimeUnavailable('Access unavailable')
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required_tables = required_tables_for_revision(versions[0][0])
            if not required_tables <= tables:
                raise RuntimeUnavailable('Access unavailable')
            if versions[0][0] == IDENTITY_REVISION:
                from .family_note_identity import verify_family_note_identity_schema
                from .transport import TransportError
                try:
                    verify_family_note_identity_schema(connection)
                except TransportError:
                    raise RuntimeUnavailable('Access unavailable') from None
            key = connection.execute('SELECT typeof(secret),length(secret) FROM access_admission_key WHERE id=1').fetchone()
            if key != ('blob', 32):
                raise RuntimeUnavailable('Access unavailable')
            # A bound primary never becomes safe to read by omitting the
            # journal configuration or turning intake off. Restoring an older
            # bound snapshot still requires replay against the external head.
            if (versions[0][0] in COLLABORATION_REVISIONS and self.original_deletions is None
                    and connection.execute('SELECT count(*) FROM access_original_deletion_state').fetchone()[0]):
                raise RuntimeUnavailable('Access unavailable')
            if self.original_deletions is not None:
                try:
                    self.original_deletions.assert_current(connection)
                except RuntimeError:
                    raise RuntimeUnavailable('Access unavailable') from None
        except (OSError, sqlite3.Error, ValueError, RuntimeUnavailable):
            if connection is not None:
                connection.close()
            raise RuntimeUnavailable('Access unavailable') from None
        try:
            yield connection
        finally:
            # Includes successful callers that forgot to commit and failed requests.
            # The domain layer owns commits; the adapter never commits on their behalf.
            if connection.in_transaction:
                connection.rollback()
            connection.close()


@dataclass(frozen=True, repr=False)
class RuntimeConfiguration:
    database: Path
    web_origin: str
    original_roots: tuple[Path, ...]
    derived_root: Path
    photo_cache: object = None
    discovery_indexes: tuple[Path, ...] = ()
    incoming_root: Path | None = None
    upload_review_enabled: bool = False
    annotation_intake_enabled: bool = False
    assistant_enabled: bool = False
    memory_collaboration_enabled: bool = False
    memory_originals_enabled: bool = False
    memory_generation_enabled: bool = False
    memory_editorial_enabled: bool = False
    memory_editions_enabled: bool = False
    family_note_erasure_enabled: bool = False
    story_title_suggestions_enabled: bool = False
    story_title_url: str | None = None
    story_title_model: str | None = None
    story_title_timeout_seconds: float = 30
    original_deletion_journal_path: Path | None = None
    original_deletion_namespace: str | None = None
    assistant_journal_path: Path | None = None
    assistant_asr_url: str | None = None
    assistant_asr_model: str | None = None
    assistant_asr_token: str | None = None
    assistant_tts_url: str | None = None
    assistant_tts_token: str | None = None
    update_root: Path | None = None
    assistant_asr_timeout_seconds: float = 45
    assistant_tts_timeout_seconds: float = 45

    def with_model_deployment(self, deployment, *, platform, credential_values=None, rollback=False):
        """Return explicit provider settings only; never build/serve or enable features."""
        from dataclasses import replace
        from .model_binding import project_configuration
        projection = project_configuration(deployment, target='assistant', platform=platform,
            feature_enabled=self.assistant_enabled, rollback=rollback)
        return replace(self, **projection.bind_fields(vars(self), credential_values=credential_values))

    def with_story_title_model_deployment(self, deployment, *, platform, rollback=False):
        """Select only the explicit title role; never enable it or invoke a model."""
        from dataclasses import replace
        from .model_binding import project_configuration
        projection = project_configuration(deployment, target='story-titles', platform=platform,
            feature_enabled=self.story_title_suggestions_enabled, rollback=rollback)
        return replace(self, **projection.bind_fields(vars(self)))

    def build_app(self, *, clock=time.time):
        """Build only; catalog storage opens lazily in the request worker.

        An explicitly selected journal is validated here; no file is created.

        No environment variables, .env, existing model settings, implicit roots,
        proxy trust or production credentials are consulted. Missing/wrong storage
        returns generic 503 from protected routes. The public code shell remains.

        `discovery_indexes` is empty by default, so discovery stays unmounted from
        every existing deployment's behaviour: with no paths the routes answer 503.
        Supplying paths is an explicit operator opt-in and the artifacts are loaded
        and validated here, so a missing or stale artifact refuses at startup rather
        than silently degrading to 503 and looking unconfigured.

        `incoming_root` is likewise unset by default, so upload answers 503 and no
        deployment gains a write surface by accident. Supplying it constructs the runtime
        here, which refuses an incoming root that overlaps an original root — the invariant
        that keeps an unassigned upload unservable.
        """
        if type(self.story_title_suggestions_enabled) is not bool:
            raise ValueError('Explicit title suggestion opt-in required')
        if type(self.story_title_timeout_seconds) not in (int, float) or not 0 < self.story_title_timeout_seconds <= 30:
            raise ValueError('Invalid title provider timeout')
        if (self.story_title_url is None) != (self.story_title_model is None):
            raise ValueError('Title URL and model must be selected together')
        if self.story_title_url is not None and not self.story_title_suggestions_enabled:
            raise ValueError('Title provider requires title suggestion opt-in')
        title_suggester = None
        if self.story_title_url is not None:
            from .story_titles import LocalStoryTitleSuggester
            title_suggester = LocalStoryTitleSuggester(url=self.story_title_url,
                model=self.story_title_model, timeout=self.story_title_timeout_seconds)
        if type(self.family_note_erasure_enabled) is not bool:
            raise ValueError('Explicit family note erasure opt-in required')
        if (self.original_deletion_journal_path is None) != (self.original_deletion_namespace is None):
            raise ValueError('Deletion journal and namespace must be selected together')
        if (self.annotation_intake_enabled or self.memory_originals_enabled or self.memory_generation_enabled or self.memory_editorial_enabled or self.memory_editions_enabled or self.family_note_erasure_enabled) and self.original_deletion_journal_path is None:
            raise ValueError('Original intake and generation require a deletion journal')
        original_deletions = None
        if self.original_deletion_journal_path is not None:
            selected = self.original_deletion_journal_path
            protected = (self.database, self.derived_root, *self.original_roots,
                         *self.discovery_indexes,
                         *((self.incoming_root,) if self.incoming_root else ()),
                         *((self.update_root,) if self.update_root else ()))
            if not isinstance(selected, Path) or any(selected.is_relative_to(other) or other.is_relative_to(selected)
                                                    for other in protected):
                raise ValueError('Deletion journal must be separate from runtime data')
            from .original_deletions import OriginalDeletionJournal
            original_deletions = OriginalDeletionJournal(selected, self.original_deletion_namespace)
        if self.family_note_erasure_enabled:
            original_deletions.require_family_format()
        database = ExistingDatabase(self.database, original_deletions=original_deletions)
        access = AccessRuntime(database, self.web_origin, clock=clock)
        media = MediaRuntime(self.original_roots, self.derived_root, self.photo_cache)
        discovery = None
        if self.discovery_indexes:
            from .discovery_index import runtime as discovery_runtime
            discovery = discovery_runtime(access, self.discovery_indexes)
        upload = None
        if self.incoming_root is not None:
            from .upload import UploadRuntime
            upload = UploadRuntime(access, self.incoming_root, self.original_roots)
        if type(self.upload_review_enabled) is not bool:
            raise ValueError('Explicit review opt-in required')
        if type(self.annotation_intake_enabled) is not bool:
            raise ValueError('Explicit annotation intake opt-in required')
        if type(self.assistant_enabled) is not bool:
            raise ValueError('Explicit assistant opt-in required')
        for timeout in (self.assistant_asr_timeout_seconds, self.assistant_tts_timeout_seconds):
            if type(timeout) not in (int, float) or not 0 < timeout <= 60:
                raise ValueError('Invalid assistant provider timeout')
        if (self.assistant_asr_url is None) != (self.assistant_asr_model is None):
            raise ValueError('ASR URL and model must be selected together')
        if self.assistant_asr_url is not None and not self.assistant_enabled:
            raise ValueError('Assistant ASR requires assistant opt-in')
        if self.assistant_tts_url is not None and not self.assistant_enabled:
            raise ValueError('Assistant TTS requires assistant opt-in')
        assistant_journal = None
        if self.assistant_journal_path is not None:
            if not self.assistant_enabled:
                raise ValueError('Journal requires assistant opt-in')
            selected = Path(self.assistant_journal_path)
            protected = (self.database, self.derived_root, *self.original_roots,
                         *self.discovery_indexes,
                         *((self.incoming_root,) if self.incoming_root else ()),
                         *((self.update_root,) if self.update_root else ()))
            if any(selected.is_relative_to(other) or other.is_relative_to(selected)
                   for other in protected):
                raise ValueError('Journal must be separate from runtime data')
            from .assistant_journal import Journal
            assistant_journal = Journal(selected, clock=clock)
        assistant_asr = None
        if self.assistant_asr_url is not None:
            from .assistant_speech import LocalAssistantAsr
            assistant_asr = LocalAssistantAsr(url=self.assistant_asr_url,
                model=self.assistant_asr_model, token=self.assistant_asr_token,
                timeout=self.assistant_asr_timeout_seconds)
        assistant_tts = None
        if self.assistant_tts_url is not None:
            from .assistant_speech import LocalAssistantTts
            assistant_tts = LocalAssistantTts(url=self.assistant_tts_url,
                token=self.assistant_tts_token, timeout=self.assistant_tts_timeout_seconds)
        review = None
        if self.upload_review_enabled:
            from .upload_review import UploadReviewRuntime
            review = UploadReviewRuntime(upload, self.photo_cache)
        from ..main import create_app
        return create_app(access_runtime=access, media_runtime=media, discovery_runtime=discovery,
                          upload_runtime=upload, upload_review_runtime=review,
                          annotation_intake_enabled=self.annotation_intake_enabled,
                          assistant_enabled=self.assistant_enabled,
                          memory_collaboration_enabled=self.memory_collaboration_enabled,
                          memory_originals_enabled=self.memory_originals_enabled,
                          memory_generation_enabled=self.memory_generation_enabled,
                          memory_editorial_enabled=self.memory_editorial_enabled,
                          memory_editions_enabled=self.memory_editions_enabled,
                          family_note_erasure_enabled=self.family_note_erasure_enabled,
                          story_title_suggester=title_suggester,
                          assistant_asr=assistant_asr, assistant_tts=assistant_tts,
                          assistant_journal=assistant_journal,
                          update_root=self.update_root)
