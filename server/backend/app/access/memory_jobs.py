"""Private, expiring story conversations and review-only narrative jobs.

No model I/O runs in these transactions. Jobs keep controls and references;
source text is freshly hydrated by the bounded worker, never a queue snapshot.
"""
import hashlib
import json
import uuid

from .library import _integer
from .memory_books import MemoryBooks, _stored as book_content
from .memory_stories import MemoryStories, _json
from .memory_narrative import MAX_OUTPUT_BYTES, validate_companion
from .memory_source_refs import available as source_refs_available, current_groups
from .service import AccessDenied, AccessService
from .stories import _uuid
from .transport import TransportError

RETENTION = 30 * 86400
MAX_TURNS = 128
PAGE_SIZE = 16
EDITORIAL_CONTEXT_PROFILE = 'memoir_editorial_v1'


def editorial_choice(controls, *, enabled=False):
    """Persist a context choice, never infer it from a later feature toggle."""
    if type(enabled) is not bool or type(controls) is not dict:
        raise TransportError(503, 'Memoir drafting context unavailable')
    if 'context_profile' not in controls:
        return False
    if (type(controls['context_profile']) is not str
            or controls['context_profile'] != EDITORIAL_CONTEXT_PROFILE or not enabled):
        raise TransportError(503, 'Memoir drafting context unavailable')
    return True


def text(value, maximum, *, blank=False):
    try:
        if (type(value) is not str or len(value.encode('utf-8')) > maximum or
            any((ord(c) < 32 or 0x7f <= ord(c) <= 0x9f) and c not in '\n\t' for c in value) or
            (not blank and not value.strip())):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise TransportError(422, 'Invalid or oversized memory text') from None
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def clipped(value, maximum):
    return value.encode('utf-8')[:maximum].decode('utf-8', errors='ignore')


def parent(access, library, member, target_type, ident):
    """All child media are reauthorized, including every essay of a memoir."""
    if target_type == 'story':
        store = MemoryStories(access)
        row = store._row(ident, library)
        details = [store._read(row, library, member)]
        return row, details, store._can_edit(member, row), _json(row['content'])
    if target_type == 'book':
        books = MemoryBooks(access)
        row = books._row(ident, library)
        stored = book_content(row['content'])
        details = [books.stories._read(books.stories._row(i, library), library, member)
                   for i in stored['story_ids']]
        return row, details, books._can_edit(member, row), stored
    raise TransportError(400, 'Invalid memory target')


def context(access, library, member, target_type, ident, instructions='', recent=None,
            *, editorial_context=False, principal_neutral_fingerprint=False):
    """Model-sized context plus a digest of full current authorized dependencies.

    Only consented, accepted contributions enter model prompts. Family text,
    transcript, editorial wording, and AI observations retain distinct labels.
    Date hints are not part of this story-detail snapshot, so none are inferred
    or synthesized here. Deterministic excerpts bound prompts; full evidence
    remains in its original store, outside job input JSON.
    """
    if type(editorial_context) is not bool or type(principal_neutral_fingerprint) is not bool:
        raise TransportError(400, 'Invalid memoir context choice')
    if editorial_context and target_type != 'book':
        raise TransportError(400, 'Memoir context requires a book')
    row, details, can_edit, stored = parent(access, library, member, target_type, ident)
    chapters, sources, dependencies = [], [], []
    seen = set()
    refs_ready = source_refs_available(access.db)

    def add_source(source):
        if len(sources) >= 96:
            raise TransportError(422, 'Choose a smaller story context')
        sources.append(source)

    # The owner's opening note supplies the memoir's editorial direction. It
    # remains distinct from independent family evidence and counts toward the
    # same source/prompt budgets as every other source.
    introduction_id = None
    if target_type == 'book' and stored.get('introduction', '').strip():
        introduction_id = 'editorial-book-' + ident
        add_source({'id': introduction_id, 'kind': 'editorial',
                    'text': stored['introduction'], 'asset_id': None, 'author': None})

    for story in details:
        linked_groups = current_groups(access.db, story['id'], int(story['revision']),
            [chapter['id'] for chapter in story['chapters']], library) if refs_ready else []
        linked_ids = list(dict.fromkeys(ident for _chapter, refs in linked_groups for ident in refs))
        # Explicit current-revision links preserve chapter sources across a
        # reviewed story save. No older revision or merely accepted, unlinked
        # chapter contribution can opt itself into a new prompt.
        linked_clause = (' OR c.id IN (' + ','.join('?' for _ in linked_ids) + ')') if linked_ids else ''
        contributions = access.db.execute('''SELECT c.id,c.chapter_id,c.kind,c.original_text,c.sha256,
                c.byline,d.transcript,d.polished_text,d.revision,d.state
            FROM access_memory_contributions c LEFT JOIN access_memory_contribution_derivations d
            ON d.contribution_id=c.id AND d.revision=(SELECT MAX(revision)
                FROM access_memory_contribution_derivations WHERE contribution_id=c.id)
            WHERE c.story_id=? AND c.library_id=? AND c.state='accepted'
                AND c.local_processing_consent=1
                AND (c.chapter_id IS NULL OR c.base_story_revision=?''' + linked_clause + ''')
            ORDER BY c.created_at,c.id LIMIT 17''',
            (story['id'], library, int(story['revision']), *linked_ids)).fetchall()
        if len(contributions)>16:
            raise TransportError(422, 'Choose a smaller set of contributions for one drafting pass')
        # Durable family editions are shared after review. Reader-specific edit
        # affordances cannot turn identical authorized sources into a different
        # source snapshot. Private job fingerprints keep their existing profile.
        dependency_story = ({key: value for key, value in story.items() if key != 'can_edit'}
                            if principal_neutral_fingerprint else story)
        dependencies.append([dependency_story, contributions, linked_groups]
                            if refs_ready else [dependency_story, contributions])
        contribution_sources = []
        for value in contributions:
            cid, chapter_id, kind, original, sha, byline, transcript, polished, revision, state = value
            source_text = original if kind == 'text' else transcript if state == 'ready' else None
            if source_text:
                source_id = 'contribution-' + cid
                contribution_sources.append((chapter_id, source_id))
                add_source({'id': source_id,
                                'kind': 'family' if kind == 'text' else 'transcript',
                                'text': clipped(source_text, 512),
                                'asset_id': None, 'author': byline or None})
        for chapter in story['chapters']:
            if len(chapters) == 24:
                raise TransportError(422, 'Choose a smaller memoir for one drafting pass')
            refs = [introduction_id] if introduction_id else []
            assets = chapter['asset_ids']
            for item in story['items']:
                if item['id'] not in assets:
                    continue
                for evidence in item['evidence']:
                    if evidence['id'] not in seen:
                        author = None
                        if evidence['source'] == 'family' and evidence['id'].startswith('family-'):
                            # Authorship is a voluntary display label, never an account identity.
                            # Resolve the current note in this same authorization transaction;
                            # asset membership or an evidence ID alone is not authority.
                            note = access.db.execute('''SELECT id,byline,revision
                                FROM access_stories
                                WHERE id=? AND library_id=? AND asset_id=?
                                  AND revision=? AND deleted=0''',
                                (evidence['id'][len('family-'):], library, item['id'],
                                 evidence['revision'])).fetchone()
                            if note is None:
                                raise TransportError(503, 'Family source unavailable')
                            byline = text(note[1], 256, blank=True)
                            author = byline if byline.strip() else None
                            # Include the full label in the dependency fingerprint. Old
                            # queued/ready outputs cannot silently acquire a different voice.
                            dependencies.append(['asset_family_note_authorship_v1',
                                                 note[0], item['id'], note[2], byline])
                        add_source({'id': evidence['id'], 'kind': evidence['source'],
                            'text': clipped(evidence['text'], 384), 'asset_id': item['id'], 'author': author})
                        seen.add(evidence['id'])
                    refs.append(evidence['id'])
            refs += [cid for chapter_id, cid in contribution_sources
                     if chapter_id is None or chapter_id == chapter['id']]
            # Current editorial words are attributed separately, never presented
            # as independent proof of the events they describe.
            editorial = 'editorial-' + story['id'] + '-' + chapter['id']
            if chapter['narration'].strip():
                add_source({'id': editorial, 'kind': 'editorial',
                            'text': clipped(chapter['narration'], 512),
                            'asset_id': None, 'author': None})
                refs.append(editorial)
            chapter_title = chapter['title']
            if target_type == 'book' and story.get('title', '').strip():
                # Preserve both labels even when a child title fills the entire
                # title budget; never clip away all chapter context.
                suffix = clipped(chapter_title, 256)
                prefix = clipped(story['title'], 512 - len(suffix.encode('utf-8')) - 4)
                chapter_title = prefix + ' · ' + suffix
            chapters.append({'id': chapter['id'] if target_type == 'story' else story['id'] + '-' + chapter['id'],
                'title': clipped(chapter_title, 512), 'narration': clipped(chapter['narration'], 1024),
                'asset_ids': assets, 'evidence_ids': list(dict.fromkeys(refs))})
    bundle = {'version': 1, 'library_id': library,
        'target': {'type': target_type, 'id': ident, 'revision': row['revision']},
        'language': stored['language'], 'title': clipped(stored['title'], 512),
        'theme': stored.get('theme', 'memoir'), 'chapters': chapters, 'sources': sources,
        'recent_turns': recent or [], 'instructions': instructions}
    from .memory_narrative import _validate_bundle
    try:
        bundle = _validate_bundle(bundle)
    except ValueError:
        raise TransportError(422, 'Choose a smaller story context') from None
    fingerprint = digest([library, target_type, row['content'], row['revision'], dependencies])
    if principal_neutral_fingerprint:
        fingerprint = digest(['reviewed_memoir_sources_v1', fingerprint])
    if editorial_context:
        from .memory_editorial_context import enrich
        bundle, sidecar = enrich(access, library, member, ident, bundle)
        fingerprint = digest([fingerprint, EDITORIAL_CONTEXT_PROFILE, sidecar])
    return bundle, fingerprint, can_edit


def prune(db, now):
    """Caller owns a write transaction; no expired history is returned by reads."""
    db.execute('PRAGMA secure_delete=ON')
    db.execute('DELETE FROM access_memory_conversations WHERE expires_at<=?', (now,))
    db.execute('DELETE FROM access_memory_jobs WHERE expires_at<=?', (now,))


def maintenance(runtime):
    """Explicit collaboration runtime only; no migration or storage creation."""
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        with access._transaction(write=True):
            MemoryJobs(access)._ready()
            prune(db, access._now())


class MemoryJobs:
    def __init__(self, access, *, editorial_enabled=False):
        if type(editorial_enabled) is not bool:
            raise ValueError('editorial_feature_flag_must_be_boolean')
        self.access, self.db = access, access.db
        self.editorial_enabled = editorial_enabled

    def _controls(self, controls, editorial_context):
        if type(editorial_context) is not bool:
            raise TransportError(400, 'Invalid memoir context choice')
        if not editorial_context:
            return controls
        enriched = {**controls, 'context_profile': EDITORIAL_CONTEXT_PROFILE}
        editorial_choice(enriched, enabled=self.editorial_enabled)
        return enriched

    def _job_context(self, library, member, row):
        selected = editorial_choice(_json(row['input_json']), enabled=self.editorial_enabled)
        return context(self.access, library, member,
            'story' if row['story_id'] else 'book', row['story_id'] or row['book_id'],
            editorial_context=selected)

    def _ready(self):
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'access_memory_jobs', 'access_memory_conversations', 'access_memory_turns',
                'access_memory_contributions'} <= tables:
            raise TransportError(503, 'Memory companion unavailable')

    def _conversation(self, token, library, ident):
        member = self.access._require(token, library, 'library.read')
        self._ready()
        row = self.access._one('''SELECT * FROM access_memory_conversations
            WHERE id=? AND library_id=? AND actor_id=? AND expires_at>?''',
            (_uuid(ident), library, member['account_id'], self.access._now()))
        if row is None:
            raise AccessDenied('Access denied')
        parent(self.access, library, member, 'story' if row['story_id'] else 'book',
               row['story_id'] or row['book_id'])
        return row, member

    def start(self, token, library, target_type, target_id, ident):
        target_id, ident = _uuid(target_id), _uuid(ident)
        with self.access._transaction(write=True):
            member = self.access._require(token, library, 'library.read')
            self._ready()
            parent(self.access, library, member, target_type, target_id)
            now = self.access._now()
            prune(self.db, now)
            prior = self.access._one('SELECT * FROM access_memory_conversations WHERE id=?', (ident,))
            if prior:
                if (prior['library_id'] != library or prior['actor_id'] != member['account_id'] or
                    prior['story_id' if target_type == 'story' else 'book_id'] != target_id):
                    raise AccessDenied('Access denied')
            else:
                count = self.db.execute('SELECT count(*) FROM access_memory_conversations WHERE actor_id=?',
                                        (member['account_id'],)).fetchone()[0]
                if count >= 32:
                    raise TransportError(429, 'Close an older conversation before starting another')
                self.db.execute('''INSERT INTO access_memory_conversations
                    (id,library_id,actor_id,story_id,book_id,created_at,expires_at) VALUES (?,?,?,?,?,?,?)''',
                    (ident, library, member['account_id'], target_id if target_type == 'story' else None,
                     target_id if target_type == 'book' else None, now, now+RETENTION))
            return {'version': 1, 'id': ident, 'target_type': target_type, 'target_id': target_id,
                    'expires_at': prior['expires_at'] if prior else now+RETENTION}

    def conversations(self, token, library, target_type, target_id, preview=False):
        if type(preview) is not bool:
            raise TransportError(400, 'Invalid conversation preview option')
        target_id = _uuid(target_id)
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            self._ready()
            parent(self.access, library, member, target_type, target_id)
            column = 'story_id' if target_type=='story' else 'book_id'
            preview_column = ", (SELECT t.input_text FROM access_memory_turns t " \
                "WHERE t.conversation_id=c.id ORDER BY t.sequence ASC LIMIT 1) AS first_message_preview" if preview else ''
            rows = self.db.execute(f'''SELECT c.id,c.created_at,c.expires_at{preview_column}
                FROM access_memory_conversations c
                WHERE c.actor_id=? AND c.library_id=? AND c.{column}=? AND c.expires_at>?
                ORDER BY c.created_at DESC,c.id DESC LIMIT 8''',
                (member['account_id'], library, target_id, self.access._now())).fetchall()
            names = ('id','created_at','expires_at','first_message_preview') if preview else ('id','created_at','expires_at')
            items=[]
            for row in rows:
                item=dict(zip(names,row))
                if preview:
                    raw=item['first_message_preview']
                    if raw is None:
                        item['first_message_preview']=''
                    else:
                        try:
                            clean=text(raw,4096)
                        except TransportError:
                            clean=''
                        item['first_message_preview']=' '.join(clean.split())[:80].rstrip()
                items.append(item)
            return {'version':1, 'items':items}

    def turns(self, token, library, ident, page, reply_context=False, recent_first=False):
        if type(page) is not int or not 1 <= page <= 100000:
            raise TransportError(400, 'Invalid page')
        if type(reply_context) is not bool:
            raise TransportError(400, 'Invalid reply context option')
        if type(recent_first) is not bool:
            raise TransportError(400, 'Invalid history order option')
        with self.access._transaction():
            conversation, _ = self._conversation(token, library, ident)
            direction = 'DESC' if recent_first else 'ASC'
            cursor = self.db.execute(f'''SELECT t.id,t.sequence,t.input_text,t.reply_text,t.reply_kind,t.job_id,
                    j.state FROM access_memory_turns t LEFT JOIN access_memory_jobs j ON j.id=t.job_id
                WHERE t.conversation_id=? ORDER BY t.sequence {direction} LIMIT ? OFFSET ?''',
                (ident, PAGE_SIZE+1, (page-1)*PAGE_SIZE))
            names = [c[0] for c in cursor.description]
            rows = [dict(zip(names, r)) for r in cursor.fetchall()]
            page_rows = rows[:PAGE_SIZE]
            # Recent pages still read in conversation order within each page.
            # The extra row is only a has_more sentinel, never a visible turn.
            if recent_first:
                page_rows.reverse()
            member = self.access._require(token, library, 'library.read')
            bundle, fingerprint, _ = context(self.access, library, member,
                'story' if conversation['story_id'] else 'book',
                conversation['story_id'] or conversation['book_id'])
            for item in page_rows:
                if reply_context:
                    item.update(reply_source_ids=[], reply_questions=[])
                job = self.access._one('''SELECT kind,state,source_fingerprint,output_json,input_json,story_id,book_id FROM access_memory_jobs
                    WHERE id=? AND kind='chat' AND library_id=? AND actor_id=? AND conversation_id=?
                    AND story_id IS ? AND book_id IS ? AND expires_at>?''',
                    (item['job_id'], library, member['account_id'], ident,
                     conversation['story_id'], conversation['book_id'], self.access._now()))
                current_bundle, current_fingerprint = bundle, fingerprint
                if job is not None:
                    try:
                        controls = _json(job['input_json'])
                        if type(controls) is not dict:
                            raise ValueError()
                        if 'context_profile' in controls:
                            current_bundle, current_fingerprint, _ = self._job_context(library, member, job)
                    except (TransportError, ValueError, TypeError, UnicodeError, RecursionError):
                        current_fingerprint = None
                if job is None or job['source_fingerprint'] != current_fingerprint:
                    item.update(reply_text=None, reply_kind=None, state='stale')
                elif reply_context and job['state'] == 'ready' and item['reply_text']:
                    # Hydrate only already-retained, validated reply metadata. No
                    # source prose, model call, new retention or schema is added.
                    raw = job['output_json']
                    try:
                        if type(raw) is not str or len(raw.encode('utf-8')) > MAX_OUTPUT_BYTES:
                            raise ValueError('Invalid reply metadata')
                        result = validate_companion(_json(raw), current_bundle)
                        if result['reply'] != item['reply_text'] or result['kind'] != item['reply_kind']:
                            raise ValueError('Reply metadata does not match the turn')
                    except (ValueError, TypeError, UnicodeError, RecursionError):
                        continue
                    item.update(reply_source_ids=result['source_ids'], reply_questions=result['questions'])
            return {'version': 1, 'id': ident, 'expires_at': conversation['expires_at'], 'page': page,
                    'has_more': len(rows)>PAGE_SIZE, 'items': page_rows}

    def _queue(self, member, library, target_type, target_id, revision, mutation, controls,
               conversation=None, turn=None):
        bundle, fingerprint, can_edit = context(self.access, library, member, target_type, target_id,
            editorial_context=editorial_choice(controls, enabled=self.editorial_enabled))
        if conversation is None and not can_edit:
            raise AccessDenied('Access denied')
        body_digest = digest([library, target_type, target_id, revision, controls, conversation, turn])
        prior = self.access._one('SELECT * FROM access_memory_jobs WHERE actor_id=? AND mutation_id=?',
                                (member['account_id'], mutation))
        if prior:
            if prior['request_digest'] != body_digest:
                raise TransportError(409, 'Request identifier already used; keep your message')
            if prior['source_fingerprint'] != fingerprint:
                return {**prior, 'state':'stale', 'output_json':None, 'error_code':'source_changed'}
            return prior
        if bundle['target']['revision'] != revision:
            raise TransportError(409, 'Story changed; keep your message and reload')
        pending = self.db.execute('''SELECT count(*) FROM access_memory_jobs WHERE actor_id=?
            AND state IN ('queued','running') AND expires_at>?''',
            (member['account_id'], self.access._now())).fetchone()[0]
        if pending >= 4:
            raise TransportError(429, 'Wait for your current memory tasks')
        ident, now = str(uuid.uuid4()), self.access._now()
        expiry = now+RETENTION
        if conversation:
            expiry = self.access._one('SELECT expires_at FROM access_memory_conversations WHERE id=?',
                                     (conversation,))['expires_at']
        raw = json.dumps(controls, ensure_ascii=True, separators=(',', ':'))
        self.db.execute('''INSERT INTO access_memory_jobs (id,library_id,actor_id,story_id,book_id,
            conversation_id,kind,state,mutation_id,request_digest,base_revision,source_fingerprint,
            input_json,created_at,updated_at,expires_at) VALUES (?,?,?,?,?,?,?,'queued',?,?,?,?,?,?,?,?)''',
            (ident, library, member['account_id'], target_id if target_type=='story' else None,
             target_id if target_type=='book' else None, conversation, 'chat' if conversation else 'narrative',
             mutation, body_digest, revision, fingerprint, raw, now, now, expiry))
        return self.access._one('SELECT * FROM access_memory_jobs WHERE id=?', (ident,))

    @staticmethod
    def _present(row):
        return {'version': 1, **{k: row[k] for k in ('id','kind','state',
                'created_at','updated_at','expires_at','error_code')},
                'result': _json(row['output_json']) if row['output_json'] else None,
                'needs_review': True, 'base_revision': str(row['base_revision'])}

    def narrative(self, token, library, target_type, target_id, revision, mutation, instructions,
                  editorial_context=False):
        target_id, mutation = _uuid(target_id), _uuid(mutation)
        revision = _integer(revision, 2**63-2)
        instructions = text(instructions, 4096, blank=True)
        with self.access._transaction(write=True):
            member = self.access._require(token, library, 'story.write')
            self._ready()
            prune(self.db, self.access._now())
            controls = self._controls({'instructions': instructions}, editorial_context)
            row = self._queue(member, library, target_type, target_id, revision, mutation, controls)
            return self._present(row)

    def send(self, token, library, conversation_id, revision, mutation, message,
             editorial_context=False):
        message = text(message, 4096)
        mutation = _uuid(mutation)
        revision = _integer(revision, 2**63-2)
        with self.access._transaction(write=True):
            conversation, member = self._conversation(token, library, conversation_id)
            prune(self.db, self.access._now())
            target_type = 'story' if conversation['story_id'] else 'book'
            target_id = conversation['story_id'] or conversation['book_id']
            controls = self._controls({}, editorial_context)
            prior = self.access._one('''SELECT * FROM access_memory_turns
                WHERE conversation_id=? AND mutation_id=?''', (conversation_id, mutation))
            request_digest = digest([revision, message, EDITORIAL_CONTEXT_PROFILE]
                if editorial_context else [revision, message])
            if prior:
                if prior['request_digest'] != request_digest:
                    raise TransportError(409, 'Message identifier already used; keep your text')
                job = self.access._one('SELECT * FROM access_memory_jobs WHERE id=?', (prior['job_id'],))
                if job is None:
                    raise TransportError(409, 'Message task expired')
                _, current, _ = self._job_context(library, member, job)
                if current != job['source_fingerprint']:
                    job = {**job, 'state':'stale', 'output_json':None, 'error_code':'source_changed'}
                return self._present(job)
            # Serialize conversation turns so a queued reply cannot miss previous context.
            if self.db.execute('''SELECT 1 FROM access_memory_jobs WHERE conversation_id=?
                    AND state IN ('queued','running') LIMIT 1''', (conversation_id,)).fetchone():
                raise TransportError(409, 'Wait for the previous reply')
            count = self.db.execute('SELECT count(*) FROM access_memory_turns WHERE conversation_id=?',
                                    (conversation_id,)).fetchone()[0]
            if count >= MAX_TURNS:
                raise TransportError(429, 'Start a new conversation')
            turn_id = str(uuid.uuid4())
            job = self._queue(member, library, target_type, target_id, revision, mutation,
                              {**controls, 'turn_id': turn_id}, conversation_id, message)
            self.db.execute('''INSERT INTO access_memory_turns
                (id,conversation_id,sequence,mutation_id,request_digest,input_text,job_id,created_at)
                VALUES (?,?,?,?,?,?,?,?)''', (turn_id, conversation_id, count+1, mutation,
                    request_digest, message, job['id'], self.access._now()))
            return self._present(job)

    def get(self, token, library, ident, cancel=False):
        with self.access._transaction(write=cancel):
            member = self.access._require(token, library, 'library.read')
            self._ready()
            row = self.access._one('''SELECT * FROM access_memory_jobs
                WHERE id=? AND library_id=? AND actor_id=? AND expires_at>?''',
                (_uuid(ident), library, member['account_id'], self.access._now()))
            if row is None:
                raise AccessDenied('Access denied')
            _, _, can_edit, _ = parent(self.access, library, member,
                    'story' if row['story_id'] else 'book', row['story_id'] or row['book_id'])
            if row['kind']=='narrative' and not can_edit:
                raise AccessDenied('Access denied')
            if cancel:
                self.db.execute('''UPDATE access_memory_jobs SET state='cancelled',output_json=NULL,
                    lease_id=NULL,lease_until=NULL,updated_at=? WHERE id=?''', (self.access._now(), ident))
                self.db.execute('UPDATE access_memory_turns SET reply_text=NULL,reply_kind=NULL WHERE job_id=?', (ident,))
                row = self.access._one('SELECT * FROM access_memory_jobs WHERE id=?', (ident,))
            elif row['state']=='ready':
                try:
                    _, current, _ = self._job_context(library, member, row)
                except (TransportError, ValueError, TypeError, UnicodeError, RecursionError):
                    current = None
                if current != row['source_fingerprint']:
                    row = {**row, 'state':'stale', 'output_json':None, 'error_code':'source_changed'}
            return self._present(row)

    def close(self, token, library, ident):
        self.db.execute('PRAGMA secure_delete=ON')
        with self.access._transaction(write=True):
            self._conversation(token, library, ident)
            self.db.execute('DELETE FROM access_memory_conversations WHERE id=?', (ident,))
            return {'version':1, 'deleted':True}
