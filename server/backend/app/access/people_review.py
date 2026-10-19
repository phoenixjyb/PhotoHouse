"""Explicit owner visual confirmations; no assignment or search-index writes.

The existing audit stores opaque, revision-bound confirmation markers. A manual
catalog association alone is never evidence of this separate human action.
"""
from dataclasses import asdict
import hashlib
import hmac
import json
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import discovery as d
from .discovery_provider import RefreshingPeopleIndex
from .discovery_transport import DiscoveryRuntime
from .library import LibraryRoute, _integer, _query
from .people import People, SCOPED
from .service import AccessService
from .transport import _body, _runtime, credentials_from_request, TransportError

router = APIRouter(route_class=LibraryRoute)
BATCH_SIZE = 12
SCAN_LIMIT = 120


class PeopleReview(People):
    def __init__(self, access, provider=None, budget=None):
        super().__init__(access)
        self.provider = provider
        self.budget = budget or d.ReadBudget()

    def _index(self, library, read, check):
        # Called only after current owner authorization, inside the transaction.
        if self.provider is None:
            raise d.DiscoveryUnavailable()
        index = self.provider.get(library)
        if type(index) is not RefreshingPeopleIndex:
            raise d.DiscoveryUnavailable()
        d.validate(index, library, self.budget.rows)
        if len(d.packed(asdict(index))) > self.budget.index_bytes:
            raise d.DiscoveryUnavailable()
        source = {'reviewed_people': d.reviewed_people_source(library, index.people, read)}
        d.validate_people_source(index, source)
        current = d.reviewed_faces_source(library, index.assignments, read)
        if {(str(f), str(a), str(p), s) for f, a, p, s in current} != {
                (a.id, a.asset_id, a.person_id, a.source) for a in index.assignments}:
            raise d.DiscoveryChanged()
        check()
        return index

    def _target(self, person, library, index):
        row = self._person(person, library)
        if (self.db.execute('SELECT library_id FROM access_person_libraries WHERE person_id=?',
                            (person,)).fetchone() != (library,) or
                not self._exclusive(person, library)):
            raise TransportError(409, 'Person ownership changed; refresh review')
        selected = next((p for p in index.people if p.id == str(person)), None)
        if selected is None or selected.label != row[1] or row[3] > 128:
            raise TransportError(409, 'Reviewed identity unavailable; refresh review')
        return row

    def _proof(self, member, library, row, target):
        key = self.db.execute('SELECT secret FROM access_admission_key WHERE id=1').fetchone()[0]
        binding = [library, member['account_id'], member['revision'],
                   self._face_revision(row, library), self._revision(target, library)]
        return hmac.new(key, b'PhotoHouse face visual confirmation v1\0' +
                        json.dumps(binding).encode(), hashlib.sha256).hexdigest()

    def _record(self, member, library, row, target):
        proof = self._proof(member, library, row, target)
        action = 'face.review.' + proof
        saved = self.db.execute('''SELECT id FROM access_audit
            WHERE actor_account=? AND library_id=? AND action=? ORDER BY id DESC LIMIT 1''',
            (member['account_id'], library, action)).fetchone()
        return proof, action, saved

    def _run(self, token, library, action, *, write=False):
        with self.budget.attempt(self.db, lambda: False) as (check, read):
            with self.access._transaction(write=write):
                member = self.access._require(token, library, 'library.people.manage')
                index = self._index(library, read, check)
                result = action(member, index, check, read)
                check()
                if len(d.packed(result)) > min(64 * 1024, self.budget.response_bytes):
                    raise d.DiscoveryUnavailable()
                return result

    def queue(self, token, library, person, before=None):
        def action(member, index, check, read):
            target = self._target(person, library, index)
            active = {int(a.id) for a in index.assignments}
            cursor = before
            items, scanned, exhausted = [], 0, False
            while len(items) < BATCH_SIZE and scanned < SCAN_LIMIT:
                rows = read('SELECT f.id' + SCOPED + " AND f.person_id=? AND f.label_source='manual'"
                            + ' AND (? IS NULL OR f.id<?) ORDER BY f.id DESC LIMIT 24',
                            (library, person, cursor, cursor))
                if not rows:
                    exhausted = True
                    break
                for face, in rows:
                    check()
                    cursor = face
                    scanned += 1
                    if face not in active:
                        row = self._face(face, library)
                        proof, _, saved = self._record(member, library, row, target)
                        if saved is None:
                            item = self._present_face(row, library)
                            item.update(person_revision=self._revision(target, library), review_revision=proof,
                                crop_url=f'/faces/{face}/crop?' + urlencode({'library': library}),
                                thumbnail_url=f'/assets/{row[1]}/thumbnail?' + urlencode({'library': library}),
                                identity_confirmed=False, search_eligible=False)
                            items.append(item)
                    if len(items) == BATCH_SIZE or scanned == SCAN_LIMIT:
                        break
                else:
                    if len(rows) < 24:
                        exhausted = True
                        break
                    continue
                break
            return {'status': 'requires_explicit_review', 'library_id': library,
                    'person': {'id': str(person), 'display_name': target[1],
                               'revision': self._revision(target, library)},
                    'items': items, 'next_before': None if exhausted else str(cursor)}
        return self._run(token, library, action)

    def _selected(self, face, library, index):
        row = self._face(face, library)
        if row[2] is None or row[3] != 'manual':
            raise TransportError(409, 'Manual association changed; refresh review')
        return row, self._target(row[2], library, index)

    def status(self, token, library, face):
        def action(member, index, check, read):
            row, target = self._selected(face, library, index)
            proof, _, saved = self._record(member, library, row, target)
            return {'face_id': str(face), 'asset_id': str(row[1]), 'person_id': str(row[2]),
                    'identity_confirmed': saved is not None, 'review_revision': proof,
                    'search_activated': False}
        return self._run(token, library, action)

    def confirm(self, token, library, face, body):
        person = _integer(body['person_id'], 2**63 - 1)
        if any(not d.hashed(body[key]) for key in ('revision', 'person_revision', 'review_revision')):
            raise TransportError(400, 'Invalid review')
        def action(member, index, check, read):
            row, target = self._selected(face, library, index)
            proof, marker, saved = self._record(member, library, row, target)
            expected = {'revision': self._face_revision(row, library),
                        'person_revision': self._revision(target, library), 'review_revision': proof}
            if row[2] != person or any(not hmac.compare_digest(body[k], v) for k, v in expected.items()):
                raise TransportError(409, 'Review changed; refresh before confirming')
            if self._face_job_conflict(row[1]):
                raise TransportError(409, 'Face processing active; review later')
            if saved is None:
                self.access._audit(member['account_id'], marker, library)
            return {'status': 'visual_confirmation_recorded', 'face_id': str(face),
                    'asset_id': str(row[1]), 'person_id': str(person), 'source': 'manual',
                    'review_revision': proof, 'identity_confirmed': True, 'search_activated': False}
        return self._run(token, library, action, write=True)


def _call(runtime, engine, method, token, library, *args):
    with runtime.connection_factory() as connection:
        valid = isinstance(engine, DiscoveryRuntime) and engine.access is runtime
        service = PeopleReview(AccessService(connection, clock=runtime.clock),
                               engine.provider if valid else None, engine.budget if valid else None)
        try:
            return getattr(service, method)(token, library, *args)
        except d.DiscoveryChanged:
            raise TransportError(409, 'Review source changed; refresh review') from None
        except d.DiscoveryInvalid:
            raise TransportError(400, 'Invalid review') from None
        except d.DiscoveryBusy:
            raise TransportError(429, 'Review busy; try later') from None
        except (d.DiscoveryUnavailable, d.DiscoveryCancelled):
            raise TransportError(503, 'Review unavailable') from None


async def _invoke(request, method, token, library, *args):
    runtime = _runtime(request, allow_query=True)
    engine = getattr(request.app.state, 'discovery_runtime', None)
    return JSONResponse(await run_in_threadpool(_call, runtime, engine, method, token, library, *args))


@router.get('/admin/people/{person_id}/review')
async def queue(person_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'before'})
    before = _integer(query['before'], 2**63 - 1) if 'before' in query else None
    return await _invoke(request, 'queue', token, query['library'], _integer(person_id, 2**63 - 1), before)


@router.get('/admin/faces/{face_id}/review')
async def status(face_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    return await _invoke(request, 'status', token, query['library'], _integer(face_id, 2**63 - 1))


@router.post('/admin/faces/{face_id}/review')
async def confirm(face_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'person_id', 'revision', 'person_revision', 'review_revision'})
    return await _invoke(request, 'confirm', token, query['library'], _integer(face_id, 2**63 - 1), body)
