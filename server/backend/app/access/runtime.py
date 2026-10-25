"""Explicit existing-SQLite adapter; no environment discovery or import-time I/O.

Deployment wiring must deliberately construct RuntimeConfiguration. Importing the
default app never imports this module or enables these connections. This module
never migrates, bootstraps, maps assets, opens listeners or starts workers.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import math
import sqlite3
import stat
import time

from .media import MediaRuntime
from .transport import AccessRuntime
from .memory_book_edition_schema import EDITION_REVISION, EDITION_TABLE, SOURCES_TABLE
from .family_note_identity_schema import IDENTITY_REVISION, IDENTITY_TABLES
from .memory_group_schema import GROUP_REVISIONS, TABLE as GROUP_TABLE, REVISION_TABLE as GROUP_HISTORY

from .photo_stack_schema import REVISION as PHOTO_STACK_REVISION, TABLES as PHOTO_STACK_TABLES
from .semantic_request_snapshot import RequestSnapshotConnection, RequestSourceSnapshot

REQUIRED_REVISION = 'a0c9d2e4f817'
EDITORIAL_REVISION = 'b1d7e4a9c230'
IDENTITY_REVISIONS = frozenset({IDENTITY_REVISION, *GROUP_REVISIONS})
EDITION_REVISIONS = frozenset({EDITION_REVISION, *IDENTITY_REVISIONS})
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
    EDITION_TABLE, SOURCES_TABLE, *IDENTITY_TABLES, GROUP_TABLE, GROUP_HISTORY, *PHOTO_STACK_TABLES,
})


def required_tables_for_revision(revision):
    """Return the runtime table contract for one already-supported revision."""
    if type(revision) is not str or revision not in COMPATIBLE_REVISIONS:
        raise ValueError('Unsupported schema revision')
    required_tables = REQUIRED_TABLES
    if revision != PHOTO_STACK_REVISION:
        required_tables = required_tables - set(PHOTO_STACK_TABLES)
    if revision not in GROUP_REVISIONS:
        required_tables = required_tables - {GROUP_TABLE, GROUP_HISTORY}
    if revision not in IDENTITY_REVISIONS:
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
            if versions[0][0] == PHOTO_STACK_REVISION:
                from .photo_stack_schema import available as photo_stack_schema_available
                if not photo_stack_schema_available(connection):
                    raise RuntimeUnavailable('Access unavailable')
            if versions[0][0] in GROUP_REVISIONS:
                from .memory_group_schema import verify_memory_group_schema
                if not verify_memory_group_schema(connection):
                    raise RuntimeUnavailable('Access unavailable')
            if versions[0][0] in IDENTITY_REVISIONS:
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

    @contextmanager
    def source_snapshot(self):
        """Open a fresh, guarded read-only connection for one semantic request."""
        connection = None
        try:
            before = self.path.lstat()
            if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                    or before.st_nlink != 1 or self.path.resolve(strict=True) != self.path):
                raise RuntimeUnavailable('Access unavailable')
            from .semantic_request_snapshot import path_identity
            before_identity = path_identity(self.path)
            if before_identity is None:
                raise RuntimeUnavailable('Access unavailable')
            connection = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True,
                timeout=self.timeout, factory=RequestSnapshotConnection)
            connection.original_deletions = self.original_deletions
            after = self.path.lstat()
            after_identity = path_identity(self.path)
            if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                    or after_identity is None
                    or before_identity[0] != after_identity[0]
                    or (before_identity[1][0][1] is not None
                        and before_identity[1][0] != after_identity[1][0])):
                raise RuntimeUnavailable('Access unavailable')
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA query_only=ON')
            if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
                raise RuntimeUnavailable('Access unavailable')
            versions = connection.execute('SELECT version_num FROM alembic_version').fetchall()
            if len(versions) != 1 or versions[0][0] not in COMPATIBLE_REVISIONS:
                raise RuntimeUnavailable('Access unavailable')
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not required_tables_for_revision(versions[0][0]) <= tables:
                raise RuntimeUnavailable('Access unavailable')
            if versions[0][0] == PHOTO_STACK_REVISION:
                from .photo_stack_schema import available as photo_stack_schema_available
                if not photo_stack_schema_available(connection):
                    raise RuntimeUnavailable('Access unavailable')
            if versions[0][0] in GROUP_REVISIONS:
                from .memory_group_schema import verify_memory_group_schema
                if not verify_memory_group_schema(connection):
                    raise RuntimeUnavailable('Access unavailable')
            if versions[0][0] in IDENTITY_REVISIONS:
                from .family_note_identity import verify_family_note_identity_schema
                from .transport import TransportError
                try:
                    verify_family_note_identity_schema(connection)
                except TransportError:
                    raise RuntimeUnavailable('Access unavailable') from None
            key = connection.execute(
                'SELECT typeof(secret),length(secret) FROM access_admission_key WHERE id=1').fetchone()
            if key != ('blob', 32):
                raise RuntimeUnavailable('Access unavailable')
            if (versions[0][0] in COLLABORATION_REVISIONS and self.original_deletions is None
                    and connection.execute(
                        'SELECT count(*) FROM access_original_deletion_state').fetchone()[0]):
                raise RuntimeUnavailable('Access unavailable')
            if self.original_deletions is not None:
                try:
                    self.original_deletions.assert_current(connection)
                except RuntimeError:
                    raise RuntimeUnavailable('Access unavailable') from None
            checked_identity = path_identity(self.path)
            from .semantic_request_snapshot import _stable_during_sqlite_setup
            if (checked_identity is None or checked_identity[0] != after_identity[0]
                    or not _stable_during_sqlite_setup(before_identity, checked_identity)):
                raise RuntimeUnavailable('Access unavailable')
            connection.seal_read_only_environment()
            opened_identity = path_identity(self.path)
            if (opened_identity is None
                    or not _stable_during_sqlite_setup(checked_identity, opened_identity)):
                raise RuntimeUnavailable('Access unavailable')
            connection.bind_open_identity(self.path, opened_identity)
        except (OSError, sqlite3.Error, ValueError, RuntimeUnavailable):
            if connection is not None:
                connection.close()
            raise RuntimeUnavailable('Access unavailable') from None
        try:
            yield connection
        finally:
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
    memory_groups_enabled: bool = False
    memory_group_vectors: object = None
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
    assistant_workspace_path: Path | None = None
    assistant_kinship_path: Path | None = None
    assistant_asr_url: str | None = None
    assistant_asr_model: str | None = None
    assistant_asr_token: str | None = None
    assistant_tts_url: str | None = None
    assistant_tts_token: str | None = None
    update_root: Path | None = None
    assistant_asr_timeout_seconds: float = 45
    assistant_tts_timeout_seconds: float = 45
    assistant_reply_speech_enabled: bool = False
    assistant_saved_memory_cards_enabled: bool = False
    assistant_intent_url: str | None = None
    assistant_intent_model: str | None = None
    assistant_intent_timeout_seconds: float = 20
    semantic_configuration_path: Path | None = None
    assistant_semantic_search_enabled: bool = False
    selected_story_provider: object = None
    selected_story_drafts_enabled: bool = False
    selected_story_ui_enabled: bool = False

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
        # Validate this boundary before storage is opened or optional providers
        # are constructed. This mirrors create_app while keeping this a pure
        # object-injection point.
        if (type(self.selected_story_drafts_enabled) is not bool or
                (self.selected_story_drafts_enabled and self.selected_story_provider is None)):
            raise ValueError('Explicit selected-story API opt-in and provider required')
        if (type(self.selected_story_ui_enabled) is not bool or
                (self.selected_story_ui_enabled and not self.selected_story_drafts_enabled)):
            raise ValueError('Explicit selected-story UI and API opt-in required')
        if type(self.memory_collaboration_enabled) is not bool:
            raise ValueError('Explicit memory opt-in required')
        if self.selected_story_provider is not None and not self.memory_collaboration_enabled:
            raise ValueError('Selected-story provider requires collaboration opt-in')
        if (type(self.assistant_semantic_search_enabled) is not bool or
                (self.semantic_configuration_path is not None and
                 not self.assistant_semantic_search_enabled)):
            raise ValueError('Explicit semantic configuration opt-in required')
        if self.assistant_semantic_search_enabled and (
                not self.assistant_enabled or self.assistant_workspace_path is None or
                not self.discovery_indexes or self.semantic_configuration_path is None):
            raise ValueError('Semantic search requires assistant, workspace and discovery configuration')
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
        if (type(self.assistant_intent_timeout_seconds) not in (int, float) or
                not 0 < self.assistant_intent_timeout_seconds <= 45 or
                not math.isfinite(self.assistant_intent_timeout_seconds)):
            raise ValueError('Invalid assistant intent timeout')
        if (self.assistant_intent_url is None) != (self.assistant_intent_model is None):
            raise ValueError('Intent URL and model must be selected together')
        if self.assistant_intent_url is not None and (
                not self.assistant_enabled or type(self.assistant_intent_url) is not str or
                type(self.assistant_intent_model) is not str):
            raise ValueError('Assistant intent planner requires explicit assistant opt-in and settings')
        assistant_kinship_provider = None
        if self.assistant_kinship_path is not None:
            selected = self.assistant_kinship_path
            protected = (self.database, self.derived_root, *self.original_roots,
                         *self.discovery_indexes,
                         *((self.incoming_root,) if self.incoming_root else ()),
                         *((self.update_root,) if self.update_root else ()),
                         *((self.assistant_journal_path,) if self.assistant_journal_path else ()),
                         *((self.assistant_workspace_path,) if self.assistant_workspace_path else ()),
                         *((self.original_deletion_journal_path,)
                           if self.original_deletion_journal_path else ()))
            if (not self.assistant_enabled or not isinstance(selected, Path) or
                    not selected.is_absolute() or '..' in selected.parts or
                    any(selected.is_relative_to(other) or other.is_relative_to(selected)
                        for other in protected)):
                raise ValueError('Assistant kinship catalog must be explicit and separate from runtime data')
            from .kinship import PrivateKinshipProvider
            assistant_kinship_provider = PrivateKinshipProvider(
                selected, source_root=Path(__file__).resolve().parents[4])
        if type(self.assistant_reply_speech_enabled) is not bool:
            raise ValueError('Explicit private reply speech opt-in required')
        if type(self.assistant_saved_memory_cards_enabled) is not bool:
            raise ValueError('Explicit saved-memory cards opt-in required')
        if self.assistant_saved_memory_cards_enabled and (not self.assistant_enabled or
                not self.memory_collaboration_enabled or self.assistant_workspace_path is None):
            raise ValueError('Saved-memory cards require assistant, workspace and collaboration')
        for timeout in (self.assistant_asr_timeout_seconds, self.assistant_tts_timeout_seconds):
            if type(timeout) not in (int, float) or not 0 < timeout <= 60:
                raise ValueError('Invalid assistant provider timeout')
        if (self.assistant_asr_url is None) != (self.assistant_asr_model is None):
            raise ValueError('ASR URL and model must be selected together')
        if self.assistant_asr_url is not None and not self.assistant_enabled:
            raise ValueError('Assistant ASR requires assistant opt-in')
        if self.assistant_tts_url is not None and not self.assistant_enabled:
            raise ValueError('Assistant TTS requires assistant opt-in')
        if (self.assistant_reply_speech_enabled and
                (not self.assistant_enabled or self.assistant_tts_url is None or
                 self.assistant_journal_path is None or self.assistant_workspace_path is None)):
            raise ValueError('Private reply speech requires assistant TTS, journal and workspace')
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
        assistant_workspace_store = None
        if self.assistant_workspace_path is not None:
            if not self.assistant_enabled:
                raise ValueError('Assistant workspace requires assistant opt-in')
            selected = self.assistant_workspace_path
            protected = (self.database, self.derived_root, *self.original_roots,
                         *self.discovery_indexes,
                         *((self.incoming_root,) if self.incoming_root else ()),
                         *((self.update_root,) if self.update_root else ()),
                         *((self.assistant_journal_path,) if self.assistant_journal_path else ()),
                         *((self.original_deletion_journal_path,) if self.original_deletion_journal_path else ()))
            if (not isinstance(selected, Path) or not selected.is_absolute() or
                    any(selected.is_relative_to(other) or other.is_relative_to(selected)
                        for other in protected)):
                raise ValueError('Assistant workspace must be separate from runtime data')
            from .assistant_workspace_store import AssistantWorkspaceStore
            # This opens only an existing validated store in mode=rw. It never
            # initializes or creates the optional private database.
            assistant_workspace_store = AssistantWorkspaceStore(selected, clock=clock)
        semantic_search_runtime = None
        if self.assistant_semantic_search_enabled:
            from .semantic_configuration import load_semantic_runtime
            semantic_protected_paths = (self.database, self.derived_root, *self.original_roots,
                *self.discovery_indexes,
                *((self.incoming_root,) if self.incoming_root else ()),
                *((self.update_root,) if self.update_root else ()),
                *((self.assistant_workspace_path,) if self.assistant_workspace_path else ()),
                *((self.assistant_journal_path,) if self.assistant_journal_path else ()),
                *((self.assistant_kinship_path,) if self.assistant_kinship_path else ()),
                *((self.original_deletion_journal_path,)
                  if self.original_deletion_journal_path else ()))
            semantic_search_runtime = load_semantic_runtime(
                self.semantic_configuration_path, discovery=discovery,
                source_root=Path(__file__).resolve().parents[4],
                protected_paths=semantic_protected_paths)
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
        assistant_intent_planner = None
        if self.assistant_intent_url is not None:
            from .search_intent_local import LocalIntentPlanner
            assistant_intent_planner = LocalIntentPlanner(url=self.assistant_intent_url,
                model=self.assistant_intent_model, timeout=self.assistant_intent_timeout_seconds)
        review = None
        if self.upload_review_enabled:
            from .upload_review import UploadReviewRuntime
            review = UploadReviewRuntime(upload, self.photo_cache)
        from ..main import create_app
        return create_app(access_runtime=access, media_runtime=media, discovery_runtime=discovery,
                          upload_runtime=upload, upload_review_runtime=review,
                          annotation_intake_enabled=self.annotation_intake_enabled,
                          assistant_enabled=self.assistant_enabled,
                          memory_groups_enabled=self.memory_groups_enabled,
                          memory_group_vectors=self.memory_group_vectors,
                          memory_collaboration_enabled=self.memory_collaboration_enabled,
                          memory_originals_enabled=self.memory_originals_enabled,
                          memory_generation_enabled=self.memory_generation_enabled,
                          memory_editorial_enabled=self.memory_editorial_enabled,
                          memory_editions_enabled=self.memory_editions_enabled,
                          family_note_erasure_enabled=self.family_note_erasure_enabled,
                          story_title_suggester=title_suggester,
                          assistant_asr=assistant_asr, assistant_tts=assistant_tts,
                          assistant_journal=assistant_journal,
                          assistant_workspace_store=assistant_workspace_store,
                          assistant_kinship_provider=assistant_kinship_provider,
                          assistant_intent_planner=assistant_intent_planner,
                          assistant_reply_speech_enabled=self.assistant_reply_speech_enabled,
                          assistant_saved_memory_cards_enabled=self.assistant_saved_memory_cards_enabled,
                          semantic_search_runtime=semantic_search_runtime,
                          assistant_semantic_search_enabled=self.assistant_semantic_search_enabled,
                          selected_story_provider=self.selected_story_provider,
                          selected_story_drafts_enabled=self.selected_story_drafts_enabled,
                          selected_story_ui_enabled=self.selected_story_ui_enabled,
                          update_root=self.update_root)
