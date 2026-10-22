"""Authorized, immutable selected-source inputs for an unsaved story proposal.

This internal core performs bounded reads only. It opens no provider, creates no
job, and grants no save authority. A future operation owner must call revalidate
after inference and before exposing output, and separately own admission/lifetime.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import uuid

from .memory_narrative import (
    _canonical_uuid, _id, _object, _revision_string, _string_list, _text,
    _validate_bundle,
)
from .memory_stories import MemoryStories, SOURCE_POLICY, _json, source_policy
from .service import AccessDenied, AccessService
from .story_workspace import _selection, collect_items, selection_revision
from .transport import TransportError


MAX_REQUEST_BYTES = 32 * 1024
MAX_SNAPSHOT_BYTES = 384 * 1024
_REQUEST_KEYS = {'version', 'request_id', 'target', 'selection', 'theme',
                 'language', 'title', 'author_direction'}
_SELECTION_KEYS = {'asset_ids', 'selection_revision', 'source_policy', 'chapters'}


def _encode(value, limit):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(',', ':')).encode('utf-8', errors='strict')
    if len(encoded) > limit:
        raise ValueError('Draft context exceeds its size limit')
    return encoded


def validate_request(request):
    """Validate the closed reference-only request, returning detached JSON data."""
    try:
        _object(request, _REQUEST_KEYS, 'request')
        encoded = _encode(request, MAX_REQUEST_BYTES)
        # Validate the exact captured bytes, not caller-owned mutable objects.
        request = json.loads(encoded)
        if type(request['version']) is not int or request['version'] != 1:
            raise ValueError('Unsupported draft request')
        _canonical_uuid(request['request_id'], 'request id')
        target = _object(request['target'], {'story_id', 'base_revision'}, 'target')
        if target['story_id'] is None:
            if type(target['base_revision']) is not str or target['base_revision'] != '0':
                raise ValueError('Invalid new story revision')
        else:
            _canonical_uuid(target['story_id'], 'story id')
            _revision_string(target['base_revision'], 'base revision')
        selection = _object(request['selection'], _SELECTION_KEYS, 'selection')
        assets = selection['asset_ids']
        if (type(assets) is not list or not 1 <= len(assets) <= 24 or
                any(type(asset) is not str for asset in assets)):
            raise ValueError('Invalid selected media')
        _text(request['title'], 512, 'title')
        _text(request['theme'], 256, 'theme')
        _text(request['language'], 2, 'language')
        _text(request['author_direction'], 8192, 'author direction')
        _selection({'asset_ids': ','.join(assets), 'title': request['title'],
                    'theme': request['theme'], 'language': request['language']})
        revision = selection['selection_revision']
        if type(revision) is not str or re.fullmatch(r'[0-9a-f]{64}', revision) is None:
            raise ValueError('Invalid selection revision')
        if type(selection['source_policy']) is not str or selection['source_policy'] != SOURCE_POLICY:
            raise ValueError('Invalid source policy')
        chapters = selection['chapters']
        if type(chapters) is not list or not 1 <= len(chapters) <= 6:
            raise ValueError('Invalid chapters')
        flattened = []
        for index, chapter in enumerate(chapters):
            _object(chapter, {'id', 'title', 'asset_ids', 'evidence_ids'}, 'chapter')
            if chapter['id'] != f'chapter-{index + 1}':
                raise ValueError('Invalid chapter order')
            _text(chapter['title'], 512, 'chapter title', nonblank=True)
            if len(chapter['title']) > 160 or any(ord(char) < 32 for char in chapter['title']):
                raise ValueError('Invalid chapter title')
            media = _string_list(chapter['asset_ids'], 4, 128, 'chapter assets', ids=True)
            if not media:
                raise ValueError('Empty chapter media')
            flattened.extend(media)
            _string_list(chapter['evidence_ids'], 12, 128, 'chapter evidence', ids=True)
        if flattened != assets:
            raise ValueError('Chapters must partition the ordered selection')
        return json.loads(encoded)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TransportError(400, 'Invalid or oversized draft request') from None


@dataclass(frozen=True, slots=True, repr=False)
class SourceSnapshot:
    """Private process-local evidence; accessors return detached mutable copies.

    No token is retained. This is data, not an authorization capability or a
    serialized request accepted from a client. Revalidation always reads again.
    """

    account_id: str
    library_id: str
    request_digest: str
    operation_id: str
    _request_bytes: bytes
    _document_bytes: bytes
    _bundle_bytes: bytes
    _authorization_bytes: bytes

    def document(self):
        return json.loads(self._document_bytes)

    def bundle(self):
        return json.loads(self._bundle_bytes)


def _source(access, library, item, evidence):
    """Enrich only an already eligible current item source, in its read snapshot."""
    source_id = _id(evidence['id'], 'source id')
    origin = evidence.get('origin_asset_id', item['id'])
    byline = None
    revision = None
    if source_id.startswith('family-') and evidence['source'] == 'family':
        # The existing resolver established destination eligibility, including
        # group links. Check the original note again in the SAME transaction;
        # an origin ID alone cannot authorize a shared note.
        note = access.db.execute('''SELECT s.byline,s.revision FROM access_stories s
            JOIN assets a ON a.id=s.asset_id
            JOIN access_asset_libraries l ON l.asset_id=a.id
            WHERE s.id=? AND s.library_id=? AND s.asset_id=? AND s.revision=?
              AND s.deleted=0 AND l.library_id=?
              AND (a.status IS NULL OR a.status='active')''',
            (source_id[len('family-'):], library, origin, evidence['revision'], library)).fetchone()
        if note is None:
            raise TransportError(409, 'Story references changed')
        byline = _text(note[0], 256, 'source byline')
        revision = note[1]
        kind = 'family_note'
    elif source_id.startswith('caption-') and evidence['source'] in {'family', 'ai'}:
        origin = item['id']
        kind = 'family_edited_caption' if evidence['source'] == 'family' else 'ai_caption'
    else:
        raise TransportError(503, 'Story evidence unavailable')
    text = _text(evidence['text'], 8192, 'source text', nonblank=True)
    descriptor = {'source_id': source_id, 'source_kind': kind,
                  'origin_asset_id': origin, 'source_revision': revision,
                  'byline': byline, 'text': text}
    # Hash the current bounded preview descriptor as well as the exact original
    # byline/origin resolved above. Neither hashes nor bylines come from a model.
    digest = hashlib.sha256(_encode([evidence, descriptor], 32 * 1024)).hexdigest()
    return descriptor | {'source_digest': digest}


def _resolve(runtime, token, library, request, operation_id, *, expected_actor=None):
    selection = request['selection']
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock,
                               memory_groups_enabled=runtime.memory_groups_enabled)
        with access._transaction():
            member = access._require(token, library, 'story.write')
            if expected_actor is not None and member['account_id'] != expected_actor:
                raise AccessDenied('Access denied')
            target = request['target']
            if target['story_id'] is not None:
                store = MemoryStories(access)
                store._ready()
                row = store._row(target['story_id'], library)
                if not store._can_edit(member, row):
                    raise AccessDenied('Access denied')
                source_policy(_json(row['content']))
                if str(row['revision']) != target['base_revision']:
                    raise TransportError(409, 'Story references changed')
            groups = [] if runtime.memory_groups_enabled else None
            items = collect_items(db, library, [int(asset) for asset in selection['asset_ids']],
                                  memory_groups_enabled=runtime.memory_groups_enabled,
                                  group_dependencies=groups)
            if selection_revision(library, items, groups) != selection['selection_revision']:
                raise TransportError(409, 'Story references changed')
            by_asset = {item['id']: item for item in items}
            available = {item['id']: {entry['id']: entry for entry in item['evidence']}
                         for item in items}
            for chapter in selection['chapters']:
                eligible = {source for asset in chapter['asset_ids'] for source in available[asset]}
                if not set(chapter['evidence_ids']) <= eligible:
                    raise TransportError(422, 'Invalid selected story evidence')

            descriptors = {}
            chapters = []
            for chapter in selection['chapters']:
                sources = []
                for reference in chapter['evidence_ids']:
                    destinations = [asset for asset in chapter['asset_ids'] if reference in available[asset]]
                    for asset in destinations:
                        descriptor = _source(access, library, by_asset[asset], available[asset][reference])
                        if reference in descriptors and descriptors[reference] != descriptor:
                            raise TransportError(503, 'Story evidence unavailable')
                        descriptors[reference] = descriptor
                    sources.append(descriptors[reference] | {'selected_asset_ids': destinations})
                chapters.append({'id': chapter['id'], 'title': chapter['title'],
                                 'asset_ids': chapter['asset_ids'], 'sources': sources})
            document = {'version': 1, 'request_id': request['request_id'], 'library_id': library,
                        'target': target, 'selection_revision': selection['selection_revision'],
                        'source_policy': SOURCE_POLICY,
                        'media': [{'asset_id': item['id'], 'kind': item['kind'],
                                   'recorded_at': item['taken_at'], 'stack_id': None} for item in items],
                        'chapters': chapters}
            bundle = {'version': 3, 'library_id': library,
                      'target': {'type': 'draft', 'id': operation_id, 'revision': 0},
                      'selection_revision': selection['selection_revision'],
                      'language': request['language'], 'theme': request['theme'],
                      'title': request['title'], 'instructions': request['author_direction'],
                      'chapters': [chapter | {'narration': ''} for chapter in selection['chapters']],
                      'sources': [{'id': source['source_id'], 'source_kind': source['source_kind'],
                                   'kind': 'ai' if source['source_kind'] == 'ai_caption' else 'family',
                                   'text': source['text'], 'asset_id': source['origin_asset_id'],
                                   'author': source['byline']} for source in descriptors.values()],
                      'recent_turns': []}
            clean = _validate_bundle(bundle, allow_draft=True)
            actor = member['account_id']
            request_bytes = _encode(request, MAX_REQUEST_BYTES)
            request_digest = hashlib.sha256(_encode([actor, library, request],
                                                    MAX_REQUEST_BYTES + 2048)).hexdigest()
            authorization = {key: member[key] for key in
                             ('account_id', 'revision', 'role', 'status', 'expires_at')}
            authorization['memory_groups_enabled'] = runtime.memory_groups_enabled
            return SourceSnapshot(actor, library, request_digest, operation_id,
                                  request_bytes, _encode(document, MAX_SNAPSHOT_BYTES),
                                  _encode(clean, 64 * 1024), _encode(authorization, 2048))


def resolve_snapshot(runtime, token, library, request):
    """Authorize and freeze one request without keeping a transaction open."""
    clean = validate_request(request)
    try:
        _text(library, 128, 'library', nonblank=True)
        return _resolve(runtime, token, library, clean, str(uuid.uuid4()))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TransportError(422, 'Invalid or oversized story context') from None


def revalidate_snapshot(runtime, token, snapshot):
    """Reject revoked, changed or differently owned snapshots; never refresh prose.

    This check is mandatory after future inference. It does not implement an
    operation registry, request deduplication, expiry, admission or late-output
    fencing; those remain the operation owner's responsibility.
    """
    if type(snapshot) is not SourceSnapshot:
        raise ValueError('Expected an internal source snapshot')
    clean = validate_request(json.loads(snapshot._request_bytes))
    try:
        current = _resolve(runtime, token, snapshot.library_id, clean, snapshot.operation_id,
                           expected_actor=snapshot.account_id)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TransportError(409, 'Story references changed') from None
    if current.account_id != snapshot.account_id:
        raise AccessDenied('Access denied')
    if (current.request_digest != snapshot.request_digest or
            current._authorization_bytes != snapshot._authorization_bytes or
            current._document_bytes != snapshot._document_bytes or
            current._bundle_bytes != snapshot._bundle_bytes):
        raise TransportError(409, 'Story references changed')
