"""Private kinship graph contract tests with fictional people only."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.kinship import (
    KinshipGraph,
    KinshipUnavailable,
    PrivateKinshipProvider,
    load_private_graph,
)
from app.access.discovery_provider import ReviewedPerson


SOURCE_ROOT = ROOT.parent


def graph_document(*, revision='revision-1', perspective='child', scope=None):
    return {
        'schema': 1,
        'graph_id': 'fictional-household',
        'revision': revision,
        'perspective_id': perspective,
        'scope': scope or {'account_id': 'account-one', 'library_id': 'library-one'},
        'people': [
            {'id': 'child', 'name_en': 'Child One', 'name_zh': '示例儿童',
             'aliases': ['the child'], 'catalog_binding': None},
            {'id': 'mother', 'name_en': 'Parent One', 'name_zh': '示例家长一',
             'aliases': ['Ma One'], 'catalog_binding': None},
            {'id': 'father', 'name_en': 'Parent Two', 'name_zh': '示例家长二',
             'aliases': [], 'catalog_binding': None},
            {'id': 'maternal-grandmother', 'name_en': 'Grandparent One', 'name_zh': None,
             'aliases': [], 'catalog_binding': None},
            {'id': 'maternal-grandfather', 'name_en': 'Grandparent Two', 'name_zh': None,
             'aliases': [], 'catalog_binding': None},
            {'id': 'paternal-grandmother', 'name_en': 'Grandparent Three', 'name_zh': None,
             'aliases': [], 'catalog_binding': None},
            {'id': 'paternal-grandfather', 'name_en': 'Grandparent Four', 'name_zh': None,
             'aliases': [], 'catalog_binding': None},
            {'id': 'older-sister', 'name_en': 'Sibling One', 'name_zh': '示例姐姐',
             'aliases': ['Sis One'], 'catalog_binding': None},
            {'id': 'younger-sister', 'name_en': 'Sibling Two', 'name_zh': '示例妹妹',
             'aliases': [], 'catalog_binding': None},
            {'id': 'elder-daughter', 'name_en': 'Child Two', 'name_zh': '示例女儿一',
             'aliases': [], 'catalog_binding': None},
            {'id': 'younger-daughter', 'name_en': 'Child Three', 'name_zh': '示例女儿二',
             'aliases': [], 'catalog_binding': None},
            {'id': 'husband', 'name_en': 'Partner One', 'name_zh': '示例配偶',
             'aliases': ['Partner Alias'], 'catalog_binding': None},
        ],
        'assertions': [
            {'id': 'a-mother', 'subject_id': 'child', 'relation': 'mother', 'object_id': 'mother', 'source': 'user'},
            {'id': 'a-father', 'subject_id': 'child', 'relation': 'father', 'object_id': 'father', 'source': 'user'},
            {'id': 'a-mgm', 'subject_id': 'mother', 'relation': 'mother', 'object_id': 'maternal-grandmother', 'source': 'user'},
            {'id': 'a-mgf', 'subject_id': 'mother', 'relation': 'father', 'object_id': 'maternal-grandfather', 'source': 'user'},
            {'id': 'a-pgm', 'subject_id': 'father', 'relation': 'mother', 'object_id': 'paternal-grandmother', 'source': 'user'},
            {'id': 'a-pgf', 'subject_id': 'father', 'relation': 'father', 'object_id': 'paternal-grandfather', 'source': 'user'},
            {'id': 'a-older', 'subject_id': 'child', 'relation': 'older_sister', 'object_id': 'older-sister', 'source': 'user'},
            {'id': 'a-younger', 'subject_id': 'child', 'relation': 'younger_sister', 'object_id': 'younger-sister', 'source': 'user'},
            {'id': 'a-elder-daughter', 'subject_id': 'child', 'relation': 'elder_daughter', 'object_id': 'elder-daughter', 'source': 'user'},
            {'id': 'a-younger-daughter', 'subject_id': 'child', 'relation': 'younger_daughter', 'object_id': 'younger-daughter', 'source': 'user'},
            {'id': 'a-husband', 'subject_id': 'child', 'relation': 'husband', 'object_id': 'husband', 'source': 'user'},
        ],
    }


class KinshipGraphTests(unittest.TestCase):
    def setUp(self):
        self.graph = KinshipGraph(graph_document())

    def test_bare_relative_uses_explicit_perspective_in_english_and_chinese(self):
        for phrase in ('mom', 'my mother', '妈妈', '母亲'):
            with self.subTest(phrase=phrase):
                self.assertEqual(self.graph.resolve(phrase), {'mother'})

    def test_parent_chains_reach_maternal_and_paternal_grandparents(self):
        for phrase, expected in (
            ("my mother's mother", 'maternal-grandmother'),
            ("my mother's father", 'maternal-grandfather'),
            ("my father's mother", 'paternal-grandmother'),
            ("my father's father", 'paternal-grandfather'),
            ('我妈妈的妈妈', 'maternal-grandmother'),
            ('我妈妈的爸爸', 'maternal-grandfather'),
            ('我爸爸的妈妈', 'paternal-grandmother'),
            ('我爸爸的爸爸', 'paternal-grandfather'),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(self.graph.resolve(phrase), {expected})

    def test_parent_name_can_anchor_a_conjoined_parent_pair(self):
        people, phrases, ambiguous = self.graph.mentions(
            "Parent One's mother and father")
        self.assertEqual(people, {'maternal-grandmother', 'maternal-grandfather'})
        self.assertEqual(set(phrases), {"Parent One's mother", 'father'})
        self.assertFalse(ambiguous)

    def test_sibling_daughter_spouse_and_direct_aliases_resolve(self):
        for phrase, expected in (
            ('older sister', 'older-sister'), ('姐姐', 'older-sister'),
            ('Sibling One', 'older-sister'), ('Sis One', 'older-sister'),
            ('younger sister', 'younger-sister'), ('妹妹', 'younger-sister'),
            ('my elder daughter', 'elder-daughter'), ('大女儿', 'elder-daughter'),
            ('my younger daughter', 'younger-daughter'), ('小女儿', 'younger-daughter'),
            ('my husband', 'husband'), ('my spouse', 'husband'),
            ('丈夫', 'husband'), ('配偶', 'husband'), ('Partner Alias', 'husband'),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(self.graph.resolve(phrase), {expected})

    def test_missing_and_ambiguous_phrases_are_distinct_from_unique_matches(self):
        document = graph_document()
        document['people'].append({
            'id': 'other-parent', 'name_en': 'Parent Other', 'name_zh': None,
            'aliases': ['Ma One'], 'catalog_binding': None,
        })
        graph = KinshipGraph(document)
        self.assertEqual(graph.resolve('not in this graph'), set())
        self.assertEqual(graph.resolve('Ma One'), {'mother', 'other-parent'})

    def test_mentions_returns_consumed_relative_and_alias_phrases(self):
        people, phrases, ambiguous = self.graph.mentions(
            'Photos with my mother and Sis One')
        self.assertEqual(people, {'mother', 'older-sister'})
        self.assertEqual(set(phrases), {'my mother', 'Sis One'})
        self.assertFalse(ambiguous)

    def test_conjunction_includes_requested_people_without_implicitly_adding_anchor(self):
        people, phrases, ambiguous = self.graph.mentions(
            'Child One and my mother together')
        self.assertEqual(people, {'child', 'mother'})
        self.assertNotIn('older-sister', people)
        self.assertNotIn('father', people)
        self.assertFalse(ambiguous)

    def test_spouse_and_sibling_do_not_imply_unasserted_parent_links(self):
        for phrase in ("my husband's mother", "my older sister's father",
                       "my younger sister's mother", '我丈夫的妈妈', '我姐姐的爸爸'):
            with self.subTest(phrase=phrase):
                self.assertEqual(self.graph.resolve(phrase), set())

    def test_identity_digest_changes_with_revision_and_perspective(self):
        changed_revision = KinshipGraph(graph_document(revision='revision-2'))
        changed_perspective = KinshipGraph(graph_document(perspective='mother'))
        self.assertTrue(self.graph.digest)
        self.assertNotEqual(self.graph.digest, changed_revision.digest)
        self.assertNotEqual(self.graph.digest, changed_perspective.digest)
        self.assertEqual(self.graph.perspective_id, 'child')

    def test_catalog_ids_require_unique_current_reviewed_match_or_explicit_binding(self):
        targets = {'mother'}
        reviewed = (ReviewedPerson('library-one', '301', 'Parent One / 示例家长一',
                                   ('Parent One', '示例家长一'), True),)
        self.assertEqual(self.graph.catalog_ids(targets, reviewed), {'301'})

        duplicate = reviewed + (ReviewedPerson('library-one', '302', 'Parent One', (), True),)
        with self.assertRaises(KinshipUnavailable):
            self.graph.catalog_ids(targets, duplicate)
        with self.assertRaises(KinshipUnavailable):
            self.graph.catalog_ids(targets, ())

        bound_doc = graph_document()
        bound_doc['people'][1]['catalog_binding'] = {'person_id': '303', 'label': 'Current Parent One'}
        bound = KinshipGraph(bound_doc)
        current = (ReviewedPerson('library-one', '303', 'Current Parent One', (), True),)
        self.assertEqual(bound.catalog_ids(targets, current), {'303'})
        stale = (ReviewedPerson('library-one', '303', 'Renamed Parent', (), True),)
        with self.assertRaises(KinshipUnavailable):
            bound.catalog_ids(targets, stale)

    def test_generic_relative_alias_cannot_supply_a_catalog_identity_join(self):
        document = graph_document()
        document['people'][1]['aliases'].append('妈妈')
        graph = KinshipGraph(document)
        unrelated = (ReviewedPerson('library-one', '301', 'Another Person', ('妈妈',), True),)
        with self.assertRaises(KinshipUnavailable):
            graph.catalog_ids({'mother'}, unrelated)

    def test_distinct_logical_people_cannot_collapse_to_one_reviewed_identity(self):
        reviewed = (ReviewedPerson('library-one', '301', 'Parent One', ('Parent Two',), True),)
        with self.assertRaises(KinshipUnavailable):
            self.graph.catalog_ids({'mother', 'father'}, reviewed)

    def test_foreign_library_catalog_identity_is_never_a_binding_candidate(self):
        foreign = (ReviewedPerson('another-library', '301', 'Parent One', (), True),)
        with self.assertRaises(KinshipUnavailable):
            self.graph.catalog_ids({'mother'}, foreign)


class PrivateKinshipProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='private-kinship-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        os.chmod(self.root, 0o700)
        self.path = self.root / 'catalog.json'
        self.write(graph_document())

    def write(self, document):
        self.path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        os.chmod(self.path, 0o600)

    def test_scoped_provider_returns_graph_only_for_exact_account_and_library(self):
        provider = PrivateKinshipProvider(self.path, source_root=SOURCE_ROOT)
        self.assertIsNotNone(provider.get('account-one', 'library-one'))
        self.assertIsNone(provider.get('account-two', 'library-one'))
        self.assertIsNone(provider.get('account-one', 'library-two'))

    def test_selected_account_allowlist_is_exact_and_empty_draft_is_inactive(self):
        document = graph_document(scope={'account_ids': ['account-one', 'account-two'], 'library_id': 'library-one'})
        self.write(document)
        provider = PrivateKinshipProvider(self.path, source_root=SOURCE_ROOT)
        self.assertIsNotNone(provider.get('account-one', 'library-one'))
        self.assertIsNotNone(provider.get('account-two', 'library-one'))
        self.assertIsNone(provider.get('account-three', 'library-one'))
        self.assertIsNone(provider.get('account-one', 'library-two'))
        self.write(graph_document(scope={'account_ids': [], 'library_id': None}))
        self.assertIsNone(provider.get('account-one', 'library-one'))

    def test_owner_only_file_and_parent_are_required(self):
        provider = PrivateKinshipProvider(self.path, source_root=SOURCE_ROOT)
        os.chmod(self.path, 0o644)
        with self.assertRaises(KinshipUnavailable):
            provider.get('account-one', 'library-one')
        os.chmod(self.path, 0o600)
        os.chmod(self.root, 0o755)
        with self.assertRaises(KinshipUnavailable):
            provider.get('account-one', 'library-one')

    def test_graph_edit_and_deletion_fail_closed_without_private_error_text(self):
        provider = PrivateKinshipProvider(self.path, source_root=SOURCE_ROOT)
        original = provider.get('account-one', 'library-one')
        self.write(graph_document(revision='revision-2'))
        changed = provider.get('account-one', 'library-one')
        self.assertNotEqual(original.digest, changed.digest)
        self.path.unlink()
        with self.assertRaises(KinshipUnavailable) as caught:
            provider.get('account-one', 'library-one')
        self.assertNotIn('Child One', str(caught.exception))

    def test_duplicate_keys_unknown_fields_and_cycles_are_rejected_generically(self):
        self.path.write_text('{"schema":1,"schema":1}', encoding='utf-8')
        os.chmod(self.path, 0o600)
        with self.assertRaises(KinshipUnavailable):
            load_private_graph(self.path, SOURCE_ROOT)

        bad = graph_document()
        bad['unexpected_private_field'] = 'fictional secret'
        self.write(bad)
        with self.assertRaises(KinshipUnavailable) as caught:
            load_private_graph(self.path, SOURCE_ROOT)
        self.assertNotIn('fictional secret', str(caught.exception))

        bad = graph_document()
        bad['assertions'].extend([
            {'id': 'cycle-one', 'subject_id': 'mother', 'relation': 'mother', 'object_id': 'father', 'source': 'user'},
            {'id': 'cycle-two', 'subject_id': 'father', 'relation': 'mother', 'object_id': 'mother', 'source': 'user'},
        ])
        self.write(bad)
        with self.assertRaises(KinshipUnavailable):
            load_private_graph(self.path, SOURCE_ROOT)

        bad = graph_document()
        bad['assertions'].append(
            {'id': 'contradiction', 'subject_id': 'child', 'relation': 'mother',
             'object_id': 'father', 'source': 'user'})
        self.write(bad)
        with self.assertRaises(KinshipUnavailable):
            load_private_graph(self.path, SOURCE_ROOT)

    def test_symlink_and_source_root_catalog_are_rejected(self):
        link = self.root / 'link.json'
        link.symlink_to(self.path)
        with self.assertRaises(KinshipUnavailable):
            load_private_graph(link, SOURCE_ROOT)
        with self.assertRaises(KinshipUnavailable):
            load_private_graph(self.path, self.root)


if __name__ == '__main__':
    unittest.main()
