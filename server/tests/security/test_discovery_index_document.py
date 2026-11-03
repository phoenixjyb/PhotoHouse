"""Canonical index bindings and admission survive immutable tuple reuse."""
from dataclasses import asdict, replace
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.access import discovery as d
from app.access.discovery_index import accepted, DiscoveryIndexRefused
from app.access.discovery_provider import (ReviewedIndex, ProjectedIndex,
    RefreshingPlaceIndex, RefreshingPeopleIndex, ReviewedPerson, ReviewedFace,
    ReviewedPlace, NamedPlace, RegionRule, MemoryIndexProvider)
from app.access.service import AccessService
from phone_discovery_fixture import create, reviewed, TOKEN, NOW


class DiscoveryIndexDocumentTests(unittest.TestCase):
    def indexes(self):
        common = dict(library_id='family-a', revision='1', scope_ids=('101', '102'),
            indexed_ids=('101', '102'), source_digest='a' * 64,
            people=(ReviewedPerson('family-a', '301', '示例 "person"', ('café',), True),),
            pinned_ids=('301',), assignments=(ReviewedFace('201', '101', '301'),),
            places=(ReviewedPlace('family-a', '601', '湖边'), NamedPlace('family-a', '602', 'Home', ('家',))),
            regions=(('101', '601'), ('102', '602')))
        yield ReviewedIndex(**common)
        yield ProjectedIndex(**common)
        rules = (RegionRule('601', -1.0, -1, 1, 1.0), RegionRule('602', -2, 2, 2, 3))
        yield RefreshingPlaceIndex(**(common | dict(people=(), pinned_ids=(), assignments=(),
            enabled=('date', 'locations', 'media'))), region_rules=rules)
        yield RefreshingPeopleIndex(**(common | dict(enabled=('people', 'date', 'locations', 'media'))),
            region_rules=rules, catalog_digest='b' * 64)

    def test_every_accepted_index_shape_retains_exact_canonical_bytes(self):
        for index in self.indexes():
            with self.subTest(kind=type(index).__name__):
                d.validate(index, 'family-a', 100000)
                self.assertEqual(d.packed(d._index_document(index)), d.packed(asdict(index)))

    def test_large_index_admission_keeps_exact_byte_threshold_and_validation(self):
        index = next(self.indexes())
        scope = tuple(str(value) for value in range(101, 28115))
        index = replace(index, scope_ids=scope, indexed_ids=scope,
                        regions=tuple((value, '601') for value in scope[:13231]))
        expected = len(d.packed(asdict(index)))
        self.assertIs(accepted(index, d.ReadBudget(index_bytes=expected)), index)
        with self.assertRaises(DiscoveryIndexRefused):
            accepted(index, d.ReadBudget(index_bytes=expected - 1))
        with self.assertRaises(DiscoveryIndexRefused):
            accepted(replace(index, scope_ids=('102', '101')), d.ReadBudget())

    def test_search_and_binding_match_the_prior_serializer_and_source_changes_still_fence(self):
        db = create(sqlite3.connect(':memory:'))
        self.addCleanup(db.close)
        access = AccessService(db, clock=lambda: NOW)
        index = reviewed(access)
        service = d.DiscoveryReads(access, MemoryIndexProvider((index,)), d.ReadBudget(seconds=30))
        with patch.object(d, '_index_document', asdict):
            before = service.facets(TOKEN, 'family-a')
            result = service.search(TOKEN, 'family-a', binding=before['binding'], filters={'media': ['image']})
        self.assertEqual(service.facets(TOKEN, 'family-a'), before)
        self.assertEqual(service.search(TOKEN, 'family-a', binding=before['binding'], filters={'media': ['image']}), result)
        db.execute("UPDATE captions SET text='Changed source' WHERE asset_id=101")
        db.commit()
        with self.assertRaises(d.DiscoveryChanged):
            service.search(TOKEN, 'family-a', binding=before['binding'], filters={'media': ['image']})


if __name__ == '__main__':
    unittest.main()
