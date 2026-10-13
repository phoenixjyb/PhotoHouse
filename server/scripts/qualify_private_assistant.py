"""Qualify private assistant conversations using disposable generated fixtures.

The command accepts no database, media, provider, service, or network options.
It writes only to a new absolute directory beneath an existing private parent.
Windows CLI runs use the same bounded child Job policy as other qualifications.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict
import json
import io
import wave
import os
from pathlib import Path, PureWindowsPath
import sqlite3
import sys
import uuid

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / 'backend'))
sys.path.insert(0, str(SERVER / 'scripts'))

from app.access.private_storage import require_private_directory, require_private_file

ORIGIN = 'https://private-assistant.synthetic.test'
LIBRARY = 'synthetic-library'
OTHER_LIBRARY = 'synthetic-other-library'
OWNER, OTHER = 'synthetic-owner', 'synthetic-other-member'
FOREIGN = 'synthetic-foreign-owner'
TOKEN, OTHER_TOKEN, FOREIGN_TOKEN = 'a' * 43, 'b' * 43, 'c' * 43
NOW = 2_000_000_000
BASE = '/assistant/workspace/v1'
MAIN_REVISION = 'a0c9d2e4f817'
CASES = (
    'migrated_synthetic_runtime_and_generated_discovery_index',
    'private_thread_create_turn_and_idempotent_recovery',
    'saved_reply_speech_parent_receipt_and_duplicate_refusal',
    'explicit_asset_number_current_library_and_opaque_context',
    'playback_terminal_events_preserve_legacy_receipts',
    'safe_asr_failures_are_journaled_without_audio',
    'negotiated_saved_story_memoir_and_strict_legacy_recovery',
    'saved_memory_reply_speech_revalidates_sources_after_synthesis',
    'opt_in_unicode_label_and_paged_history',
    'foreign_actor_reads_are_indistinguishable',
    'fixed_retention_expires_private_text',
)
REPORT_NAME = 'qualification-report.json'
FAILURE_NAME = 'qualification-failure.json'
DATA_NAMES = ('main.sqlite', 'assistant-workspace.sqlite', 'assistant-journal.sqlite', 'discovery-index.json')
MAX_REPORT_BYTES = 8192


def _windows_path_check(target, *, windows=None):
    if windows is None:
        windows = os.name == 'nt'
    win = PureWindowsPath(str(target))
    if win.anchor.startswith(('\\\\', '//')):
        raise ValueError('local_output_required')
    if not windows:
        return
    paths = [win / name for name in (*DATA_NAMES, REPORT_NAME, FAILURE_NAME)]
    units = lambda value: len(str(value).encode('utf-16le')) // 2
    if (any(units(path) > 259 for path in paths)
            or any(units(units_path) > 247 for units_path in (win, *win.parents))
            or units(sys.executable) > 259
            or units(Path(__file__).resolve()) > 259):
        raise ValueError('windows_fixture_path_too_long')


def _validate_output(target):
    target = Path(target)
    if '?' in str(target) or '#' in str(target):
        raise ValueError('canonical_output_path_required')
    if (not target.is_absolute() or '..' in target.parts
            or os.path.lexists(target)
            or target.parent.resolve(strict=True) != target.parent):
        raise ValueError('new_absolute_output_required')
    _windows_path_check(target)
    # Reject aliases/reparse points anywhere in the selected parent chain.
    for parent in (target.parent, *target.parent.parents):
        _require_direct_directory(parent)
    require_private_directory(target.parent)
    return target


def _require_direct_directory(parent):
    info = parent.lstat()
    if (not parent.is_dir() or parent.is_symlink()
            or getattr(info, 'st_file_attributes', 0) & 0x400):
        raise ValueError('direct_private_parent_required')


def _create_file(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    os.close(descriptor)
    require_private_file(path)


def _write_json(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'w', encoding='ascii', newline='\n') as stream:
        require_private_file(path)
        json.dump(value, stream, sort_keys=True, separators=(',', ':'))
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def _load_runtime():
    """Load application dependencies only after the bounded child starts run()."""
    global SERVER, command, Config, create_engine, URL
    global RETENTION_SECONDS, initialize_v2, initialize_journal, LocalAssistantTts
    global session_digest, ReadBudget, digest, scoped_source, ReviewedIndex
    global RuntimeConfiguration

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    from app.access.assistant_workspace_store import RETENTION_SECONDS, initialize_v2
    from app.access.assistant_journal import initialize as initialize_journal
    from app.access.assistant_speech import LocalAssistantTts
    from app.access.credentials import session_digest
    from app.access.discovery import ReadBudget, digest, scoped_source
    from app.access.discovery_provider import ReviewedIndex
    from app.access.runtime import RuntimeConfiguration


def _migrate(database):
    engine = create_engine(URL.create('sqlite', database=str(database)))
    try:
        with engine.begin() as connection:
            config = Config()
            config.set_main_option('script_location', str(SERVER / 'backend' / 'migrations').replace('%', '%%'))
            config.attributes['connection'] = connection
            command.upgrade(config, MAIN_REVISION)
    finally:
        engine.dispose()


def _seed_main(database):
    _create_file(database)
    _migrate(database)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        for account, phone in ((OWNER, '+12025550101'), (OTHER, '+12025550102'),
                               (FOREIGN, '+12025550103')):
            db.execute('''INSERT INTO access_accounts(id,phone_login,password_hash,state,display_name)
                          VALUES(?,?,?,'active',?)''',
                       (account, phone, 'synthetic-unused-password-hash', 'Synthetic member'))
        for token, account in ((TOKEN, OWNER), (OTHER_TOKEN, OTHER), (FOREIGN_TOKEN, FOREIGN)):
            db.execute('INSERT INTO access_sessions(digest,account_id,expires_at,revoked) VALUES(?,?,?,0)',
                       (session_digest(token), account, (1 << 63) - 1))
        db.execute('INSERT INTO access_libraries(id,state,bootstrap_operator) VALUES(? ,\'active\',?)',
                   (LIBRARY, OWNER))
        db.execute('INSERT INTO access_libraries(id,state,bootstrap_operator) VALUES(? ,\'active\',?)',
                   (OTHER_LIBRARY, FOREIGN))
        for account, library, role in ((OWNER, LIBRARY, 'owner'),
                                       (OTHER, LIBRARY, 'viewer'),
                                       (FOREIGN, OTHER_LIBRARY, 'owner')):
            db.execute('''INSERT INTO access_memberships(account_id,library_id,status,role,revision,
                          expires_at,originals,approved_by) VALUES(?,?,'approved',?,1,NULL,0,?)''',
                       (account, library, role, OWNER if library == LIBRARY else FOREIGN))
        # All media metadata and captions are disposable, invented fixture rows.
        for asset_id, checksum, path in ((1, 'd' * 64, 'synthetic-only/photo-one'),
                                         (2, 'e' * 64, 'synthetic-only/photo-two')):
            db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
                          VALUES(?,?,?,'active','image/jpeg',640,480,'2026-01-01 12:00:00')''',
                       (asset_id, path, checksum))
            db.execute('INSERT INTO access_asset_libraries(asset_id,library_id) VALUES(?,?)',
                       (asset_id, LIBRARY))
        db.executemany('''INSERT INTO captions(asset_id,text,model,user_edited,superseded)
                          VALUES(?,?,'synthetic-fixture',0,0)''',
                       ((1, 'Synthetic fixture caption one'),
                        (2, 'Synthetic fixture caption two')))
        db.commit()
    with closing(sqlite3.connect(database)) as check:
        revision = check.execute('SELECT version_num FROM alembic_version').fetchall()
        key = check.execute('SELECT typeof(secret),length(secret) FROM access_admission_key WHERE id=1').fetchone()
        if revision != [(MAIN_REVISION,)] or key != ('blob', 32):
            raise RuntimeError('synthetic_main_database_invalid')


def _write_discovery_index(database, index_path):
    with closing(sqlite3.connect(database)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        with ReadBudget().attempt(db, lambda: False) as (_, read):
            source = scoped_source(LIBRARY, read)
    ids = tuple(str(row[0]) for row in source['assets'])
    index = ReviewedIndex(library_id=LIBRARY, revision='1', scope_ids=ids,
                          indexed_ids=ids, source_digest=digest(source))
    packed = json.dumps(asdict(index), sort_keys=True, separators=(',', ':')).encode('utf-8')
    descriptor = os.open(index_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(packed)
        stream.flush()
        os.fsync(stream.fileno())
    require_private_file(index_path)


def _synthetic_tts_class():
    """Build the fixture subtype after its runtime base has been loaded."""
    class SyntheticTts(LocalAssistantTts):
        """In-process fixture: constructor and synthesis never make a provider request."""
        def __init__(self):
            self.calls = []
            stream = io.BytesIO()
            with wave.open(stream, 'wb') as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(16000)
                writer.writeframes(b'\0\0' * 1600)
            self.audio = stream.getvalue()

        def synthesize(self, words, language):
            self.calls.append((words, language))
            return self.audio

    return SyntheticTts


def _auth(token):
    return {'Authorization': 'Bearer ' + token}


def _assert(condition, code):
    if not condition:
        raise RuntimeError(code)


def _save_synthetic_story(client, title, narration, *, revision='0', ident=None):
    """Create/edit a generated family story only through its protected API."""
    preview = client.post('/story-workspace/preview?library=' + LIBRARY,
        headers=_auth(TOKEN), json={'asset_ids': '1', 'theme': 'everyday',
            'language': 'en', 'title': title})
    _assert(preview.status_code == 200, 'synthetic_story_preview_failed')
    chapters = [{'id': 'chapter-1', 'title': title,
                 'narration': narration, 'asset_ids': ['1'], 'evidence_ids': []}]
    body = {'title': title, 'theme': 'everyday', 'language': 'en',
            'asset_ids': '1', 'chapters': json.dumps(chapters, separators=(',', ':')),
            'selection_revision': preview.json()['selection_revision'],
            'revision': revision, 'mutation_id': str(uuid.uuid4())}
    if ident is None:
        response = client.post('/memory-stories?library=' + LIBRARY,
                               headers=_auth(TOKEN), json=body)
    else:
        response = client.put(f'/memory-stories/{ident}?library={LIBRARY}',
                              headers=_auth(TOKEN), json=body)
    _assert(response.status_code == 200, 'synthetic_story_save_failed')
    return response.json()


def _save_synthetic_memoir(client, story_id, title, introduction):
    """Create a generated memoir through the protected memory API."""
    response = client.post('/memory-community/v1/books?library=' + LIBRARY,
        headers=_auth(TOKEN), json={'title': title, 'language': 'en',
            'introduction': introduction, 'story_ids': story_id,
            'revision': '0', 'mutation_id': str(uuid.uuid4())})
    _assert(response.status_code == 200, 'synthetic_memoir_save_failed')
    return response.json()


def _report(native):
    return {'status': 'passed', 'synthetic_only': True, 'native_windows': native,
            'source_revision': MAIN_REVISION, 'cases_passed': list(CASES),
            'production_database_opened': False, 'family_media_opened': False,
            'provider_or_model_used': False, 'socket_listener_started': False,
            'network_accessed': False, 'workers_executed': False}


def run(output):
    target = _validate_output(Path(output))
    target.mkdir(mode=0o700)
    require_private_directory(target)
    phase = 'migration'
    clock = [NOW]
    try:
        _load_runtime()
        database = target / 'main.sqlite'
        workspace_path = target / 'assistant-workspace.sqlite'
        journal_path = target / 'assistant-journal.sqlite'
        initialize_journal(journal_path)
        index_path = target / 'discovery-index.json'
        _seed_main(database)
        _write_discovery_index(database, index_path)
        workspace = initialize_v2(workspace_path, clock=lambda: clock[0])
        originals = target / 'synthetic-originals'
        derived = target / 'synthetic-derived'
        originals.mkdir(mode=0o700)
        derived.mkdir(mode=0o700)
        require_private_directory(originals)
        require_private_directory(derived)
        configuration = RuntimeConfiguration(
            database=database.resolve(), web_origin=ORIGIN, original_roots=(originals.resolve(),),
            derived_root=derived.resolve(), discovery_indexes=(index_path.resolve(),),
            assistant_enabled=True, assistant_workspace_path=workspace_path.resolve(),
            assistant_journal_path=journal_path.resolve(),
            assistant_tts_url="http://127.0.0.1:19001/tts", assistant_reply_speech_enabled=True,
            memory_collaboration_enabled=True, assistant_saved_memory_cards_enabled=True)
        app = configuration.build_app(clock=lambda: clock[0])
        tts = _synthetic_tts_class()()
        app.state.assistant_tts = tts

        # TestClient is an in-process ASGI harness. The turn implementation is a
        # fixed local fixture, so this qualification cannot call a provider.
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from app.access import assistant as assistant_engine

        phase = 'thread_turn_and_recovery'
        with TestClient(app, base_url=ORIGIN) as client:
            list_url = BASE + '/threads?library_id=' + LIBRARY + '&include_labels=true'
            capability = client.get(BASE + '/capabilities?library_id=' + LIBRARY,
                                    headers=_auth(TOKEN))
            _assert(capability.status_code == 200 and capability.json().get('history_paging') is True,
                    'synthetic_capability_unavailable')
            created = client.post(BASE + '/threads', headers=_auth(TOKEN),
                                  json={'library_id': LIBRARY})
            _assert(created.status_code == 201, 'synthetic_thread_create_failed')
            thread_id = created.json()['thread']['thread_id']
            request_id = str(uuid.uuid4())
            question = 'find photos'
            body = {'library_id': LIBRARY, 'request_id': request_id,
                    'expected_revision': 0, 'text': question}
            with patch.object(assistant_engine, '_turn', wraps=assistant_engine._turn) as engine_turn:
                first = client.post(f'{BASE}/threads/{thread_id}/turns',
                                    headers=_auth(TOKEN), json=body)
                _assert(first.status_code == 200, 'synthetic_turn_failed')
                first_result = first.json().get('result')
                _assert(first_result is not None and first_result.get('kind') == 'results'
                        and first_result.get('context') is not None,
                        'synthetic_turn_missing_context')
                expected_ids = first_result['context']['visible_ids']
                _assert(set(expected_ids) == {'1', '2'} and first_result.get('total') == 2 and
                        [item['id'] for item in first_result.get('items', [])] == expected_ids,
                        'synthetic_turn_wrong_or_unhydrated_items')
                recovered = client.get(f'{BASE}/threads/{thread_id}/requests/{request_id}'
                                       f'?library_id={LIBRARY}', headers=_auth(TOKEN))
                _assert(recovered.status_code == 200 and recovered.json().get('recovered') is True,
                        'synthetic_turn_recovery_failed')
                recovered_result = recovered.json().get('result')
                _assert(recovered_result is not None and recovered_result.get('context') ==
                        first_result.get('context') and recovered_result.get('total') == 2
                        and [item['id'] for item in recovered_result.get('items', [])] == expected_ids
                        and recovered_result.get('effect') is None,
                        'synthetic_recovery_changed_result_or_effect')
                replay = client.post(f'{BASE}/threads/{thread_id}/turns',
                                     headers=_auth(TOKEN), json=body)
                _assert(replay.status_code == 200 and replay.json().get('recovered') is True,
                        'synthetic_duplicate_request_not_recovered')
                _assert(engine_turn.call_count == 1, 'synthetic_duplicate_regenerated')

            phase = 'saved_reply_speech'
            speech_id = str(uuid.uuid4())
            speech_headers = {**_auth(TOKEN), 'X-PhotoHouse-Request-Id': speech_id,
                              'X-PhotoHouse-Parent-Request-Id': request_id}
            speech_url = f'{BASE}/threads/{thread_id}/requests/{request_id}/speech'
            speech_body = {'library_id': LIBRARY, 'expected_revision': 1}
            spoken = client.post(speech_url, headers=speech_headers, json=speech_body)
            _assert(spoken.status_code == 200 and spoken.content == tts.audio and
                    spoken.headers.get('X-PhotoHouse-Request-Id') == speech_id and
                    spoken.headers.get('X-PhotoHouse-Receipt-Status') == 'succeeded' and
                    spoken.headers.get('cache-control') == 'no-store' and
                    tts.calls == [(first_result['reply'], 'en')],
                    'synthetic_saved_reply_speech_failed')
            duplicate_speech = client.post(speech_url, headers=speech_headers, json=speech_body)
            _assert(duplicate_speech.status_code == 409 and len(tts.calls) == 1,
                    'synthetic_duplicate_speech_regenerated')
            journal_record = app.state.assistant_journal.get(speech_id, OWNER, LIBRARY)
            _assert(journal_record['operation'] == 'speech' and
                    journal_record['parent_request_id'] == request_id and
                    journal_record['status'] == 'succeeded' and
                    journal_record['input_text'] is None and journal_record['recognized_text'] is None,
                    'synthetic_speech_journal_failed')

            phase = 'playback_terminal_event'
            _assert(spoken.headers.get('X-PhotoHouse-Playback-Tracking') == 'enabled',
                    'synthetic_playback_tracking_not_advertised')
            playback_url = '/assistant/v1/receipts/' + speech_id + '/playback'
            for _ in range(2):
                playback = client.post(playback_url, headers=_auth(TOKEN),
                    json={'library_id': LIBRARY, 'outcome': 'completed'})
                _assert(playback.status_code == 200 and playback.json() ==
                        dict(version=1, request_id=speech_id, playback_outcome='completed'),
                        'synthetic_playback_report_failed')
            _assert(client.post(playback_url, headers=_auth(OTHER_TOKEN),
                    json={'library_id': LIBRARY, 'outcome': 'completed'}).status_code == 404 and
                    client.post(playback_url, headers=_auth(TOKEN),
                    json={'library_id': LIBRARY, 'outcome': 'cancelled'}).status_code == 409 and
                    app.state.assistant_journal.get(speech_id, OWNER, LIBRARY) == journal_record,
                    'synthetic_playback_scope_or_legacy_receipt_changed')

            phase = 'explicit_asset_number'
            numbered = client.post('/assistant/v1/turns', headers=_auth(TOKEN),
                json={'library_id': LIBRARY, 'text': 'open asset id 1', 'context': None})
            _assert(numbered.status_code == 200 and numbered.json()['effect'] ==
                    {'type': 'open_asset', 'asset_id': '1'} and
                    [item['id'] for item in numbered.json()['items']] == ['1'],
                    'synthetic_numbered_asset_failed')
            followup = client.post('/assistant/v1/turns', headers=_auth(TOKEN),
                json={'library_id': LIBRARY, 'text': 'open the first result',
                      'context': numbered.json()['context']})
            _assert(followup.status_code == 200 and followup.json()['effect']['asset_id'] == '1',
                    'synthetic_numbered_context_failed')

            phase = 'safe_asr_failure'
            from app.access.assistant_speech import LocalAssistantAsr, AssistantAsrFailure
            class SyntheticFailedAsr(LocalAssistantAsr):
                def __init__(self, code, status):
                    self.code, self.status = code, status
                def transcribe(self, payload):
                    raise AssistantAsrFailure(self.code, self.status)
            for code, status in (('speech_no_input', 422), ('speech_busy', 503),
                                 ('speech_timeout', 504), ('speech_invalid_response', 502),
                                 ('speech_unavailable', 503)):
                app.state.assistant_asr = SyntheticFailedAsr(code, status)
                failed_id = str(uuid.uuid4())
                failed = client.post('/assistant/v1/transcribe', content=tts.audio,
                    headers={**_auth(TOKEN), 'Content-Type': 'audio/wav',
                             'X-PhotoHouse-Library-Id': LIBRARY,
                             'X-PhotoHouse-Request-Id': failed_id})
                saved = app.state.assistant_journal.get(failed_id, OWNER, LIBRARY)
                _assert(failed.status_code == status and failed.json()['error'] == code and
                        saved['status'] == 'failed' and saved['error_code'] == code and
                        saved['recognized_text'] is None, 'synthetic_asr_category_failed')
            app.state.assistant_asr = None
            _assert(tts.audio not in journal_path.read_bytes(), 'synthetic_audio_was_retained')

            phase = 'saved_memory_cards_and_recovery'
            story_title = 'Synthetic Amber Story'
            memoir_title = 'Synthetic Amber Memoir'
            story = _save_synthetic_story(client, story_title,
                'A synthetic amber picnic beside the lake.')
            memoir = _save_synthetic_memoir(client, story['id'], memoir_title,
                'A synthetic amber memoir opening.')
            cards_capability = client.get(BASE + '/saved-memory-capabilities?library_id=' + LIBRARY,
                                          headers=_auth(TOKEN))
            speech_capability = client.get(
                BASE + '/saved-memory-speech-capabilities?library_id=' + LIBRARY,
                headers=_auth(TOKEN))
            _assert(cards_capability.status_code == 200 and
                    cards_capability.json() == {'version': 1, 'available': True} and
                    speech_capability.status_code == 200 and
                    speech_capability.json() == {'version': 1, 'available': True},
                    'synthetic_saved_memory_capability_failed')

            memory_thread = client.post(BASE + '/threads', headers=_auth(TOKEN),
                                        json={'library_id': LIBRARY})
            _assert(memory_thread.status_code == 201, 'synthetic_memory_thread_create_failed')
            memory_thread_id = memory_thread.json()['thread']['thread_id']
            story_request_id = str(uuid.uuid4())
            story_turn = client.post(f'{BASE}/threads/{memory_thread_id}/turns',
                headers=_auth(TOKEN), json={'library_id': LIBRARY,
                    'request_id': story_request_id, 'expected_revision': 0,
                    'text': 'find saved story amber', 'accepts': ['saved_memory_cards_v1']})
            _assert(story_turn.status_code == 200, 'synthetic_memory_story_turn_failed')
            story_result = story_turn.json().get('result')
            _assert(type(story_result) is dict and story_result.get('kind') == 'memory_cards' and
                    [card.get('id') for card in story_result.get('memory_cards', [])] == [story['id']] and
                    story_result.get('effect') is None and story_result.get('items') == [],
                    'synthetic_memory_story_cards_invalid')

            story_recovery = client.get(
                f'{BASE}/threads/{memory_thread_id}/requests/{story_request_id}?library_id={LIBRARY}',
                headers=_auth(TOKEN))
            recovered_memory = story_recovery.json().get('result') if story_recovery.status_code == 200 else None
            _assert(story_recovery.status_code == 200 and story_recovery.json().get('recovered') is True and
                    type(recovered_memory) is dict and set(recovered_memory) == {
                        'version', 'kind', 'reply', 'context', 'filters', 'total',
                        'has_more', 'effect', 'items'} and
                    recovered_memory.get('kind') == 'results' and
                    recovered_memory.get('reply') == story_result['reply'] and
                    recovered_memory.get('context') is None and recovered_memory.get('total') == 0 and
                    recovered_memory.get('has_more') is False and recovered_memory.get('effect') is None and
                    recovered_memory.get('items') == [] and 'memory_cards' not in recovered_memory and
                    story['id'] not in story_recovery.text and story_title not in story_recovery.text,
                    'synthetic_memory_recovery_not_legacy_safe')

            memory_speech_url = f'{BASE}/threads/{memory_thread_id}/requests/{story_request_id}/speech'
            story_speech_id = str(uuid.uuid4())
            story_audio = client.post(memory_speech_url,
                headers={**_auth(TOKEN), 'X-PhotoHouse-Request-Id': story_speech_id,
                         'X-PhotoHouse-Parent-Request-Id': story_request_id},
                json={'library_id': LIBRARY, 'expected_revision': 1})
            _assert(story_audio.status_code == 200 and story_audio.content == tts.audio and
                    tts.calls[-1] == (story_result['reply'], 'en') and
                    story_title not in tts.calls[-1][0] and story['id'] not in tts.calls[-1][0],
                    'synthetic_memory_story_speech_failed')

            phase = 'saved_memory_memoir_cards_and_speech'
            memoir_request_id = str(uuid.uuid4())
            memoir_turn = client.post(f'{BASE}/threads/{memory_thread_id}/turns',
                headers=_auth(TOKEN), json={'library_id': LIBRARY,
                    'request_id': memoir_request_id, 'expected_revision': 1,
                    'text': 'find memoir amber', 'accepts': ['saved_memory_cards_v1']})
            _assert(memoir_turn.status_code == 200, 'synthetic_memory_memoir_turn_failed')
            memoir_result = memoir_turn.json().get('result')
            _assert(type(memoir_result) is dict and memoir_result.get('kind') == 'memory_cards' and
                    [card.get('id') for card in memoir_result.get('memory_cards', [])] == [memoir['id']] and
                    memoir_result.get('effect') is None and memoir_result.get('items') == [],
                    'synthetic_memory_memoir_cards_invalid')
            memoir_speech_id = str(uuid.uuid4())
            memoir_audio = client.post(
                f'{BASE}/threads/{memory_thread_id}/requests/{memoir_request_id}/speech',
                headers={**_auth(TOKEN), 'X-PhotoHouse-Request-Id': memoir_speech_id,
                         'X-PhotoHouse-Parent-Request-Id': memoir_request_id},
                json={'library_id': LIBRARY, 'expected_revision': 2})
            _assert(memoir_audio.status_code == 200 and memoir_audio.content == tts.audio and
                    tts.calls[-1] == (memoir_result['reply'], 'en') and
                    memoir_title not in tts.calls[-1][0] and memoir['id'] not in tts.calls[-1][0],
                    'synthetic_memory_memoir_speech_failed')

            phase = 'saved_memory_source_drift_during_speech'
            drift_request_id = str(uuid.uuid4())
            drift_turn = client.post(f'{BASE}/threads/{memory_thread_id}/turns',
                headers=_auth(TOKEN), json={'library_id': LIBRARY,
                    'request_id': drift_request_id, 'expected_revision': 2,
                    'text': 'find saved story amber', 'accepts': ['saved_memory_cards_v1']})
            _assert(drift_turn.status_code == 200, 'synthetic_memory_drift_turn_failed')
            calls_before_drift = len(tts.calls)
            original_synthesize = tts.synthesize

            def edit_story_during_speech(words, language):
                audio = original_synthesize(words, language)
                _save_synthetic_story(client, story_title,
                    'The synthetic amber picnic changed during reply speech.',
                    revision=story['revision'], ident=story['id'])
                return audio

            with patch.object(tts, 'synthesize', side_effect=edit_story_during_speech):
                drift_audio = client.post(
                    f'{BASE}/threads/{memory_thread_id}/requests/{drift_request_id}/speech',
                    headers={**_auth(TOKEN), 'X-PhotoHouse-Request-Id': str(uuid.uuid4()),
                             'X-PhotoHouse-Parent-Request-Id': drift_request_id},
                    json={'library_id': LIBRARY, 'expected_revision': 3})
            _assert(drift_audio.status_code == 409 and drift_audio.content != tts.audio and
                    len(tts.calls) == calls_before_drift + 1,
                    'synthetic_memory_source_drift_audio_not_withheld')
            removed_memory_thread = client.request('DELETE',
                f'{BASE}/threads/{memory_thread_id}', headers=_auth(TOKEN),
                json={'library_id': LIBRARY, 'expected_revision': 3})
            _assert(removed_memory_thread.status_code == 200 and
                    removed_memory_thread.json().get('deleted') is True,
                    'synthetic_memory_thread_cleanup_failed')

            # Populate additional deterministic rows through the private store
            # API to exercise paging without repeated engine work.
            for revision in range(1, 45):
                workspace.append_exchange(OWNER, LIBRARY, thread_id, str(uuid.uuid4()),
                    revision, f'Synthetic history question {revision + 1}',
                    f'Synthetic history reply {revision + 1}', [], [])

            phase = 'labels_and_history'
            labeled = client.get(list_url, headers=_auth(TOKEN))
            _assert(labeled.status_code == 200, 'synthetic_label_list_failed')
            label_rows = labeled.json()['threads']
            _assert(len(label_rows) == 1 and label_rows[0].get('label') == question,
                    'synthetic_label_projection_failed')
            detail = client.get(f'{BASE}/threads/{thread_id}?library_id={LIBRARY}',
                                headers=_auth(TOKEN))
            _assert(detail.status_code == 200, 'synthetic_thread_detail_failed')
            _assert(detail.json()['thread']['revision'] == 45 and
                    [row['revision'] for row in detail.json()['exchanges']] == list(range(26, 46)),
                    'synthetic_latest_detail_window_failed')
            _assert(detail.json()['has_older_exchanges'] is True,
                    'synthetic_detail_older_flag_failed')
            cursor = detail.json()['exchanges'][0]['revision']
            first_page = client.get(f'{BASE}/threads/{thread_id}/history?library_id={LIBRARY}'
                f'&snapshot_revision=45&before_revision={cursor}', headers=_auth(TOKEN))
            _assert(first_page.status_code == 200, 'synthetic_history_first_page_failed')
            page_one = first_page.json()
            _assert([row['revision'] for row in page_one['exchanges']] == list(range(6, 26))
                    and page_one['has_older_exchanges'] is True
                    and page_one['next_before_revision'] == 6,
                    'synthetic_history_first_cursor_failed')
            second_page = client.get(f'{BASE}/threads/{thread_id}/history?library_id={LIBRARY}'
                f'&snapshot_revision=45&before_revision={page_one["next_before_revision"]}',
                headers=_auth(TOKEN))
            _assert(second_page.status_code == 200, 'synthetic_history_second_page_failed')
            page_two = second_page.json()
            _assert([row['revision'] for row in page_two['exchanges']] == list(range(1, 6))
                    and page_two['has_older_exchanges'] is False
                    and page_two['next_before_revision'] is None,
                    'synthetic_history_terminal_cursor_failed')
            stale = client.get(f'{BASE}/threads/{thread_id}/history?library_id={LIBRARY}'
                '&snapshot_revision=44&before_revision=26', headers=_auth(TOKEN))
            _assert(stale.status_code == 409, 'synthetic_history_revision_drift_not_refused')

            phase = 'foreign_actor_scope'
            own_foreign_actor = client.get(f'{BASE}/threads/{thread_id}?library_id={LIBRARY}',
                                           headers=_auth(OTHER_TOKEN))
            other_library_actor = client.get(f'{BASE}/threads/{thread_id}?library_id={OTHER_LIBRARY}',
                                             headers=_auth(FOREIGN_TOKEN))
            _assert(own_foreign_actor.status_code == other_library_actor.status_code == 404,
                    'synthetic_foreign_thread_read_not_hidden')
            foreign_history = client.get(f'{BASE}/threads/{thread_id}/history?library_id={LIBRARY}'
                '&snapshot_revision=45&before_revision=26', headers=_auth(OTHER_TOKEN))
            _assert(foreign_history.status_code == 404, 'synthetic_foreign_history_not_hidden')

            phase = 'retention'
            clock[0] += RETENTION_SECONDS + 1
            expired_list = client.get(list_url, headers=_auth(TOKEN))
            expired_detail = client.get(f'{BASE}/threads/{thread_id}?library_id={LIBRARY}',
                                        headers=_auth(TOKEN))
            _assert(expired_list.status_code == 200 and expired_list.json()['threads'] == [],
                    'synthetic_expired_label_or_thread_visible')
            _assert(expired_detail.status_code == 404, 'synthetic_expired_detail_visible')
            pruned = workspace.prune()
            with workspace.connection() as db:
                retained = tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                    for table in ('threads', 'exchanges', 'turn_requests', 'thread_context'))
            _assert(all(value == 0 for value in retained), 'synthetic_private_retention_failed')
            _assert(type(pruned.get('threads')) is int,
                    'synthetic_retention_result_invalid')

        report = _report(os.name == 'nt')
        _write_json(target / REPORT_NAME, report)
        return report
    except Exception as error:
        code = getattr(error, 'winerror', None)
        if type(code) is not int or not 0 <= code <= 65535:
            code = None
        try:
            _write_json(target / FAILURE_NAME, {'status': 'failed', 'synthetic_only': True,
                'phase': phase, 'exception_class': type(error).__name__ if type(error).__name__ in
                {'OSError', 'ValueError', 'RuntimeError', 'OperationalError', 'IntegrityError'} else 'Exception',
                'winerror': code})
        except Exception:
            pass
        raise


def _bounded_report(target):
    _validate_output(target)
    from bounded_windows_job import CheckRefused, WindowsAPI, run_bounded
    system_root = os.environ.get('SystemRoot')
    if not system_root:
        raise CheckRefused('system_root_unavailable')
    executable = str(Path(sys.executable).resolve())
    environment = {'PATH': str(Path(executable).parent), 'SYSTEMROOT': system_root,
                   'WINDIR': system_root, 'TEMP': str(target.parent), 'TMP': str(target.parent),
                   'PHOTOHOUSE_NO_DOTENV': '1', 'PYTHONNOUSERSITE': '1',
                   'PYTHONDONTWRITEBYTECODE': '1'}
    program = ('import runpy\n'
               f"runpy.run_path({str(Path(__file__).resolve())!r},run_name='photohouse_private_qualification')['run']({str(target)!r})\n")
    code = run_bounded(WindowsAPI(), executable,
        [executable, '-I', '-B', '-c', program], environment, str(target.parent),
        timeout_seconds=900, memory_limit=2 * 1024**3, process_limit=4,
        minimum_free_ram=8 * 1024**3)
    if code != 0:
        raise CheckRefused('qualification_child_failed')
    path = target / REPORT_NAME
    require_private_file(path)
    with path.open('rb') as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if not 0 < len(raw) <= MAX_REPORT_BYTES:
        raise CheckRefused('qualification_report_unavailable')
    value = json.loads(raw)
    expected = _report(True)
    if (type(value) is not dict or value != expected or
            any(type(value.get(key)) is not bool for key, item in expected.items()
                if type(item) is bool)):
        raise CheckRefused('qualification_report_unavailable')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True,
                        help='absent absolute directory beneath an existing private parent')
    args = parser.parse_args(argv)
    result = _bounded_report(Path(args.out)) if os.name == 'nt' else run(args.out)
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","synthetic_only":true}', file=sys.stderr)
        raise SystemExit(2) from None
