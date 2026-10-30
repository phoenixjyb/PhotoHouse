"""One-item story workers. Explicit adapters; never publish or overwrite a story.

Claims and commits use short write transactions. Provider I/O is outside SQLite
transactions. Expired leases are not automatically reclaimed or retried.
"""
import asyncio
import hashlib
import hmac
import json
import math
import sqlite3
import threading
import time
import uuid

from .host_inference_admission import HostAdmissionError
from .memory_jobs import MemoryJobs, context, parent, prune, text, digest, editorial_choice
from .memory_stories import _json
from .memory_narrative import validate_narrative, validate_companion
from .service import AccessDenied, AccessService
from .transport import TransportError
from .selected_story_operations import PreparationScope

LEASE_SECONDS = 300
MAX_CONTRIBUTION_TEXT_BYTES = 8192
MAX_CONTRIBUTION_AUDIO_BYTES = 2 * 1024 * 1024


class _JobCancellation:
    """Per-job invalidation combined with a worker-wide shutdown signal."""
    def __init__(self, local, stop_event):
        self.local, self.stop_event = local, stop_event

    def set(self):
        self.local.set()

    def is_set(self):
        return self.local.is_set() or self.stop_event.is_set()


class OwnedSavedStoryNarrator:
    """Synchronous per-job bridge to a fresh privately owned model provider."""
    def __init__(self, provider_factory, *, timeout=60, stop_event=None,
                 monotonic=time.monotonic):
        if (not callable(provider_factory) or type(timeout) not in (int, float)
                or not math.isfinite(timeout) or not 0 < timeout <= 60
                or (stop_event is not None and
                    not isinstance(stop_event, type(threading.Event())))
                or not callable(monotonic)):
            raise ValueError('invalid_saved_story_narrator_configuration')
        self.provider_factory = provider_factory
        self.timeout = float(timeout)
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        self.monotonic = monotonic

    def cancel(self):
        self.stop_event.set()

    def narrative(self, bundle):
        if self.stop_event.is_set():
            raise RuntimeError('saved_story_worker_stopping')
        provider = self.provider_factory()
        if (not callable(getattr(provider, 'prepare', None)) or
                not callable(getattr(provider, 'stop_and_reconcile', None)) or
                not callable(getattr(provider, 'close', None))):
            raise RuntimeError('saved_story_provider_unavailable')
        local = threading.Event()
        scope = PreparationScope(str(uuid.uuid4()), self.monotonic() + self.timeout,
            _JobCancellation(local, self.stop_event), self.monotonic)
        return asyncio.run(self._prepare(provider, bundle, scope, local))

    async def _prepare(self, provider, bundle, scope, local):
        task = None
        result = error = None
        try:
            task = asyncio.create_task(provider.prepare(bundle, scope))
            async with asyncio.timeout(self.timeout):
                result = await asyncio.shield(task)
            if scope.cancelled():
                raise RuntimeError('saved_story_preparation_cancelled')
        except BaseException as caught:
            error = caught
        finally:
            local.set()
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            try:
                stopped = await provider.stop_and_reconcile(scope)
                closed = await provider.close()
            except BaseException as caught:
                stopped, closed = False, False
                error = error or caught
            if stopped is not True or closed is not True:
                raise RuntimeError('saved_story_provider_cleanup_unproven') from None
        if error is not None:
            raise error
        return result


def verify_contribution_original(row):
    """Validate bounded original storage and its recorded content digest."""
    kind = row['kind']
    if kind == 'text':
        if row['original_audio'] is not None or row['duration_ms'] is not None:
            raise AccessDenied('Access denied')
        original = row['original_text']
        if type(original) is not str:
            raise AccessDenied('Access denied')
        try:
            raw = original.encode('utf-8', errors='strict')
        except UnicodeError:
            raise AccessDenied('Access denied') from None
        if not 1 <= len(raw) <= MAX_CONTRIBUTION_TEXT_BYTES:
            raise AccessDenied('Access denied')
    elif kind == 'audio':
        if row['original_text'] is not None:
            raise AccessDenied('Access denied')
        if (type(row['duration_ms']) is not int or
                not 1 <= row['duration_ms'] <= 30000):
            raise AccessDenied('Access denied')
        original = row['original_audio']
        if type(original) is not bytes or not 1 <= len(original) <= MAX_CONTRIBUTION_AUDIO_BYTES:
            raise AccessDenied('Access denied')
        raw = original
    else:
        raise AccessDenied('Access denied')
    recorded = row['sha256']
    if (type(recorded) is not str or len(recorded) != 64 or
            any(character not in '0123456789abcdef' for character in recorded) or
            not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), recorded)):
        raise AccessDenied('Access denied')
    return raw


def member(access, actor, library):
    row = access._one('''SELECT m.* FROM access_memberships m
        JOIN access_accounts a ON a.id=m.account_id JOIN access_libraries l ON l.id=m.library_id
        WHERE m.account_id=? AND m.library_id=? AND m.status='approved' AND a.state='active'
        AND l.state='active' AND (m.expires_at IS NULL OR m.expires_at>?)''',
        (actor, library, access._now()))
    if row is None:
        raise AccessDenied('Access denied')
    return row


def job_context(access, row, *, editorial_enabled=False):
    principal = member(access, row['actor_id'], row['library_id'])
    controls = _json(row['input_json'])
    selected = editorial_choice(controls, enabled=editorial_enabled)
    recent = []
    if row['kind'] == 'chat':
        conversation = access._one('''SELECT * FROM access_memory_conversations
            WHERE id=? AND actor_id=? AND library_id=? AND expires_at>?''',
            (row['conversation_id'], row['actor_id'], row['library_id'], access._now()))
        if (conversation is None or conversation['story_id'] != row['story_id'] or
            conversation['book_id'] != row['book_id']):
            raise AccessDenied('Access denied')
        turn = access._one('''SELECT * FROM access_memory_turns WHERE id=?
            AND conversation_id=? AND job_id=?''',
            (controls.get('turn_id'), row['conversation_id'], row['id']))
        if turn is None:
            raise AccessDenied('Access denied')
        rows = access.db.execute('''SELECT t.input_text,CASE WHEN j.state='ready'
                AND j.source_fingerprint=? THEN COALESCE(t.reply_text,'') ELSE '' END
            FROM access_memory_turns t LEFT JOIN access_memory_jobs j ON j.id=t.job_id
            WHERE t.conversation_id=? AND t.sequence<=? ORDER BY t.sequence DESC LIMIT 8''',
            (row['source_fingerprint'], row['conversation_id'], turn['sequence'])).fetchall()
        recent = [{'user':r[0], 'assistant':r[1]} for r in reversed(rows)]
    target_type = 'story' if row['story_id'] else 'book'
    bundle, fingerprint, can_edit = context(access, row['library_id'], principal, target_type,
        row['story_id'] or row['book_id'], controls.get('instructions', ''), recent,
        editorial_context=selected, full_narration=_is_auto_saved_story(row))
    if row['kind']=='narrative' and not can_edit:
        raise AccessDenied('Access denied')
    if bundle['target']['revision'] != row['base_revision'] or fingerprint != row['source_fingerprint']:
        raise TransportError(409, 'Source changed')
    return bundle


def _is_auto_saved_story(row):
    return (row['kind'] == 'narrative' and row['story_id'] is not None and
            row['mutation_id'] == MemoryJobs.auto_refinement_mutation(
                row['story_id'], row['base_revision'], row['actor_id']))


def process_job(db, *, narrator, clock=time.time, editorial_enabled=False,
                memory_groups_enabled=False, saved_story_only=False):
    """Process one queued narrative or chat. Returns only job ID/state metadata."""
    if type(editorial_enabled) is not bool:
        raise ValueError('editorial_feature_flag_must_be_boolean')
    if type(memory_groups_enabled) is not bool:
        raise ValueError('memory_groups_feature_flag_must_be_boolean')
    if type(saved_story_only) is not bool:
        raise ValueError('saved_story_only_flag_must_be_boolean')
    access = AccessService(db, clock=clock, memory_groups_enabled=memory_groups_enabled)
    with access._transaction(write=True):
        now = access._now()
        prune(db, now)
        cursor = db.execute("SELECT * FROM access_memory_jobs WHERE state='queued' ORDER BY created_at,id LIMIT 512")
        fields = [column[0] for column in cursor.description]
        candidates = [dict(zip(fields, values)) for values in cursor.fetchall()]
        row = next((candidate for candidate in candidates
                    if _is_auto_saved_story(candidate) is saved_story_only), None)
        if row is None:
            return None
        try:
            bundle = job_context(access, row, editorial_enabled=editorial_enabled)
            turn_fingerprint = digest(bundle['recent_turns'])
        except (AccessDenied, TransportError, ValueError, TypeError):
            db.execute("UPDATE access_memory_jobs SET state='stale',error_code='source_changed',updated_at=? WHERE id=?",
                       (now, row['id']))
            return {'id': row['id'], 'state':'stale'}
        lease = str(uuid.uuid4())
        db.execute("UPDATE access_memory_jobs SET state='running',lease_id=?,lease_until=?,updated_at=? WHERE id=?",
                   (lease, now+LEASE_SECONDS, now, row['id']))
    try:
        result = narrator.companion(bundle) if row['kind']=='chat' else narrator.narrative(bundle)
        result = validate_companion(result, bundle) if row['kind']=='chat' else validate_narrative(result, bundle)
        raw = json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        failure = None
    except HostAdmissionError as error:
        if saved_story_only and error.reason in {'busy', 'maintenance'}:
            with access._transaction(write=True):
                now = access._now()
                current = access._one('SELECT * FROM access_memory_jobs WHERE id=?', (row['id'],))
                if current is None:
                    return {'id': row['id'], 'state': 'cancelled'}
                if current['state'] != 'running' or current['lease_id'] != lease:
                    return {'id': row['id'], 'state': current['state']}
                db.execute("""UPDATE access_memory_jobs SET state='queued',lease_id=NULL,
                    lease_until=NULL,error_code=NULL,updated_at=? WHERE id=? AND lease_id=?""",
                    (now, row['id'], lease))
            return {'id': row['id'], 'state': 'deferred'}
        raw, failure = None, 'local_processing_failed'
    except Exception:
        # Never retain provider errors, prompts, audio or raw generated responses.
        raw, failure = None, 'local_processing_failed'
    with access._transaction(write=True):
        now = access._now()
        current = access._one('SELECT * FROM access_memory_jobs WHERE id=?', (row['id'],))
        if current is None:
            return {'id': row['id'], 'state':'cancelled'}
        if current['state'] != 'running' or current['lease_id'] != lease:
            return {'id': row['id'], 'state':current['state']}
        state = 'failed' if failure else 'ready'
        if current['expires_at'] <= now:
            db.execute('DELETE FROM access_memory_jobs WHERE id=?', (row['id'],))
            return {'id': row['id'], 'state':'expired'}
        try:
            if current['lease_until'] <= now:
                raise AccessDenied('Access denied')
            refreshed = job_context(access, current, editorial_enabled=editorial_enabled)
            if digest(refreshed['recent_turns']) != turn_fingerprint:
                raise AccessDenied('Access denied')
        except (AccessDenied, TransportError, ValueError, TypeError):
            state, raw, failure = 'stale', None, 'source_changed'
        db.execute('''UPDATE access_memory_jobs SET state=?,output_json=?,error_code=?,
            lease_id=NULL,lease_until=NULL,updated_at=? WHERE id=? AND lease_id=?''',
            (state, raw if state=='ready' else None, failure, now, row['id'], lease))
        if row['kind']=='chat' and state=='ready':
            db.execute('''UPDATE access_memory_turns SET reply_text=?,reply_kind=?
                WHERE job_id=? AND conversation_id=?''',
                (result['reply'], result['kind'], row['id'], row['conversation_id']))
        return {'id':row['id'], 'state':state}


def contribution_context(access, row):
    verify_contribution_original(row)
    principal = member(access, row['author_id'], row['library_id'])
    story, details, _, _ = parent(access, row['library_id'], principal, 'story', row['story_id'])
    if row['state']!='accepted' or row['local_processing_consent'] != 1:
        raise AccessDenied('Access denied')
    if row['chapter_id'] and row['chapter_id'] not in {c['id'] for c in details[0]['chapters']}:
        raise AccessDenied('Access denied')
    if row['chapter_id'] and row['base_story_revision'] != story['revision']:
        raise AccessDenied('Access denied')
    return story['revision']


def process_contribution(db, *, transcribe, polish, clock=time.time):
    """Retained originals stay immutable; only separate derivations are written."""
    access = AccessService(db, clock=clock)
    with access._transaction(write=True):
        row = access._one('''SELECT c.*,d.revision AS derivation_revision FROM access_memory_contributions c
            JOIN access_memory_contribution_derivations d ON d.contribution_id=c.id
            WHERE d.state='waiting' ORDER BY c.created_at,c.id,d.revision LIMIT 1''')
        if row is None:
            return None
        now = access._now()
        try:
            source_revision = contribution_context(access, row)
        except (AccessDenied, TransportError):
            db.execute('''UPDATE access_memory_contribution_derivations SET state='cancelled',
                transcript=NULL,polished_text=NULL,tags='[]',provider=NULL,model=NULL,
                lease_id=NULL,lease_until=NULL,error_code='source_changed',updated_at=?
                WHERE contribution_id=? AND revision=?''',
                (now, row['id'], row['derivation_revision']))
            return {'id':row['id'], 'state':'cancelled'}
        lease = str(uuid.uuid4())
        db.execute('''UPDATE access_memory_contribution_derivations SET state='running',
            lease_id=?,lease_until=?,updated_at=? WHERE contribution_id=? AND revision=?''',
            (lease, now+LEASE_SECONDS, now, row['id'], row['derivation_revision']))
    transcript, polished, tags, provider, model, error = None, None, '[]', None, None, None
    try:
        if row['kind']=='audio':
            asr = transcribe(bytes(row['original_audio']), row['language'])
            if type(asr) is not dict or set(asr) != {'text','provider','model'}:
                raise ValueError()
            transcript = text(asr['text'], 8192)
        response = polish(transcript if row['kind']=='audio' else row['original_text'], row['language'])
        if type(response) is not dict or set(response) != {'text','tags','provider','model'}:
            raise ValueError()
        polished = text(response['text'], 8192)
        provider, model = text(response['provider'], 60), text(response['model'], 120)
        values = response['tags']
        if type(values) is not list or len(values)>16 or len(set(values)) != len(values):
            raise ValueError()
        tags = json.dumps([text(t, 128) for t in values], ensure_ascii=False)
    except Exception:
        transcript, polished, tags, provider, model, error = None, None, '[]', None, None, 'local_processing_failed'
    with access._transaction(write=True):
        now = access._now()
        current = access._one('''SELECT c.*,d.state AS derivation_state,d.lease_id,d.lease_until
            FROM access_memory_contributions c JOIN access_memory_contribution_derivations d
            ON d.contribution_id=c.id WHERE c.id=? AND d.revision=?''',
            (row['id'], row['derivation_revision']))
        if current is None or current['derivation_state']!='running' or current['lease_id']!=lease:
            return {'id':row['id'], 'state':'cancelled'}
        state = 'failed' if error else 'ready'
        try:
            if (current['lease_until'] <= now or current['sha256'] != row['sha256'] or
                contribution_context(access, current) != source_revision):
                raise AccessDenied('Access denied')
        except (AccessDenied, TransportError):
            state, error = 'cancelled', 'source_changed'
            transcript, polished, tags, provider, model = None, None, '[]', None, None
        db.execute('''UPDATE access_memory_contribution_derivations SET state=?,transcript=?,polished_text=?,
            tags=?,provider=?,model=?,error_code=?,lease_id=NULL,lease_until=NULL,updated_at=?
            WHERE contribution_id=? AND revision=? AND lease_id=?''',
            (state, transcript, polished, tags, provider, model, error, now,
             row['id'], row['derivation_revision'], lease))
        return {'id':row['id'], 'state':state}


def recover_job(db, ident, *, clock=time.time):
    """Explicit stopped-worker recovery; preserve failures, never bulk retry."""
    access = AccessService(db, clock=clock)
    with access._transaction(write=True):
        now = access._now()
        changed = db.execute('''UPDATE access_memory_jobs SET state='failed',error_code='interrupted',
            output_json=NULL,lease_id=NULL,lease_until=NULL,updated_at=?
            WHERE id=? AND state='running' AND lease_until<=?''', (now, ident, now)).rowcount
        if changed != 1:
            raise ValueError('Recovery unavailable')
        return {'id':ident, 'state':'failed'}


def recover_contribution(db, ident, revision, *, clock=time.time):
    """One expired claim, after independently stopping its worker. No requeue."""
    if type(revision) is not int or revision<1:
        raise ValueError('Recovery unavailable')
    access = AccessService(db, clock=clock)
    with access._transaction(write=True):
        now = access._now()
        changed = db.execute('''UPDATE access_memory_contribution_derivations SET state='failed',
            error_code='interrupted',transcript=NULL,polished_text=NULL,tags='[]',provider=NULL,
            model=NULL,lease_id=NULL,lease_until=NULL,updated_at=?
            WHERE contribution_id=? AND revision=? AND state='running' AND lease_until<=?''',
            (now, ident, revision, now)).rowcount
        if changed != 1:
            raise ValueError('Recovery unavailable')
        return {'id':ident, 'revision':revision, 'state':'failed'}
