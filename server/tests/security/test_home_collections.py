"""Synthetic LAN library navigation; no live database or family media."""
import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.home_catalog import Configuration, Publication
from app.home_collections import CollectionIndex
from app.home_calendar import create_home_calendar
from app.home_originals import SourceIndex, create_home_originals
from app.photo_delivery import PhotoCache
from build_home_source_index import inspect_source
from export_home_tv_collections import export


ROOT = Path(__file__).resolve().parents[2]
PHOTO = (ROOT / 'tests/security/fixtures/home-8x8.jpg').read_bytes()


class HomeCollectionsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        self.root = root
        originals = root / 'originals'; originals.mkdir()
        media = root / 'prepared'; media.mkdir()
        for aid in (101, 102):
            (originals / f'{aid}.jpg').write_bytes(PHOTO)
        missing = {'state': 'unavailable', 'reason': 'not_prepared'}
        self.catalog = {'version': 2, 'revision': 4, 'library_id': 'home-library',
                        'title': 'PhotoHouse', 'assets': [
            {'id': aid, 'kind': 'photo', 'label': f'Asset {aid}', 'width': 8, 'height': 8,
             'previews': {'grid': missing, 'display': missing}, 'video': None}
            for aid in (102, 101)]}
        raw = json.dumps(self.catalog).encode()
        (root / 'catalog.json').write_bytes(raw)
        self.catalog_sha = hashlib.sha256(raw).hexdigest()
        (root / 'control.json').write_text(json.dumps({'version': 2, 'enabled': True,
            'revision': 4, 'catalog_sha256': self.catalog_sha}))
        self.config = Configuration(root / 'control.json', media,
                                    'https://photos.example.test', ('192.168.40.0/24',))
        entries = [dict(id=aid, **inspect_source(originals / f'{aid}.jpg',
                                                  (originals,), 'photo')) for aid in (101, 102)]
        source_raw = json.dumps({'version': 1, 'catalog_sha256': self.catalog_sha,
                                 'assets': entries}).encode()
        source_path = root / 'sources.json'; source_path.write_bytes(source_raw)
        self.sources = SourceIndex(Publication(self.config), source_path,
                                   hashlib.sha256(source_raw).hexdigest(), (originals,))
        self.db = root / 'metadata.sqlite'
        with closing(sqlite3.connect(self.db)) as db, db:
            db.executescript('''CREATE TABLE assets(id INTEGER PRIMARY KEY,status TEXT);
                CREATE TABLE access_libraries(id TEXT PRIMARY KEY,state TEXT);
                CREATE TABLE access_asset_libraries(asset_id INTEGER,library_id TEXT);''')
            db.executemany('INSERT INTO assets VALUES (?,?)', ((101, 'active'), (102, 'active')))
            db.executemany('INSERT INTO access_libraries VALUES (?,?)',
                           (('family', 'active'), ('work', 'active'), ('empty', 'active')))
            db.executemany('INSERT INTO access_asset_libraries VALUES (?,?)',
                           ((101, 'family'), (102, 'work')))
        self.collection_path = root / 'collections.json'
        receipt = export(self.db, root / 'catalog.json', self.collection_path)
        self.collections = CollectionIndex(self.sources.publication, self.collection_path,
                                            receipt['sha256'])
        app = create_home_originals(self.config, self.sources,
                                    PhotoCache(root / 'cache'), self.collections)
        self.client = TestClient(app, base_url=self.config.origin,
                                 client=('192.168.40.20', 1))
        self.addCleanup(self.client.close)

    def test_lists_named_libraries_and_filters_before_pagination(self):
        listing = self.client.get('/home/v3/collections')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([(x['id'], x['media_count']) for x in listing.json()['collections']],
                         [('empty', 0), ('family', 1), ('work', 1)])
        self.assertNotIn('asset_ids', listing.text)
        all_items = self.client.get('/home/v3/catalog?page_size=1').json()
        self.assertEqual(all_items['total'], 2)
        family = self.client.get('/home/v3/catalog?collection=family&page_size=1').json()
        self.assertEqual((family['total'], family['items'][0]['id']), (1, 101))
        ready = self.client.get('/home/v3/catalog?collection=family&browse=1&availability=ready&media=photo').json()
        self.assertEqual((ready['total'], ready['browse']['ready_total']), (1, 1))
        empty = self.client.get('/home/v3/catalog?collection=empty').json()
        self.assertEqual((empty['total'], empty['items']), (0, []))
        self.assertEqual(self.client.get('/home/v3/catalog?collection=missing').status_code, 404)
        self.assertEqual(self.client.get('/home/v3/catalog?collection=INVALID').status_code, 400)
        self.assertEqual(self.client.get('/home/v3/catalog?collection=family&page=2').status_code, 400)

    def test_tampered_index_or_wrong_peer_fails_closed(self):
        self.assertEqual(self.client.get('/home/v3/collections').status_code, 200)
        self.collection_path.write_text(self.collection_path.read_text() + ' ')
        self.assertEqual(self.client.get('/home/v3/collections').status_code, 503)
        self.assertEqual(self.client.get('/home/v3/catalog?collection=family').status_code, 503)
        other = TestClient(self.client.app, base_url=self.config.origin,
                           client=('192.168.41.10', 1))
        self.addCleanup(other.close)
        self.assertEqual(other.get('/home/v3/collections').status_code, 403)

    def test_calendar_search_composition_keeps_library_selector(self):
        # The live Home service composes calendar, tags, search and v3 media.
        # Their indexes are lazy for a v3 request, but the collection index must
        # still reach the nested media app.
        unavailable = self.root / 'unused-discovery.json'
        app = create_home_calendar(self.config, self.sources, PhotoCache(self.root / 'other-cache'),
                                   unavailable, '0' * 64, unavailable, '0' * 64, self.collections)
        with TestClient(app, base_url=self.config.origin, client=('192.168.40.20', 1)) as client:
            self.assertEqual(client.get('/home/v3/collections').json()['collections'][1]['id'], 'family')
            self.assertEqual(client.get('/home/v3/catalog?collection=work').json()['items'][0]['id'], 102)

    def test_export_rejects_stale_catalog_and_never_overwrites(self):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("INSERT INTO assets VALUES (103,'active')")
        candidate = self.root / 'stale.json'
        with self.assertRaises(ValueError):
            export(self.db, self.root / 'catalog.json', candidate)
        self.assertFalse(candidate.exists())
        with self.assertRaises(ValueError):
            export(self.db, self.root / 'catalog.json', self.collection_path)
