"""Qualify experimental oral-history intake using generated private fixtures only.

This source-only runner is not production admission, transport, or erasure approval.
It accepts only --out, creates a new private generated fixture directory, and never
exports section audio. On Windows it uses the bounded native child policy.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import sqlite3
import sys
import uuid

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / 'backend'))
sys.path.insert(0, str(SERVER / 'scripts'))

from app.access.private_storage import require_private_directory, require_private_file

REPORT = 'oral-history-qualification.json'
FAILURE = 'oral-history-qualification-failure.json'
MAX_REPORT_BYTES = 8192
NOW = 2_000_000_000
LIBRARY = 'synthetic-library'
AUTHOR_TOKEN = 'd' * 43
OWNER_TOKEN = 'a' * 43
FOREIGN_TOKEN = 'c' * 43

CASES = (
    'fixture_a0_seeded', 'fixture_schema_installed', 'v3_journal_bound',
    'guarded_v3_to_v4_upgrade', 'short_then_full_section_receipts',
    'exact_retries_and_payload_conflicts', 'author_only_library_scoped_access',
    'withdrawal_retains_source_and_content_free_ledger',
    'stale_prefix_refused_then_replayed', 'corrupt_source_refused',
)


def _validate_output(target, *, windows=None):
    target = Path(target)
    if '?' in str(target) or '#' in str(target):
        raise ValueError('canonical_output_path_required')
    if (not target.is_absolute() or '..' in target.parts or os.path.lexists(target)
            or target.parent.resolve(strict=True) != target.parent):
        raise ValueError('new_absolute_output_required')
    if windows is None:
        windows = os.name == 'nt'
    win = PureWindowsPath(str(target))
    if win.anchor.startswith(('\\\\', '//')):
        raise ValueError('local_output_required')
    if windows:
        units = lambda value: len(str(value).encode('utf-16le')) // 2
        database_names = ('main.sqlite', 'oral-journal.sqlite',
                          'old-primary-prefix.sqlite', 'clean-after-replay.sqlite')
        paths = [win / name for name in (REPORT, FAILURE, *database_names)]
        if (any(units(path) > 259 for path in paths)
                or any(units(win / name) + len('-journal') > 259 for name in database_names)
                or any(units(parent) > 247 for parent in (win, *win.parents))
                or units(sys.executable) > 259 or units(Path(__file__).resolve()) > 259):
            raise ValueError('windows_fixture_path_too_long')
    for parent in (target.parent, *target.parent.parents):
        info = parent.lstat()
        if (not parent.is_dir() or parent.is_symlink()
                or getattr(info, 'st_file_attributes', 0) & 0x400):
            raise ValueError('direct_private_parent_required')
    require_private_directory(target.parent)
    return target


def _private_file(path):
    require_private_file(path)


def _write_json(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'w', encoding='ascii', newline='\n') as stream:
        _private_file(path)
        json.dump(value, stream, sort_keys=True, separators=(',', ':'))
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
        _private_file(path)


def _create_private_file(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    os.close(descriptor)
    _private_file(path)


def _copy_fixture_file(source, destination, root):
    if source.parent != root or destination.parent != root:
        raise ValueError('fixture_copy_outside_output')
    _private_file(source)
    shutil.copyfile(source, destination)
    _private_file(source)
    os.chmod(destination, 0o600)
    _private_file(destination)


def _report(native):
    return {
        'status': 'passed', 'version': 1, 'synthetic_only': True,
        'experimental_fixture_schema': True, 'native_windows': native,
        'production_admission_available': False,
        'production_transport_available': False,
        'production_erasure_available': False,
        'production_database_opened': False,
        'family_media_opened': False,
        'provider_or_model_used': False,
        'socket_listener_started': False,
        'network_accessed': False,
        'workers_executed': False,
        'services_changed': False,
        'tasks_changed': False,
        'published': False,
        'source_audio_exported': False,
        'cases': {name: True for name in CASES},
        'groups': {
            'journal_upgrade_and_recovery': 3,
            'private_durable_intake': 3,
            'identity_scope_withdrawal': 3,
            'source_integrity': 1,
        },
        'accepted_counts_before_restore': {'sessions': 1, 'sections': 2,
            'mutations': 3, 'journal_recordings': 1},
        'final_fixture_counts': {'sessions': 1, 'sections': 1,
            'mutations': 2, 'journal_recordings': 1},
    }


def _validate_report(value, expected):
    if type(value) is not dict or value != expected:
        return False
    bool_fields = ('synthetic_only', 'experimental_fixture_schema', 'native_windows',
        'production_admission_available', 'production_transport_available',
        'production_erasure_available', 'production_database_opened',
        'family_media_opened', 'provider_or_model_used', 'socket_listener_started',
        'network_accessed', 'workers_executed', 'services_changed', 'tasks_changed',
        'published', 'source_audio_exported')
    return (type(value.get('status')) is str and type(value.get('version')) is int
            and all(type(value.get(name)) is bool for name in bool_fields)
            and type(value.get('cases')) is dict
            and all(type(item) is bool for item in value['cases'].values())
            and type(value.get('groups')) is dict
            and all(type(item) is int for item in value['groups'].values())
            and all(type(value.get(group)) is dict and
                    all(type(item) is int for item in value[group].values())
                    for group in ('accepted_counts_before_restore', 'final_fixture_counts')))


def _assert(condition, code):
    if not condition:
        raise RuntimeError(code)


def _expect(error_type, action, code):
    try:
        action()
    except error_type:
        return
    raise RuntimeError(code)


def _expect_status(status, action, code):
    from app.access.transport import TransportError
    try:
        action()
    except TransportError as error:
        _assert(error.status == status, code)
        return
    raise RuntimeError(code)


def _wav(frames):
    import struct
    payload = b'\x19\x00' * frames
    return struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', len(payload) + 36,
        b'WAVE', b'fmt ', 16, 1, 1, 16000, 32000, 2, 16, b'data', len(payload)) + payload


def _load_helpers():
    # This is a runtime source helper, not an import of test code. Its seed/migration
    # writes only the caller-selected generated database.
    import qualify_private_assistant as fixture
    fixture._load_runtime()
    return fixture


def run(output):
    target = _validate_output(Path(output))
    target.mkdir(mode=0o700)
    require_private_directory(target)
    phase = 'a0_fixture'
    db = journal = None
    try:
        from app.access.oral_history_schema import install_fixture_schema, SESSION, SECTION, MUTATION
        from app.access.original_deletions import OriginalDeletionJournal, OriginalDeletionError
        from app.access.oral_history_intake import OralHistoryIntake
        from app.access.service import AccessService, AccessDenied
        from app.access.transport import TransportError

        fixture = _load_helpers()
        primary = target / 'main.sqlite'
        fixture._seed_main(primary)
        db = sqlite3.connect(primary, timeout=10)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA secure_delete=ON')
        _assert(db.execute('PRAGMA foreign_keys').fetchone()[0] == 1, 'fixture_foreign_keys_unavailable')
        author = str(uuid.uuid4())
        db.execute('''INSERT INTO access_accounts(id,phone_login,password_hash,state,display_name)
                      VALUES(?,?,'synthetic-unused-password-hash','active','Generated narrator')''',
                   (author, '+12025550999'))
        db.execute('''INSERT INTO access_sessions(digest,account_id,expires_at,revoked)
                      VALUES(?,?,?,0)''', (fixture.session_digest(AUTHOR_TOKEN), author, (1 << 63) - 1))
        db.execute('''INSERT INTO access_memberships(account_id,library_id,status,role,revision,
                      expires_at,originals,approved_by) VALUES(?,?,'approved','viewer',1,NULL,0,?)''',
                   (author, LIBRARY, fixture.OWNER))
        db.commit()
        # This table belongs to a later production deletion rollout; generated empty
        # prerequisite only, never a migration/admission change.
        db.execute('CREATE TABLE IF NOT EXISTS access_upload_annotations(id TEXT PRIMARY KEY)')
        db.execute('BEGIN IMMEDIATE')
        install_fixture_schema(db)
        db.commit()
        namespace = str(uuid.uuid4())
        journal_path = target / 'oral-journal.sqlite'
        journal = OriginalDeletionJournal.initialize(journal_path, namespace, format_version=3)
        journal.bind(db)
        _assert(journal.head()[1] == 0, 'fresh_v3_bind_invalid')

        phase = 'v3_upgrade'
        before = journal.path.read_bytes()
        db.execute('BEGIN IMMEDIATE')
        _expect(OriginalDeletionError,
            lambda: journal.upgrade_oral_format(db, expected_head=journal.head(),
                precommit_guard=lambda _db: (_ for _ in ()).throw(OriginalDeletionError('guard refused'))),
            'upgrade_guard_was_ignored')
        db.rollback()
        _assert(journal.path.read_bytes() == before, 'guard_changed_v3_journal')
        _expect(OriginalDeletionError, journal.require_oral_format,
                'v3_journal_accepted_oral_withdrawal')
        db.execute('BEGIN IMMEDIATE')
        head = journal.head()
        _assert(journal.upgrade_oral_format(db, expected_head=head) == head, 'v4_upgrade_head_changed')
        db.commit()
        journal.require_oral_format()

        phase = 'intake_and_scope'
        db.close()
        db = sqlite3.connect(primary, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA secure_delete=ON')
        access = AccessService(db, clock=lambda: NOW)
        access.original_deletions = journal
        intake = OralHistoryIntake(access, enabled=True, withdrawal_enabled=True, journal=journal)
        create_body = {'request_id': str(uuid.uuid4()), 'title': 'Synthetic interview',
            'subject_label': 'Generated subject', 'narrator_label': 'Generated speaker',
            'language': 'en', 'processing_consent': True}
        created = intake.create(AUTHOR_TOKEN, LIBRARY, create_body)
        _assert(intake.create(AUTHOR_TOKEN, LIBRARY, create_body) == created, 'create_retry_changed_receipt')
        _expect_status(409,
            lambda: intake.create(AUTHOR_TOKEN, LIBRARY, {**create_body, 'title': 'Changed title'}),
            'changed_create_retry_accepted')
        short_audio, full_audio = _wav(3200), _wav(320000)
        short_args = {'request_id': str(uuid.uuid4()), 'expected_revision': created['revision'],
                      'ordinal': 0, 'audio': short_audio}
        short = intake.append(AUTHOR_TOKEN, LIBRARY, created['session_id'], **short_args)
        _assert(short['next_ordinal'] == 1 and short['total_frames'] == 3200
                and short['section_sha256'] == hashlib.sha256(short_audio).hexdigest(),
                'short_section_order_invalid')
        db.close()
        db = sqlite3.connect(primary, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA secure_delete=ON')
        access = AccessService(db, clock=lambda: NOW)
        access.original_deletions = journal
        intake = OralHistoryIntake(access, enabled=True, withdrawal_enabled=True, journal=journal)
        _assert(intake.create(AUTHOR_TOKEN, LIBRARY, create_body) == created,
                'create_receipt_changed_after_reopen')
        _assert(intake.append(AUTHOR_TOKEN, LIBRARY, created['session_id'], **short_args) == short,
                'short_receipt_changed_after_reopen')
        _assert(intake.audio(AUTHOR_TOKEN, LIBRARY, created['session_id'], 0) == short_audio,
                'short_source_changed_after_reopen')
        prefix = target / 'old-primary-prefix.sqlite'
        _create_private_file(prefix)
        with closing(sqlite3.connect(prefix)) as backup:
            db.backup(backup)
        _private_file(prefix)
        full_args = {'request_id': str(uuid.uuid4()), 'expected_revision': short['revision'],
                     'ordinal': 1, 'audio': full_audio}
        full = intake.append(AUTHOR_TOKEN, LIBRARY, created['session_id'], **full_args)
        _assert(full['next_ordinal'] == 2 and full['total_frames'] == 323200
                and full['section_sha256'] == hashlib.sha256(full_audio).hexdigest(),
                'full_section_order_invalid')
        db.close()
        db = sqlite3.connect(primary, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA secure_delete=ON')
        access = AccessService(db, clock=lambda: NOW)
        access.original_deletions = journal
        intake = OralHistoryIntake(access, enabled=True, withdrawal_enabled=True, journal=journal)
        _assert(intake.append(AUTHOR_TOKEN, LIBRARY, created['session_id'], **full_args) == full,
                'full_receipt_changed_after_reopen')
        _assert(intake.audio(AUTHOR_TOKEN, LIBRARY, created['session_id'], 1) == full_audio,
                'full_source_changed_after_reopen')
        _assert(intake.append(AUTHOR_TOKEN, LIBRARY, created['session_id'], **short_args) == short,
                'append_retry_changed_receipt')
        _expect_status(409,
            lambda: intake.append(AUTHOR_TOKEN, LIBRARY, created['session_id'],
                **{**short_args, 'audio': _wav(3201)}), 'changed_append_retry_accepted')

        phase = 'authorization_and_withdrawal'
        _expect(AccessDenied, lambda: intake.status(OWNER_TOKEN, LIBRARY, created['session_id']),
                'library_owner_read_recording')
        _expect(AccessDenied, lambda: intake.withdraw(OWNER_TOKEN, LIBRARY, created['session_id'],
            request_id=str(uuid.uuid4()), expected_revision=full['revision']),
            'library_owner_withdrew_recording')
        _assert(journal.head()[1] == 0, 'owner_attempt_changed_journal')
        _expect(AccessDenied, lambda: intake.status(FOREIGN_TOKEN, 'synthetic-other-library', created['session_id']),
                'foreign_library_read_recording')
        _expect(AccessDenied, lambda: intake.status(AUTHOR_TOKEN, 'synthetic-other-library', created['session_id']),
                'author_cross_library_read_recording')
        raw_audio = intake.audio(AUTHOR_TOKEN, LIBRARY, created['session_id'], 1)
        withdraw_args = {'request_id': str(uuid.uuid4()), 'expected_revision': full['revision']}
        withdrawn = intake.withdraw(AUTHOR_TOKEN, LIBRARY, created['session_id'], **withdraw_args)
        _assert(intake.withdraw(AUTHOR_TOKEN, LIBRARY, created['session_id'], **withdraw_args) == withdrawn,
                'withdrawal_retry_changed_receipt')
        _expect(AccessDenied, lambda: intake.status(AUTHOR_TOKEN, LIBRARY, created['session_id']),
                'withdrawn_status_visible')
        _assert(db.execute(f'SELECT audio FROM {SECTION} WHERE session_id=? AND ordinal=1',
                           (created['session_id'],)).fetchone()[0] == raw_audio,
                'withdrawal_did_not_retain_source')
        db.execute('BEGIN')
        ledger_row = journal.oral_record(db, created['session_id'])
        db.rollback()
        _assert(ledger_row['oral_binding_json'] is not None, 'withdrawal_binding_missing')
        binding = ledger_row['oral_binding_json']
        _assert(all(secret not in binding for secret in
                    ('Synthetic interview', 'Generated subject', 'Generated speaker', 'audio')),
                'withdrawal_ledger_contains_content')
        counts = tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                       for table in (SESSION, SECTION, MUTATION))
        withdrawal_head = journal.head()
        _assert(counts == (1, 2, 3) and withdrawal_head[1] == 1,
                'generated_receipt_counts_changed')

        phase = 'stale_prefix_replay'
        db.close()
        _copy_fixture_file(prefix, primary, target)
        db = sqlite3.connect(primary, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA secure_delete=ON')
        stale_access = AccessService(db, clock=lambda: NOW)
        stale_access.original_deletions = journal
        stale_intake = OralHistoryIntake(stale_access, enabled=True, withdrawal_enabled=True,
                                         journal=journal)
        _expect_status(503, lambda: stale_intake.status(AUTHOR_TOKEN, LIBRARY, created['session_id']),
            'stale_primary_prefix_was_admitted')
        _assert(journal.review(db)['pending_count'] == 1, 'stale_prefix_review_missing')
        replay = journal.replay(db, expected_head=withdrawal_head)
        _assert(replay[-1] == 1, 'reviewed_prefix_replay_did_not_apply')
        access = AccessService(db, clock=lambda: NOW)
        access.original_deletions = journal
        replay_intake = OralHistoryIntake(access, enabled=True, withdrawal_enabled=True, journal=journal)
        _expect(AccessDenied, lambda: replay_intake.audio(AUTHOR_TOKEN, LIBRARY,
            created['session_id'], 0), 'replayed_withdrawal_exposed_audio')

        phase = 'corrupt_source_refusal'
        # A private backup lets the integrity refusal be tested without leaving a
        # mutated primary behind. Journal replay also validates restored audio.
        clean = target / 'clean-after-replay.sqlite'
        _create_private_file(clean)
        with closing(sqlite3.connect(clean)) as backup:
            db.backup(backup)
        _private_file(clean)
        corrupted = bytearray(short_audio)
        corrupted[-1] ^= 0x01
        trigger = db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='oral_history_section_update'").fetchone()
        db.execute('DROP TRIGGER oral_history_section_update')
        db.execute(f'UPDATE {SECTION} SET audio=? WHERE session_id=? AND ordinal=0',
                   (bytes(corrupted), created['session_id']))
        db.execute(trigger[0])
        db.commit()
        _expect(OriginalDeletionError, lambda: journal.replay(db), 'corrupt_source_replay_accepted')
        db.close()
        _copy_fixture_file(clean, primary, target)
        prefix.unlink()
        clean.unlink()

        report = _report(os.name == 'nt')
        report['accepted_counts_before_restore'] = {'sessions': counts[0], 'sections': counts[1],
            'mutations': counts[2], 'journal_recordings': withdrawal_head[1]}
        db = sqlite3.connect(primary, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        final_counts = tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                             for table in (SESSION, SECTION, MUTATION))
        final_session = db.execute(f'SELECT state,section_count FROM {SESSION} WHERE id=?',
                                   (created['session_id'],)).fetchone()
        _assert(final_counts == (1, 1, 2) and tuple(final_session) == ('withdrawn', 1)
                and journal.head() == withdrawal_head, 'final_restored_fixture_counts_changed')
        journal.assert_current(db)
        report['final_fixture_counts'] = {'sessions': final_counts[0], 'sections': final_counts[1],
            'mutations': final_counts[2], 'journal_recordings': withdrawal_head[1]}
        db.close()
        db = None
        _write_json(target / REPORT, report)
        return report
    except Exception as error:
        try:
            _write_json(target / FAILURE, {'status': 'failed', 'synthetic_only': True,
                'phase': phase, 'exception_class': type(error).__name__
                    if type(error).__name__ in {'OSError', 'ValueError', 'RuntimeError',
                    'OperationalError', 'IntegrityError'} else 'Exception'})
        except Exception:
            pass
        raise
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def _bounded_run(target):
    from bounded_windows_job import CheckRefused, WindowsAPI, run_bounded
    system_root = os.environ.get('SystemRoot')
    if not system_root:
        raise CheckRefused('system_root_unavailable')
    executable = str(Path(sys.executable).resolve())
    environment = {'PATH': str(Path(executable).parent), 'SYSTEMROOT': system_root,
        'WINDIR': system_root, 'TEMP': str(target.parent), 'TMP': str(target.parent),
        'PHOTOHOUSE_NO_DOTENV': '1', 'PYTHONNOUSERSITE': '1',
        'PYTHONDONTWRITEBYTECODE': '1'}
    program = ('import runpy\n' +
        f"runpy.run_path({str(Path(__file__).resolve())!r},run_name='photohouse_oral_qualification')['run']({str(target)!r})\n")
    code = run_bounded(WindowsAPI(), executable,
        [executable, '-I', '-B', '-c', program], environment, str(target.parent),
        timeout_seconds=300, memory_limit=2 * 1024**3, process_limit=8,
        minimum_free_ram=8 * 1024**3)
    if code != 0:
        raise CheckRefused('qualification_child_failed')
    path = target / REPORT
    require_private_file(path)
    with path.open('rb') as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    expected = _report(True)
    if not 0 < len(raw) <= MAX_REPORT_BYTES:
        raise CheckRefused('qualification_report_unavailable')
    value = json.loads(raw)
    if not _validate_report(value, expected):
        raise CheckRefused('qualification_report_unavailable')
    return value


def main(argv=None):
    class SafeArgumentParser(argparse.ArgumentParser):
        def error(self, _message):
            raise ValueError('invalid_command_line')

    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True,
        help='new absolute generated-fixture directory beneath an existing private parent')
    args = parser.parse_args(argv)
    target = _validate_output(Path(args.out))
    result = _bounded_run(target) if os.name == 'nt' else run(target)
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","synthetic_only":true}', file=sys.stderr)
        raise SystemExit(2) from None
