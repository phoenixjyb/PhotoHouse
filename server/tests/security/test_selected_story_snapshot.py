"""Security checks for the selected-source story snapshot boundary."""
import copy
import unittest
import uuid
from dataclasses import FrozenInstanceError, replace

import test_shared_memory_evidence as fixture
from app.access.selected_story_snapshot import (
    revalidate_snapshot, resolve_snapshot, validate_request,
)
from app.access.service import AccessDenied
from app.access.transport import TransportError


class SelectedStorySnapshotTests(unittest.TestCase):
    """Use only generated family-a/family-b fixtures from the existing suite."""

    @classmethod
    def setUpClass(cls):
        fixture.SharedMemoryEvidenceTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.SharedMemoryEvidenceTests.tearDownClass()

    def setUp(self):
        self.f = fixture.SharedMemoryEvidenceTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.runtime = self.f.runtime
        self.owner = self.f.owner
        self.member = self.f.base.member
        self.request_id = '22222222-2222-4222-8222-222222222222'

    def request(self, *, assets=('102', '101'), chapters=None, target=None,
                selection_revision=None, evidence=None):
        """Build explicit chapter partitions from a current authorized preview."""
        if selection_revision is None:
            preview = self.f.preview(','.join(assets))
            self.assertEqual(preview.status_code, 200, preview.text)
            selection_revision = preview.json()['selection_revision']
        if chapters is None:
            chapters = [
                {'id': 'chapter-1', 'title': 'First scene', 'asset_ids': [assets[0]],
                 'evidence_ids': []},
                {'id': 'chapter-2', 'title': 'Second scene', 'asset_ids': list(assets[1:]),
                 'evidence_ids': []},
            ]
        elif evidence is not None:
            chapters = copy.deepcopy(chapters)
            chapters[0]['evidence_ids'] = list(evidence)
        return {
            'version': 1,
            'request_id': self.request_id,
            'target': target or {'story_id': None, 'base_revision': '0'},
            'selection': {
                'asset_ids': list(assets),
                'selection_revision': selection_revision,
                'source_policy': 'chapter_sources_v1',
                'chapters': chapters,
            },
            'theme': 'everyday',
            'language': 'en',
            'title': 'Our afternoon',
            'author_direction': '',
        }

    def test_validate_request_returns_detached_canonical_request(self):
        raw = self.request()
        parsed = validate_request(raw)
        parsed['selection']['chapters'][0]['asset_ids'].clear()
        self.assertEqual(raw['selection']['chapters'][0]['asset_ids'], ['102'])

    def test_validate_rejects_noncanonical_ids_bad_partitions_and_oversize_body(self):
        valid = self.request()
        invalid = [
            valid | {'version': True},
            valid | {'request_id': 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'},
            valid | {'selection': valid['selection'] | {'asset_ids': ['0102', '101']}},
            valid | {'selection': valid['selection'] | {'selection_revision': 'F' * 64}},
            valid | {'selection': valid['selection'] | {'chapters': [
                valid['selection']['chapters'][0],
                valid['selection']['chapters'][1] | {'asset_ids': ['102']},
            ]}},
            valid | {'caller_supplied_sources': ['must not be accepted']},
            valid | {'author_direction': 'x' * 9000},
            valid | {'author_direction': 'x' * (32 * 1024)},
        ]
        for raw in invalid:
            with self.subTest(raw=raw):
                with self.assertRaises(TransportError) as rejected:
                    validate_request(raw)
                self.assertIn(rejected.exception.status, (400, 422))

    def test_empty_evidence_is_no_evidence_and_bundle_is_closed_v3(self):
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', self.request())
        bundle = snapshot.bundle()
        self.assertEqual(bundle['version'], 3)
        self.assertEqual(bundle['target']['type'], 'draft')
        self.assertEqual(bundle['target']['revision'], 0)
        self.assertEqual(bundle['selection_revision'], self.request()['selection']['selection_revision'])
        self.assertEqual(bundle['recent_turns'], [])
        self.assertEqual(bundle['instructions'], '')
        self.assertEqual([chapter['evidence_ids'] for chapter in bundle['chapters']], [[], []])
        self.assertEqual(bundle['sources'], [])

    def test_snapshot_documents_each_selected_media_item_without_stack_expansion(self):
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', self.request())
        document = snapshot.document()
        self.assertEqual([media['asset_id'] for media in document['media']], ['102', '101'])
        self.assertTrue(all('stack_id' in media and media['stack_id'] is None
                            for media in document['media']))
        self.assertEqual([chapter['asset_ids'] for chapter in document['chapters']],
                         [['102'], ['101']])

    def test_source_selection_is_per_chapter_and_shared_source_is_deduplicated(self):
        source = self.f.source_id
        request = self.request(chapters=[
            {'id': 'chapter-1', 'title': 'First scene', 'asset_ids': ['102'],
             'evidence_ids': [source]},
            {'id': 'chapter-2', 'title': 'Second scene', 'asset_ids': ['101'],
             'evidence_ids': [source]},
        ])
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', request)
        bundle = snapshot.bundle()
        document = snapshot.document()
        self.assertEqual([source['id'] for source in bundle['sources']].count(source), 1)
        self.assertEqual([chapter['evidence_ids'] for chapter in bundle['chapters']],
                         [[source], [source]])
        self.assertEqual(document['chapters'][0]['sources'][0]['source_id'], source)
        self.assertEqual(document['chapters'][1]['sources'][0]['source_id'], source)

    def test_shared_source_retains_original_origin_and_byline(self):
        request = self.request(assets=('102',), chapters=[
            {'id': 'chapter-1', 'title': 'First scene', 'asset_ids': ['102'],
             'evidence_ids': [self.f.source_id]},
        ])
        document = resolve_snapshot(self.runtime, self.owner, 'family-a', request).document()
        source = document['chapters'][0]['sources'][0]
        self.assertEqual([media['asset_id'] for media in document['media']], ['102'])
        self.assertEqual(source['origin_asset_id'], '101')
        self.assertEqual(source['byline'], 'A parent')
        self.assertEqual(source['selected_asset_ids'], ['102'])

    def test_plain_family_note_keeps_byline_when_groups_are_disabled(self):
        runtime = replace(self.runtime, memory_groups_enabled=False)
        preview = self.f.preview('101', client=self.f.base.f.client)
        self.assertEqual(preview.status_code, 200, preview.text)
        item = preview.json()['items'][0]
        family = next(e for e in item['evidence'] if e.get('source') == 'family')
        request = self.request(assets=('101',), chapters=[
            {'id': 'chapter-1', 'title': 'Family note', 'asset_ids': ['101'],
             'evidence_ids': [family['id']]},
        ], selection_revision=preview.json()['selection_revision'])
        source = resolve_snapshot(runtime, self.owner, 'family-a', request).document()['chapters'][0]['sources'][0]
        self.assertEqual(source['byline'], 'A parent')
        self.assertEqual(source['origin_asset_id'], '101')

    def test_caption_evidence_is_bound_to_its_chapter_asset(self):
        preview = self.f.preview('102,101').json()
        caption = next(e['id'] for item in preview['items'] if item['id'] == '102'
                       for e in item['evidence'] if e.get('source') == 'ai')
        request = self.request(chapters=[
            {'id': 'chapter-1', 'title': 'First scene', 'asset_ids': ['102'],
             'evidence_ids': [caption]},
            {'id': 'chapter-2', 'title': 'Second scene', 'asset_ids': ['101'],
             'evidence_ids': []},
        ])
        document = resolve_snapshot(self.runtime, self.owner, 'family-a', request).document()
        self.assertEqual(document['chapters'][0]['sources'][0]['selected_asset_ids'], ['102'])
        self.assertEqual(document['chapters'][0]['sources'][0]['source_kind'], 'ai_caption')

    def test_family_edited_caption_keeps_derived_kind_and_has_no_byline(self):
        self.f.f.mutate("INSERT INTO captions(asset_id,text,model,user_edited,superseded) "
                        "VALUES(102,'Family edited words','synthetic',1,0)")
        preview = self.f.preview('102').json()
        evidence = next(e for e in preview['items'][0]['evidence']
                        if e.get('source') == 'family' and e['id'].startswith('caption-'))
        request = self.request(assets=('102',), chapters=[
            {'id': 'chapter-1', 'title': 'Edited caption', 'asset_ids': ['102'],
             'evidence_ids': [evidence['id']]},
        ], selection_revision=preview['selection_revision'])
        source = resolve_snapshot(self.runtime, self.owner, 'family-a', request).document()['chapters'][0]['sources'][0]
        self.assertEqual(source['source_kind'], 'family_edited_caption')
        self.assertIsNone(source['byline'])

    def test_group_source_withdrawal_after_capture_conflicts(self):
        request = self.request(chapters=[
            {'id': 'chapter-1', 'title': 'First scene', 'asset_ids': ['102'],
             'evidence_ids': [self.f.source_id]},
            {'id': 'chapter-2', 'title': 'Second scene', 'asset_ids': ['101'],
             'evidence_ids': []},
        ])
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', request)
        self.f.base.save(self.owner, self.f.base.body(assets='101,102', sources='',
            revision=str(self.f.group['revision'])), self.f.group['id'])
        with self.assertRaises(TransportError) as changed:
            revalidate_snapshot(self.runtime, self.owner, snapshot)
        self.assertEqual(changed.exception.status, 409)

    def test_foreign_or_unselected_evidence_is_rejected(self):
        preview = self.f.preview('102,101').json()
        foreign = next(e['id'] for item in preview['items'] if item['id'] == '101'
                       for e in item['evidence'] if e.get('source') == 'ai')
        request = self.request(chapters=[
            {'id': 'chapter-1', 'title': 'First scene', 'asset_ids': ['102'],
             'evidence_ids': [foreign]},
            {'id': 'chapter-2', 'title': 'Second scene', 'asset_ids': ['101'],
             'evidence_ids': []},
        ])
        with self.assertRaises(TransportError) as rejected:
            resolve_snapshot(self.runtime, self.owner, 'family-a', request)
        self.assertEqual(rejected.exception.status, 422)

    def test_foreign_library_asset_is_denied(self):
        request = self.request(assets=('201',), chapters=[
            {'id': 'chapter-1', 'title': 'Foreign media', 'asset_ids': ['201'], 'evidence_ids': []},
        ], selection_revision='0' * 64)
        with self.assertRaises(AccessDenied):
            resolve_snapshot(self.runtime, self.owner, 'family-a', request)

    def test_inactive_or_unmapped_selected_asset_is_denied(self):
        for mutation in (
            "UPDATE assets SET status='deleted' WHERE id=101",
            "DELETE FROM access_asset_libraries WHERE asset_id=101",
        ):
            with self.subTest(mutation=mutation):
                self.f.f.mutate(mutation)
                request = self.request(assets=('101',), chapters=[
                    {'id': 'chapter-1', 'title': 'Selected media', 'asset_ids': ['101'],
                     'evidence_ids': []},
                ], selection_revision='0' * 64)
                with self.assertRaises(AccessDenied):
                    resolve_snapshot(self.runtime, self.owner, 'family-a', request)
                self.f.f.mutate("UPDATE assets SET status='active' WHERE id=101")
                self.f.f.mutate("INSERT OR IGNORE INTO access_asset_libraries VALUES (101,'family-a')")

    def test_stale_selection_revision_conflicts(self):
        request = self.request(selection_revision='0' * 64)
        with self.assertRaises(TransportError) as stale:
            resolve_snapshot(self.runtime, self.owner, 'family-a', request)
        self.assertEqual(stale.exception.status, 409)

    def test_saved_target_is_accepted_for_owner_and_stale_revision_conflicts(self):
        saved = self.f.save('102')
        request = self.request(target={'story_id': saved['id'], 'base_revision': saved['revision']})
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', request)
        self.assertEqual(snapshot.document()['target']['story_id'], saved['id'])
        self.f.f.mutate('UPDATE access_memory_stories SET revision=revision+1 WHERE id=?',
                        (saved['id'],))
        with self.assertRaises(TransportError) as stale:
            revalidate_snapshot(self.runtime, self.owner, snapshot)
        self.assertEqual(stale.exception.status, 409)

    def test_revalidation_detects_source_edit_and_does_not_refresh_snapshot(self):
        request = self.request(chapters=[
            {'id': 'chapter-1', 'title': 'First scene', 'asset_ids': ['102'],
             'evidence_ids': [self.f.source_id]},
            {'id': 'chapter-2', 'title': 'Second scene', 'asset_ids': ['101'],
             'evidence_ids': []},
        ])
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', request)
        before = snapshot.bundle()
        self.f.base.edit_note(self.f.note, revision=1, title='Edited', text='Changed family words')
        with self.assertRaises(TransportError) as changed:
            revalidate_snapshot(self.runtime, self.owner, snapshot)
        self.assertEqual(changed.exception.status, 409)
        self.assertEqual(snapshot.bundle(), before)

    def test_revalidation_detects_membership_revocation(self):
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', self.request())
        self.f.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                        (snapshot.account_id,))
        with self.assertRaises(AccessDenied):
            revalidate_snapshot(self.runtime, self.owner, snapshot)

    def test_revalidation_detects_session_revocation(self):
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', self.request())
        self.f.f.mutate('UPDATE access_sessions SET revoked=1')
        with self.assertRaises(AccessDenied):
            revalidate_snapshot(self.runtime, self.owner, snapshot)

    def test_revalidation_detects_membership_revision_change(self):
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', self.request())
        self.f.f.mutate('UPDATE access_memberships SET revision=revision+1 WHERE account_id=?',
                        (snapshot.account_id,))
        with self.assertRaises(TransportError) as changed:
            revalidate_snapshot(self.runtime, self.owner, snapshot)
        self.assertEqual(changed.exception.status, 409)

    def test_snapshot_binds_authenticated_actor_after_other_actor_is_authorized(self):
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', self.request())
        self.f.f.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=?",
                        (self.f.f.member_id,))
        with self.assertRaises(AccessDenied):
            revalidate_snapshot(self.runtime, self.f.base.member, snapshot)

    def test_contributor_can_prepare_but_cannot_edit_another_authors_story(self):
        self.f.f.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=?",
                        (self.f.f.member_id,))
        contributor_snapshot = resolve_snapshot(self.runtime, self.member, 'family-a', self.request())
        self.assertTrue(contributor_snapshot.account_id)
        saved = self.f.save('102')
        request = self.request(target={'story_id': saved['id'], 'base_revision': '1'})
        with self.assertRaises(AccessDenied):
            resolve_snapshot(self.runtime, self.member, 'family-a', request)

    def test_snapshot_values_are_immutable_and_returned_structures_are_detached(self):
        raw = self.request(chapters=[
            {'id': 'chapter-1', 'title': 'First scene', 'asset_ids': ['102'],
             'evidence_ids': [self.f.source_id]},
            {'id': 'chapter-2', 'title': 'Second scene', 'asset_ids': ['101'],
             'evidence_ids': []},
        ])
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', raw)
        raw['title'] = 'Changed by caller'
        raw['selection']['chapters'][0]['evidence_ids'].clear()
        bundle1, document1 = snapshot.bundle(), snapshot.document()
        bundle1['chapters'][0]['title'] = 'Caller mutation'
        document1['media'].clear()
        self.assertNotEqual(snapshot.bundle()['chapters'][0]['title'], 'Caller mutation')
        self.assertEqual(len(snapshot.document()['media']), 2)
        self.assertEqual(snapshot.bundle()['sources'][0]['text'], self.f.note['text'])
        self.assertNotIn(self.f.note['text'], repr(snapshot))
        with self.assertRaises(FrozenInstanceError):
            snapshot.account_id = 'Mutation'

    def test_same_actor_unchanged_snapshot_revalidates(self):
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', self.request())
        self.assertIsNone(revalidate_snapshot(self.runtime, self.owner, snapshot))

    def test_request_digest_is_key_order_independent_and_binds_request_content(self):
        request = self.request()
        first = resolve_snapshot(self.runtime, self.owner, 'family-a', request)
        reordered = {key: request[key] for key in reversed(tuple(request))}
        reordered['selection'] = {key: request['selection'][key]
                                  for key in reversed(tuple(request['selection']))}
        reordered['selection']['chapters'] = [
            {key: chapter[key] for key in reversed(tuple(chapter))}
            for chapter in request['selection']['chapters']]
        same = resolve_snapshot(self.runtime, self.owner, 'family-a', reordered)
        changed_title = resolve_snapshot(self.runtime, self.owner, 'family-a',
                                         request | {'title': 'A different title'})
        changed_direction = resolve_snapshot(self.runtime, self.owner, 'family-a',
                                              request | {'author_direction': 'Use fewer words.'})
        self.assertEqual(first.request_digest, same.request_digest)
        self.assertNotEqual(first.request_digest, changed_title.request_digest)
        self.assertNotEqual(first.request_digest, changed_direction.request_digest)

    def test_resolution_and_revalidation_perform_no_database_writes(self):
        self.f.f.trace.clear()
        snapshot = resolve_snapshot(self.runtime, self.owner, 'family-a', self.request())
        revalidate_snapshot(self.runtime, self.owner, snapshot)
        writes = [sql for sql in self.f.f.trace
                  if sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE'))]
        self.assertEqual(writes, [])


if __name__ == '__main__':
    unittest.main()
