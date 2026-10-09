"""Pure synthetic tests for reviewed memoir edition request validation."""
import json
from pathlib import Path
import sys
import unittest
import uuid
from dataclasses import FrozenInstanceError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.memory_book_edition_contract import (  # noqa: E402
    MAX_BODY_BYTES,
    EditionChildRevision,
    ReviewedManuscriptRequest,
    parse_reviewed_edition,
)
from app.access.transport import TransportError  # noqa: E402


def ident(number):
    return str(uuid.UUID(int=number))


class MemoryBookEditionContractTests(unittest.TestCase):
    def setUp(self):
        self.book_id = ident(1)
        self.story_ids = (ident(2), ident(3))
        self.children = [
            {'id': self.story_ids[0], 'revision': '8'},
            {'id': self.story_ids[1], 'revision': '5'},
        ]
        self.chapter_ids = [story_id + '-chapter-1' for story_id in self.story_ids]
        self.source_ids = ['contribution-' + ident(20), 'caption-31']
        self.bundle = {
            'version': 1,
            'library_id': 'library-a',
            'target': {'type': 'book', 'id': self.book_id, 'revision': 12},
            'language': 'zh',
            'title': 'Family memoir',
            'theme': 'family',
            'chapters': [
                {'id': self.chapter_ids[0], 'title': 'Spring', 'narration': '',
                 'asset_ids': [], 'evidence_ids': [self.source_ids[0]]},
                {'id': self.chapter_ids[1], 'title': 'Home', 'narration': '',
                 'asset_ids': [], 'evidence_ids': [self.source_ids[1]]},
            ],
            'sources': [
                {'id': self.source_ids[0], 'kind': 'family', 'text': '家人记得那天。',
                 'asset_id': None, 'author': 'Family member'},
                {'id': self.source_ids[1], 'kind': 'ai', 'text': 'A garden in spring.',
                 'asset_id': None, 'author': None},
            ],
            'recent_turns': [],
            'instructions': '',
        }
        self.body = {
            'version': 1,
            'revision': '12',
            'mutation_id': ident(40),
            'job_id': ident(41),
            'job_result_sha256': 'a' * 64,
            'source_fingerprint': 'b' * 64,
            'reviewed': True,
            'children': self.children,
            'manuscript': {
                'version': 1,
                'title': '春天的回忆',
                'chapters': [
                    {'id': self.chapter_ids[0], 'narration': '家人记得那个春天。',
                     'source_ids': [self.source_ids[0]]},
                    {'id': self.chapter_ids[1], 'narration': '后来回到了家。',
                     'source_ids': [self.source_ids[1]]},
                ],
                'questions': [],
                'needs_review': True,
            },
        }

    def parse(self, body=None, *, raw=None, bundle=None):
        if raw is None:
            raw = json.dumps(self.body if body is None else body,
                             ensure_ascii=False, separators=(',', ':'))
        return parse_reviewed_edition(raw, self.bundle if bundle is None else bundle)

    def assert_status(self, status, **kwargs):
        with self.assertRaises(TransportError) as caught:
            self.parse(**kwargs)
        self.assertEqual(caught.exception.status, status)

    def test_valid_reviewed_chinese_edition_is_immutable_and_typed(self):
        result = self.parse()
        self.assertIsInstance(result, ReviewedManuscriptRequest)
        self.assertEqual(result.revision, '12')
        self.assertEqual(result.children, tuple(
            EditionChildRevision(item['id'], item['revision']) for item in self.children))
        self.assertEqual(result.manuscript.title, '春天的回忆')
        self.assertEqual(result.manuscript.chapters[0].source_ids, (self.source_ids[0],))
        self.assertTrue(result.manuscript.needs_review)
        self.assertTrue(result.reviewed)
        self.assertEqual(len(result.request_digest), 64)
        with self.assertRaises(FrozenInstanceError):
            result.revision = '13'
        with self.assertRaises(FrozenInstanceError):
            result.manuscript.title = 'changed'

    def test_canonical_request_digest_ignores_json_key_order_and_whitespace(self):
        compact = json.dumps(self.body, ensure_ascii=False, separators=(',', ':'))
        pretty_reordered = json.dumps(self.body, ensure_ascii=False, indent=2,
                                      sort_keys=True)
        first = self.parse(raw=compact)
        second = self.parse(raw=pretty_reordered)
        self.assertEqual(first.canonical_json, second.canonical_json)
        self.assertEqual(first.request_digest, second.request_digest)

    def test_request_byte_limit_accepts_boundary_and_rejects_one_more_byte(self):
        raw = json.dumps(self.body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        padded = raw + b' ' * (MAX_BODY_BYTES - len(raw))
        self.assertEqual(len(padded), MAX_BODY_BYTES)
        self.parse(raw=padded)
        self.assert_status(413, raw=padded + b' ')

    def test_json_syntax_duplicate_keys_utf8_and_nonstandard_numbers_are_rejected(self):
        self.assert_status(400, raw=b'{"version":1,"version":1}')
        self.assert_status(400, raw=b'\xff')
        self.assert_status(400, raw=b'{"version":NaN}')
        self.assert_status(400, raw=b'{"version":Infinity}')

    def test_exact_request_keys_and_exact_json_types_are_required(self):
        self.assert_status(400, body=self.body | {'extra': 'value'})
        body = self.body.copy(); body['reviewed'] = False
        self.assert_status(400, body=body)
        body = self.body.copy(); body['reviewed'] = 1
        self.assert_status(400, body=body)
        body = self.body.copy(); body['version'] = True
        self.assert_status(400, body=body)
        body = self.body.copy(); body['revision'] = 12
        self.assert_status(400, body=body)
        body = self.body.copy(); body['children'] = [self.children[0] | {'extra': 1}, self.children[1]]
        self.assert_status(400, body=body)

    def test_identifiers_digests_and_revision_strings_are_canonical(self):
        for key, value in (
            ('mutation_id', str(uuid.UUID(int=0xabcdef)).upper()),
            ('job_id', 'not-a-uuid'),
            ('job_result_sha256', 'A' * 64),
            ('source_fingerprint', 'f' * 63),
            ('revision', '012'),
            ('revision', '9223372036854775808'),
        ):
            body = self.body.copy(); body[key] = value
            self.assert_status(400, body=body)
        body = self.body.copy(); body['children'] = [self.children[0] | {'revision': True}, self.children[1]]
        self.assert_status(400, body=body)
        body = self.body.copy(); body['children'] = [self.children[0] | {'revision': 8}, self.children[1]]
        self.assert_status(400, body=body)

    def test_children_are_ordered_unique_and_bounded(self):
        body = self.body.copy(); body['children'] = []
        self.assert_status(400, body=body)
        body = self.body.copy(); body['children'] = [self.children[0]] * 25
        self.assert_status(400, body=body)
        body = self.body.copy(); body['children'] = [self.children[0], self.children[0]]
        self.assert_status(400, body=body)

    def test_child_shape_is_parsed_but_service_must_bind_it_to_authorized_context(self):
        body = self.body.copy()
        body['children'] = [
            {'id': ident(90), 'revision': '2'},
            {'id': ident(91), 'revision': '3'},
        ]
        result = self.parse(body)
        self.assertEqual([child.id for child in result.children], [ident(90), ident(91)])

    def test_book_target_and_base_revision_are_checked(self):
        bundle = self.bundle.copy()
        bundle['target'] = self.bundle['target'] | {'type': 'story'}
        self.assert_status(422, bundle=bundle)
        bundle = self.bundle.copy()
        bundle['target'] = self.bundle['target'] | {'revision': 11}
        self.assert_status(409, bundle=bundle)
        self.assert_status(422, bundle={'target': {'type': 'book', 'revision': 12}})

    def test_manuscript_must_be_reviewable_ordered_and_cited_to_bundle(self):
        body = self.body.copy()
        body['manuscript'] = self.body['manuscript'] | {'needs_review': False}
        self.assert_status(422, body=body)
        body = self.body.copy()
        chapters = list(body['manuscript']['chapters']); chapters.reverse()
        body['manuscript'] = body['manuscript'] | {'chapters': chapters}
        self.assert_status(422, body=body)
        body = self.body.copy()
        chapters = list(body['manuscript']['chapters'])
        chapters[0] = chapters[0] | {'source_ids': ['unavailable-source']}
        body['manuscript'] = body['manuscript'] | {'chapters': chapters}
        self.assert_status(422, body=body)

    def test_malformed_surrogates_and_control_strings_are_rejected(self):
        body = self.body.copy()
        body['manuscript'] = self.body['manuscript'] | {'title': 'bad\ud800'}
        self.assert_status(422, raw=json.dumps(body, ensure_ascii=True), bundle=self.bundle)
        body = self.body.copy()
        chapters = list(body['manuscript']['chapters'])
        chapters[0] = chapters[0] | {'narration': 'bad\x01text'}
        body['manuscript'] = body['manuscript'] | {'chapters': chapters}
        self.assert_status(422, body=body)


class ReviewedEditionRetryIdentityTests(unittest.TestCase):
    def test_whole_request_digest_matches_the_validated_canonical_request(self):
        from app.access.memory_book_edition_contract import reviewed_edition_identity
        fixture = MemoryBookEditionContractTests()
        fixture.setUp()
        request = parse_reviewed_edition(json.dumps(fixture.body), fixture.bundle)
        self.assertEqual((request.mutation_id, request.request_digest),
                         reviewed_edition_identity(json.dumps(fixture.body)))
        changed = fixture.body | {'job_result_sha256': 'f' * 64}
        self.assertNotEqual(request.request_digest,
                           reviewed_edition_identity(json.dumps(changed))[1])


if __name__ == '__main__':
    unittest.main()
