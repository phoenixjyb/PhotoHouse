"""In-process read adapter for a host-approved external client.

The host creates and revokes this scope. It is intentionally independent of
credential issuance and network transport. The host session stays inside this
adapter and every disclosure goes through the existing discovery authority.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import re
import secrets
import sqlite3
import threading

from . import discovery
from .discovery_transport import DiscoveryRuntime
from .service import AccessDenied

PAGE_SIZE = 20
MAX_REFERENCES = 128
MAX_CURSORS = 16
_IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,128}')
_HANDLE = re.compile(r'[A-Za-z0-9_-]{32}')


class ExternalSearchRefused(ValueError):
    """Fixed refusal category suitable for a future transport."""


@dataclass(frozen=True)
class _SearchState:
    binding: str
    fingerprint: str
    filters: dict
    page_size: int
    coverage: str


def _filter_values(query, filters):
    if filters is None:
        filters = {}
    if type(filters) is not dict or set(filters) - {'date', 'media'}:
        raise ExternalSearchRefused('invalid_request')
    checked = {}
    if 'media' in filters:
        media = filters['media']
        if (type(media) is not list or not 1 <= len(media) <= 3
                or any(type(kind) is not str or kind not in ('image', 'video', 'other')
                       for kind in media) or len(set(media)) != len(media)):
            raise ExternalSearchRefused('invalid_request')
        checked['media'] = list(media)
    if 'date' in filters:
        bounds = filters['date']
        if (type(bounds) is not dict or set(bounds) != {'from', 'to'}
                or all(day is None for day in bounds.values())
                or any(day is not None and
                       (type(day) is not str or len(day) != 10 or discovery.taken_day(day) != day)
                       for day in bounds.values())
                or (bounds['from'] is not None and bounds['to'] is not None
                    and bounds['from'] > bounds['to'])):
            raise ExternalSearchRefused('invalid_request')
        checked['date'] = dict(bounds)
    if query is not None:
        phrase = discovery.text(query, 512, nonempty=False).strip()
        if phrase:
            checked['caption'] = phrase
    return checked


def _media_projection(item, reference):
    return {'media_ref': reference, 'kind': item['kind'],
            'captured_date': discovery.taken_day(item['taken_at'])}


class ExternalSearchSession:
    """One read-only client and library with independent expiry and revocation.

    Only a trusted host can construct the session or supply the authenticated
    client identity. References and cursors are search-scoped and process-local.
    """

    def __init__(self, runtime, *, client_id, library, host_session, expires_at):
        if (type(runtime) is not DiscoveryRuntime or type(client_id) is not str
                or not _IDENTIFIER.fullmatch(client_id) or type(library) is not str
                or not _IDENTIFIER.fullmatch(library) or type(host_session) is not str
                or not 1 <= len(host_session) <= 128
                or type(expires_at) is not int or expires_at <= 0):
            raise ExternalSearchRefused('invalid_scope')
        self._runtime = runtime
        self._client_id = client_id
        self._library = library
        self._host_session = host_session
        self._expires_at = expires_at
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._search = None
        self._references = {}
        self._cursors = {}

    def revoke(self):
        self._closed.set()
        # If a read is active, its final scope check clears the state instead.
        if self._lock.acquire(blocking=False):
            try:
                self._clear()
            finally:
                self._lock.release()

    def _inactive(self):
        if self._closed.is_set():
            return True
        if self._runtime.access.clock() < self._expires_at:
            return False
        self._closed.set()
        return True

    def _clear(self):
        self._search = None
        self._references.clear()
        self._cursors.clear()

    @contextmanager
    def _read(self, client_id):
        if type(client_id) is not str or client_id != self._client_id:
            raise ExternalSearchRefused('access_denied')
        if not self._lock.acquire(blocking=False):
            raise ExternalSearchRefused('busy')
        try:
            if self._inactive():
                raise AccessDenied()
            self._runtime.authorize(self._host_session, self._library)
            yield
            if self._inactive():
                raise AccessDenied()
            self._runtime.authorize(self._host_session, self._library)
            if self._inactive():
                raise AccessDenied()
        except (AccessDenied, discovery.DiscoveryCancelled):
            self._clear()
            raise ExternalSearchRefused('access_denied') from None
        except discovery.DiscoveryChanged:
            self._clear()
            raise ExternalSearchRefused('search_changed') from None
        except discovery.DiscoveryInvalid:
            raise ExternalSearchRefused('invalid_request') from None
        except discovery.DiscoveryBusy:
            raise ExternalSearchRefused('busy') from None
        except (discovery.DiscoveryUnavailable, discovery.DiscoveryQueryUnsupported,
                sqlite3.Error, RuntimeError, OSError):
            raise ExternalSearchRefused('unavailable') from None
        finally:
            if self._closed.is_set():
                self._clear()
            self._lock.release()

    def _call(self, operation, **values):
        return self._runtime.call(operation, self._host_session, self._library,
                                  self._inactive, values)

    def search_media(self, client_id, *, query=None, filters=None, page_size=None, cursor=None):
        with self._read(client_id):
            if cursor is None:
                size = PAGE_SIZE if page_size is None else page_size
                if type(size) is not int or not 1 <= size <= PAGE_SIZE:
                    raise ExternalSearchRefused('invalid_request')
                constraints = _filter_values(query, filters)
                current = self._call('facets', page_size=1)
                if not set(constraints) <= set(current['enabled']):
                    raise ExternalSearchRefused('filter_unavailable')
                binding, fingerprint, page = current['binding'], None, 1
                coverage = 'complete_catalog' if current['index_complete'] else 'partial_catalog'
            else:
                if (query is not None or filters is not None or page_size is not None
                        or type(cursor) is not str or not _HANDLE.fullmatch(cursor)):
                    raise ExternalSearchRefused('invalid_request')
                if cursor not in self._cursors:
                    raise ExternalSearchRefused('search_changed')
                snapshot = self._search
                binding, fingerprint = snapshot.binding, snapshot.fingerprint
                constraints, size, coverage = snapshot.filters, snapshot.page_size, snapshot.coverage
                page = self._cursors[cursor]

            result = self._call('search', binding=binding, filters=constraints, page=page,
                                page_size=size, fingerprint=fingerprint)
            if cursor is None:
                self._clear()
                self._search = _SearchState(binding, result['fingerprint'], constraints, size, coverage)
            current_refs = {asset_id: reference for reference, asset_id in self._references.items()}
            items = []
            for item in result['items']:
                asset_id = item['id']
                reference = current_refs.get(asset_id) or secrets.token_urlsafe(24)
                self._references.pop(reference, None)
                self._references[reference] = asset_id
                items.append(_media_projection(item, reference))
            while len(self._references) > MAX_REFERENCES:
                del self._references[next(iter(self._references))]
            next_cursor = None
            if result['has_more']:
                next_page = page + 1
                next_cursor = next((key for key, value in self._cursors.items()
                                    if value == next_page), None)
                next_cursor = next_cursor or secrets.token_urlsafe(24)
                self._cursors.pop(next_cursor, None)
                self._cursors[next_cursor] = next_page
                if len(self._cursors) > MAX_CURSORS:
                    del self._cursors[next(iter(self._cursors))]
            return {'version': 1, 'items': items, 'total': result['total'],
                    'next_cursor': next_cursor, 'coverage': coverage}

    def get_media_detail(self, client_id, media_ref):
        with self._read(client_id):
            if (type(media_ref) is not str or not _HANDLE.fullmatch(media_ref)
                    or media_ref not in self._references):
                raise ExternalSearchRefused('access_denied')
            result = self._call('assistant_asset', asset_id=self._references[media_ref],
                                binding=self._search.binding)
            if len(result['items']) != 1:
                self._clear()
                raise ExternalSearchRefused('search_changed')
            return _media_projection(result['items'][0], media_ref)
