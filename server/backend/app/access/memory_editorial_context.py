"""Build a model context from a current, consent-bound memoir editorial sidecar.

This adapter adds only opaque citation IDs and transition text to an already
hydrated legacy bundle. It never fetches or hydrates additional contribution
content.
"""
from __future__ import annotations

import json
import sqlite3
import uuid

from .memory_book_editorial import MemoryBookEditorial
from .memory_narrative import MAX_BUNDLE_BYTES, _json_bytes, _validate_bundle
from .transport import TransportError


def _conflict():
    raise TransportError(409, 'Memoir editorial context is stale or unavailable')


def _source_id(contribution_id):
    try:
        if (type(contribution_id) is not str
                or str(uuid.UUID(contribution_id)) != contribution_id):
            _conflict()
    except (ValueError, AttributeError):
        _conflict()
    return 'contribution-' + contribution_id


def _copy_sidecar(sidecar):
    try:
        raw = _json_bytes(sidecar, 'editorial sidecar', MAX_BUNDLE_BYTES)
        return json.loads(raw.decode('utf-8'))
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _conflict()


def enrich(access, library, member, book_id, legacy_bundle):
    """Return a detached v2 bundle and its full current sidecar snapshot.

    Callers must gate this function behind both explicit per-job opt-in and the
    deployment feature flag. Current authorization, book children, and source
    consent are rechecked here at context construction time.
    """
    try:
        legacy = _validate_bundle(legacy_bundle)
    except (TypeError, ValueError, RecursionError):
        raise TransportError(422, 'Memoir context is invalid or too large') from None
    target = legacy['target']
    if (legacy['library_id'] != library or target['type'] != 'book' or target['id'] != book_id
            or type(book_id) is not str):
        raise TransportError(400, 'Memoir editorial context requires its book target')

    editorial_store = MemoryBookEditorial(access, enabled=True)
    try:
        editorial_store._ready()
        book_row, _current_book, children, eligible = editorial_store._book_context(
            book_id, library, member)
        sidecar = editorial_store._read_sidecar(book_row, children, eligible)
    except TransportError:
        raise
    except sqlite3.Error:
        raise TransportError(503, 'Memoir editorial unavailable') from None

    # The returned sidecar DTO is already parsed against exact current child
    # revisions and eligible identities. Require a current read; empty or
    # source-changed bases need an explicit editor refresh/save first.
    if (type(sidecar) is not dict or sidecar.get('state') != 'current'
            or sidecar.get('id') != book_id
            or sidecar.get('revision') != str(book_row['revision'])
            or target['revision'] != int(book_row['revision'])):
        _conflict()

    try:
        sidecar = _copy_sidecar(sidecar)
        if set(sidecar) != {'version', 'id', 'revision', 'children', 'state',
                            'introduction_source_refs', 'transitions'}:
            _conflict()
        if type(sidecar['version']) is not int or sidecar['version'] != 1:
            _conflict()
        raw_children = sidecar['children']
        if type(raw_children) is not list or len(raw_children) != len(children):
            _conflict()
        clean_children = []
        by_story = {}
        for expected, child in zip(children, raw_children):
            if (type(child) is not dict or set(child) != {'story_id', 'revision'}
                    or child['story_id'] != expected.story_id
                    or child['revision'] != expected.revision):
                _conflict()
            clean = {'story_id': expected.story_id, 'revision': expected.revision}
            clean_children.append(clean)
            by_story[expected.story_id] = expected.revision

        source_by_id = {source['id']: source for source in legacy['sources']}
        evidence_by_child = {child['story_id']: {} for child in clean_children}
        for chapter in legacy['chapters']:
            matching = [story_id for story_id in by_story
                        if chapter['id'].startswith(story_id + '-')]
            if len(matching) == 1:
                evidence_by_child[matching[0]][chapter['id']] = set(chapter['evidence_ids'])

        def resolve(ref, allowed_stories):
            if (type(ref) is not dict or set(ref) != {
                    'story_id', 'story_revision', 'chapter_id', 'contribution_id'}):
                _conflict()
            story_id = ref['story_id']
            if (story_id not in allowed_stories
                    or ref['story_revision'] != by_story.get(story_id)):
                _conflict()
            source_id = _source_id(ref['contribution_id'])
            source = source_by_id.get(source_id)
            chapter_id = story_id + '-' + ref['chapter_id']
            chapter_evidence = evidence_by_child.get(story_id, {}).get(chapter_id)
            if (source is None or source['kind'] not in {'family', 'transcript'}
                    or chapter_evidence is None or source_id not in chapter_evidence):
                _conflict()
            return source_id

        introductions = sidecar['introduction_source_refs']
        if type(introductions) is not list or len(introductions) > 12:
            _conflict()
        raw_introduction_ids = [resolve(ref, set(by_story)) for ref in introductions]
        introduction_ids = list(dict.fromkeys(raw_introduction_ids))

        raw_transitions = sidecar['transitions']
        if type(raw_transitions) is not list or len(raw_transitions) != len(clean_children) - 1:
            _conflict()
        transitions = []
        total_refs = len(raw_introduction_ids)
        for index, transition in enumerate(raw_transitions):
            if (type(transition) is not dict or set(transition) != {
                    'left_story_id', 'right_story_id', 'text', 'source_refs'}):
                _conflict()
            left, right = clean_children[index]['story_id'], clean_children[index + 1]['story_id']
            if transition['left_story_id'] != left or transition['right_story_id'] != right:
                _conflict()
            refs = transition['source_refs']
            if type(refs) is not list or len(refs) > 12:
                _conflict()
            raw_source_ids = [resolve(ref, {left, right}) for ref in refs]
            source_ids = list(dict.fromkeys(raw_source_ids))
            transitions.append({
                'left_story_id': left,
                'right_story_id': right,
                'text': transition['text'],
                'source_ids': source_ids,
            })
            total_refs += len(raw_source_ids)
        if total_refs > 96:
            _conflict()

        enriched = {
            **legacy,
            'version': 2,
            'book_editorial': {
                'children': clean_children,
                'introduction_source_ids': introduction_ids,
                'transitions': transitions,
            },
        }
        try:
            encoded = json.dumps(enriched, ensure_ascii=False, allow_nan=False,
                                 separators=(',', ':')).encode('utf-8', errors='strict')
        except (TypeError, ValueError, UnicodeError, RecursionError):
            _conflict()
        if len(encoded) > MAX_BUNDLE_BYTES:
            raise TransportError(422, 'Choose a smaller memoir context')
        try:
            enriched = _validate_bundle(enriched)
        except (TypeError, ValueError, RecursionError):
            _conflict()
        return enriched, sidecar
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        _conflict()
