"""Bounded local annotation derivation, with explicit caller supplied model adapters.

The caller owns the database connection and supplies local ASR and wording functions.
No provider is discovered from an environment variable and no network fallback exists.
The original row is never updated; a processing failure remains visible for review.
"""
import sqlite3
import time

TEXT_BYTES = 16 * 1024
MAX_TAGS = 16


class ProcessingRefused(RuntimeError):
    pass


def _deletion_guard(db):
    journal = getattr(db, 'original_deletions', None)
    if journal is not None:
        try:
            journal.assert_current(db)
        except RuntimeError:
            raise ProcessingRefused('deletion_history_unavailable') from None


def _eligible(db, row, now):
    upload = db.execute('''SELECT 1
        FROM access_uploads u LEFT JOIN access_asset_libraries m ON m.asset_id=u.asset_id
        WHERE u.account_id=? AND u.batch=? AND (? IS NULL OR u.asset_id=?)
        AND u.destination_library_id=?
        AND ((u.state='incoming' AND m.library_id IS NULL)
          OR (u.state='assigned' AND m.library_id=?)) LIMIT 1''',
        (row['author_id'], row['batch'], row['asset_id'], row['asset_id'],
         row['library_id'], row['library_id'])).fetchone()
    if upload is None:
        return False
    member = db.execute('''SELECT 1 FROM access_memberships m
        JOIN access_accounts a ON a.id=m.account_id
        JOIN access_libraries l ON l.id=m.library_id
        WHERE m.account_id=? AND m.library_id=? AND m.status='approved'
        AND (m.expires_at IS NULL OR m.expires_at>?) AND a.state='active'
        AND l.state='active' ''', (row['author_id'], row['library_id'], now)).fetchone()
    return member is not None


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or '\x00' in value or len(value.encode('utf-8')) > TEXT_BYTES:
        raise ProcessingRefused('invalid_' + label)
    return value


def _name(value, label, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ProcessingRefused('invalid_' + label)
    return value


def _result(value, keys):
    if not isinstance(value, dict) or set(value) != keys:
        raise ProcessingRefused('invalid_provider_result')
    return value


def retry_failed(db: sqlite3.Connection, identifier: str, *, clock=time.time):
    """Explicit local operator retry; preserve the failed revision and original."""
    db.row_factory = sqlite3.Row
    now = int(clock())
    db.execute('BEGIN IMMEDIATE')
    try:
        _deletion_guard(db)
        row = db.execute('''SELECT a.*,d.revision,d.state FROM access_upload_annotations a
            JOIN access_annotation_derivations d ON d.annotation_id=a.id
            WHERE a.id=? ORDER BY d.revision DESC LIMIT 1''', (identifier,)).fetchone()
        if row is None or row['state'] not in {'failed', 'dead'} or row['consent'] != 1:
            raise ProcessingRefused('retry_not_available')
        if not _eligible(db, row, now):
            raise ProcessingRefused('scope_changed')
        revision = row['revision'] + 1
        db.execute('''INSERT INTO access_annotation_derivations
            (annotation_id,revision,state,created_at,updated_at) VALUES (?,?,'waiting',?,?)''',
            (identifier, revision, now, now))
        db.commit()
        return {'id': identifier, 'revision': revision, 'state': 'waiting'}
    except BaseException:
        db.rollback()
        raise


def recover_interrupted(db: sqlite3.Connection, identifier: str, revision: int,
                        *, clock=time.time, minimum_age=600):
    """Mark one stale running revision failed after the operator stops its worker.

    This never queues a retry or changes an authored original. The caller must
    establish that the worker is stopped; age alone cannot prove interruption.
    """
    db.row_factory = sqlite3.Row
    now = int(clock())
    if not isinstance(revision, int) or revision < 1 or minimum_age < 600:
        raise ProcessingRefused('invalid_recovery_target')
    db.execute('BEGIN IMMEDIATE')
    try:
        _deletion_guard(db)
        row = db.execute('''SELECT d.revision,d.state,d.started_at
            FROM access_annotation_derivations d WHERE d.annotation_id=?
            ORDER BY d.revision DESC LIMIT 1''', (identifier,)).fetchone()
        if (row is None or row['revision'] != revision or row['state'] != 'running'
                or row['started_at'] is None or row['started_at'] > now - minimum_age):
            raise ProcessingRefused('recovery_not_available')
        changed = db.execute('''UPDATE access_annotation_derivations
            SET state='failed',error_code='operator_recovered_interrupted',
                updated_at=?,finished_at=?
            WHERE annotation_id=? AND revision=? AND state='running' AND started_at=?''',
            (now, now, identifier, revision, row['started_at'])).rowcount
        if changed != 1:
            raise ProcessingRefused('recovery_not_available')
        db.commit()
        return {'id': identifier, 'revision': revision, 'state': 'failed'}
    except BaseException:
        db.rollback()
        raise


def process_one(db: sqlite3.Connection, *, transcribe, polish, clock=time.time):
    """Process one waiting note. Adapters are callables running on the same local host.

    `transcribe(wav_bytes, language)` returns {text, provider, model};
    `polish(text, language)` returns {text, tags, provider, model}.
    Only proposed tags are stored. A separate review must accept them.
    """
    db.row_factory = sqlite3.Row
    now = int(clock())
    db.execute('BEGIN IMMEDIATE')
    try:
        _deletion_guard(db)
        row = db.execute('''SELECT a.*,d.revision FROM access_upload_annotations a
            JOIN access_annotation_derivations d ON d.annotation_id=a.id
            WHERE d.state='waiting' AND a.consent=1
            ORDER BY a.created_at,a.id LIMIT 1''').fetchone()
        if row is None:
            db.commit()
            return None
        identifier, revision = row['id'], row['revision']
        if not _eligible(db, row, now):
            db.execute('''UPDATE access_annotation_derivations SET state='dead',error_code='scope_changed',
                updated_at=?,finished_at=? WHERE annotation_id=? AND revision=?''',
                (now, now, identifier, revision))
            db.commit()
            return {'id': identifier, 'state': 'dead'}
        db.execute('''UPDATE access_annotation_derivations SET state='running',started_at=?,updated_at=?
            WHERE annotation_id=? AND revision=? AND state='waiting' ''',
            (now, now, identifier, revision))
        db.commit()
    except BaseException:
        db.rollback()
        raise

    try:
        if row['kind'] == 'audio':
            asr = _result(transcribe(row['original_audio'], row['language']),
                          {'text', 'provider', 'model'})
            transcript = _text(asr['text'], 'transcript')
            asr_label = _name(asr['provider'], 'provider', 60)
            asr_model = _name(asr['model'], 'model', 120)
        else:
            transcript, asr_label, asr_model = None, None, None
        wording = _result(polish(transcript or row['original_text'], row['language']),
                          {'text', 'tags', 'provider', 'model'})
        polished = _text(wording['text'], 'wording')
        provider = _name(wording['provider'], 'provider', 60)
        model = _name(wording['model'], 'model', 120)
        tags = wording['tags']
        if not isinstance(tags, list) or len(tags) > MAX_TAGS or any(
                not isinstance(tag, str) or not tag.strip() or len(tag) > 128 or '\x00' in tag
                for tag in tags) or len(tags) != len(set(tags)):
            raise ProcessingRefused('invalid_tags')
        provider_name = (asr_label + ' + ' if asr_label else '') + provider
        model_name = (asr_model + ' + ' if asr_model else '') + model
    except Exception:
        finished = int(clock())
        db.execute('BEGIN IMMEDIATE')
        try:
            _deletion_guard(db)
            db.execute('''UPDATE access_annotation_derivations SET state='failed',error_code='local_processing_failed',
                updated_at=?,finished_at=? WHERE annotation_id=? AND revision=? AND state='running' ''',
                (finished, finished, identifier, revision))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        return {'id': identifier, 'state': 'failed'}

    finished = int(clock())
    db.execute('BEGIN IMMEDIATE')
    try:
        _deletion_guard(db)
        current = db.execute('''SELECT a.*,d.state FROM access_upload_annotations a
            JOIN access_annotation_derivations d ON d.annotation_id=a.id AND d.revision=?
            WHERE a.id=?''', (revision, identifier)).fetchone()
        if current is None or current['state'] != 'running':
            raise ProcessingRefused('processing_state_changed')
        if not _eligible(db, current, finished):
            db.execute('''UPDATE access_annotation_derivations SET state='dead',error_code='scope_changed',
                updated_at=?,finished_at=? WHERE annotation_id=? AND revision=?''',
                (finished, finished, identifier, revision))
            db.commit()
            return {'id': identifier, 'state': 'dead'}
        db.execute('''UPDATE access_annotation_derivations SET state='completed',transcript=?,
            polished_text=?,provider=?,model=?,updated_at=?,finished_at=?
            WHERE annotation_id=? AND revision=?''',
            (transcript, polished, provider_name, model_name, finished, finished, identifier, revision))
        db.executemany('''INSERT INTO access_annotation_tag_proposals
            (annotation_id,tag,status,revision) VALUES (? ,?,'proposed',?)''',
            [(identifier, tag, revision) for tag in tags])
        db.commit()
        return {'id': identifier, 'state': 'completed'}
    except BaseException:
        db.rollback()
        raise
