"""Default-off domain service for memoir citations and adjacent transitions.

The feature is unavailable until the explicit flag is enabled and the exact
additive editorial schema revision is installed. Legacy memoir content and
responses remain owned by :mod:`memory_books` and are never reshaped here.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import sqlite3
import uuid

from .memory_book_editorial_contract import (
    ChildRevision, ContractCode, EditorialContractError, SourceIdentity,
    parse_mutation,
)
from .memory_book_editorial_schema import BOOK_TABLE, EDITORIAL_REVISIONS, REFS_TABLE
from .memory_books import MemoryBooks
from .memory_source_refs import TABLE as STORY_SOURCE_REFS, current_groups
from .memory_stories import MemoryStories
from .service import AccessDenied
from .transport import TransportError

_RECEIPT_NAMESPACE = uuid.UUID('fa11f6ac-1469-4e25-98bc-679fd31c9655')
_MUTATION_KEYS = {
    'version', 'revision', 'mutation_id', 'children',
    'introduction_source_refs', 'transitions',
}


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))


def _request_identity(raw: bytes) -> tuple[str, bytes]:
    """Extract the receipt ID and canonical payload for replay lookup."""
    if type(raw) is not bytes:
        raise TransportError(400, 'Invalid memoir editorial request')
    if len(raw) > 65_536:
        raise TransportError(413, 'Memoir editorial request too large')
    try:
        value = _json(raw.decode('utf-8', errors='strict'))
        ident = value['mutation_id']
        if (type(value) is not dict or set(value) != _MUTATION_KEYS
                or type(value['version']) is not int or value['version'] != 1
                or type(ident) is not str or str(uuid.UUID(ident)) != ident):
            raise ValueError()
        canonical = json.dumps(value, sort_keys=True, ensure_ascii=True,
                              allow_nan=False, separators=(',', ':')).encode('ascii')
        return ident, canonical
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise TransportError(400, 'Invalid memoir editorial request') from None


def _safe_json(raw):
    try:
        return _json(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return None


def _book_id(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise TransportError(400, 'Invalid memoir identifier') from None


class MemoryBookEditorial:
    """Persist/reopen an additive editorial sidecar for one authorized memoir."""

    def __init__(self, access, *, enabled=False):
        if type(enabled) is not bool:
            raise ValueError('editorial_feature_flag_must_be_boolean')
        self.access = access
        self.db = access.db
        self.enabled = enabled
        self.books = MemoryBooks(access)
        self.stories = MemoryStories(access)

    def _ready(self):
        if not self.enabled:
            raise TransportError(503, 'Memoir editorial unavailable')
        try:
            versions = self.db.execute('SELECT version_num FROM alembic_version').fetchall()
            names = {row[0] for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if (len(versions) != 1 or versions[0][0] not in EDITORIAL_REVISIONS
                    or not {BOOK_TABLE, REFS_TABLE, STORY_SOURCE_REFS} <= names):
                raise TransportError(503, 'Memoir editorial unavailable')
            book_columns = {row[1] for row in self.db.execute(
                f'PRAGMA table_info({BOOK_TABLE})')}
            ref_columns = {row[1] for row in self.db.execute(
                f'PRAGMA table_info({REFS_TABLE})')}
            story_ref_columns = {row[1] for row in self.db.execute(
                f'PRAGMA table_info({STORY_SOURCE_REFS})')}
            if (not {'children_json', 'transitions_json', 'state'} <= book_columns
                    or not {'book_id', 'book_revision', 'section_key', 'ordinal',
                            'story_id', 'story_revision', 'chapter_id',
                            'contribution_id'} <= ref_columns
                    or not {'story_id', 'revision', 'chapter_id', 'ordinal',
                            'contribution_id'} <= story_ref_columns):
                raise TransportError(503, 'Memoir editorial unavailable')
        except TransportError:
            raise
        except Exception:
            raise TransportError(503, 'Memoir editorial unavailable') from None

    def _book_context(self, book_id, library, member):
        row = self.books._row(book_id, library)
        legacy = self.books._present(row, library, member)
        children = tuple(ChildRevision(item['id'], item['revision'])
                         for item in legacy['stories'])
        eligible = set()
        for child in children:
            story_row = self.stories._row(child.story_id, library)
            # _present rechecks story media and its same-library access before
            # its chapter ids are used as eligible current source references.
            detail = self.stories._present(story_row, library, member)
            chapter_ids = [chapter['id'] for chapter in detail['chapters']]
            try:
                groups = current_groups(self.db, child.story_id, int(child.revision),
                                        chapter_ids, library)
            except sqlite3.Error:
                raise TransportError(503, 'Memoir editorial unavailable') from None
            for chapter_id, contribution_ids in groups:
                eligible.update(SourceIdentity(child.story_id, child.revision,
                                               chapter_id, contribution_id)
                                for contribution_id in contribution_ids)
        return row, legacy, children, frozenset(eligible)

    @staticmethod
    def _can_edit(member, book_row):
        return MemoryBooks._can_edit(member, book_row)

    @staticmethod
    def _empty_transitions(children):
        return [{'left_story_id': left.story_id, 'right_story_id': right.story_id,
                 'text': '', 'source_refs': []}
                for left, right in zip(children, children[1:])]

    def _response(self, book_row, children, state, *, introduction_refs=(), transitions=()):
        if state != 'current':
            introduction_refs = ()
            transitions = ()
        return {
            'version': 1,
            'id': book_row['id'],
            'revision': str(book_row['revision']),
            'children': [asdict(child) for child in children],
            'state': state,
            'introduction_source_refs': [asdict(ref) for ref in introduction_refs],
            'transitions': [
                {'left_story_id': transition.left_story_id,
                 'right_story_id': transition.right_story_id,
                 'text': transition.text,
                 'source_refs': [asdict(ref) for ref in transition.source_refs]}
                for transition in transitions
            ] if state == 'current' else [],
        }

    def _read_sidecar(self, book_row, children, eligible):
        revision = int(book_row['revision'])
        sidecar = self.access._one(
            f'SELECT children_json,transitions_json,state FROM {BOOK_TABLE} '
            'WHERE book_id=? AND book_revision=?', (book_row['id'], revision))
        if sidecar is None:
            prior = self.db.execute(
                f'SELECT 1 FROM {BOOK_TABLE} WHERE book_id=? AND book_revision<? LIMIT 1',
                (book_row['id'], revision)).fetchone()
            return self._response(book_row, children,
                                  'source_changed' if prior else 'empty',
                                  transitions=self._empty_transitions(children) if not prior else ())
        if sidecar['state'] != 'current':
            return self._response(book_row, children, 'source_changed')
        stored_children = _safe_json(sidecar['children_json'])
        stored_transitions = _safe_json(sidecar['transitions_json'])
        if type(stored_children) is not list or type(stored_transitions) is not list:
            return self._response(book_row, children, 'source_changed')
        ref_rows = self.db.execute(
            f'SELECT section_key,ordinal,story_id,story_revision,chapter_id,contribution_id '
            f'FROM {REFS_TABLE} WHERE book_id=? AND book_revision=? '
            'ORDER BY section_key,ordinal', (book_row['id'], revision)).fetchall()
        intro = []
        transitions_by_index = [[] for _ in range(max(0, len(children) - 1))]
        try:
            for section, _ordinal, story_id, story_revision, chapter_id, contribution_id in ref_rows:
                ref = SourceIdentity(story_id, str(story_revision), chapter_id, contribution_id)
                if section == 'introduction':
                    intro.append(ref)
                elif (type(section) is str and section.startswith('transition-')
                      and section[11:].isdigit()):
                    index = int(section[11:])
                    if index >= len(transitions_by_index):
                        raise ValueError()
                    transitions_by_index[index].append(ref)
                else:
                    raise ValueError()
            if [asdict(child) for child in children] != stored_children:
                raise ValueError()
            if len(stored_transitions) != max(0, len(children) - 1):
                raise ValueError()
            transitions = []
            for index, stored in enumerate(stored_transitions):
                if (type(stored) is not dict
                        or set(stored) != {'left_story_id', 'right_story_id', 'text'}):
                    raise ValueError()
                transitions.append({
                    **stored,
                    'source_refs': [asdict(ref) for ref in transitions_by_index[index]],
                })
            mutation_id = str(uuid.uuid5(_RECEIPT_NAMESPACE,
                                         f"read:{book_row['id']}:{revision}"))
            body = json.dumps({
                'version': 1, 'revision': str(revision), 'mutation_id': mutation_id,
                'children': stored_children,
                'introduction_source_refs': [asdict(ref) for ref in intro],
                'transitions': transitions,
            }, ensure_ascii=False, separators=(',', ':'))
            parsed = parse_mutation(body, current_book_revision=str(revision),
                                    current_children=children,
                                    eligible_sources=eligible)
        except (ValueError, TypeError, EditorialContractError, IndexError):
            return self._response(book_row, children, 'source_changed')
        return self._response(book_row, children, 'current',
                              introduction_refs=parsed.introduction_source_refs,
                              transitions=parsed.transitions)

    def get(self, token, library, book_id):
        book_id = _book_id(book_id)
        try:
            with self.access._transaction():
                member = self.access._require(token, library, 'library.read')
                self._ready()
                row, _legacy, children, eligible = self._book_context(
                    book_id, library, member)
                return self._read_sidecar(row, children, eligible)
        except sqlite3.Error:
            raise TransportError(503, 'Memoir editorial unavailable') from None

    def save(self, token, library, book_id, raw):
        book_id = _book_id(book_id)
        try:
            with self.access._transaction(write=True):
                member = self.access._require(token, library, 'story.write')
                self._ready()
                requested_mutation, canonical_request = _request_identity(raw)
                try:
                    digest = hashlib.sha256(
                        b'photohouse:memory-book-editorial:v1\0' + library.encode('utf-8')
                        + b'\0' + book_id.encode('ascii') + b'\0' + canonical_request).hexdigest()
                except UnicodeError:
                    raise TransportError(400, 'Invalid memoir editorial request') from None
                row = self.books._row(book_id, library)
                if not self._can_edit(member, row):
                    raise AccessDenied('Access denied')
                actor = member['account_id']
                receipt_mutation = str(uuid.uuid5(
                    _RECEIPT_NAMESPACE, f'editorial:{actor}:{requested_mutation}'))
                prior = self.access._one('''SELECT book_id,request_digest
                    FROM access_memory_book_revisions WHERE editor_id=? AND mutation_id=?''',
                    (actor, receipt_mutation))
                if prior is not None:
                    if prior['request_digest'] != digest:
                        raise TransportError(409, 'Memoir editorial request identifier already used')
                    current, _legacy, children, eligible = self._book_context(
                        prior['book_id'], library, member)
                    return self._read_sidecar(current, children, eligible)

                row, _legacy, children, eligible = self._book_context(
                    book_id, library, member)
                try:
                    mutation = parse_mutation(raw, current_book_revision=str(row['revision']),
                                              current_children=children,
                                              eligible_sources=eligible)
                except EditorialContractError as exc:
                    status = 409 if exc.code in {
                        ContractCode.REVISION_CONFLICT, ContractCode.SOURCE_CHANGED,
                    } else 422
                    raise TransportError(status, 'Memoir editorial request is invalid or stale') from None

                current_revision = int(row['revision'])
                if current_revision >= 2**63 - 1:
                    raise TransportError(409, 'Memoir revision cannot advance')
                next_revision = current_revision + 1
                now = self.access._now()
                stored_content = row['content']
                updated = self.db.execute('''UPDATE access_memory_books
                    SET revision=?,content=?,updated_at=? WHERE id=? AND library_id=? AND revision=?''',
                    (next_revision, stored_content, now, book_id, library, current_revision))
                if updated.rowcount != 1:
                    raise TransportError(409, 'Memoir changed; reload before saving')
                self.db.execute('''INSERT INTO access_memory_book_revisions
                    (book_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                    VALUES(?,?,?,?,?,?,?)''',
                    (book_id, next_revision, actor, receipt_mutation, digest,
                     stored_content, now))
                children_json = json.dumps([asdict(child) for child in mutation.children],
                                           ensure_ascii=False, separators=(',', ':'))
                # Source references live only in the normalized refs table so a
                # deletion can remove them while retaining authored transition text.
                transitions_json = json.dumps([
                    {'left_story_id': item.left_story_id,
                     'right_story_id': item.right_story_id,
                     'text': item.text}
                    for item in mutation.transitions
                ], ensure_ascii=False, separators=(',', ':'))
                self.db.execute(f'''INSERT INTO {BOOK_TABLE}
                    (book_id,book_revision,children_json,transitions_json,state)
                    VALUES(?,?,?,?, 'current')''',
                    (book_id, next_revision, children_json, transitions_json))
                ref_rows = []
                for ordinal, ref in enumerate(mutation.introduction_source_refs):
                    ref_rows.append((book_id, next_revision, 'introduction', ordinal,
                                     ref.story_id, int(ref.story_revision), ref.chapter_id,
                                     ref.contribution_id))
                for index, transition in enumerate(mutation.transitions):
                    for ordinal, ref in enumerate(transition.source_refs):
                        ref_rows.append((book_id, next_revision, f'transition-{index:02d}',
                                         ordinal, ref.story_id, int(ref.story_revision),
                                         ref.chapter_id, ref.contribution_id))
                self.db.executemany(f'''INSERT INTO {REFS_TABLE}
                    (book_id,book_revision,section_key,ordinal,story_id,story_revision,
                     chapter_id,contribution_id) VALUES(?,?,?,?,?,?,?,?)''', ref_rows)
                self.access._audit(actor, 'memory.book_editorial_edit', library)
                saved = self.books._row(book_id, library)
                _row, _legacy, current_children, current_eligible = self._book_context(
                    book_id, library, member)
                return self._read_sidecar(saved, current_children, current_eligible)
        except sqlite3.Error:
            raise TransportError(503, 'Memoir editorial unavailable') from None
