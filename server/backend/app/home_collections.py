"""Pinned, database-free library grouping for the anonymous Home TV catalog.

The operator exports this file from an explicitly reviewed catalog snapshot.
Serving never opens the protected database or discovers new memberships.
"""
import hashlib
import json
from pathlib import Path
import re
import threading

from .home_catalog import digest, identity, integer
from .home_feed import Refused, bounded_read, direct_path, exact, unique

MAX_COLLECTIONS = 100
MAX_INDEX = 8 * 1024 * 1024
SLUG = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\Z')


def validate_collections(value, catalog, catalog_sha256):
    exact(value, ('version', 'revision', 'catalog_sha256', 'collections'))
    if (type(value['version']) is not int or value['version'] != 1
            or value['revision'] != catalog['revision']
            or value['catalog_sha256'] != catalog_sha256
            or type(value['collections']) is not list
            or len(value['collections']) > MAX_COLLECTIONS):
        raise Refused()
    assets = {item['id'] for item in catalog['assets']}
    seen = set()
    for item in value['collections']:
        exact(item, ('id', 'title', 'asset_ids'))
        slug, title, ids = item['id'], item['title'], item['asset_ids']
        if (type(slug) is not str or SLUG.fullmatch(slug) is None or slug in seen
                or type(title) is not str or not 1 <= len(title.encode('utf-8')) <= 128
                or any(ord(ch) < 32 for ch in title)
                or type(ids) is not list or len(ids) > len(assets)
                or any(not integer(aid, 1, 2**31-1) for aid in ids)
                or len(set(ids)) != len(ids) or not set(ids) <= assets):
            raise Refused()
        seen.add(slug)
    return value


class CollectionIndex:
    def __init__(self, publication, path: Path, sha256: str):
        if not digest(sha256):
            raise ValueError('Explicit collection hash required')
        direct_path(path)
        if (path in (publication.path, publication.config.manifest)
                or path.is_relative_to(publication.config.media_root)):
            raise ValueError('Collections must be separate from media and control')
        self.publication, self.path, self.sha256 = publication, path, sha256
        self.lock = threading.Lock()
        self.value = None

    def load(self, catalog):
        with self.lock:
            if self.value is None:
                before = identity(self.path)
                raw = bounded_read(self.path, MAX_INDEX)
                if hashlib.sha256(raw).hexdigest() != self.sha256:
                    raise Refused()
                value = validate_collections(json.loads(raw, object_pairs_hook=unique),
                                             catalog, self.publication.pin['catalog_sha256'])
                if identity(self.path) != before:
                    raise Refused()
                self.value, self.pin = value, before
                self.by_id = {item['id']: frozenset(item['asset_ids'])
                              for item in value['collections']}
            if identity(self.path) != self.pin:
                raise Refused(503, 'collections_changed')
            return self.value

    def selected(self, catalog, slug):
        if type(slug) is not str or SLUG.fullmatch(slug) is None:
            raise Refused(400, 'invalid_collection')
        self.load(catalog)
        ids = self.by_id.get(slug)
        if ids is None:
            raise Refused(404, 'collection_unavailable')
        return ids

    def listing(self, catalog):
        value = self.load(catalog)
        kinds = {asset['id']: asset['kind'] for asset in catalog['assets']}
        return {'version': 1, 'revision': catalog['revision'], 'collections': [
            {'id': item['id'], 'title': item['title'],
             'media_count': len(item['asset_ids']),
             'photo_count': sum(kinds[aid] == 'photo' for aid in item['asset_ids']),
             'video_count': sum(kinds[aid] == 'video' for aid in item['asset_ids'])}
            for item in value['collections']]}
