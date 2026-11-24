"""Pure synthetic checks for public-name and reviewed-alias grounding."""
from copy import deepcopy
import unittest

from backend.app.access.story_name_grounding import ground_text


def catalog(*names):
    return {'version': 1, 'source': 'synthetic fixture',
            'entries': [{'id': f'Q{index}', 'name': name, 'kind': 'singer'}
                        for index, name in enumerate(names, 1)]}


READINGS = {
    '嘉': ['jia'], '家': ['jia'], '假': ['jia'],
    '宁': ['ning'], '凝': ['ning'],
    '小': ['xiao'], '西': ['xi'], '希': ['xi'],
    '人': ['ren'], '贤': ['xian'], '祈': ['qi'],
}


class StoryNameGroundingTests(unittest.TestCase):
    def test_unique_public_singer_homophone_requires_explicit_context(self):
        original = '周末看假宁演唱会，我们很开心。'
        before = original
        result = ground_text(original, [], catalog=catalog('嘉宁'), readings=READINGS)
        self.assertEqual('周末看嘉宁演唱会，我们很开心。', result['text'])
        self.assertEqual([{'before': '假宁', 'after': '嘉宁',
                           'kind': 'public_singer', 'reference': 'Q1'}], result['repairs'])
        self.assertEqual([], result['ambiguous'])
        self.assertEqual(before, original)

        no_cue = '假宁来了，我们很开心。'
        unchanged = ground_text(no_cue, [], catalog=catalog('嘉宁'), readings=READINGS)
        self.assertEqual(no_cue, unchanged['text'])
        self.assertEqual([], unchanged['repairs'])

    def test_public_name_already_correct_and_substrings_inside_it_are_protected(self):
        entries = catalog('嘉宁', '周结伦')
        for text in ('看嘉宁演唱会。', '看周结伦演唱会。'):
            with self.subTest(text=text):
                result = ground_text(text, [], catalog=entries, readings=READINGS)
                self.assertEqual(text, result['text'])
                self.assertEqual([], result['repairs'])

    def test_packaged_catalog_and_pinyin_correct_context_supported_public_name(self):
        original = '我们在杭州看周结伦演唱会。'
        corrected = ground_text(original, [])
        self.assertEqual('我们在杭州看周杰伦演唱会。', corrected['text'])
        self.assertEqual('周结伦', corrected['repairs'][0]['before'])
        self.assertEqual('public_singer', corrected['repairs'][0]['kind'])
        self.assertEqual(original, '我们在杭州看周结伦演唱会。')
        no_context = ground_text('周结伦今天来了。', [])
        self.assertEqual('周结伦今天来了。', no_context['text'])
        already_correct = ground_text('我们去看周杰伦演唱会。', [])
        self.assertEqual('我们去看周杰伦演唱会。', already_correct['text'])

        original = '我们在杭州看周结伦演唱会，提前订了周结伦在杭州的演唱会。Mira或者小凝 她也喜欢这首歌。'
        grounded = ground_text(original, [{'name': '小宁', 'aliases': ['Mira']}])
        self.assertEqual('我们在杭州看周杰伦演唱会，提前订了周杰伦在杭州的演唱会。小宁 她也喜欢这首歌。',
                         grounded['text'])
        self.assertEqual(original, '我们在杭州看周结伦演唱会，提前订了周结伦在杭州的演唱会。Mira或者小凝 她也喜欢这首歌。')

    def test_unique_public_cue_propagates_same_spelling_to_unprompted_mentions(self):
        text = '看假宁演唱会，提前订了假宁在杭州的演唱会。'
        result = ground_text(text, [], catalog=catalog('嘉宁'), readings=READINGS)
        self.assertEqual('看嘉宁演唱会，提前订了嘉宁在杭州的演唱会。', result['text'])
        self.assertEqual(2, len(result['repairs']))

    def test_ambiguous_public_homophones_are_reported_without_replacement(self):
        text = '看假宁演唱会。'
        result = ground_text(text, [], catalog=catalog('嘉宁', '家宁'), readings=READINGS)
        self.assertEqual(text, result['text'])
        self.assertEqual([], result['repairs'])
        self.assertEqual([{'before': '假宁', 'kind': 'public_singer',
                           'references': ['Q1', 'Q2']}], result['ambiguous'])

    def test_reviewed_aliases_use_exact_matches_ascii_word_boundaries_and_canonical_name(self):
        people = [{'name': '小西', 'aliases': ['Mira']}]
        text = 'Mira来了，SuperMira也到场，Mira2没出现，Lina还没确认。'
        result = ground_text(text, people, catalog=catalog('嘉宁'), readings=READINGS)
        self.assertEqual('小西来了，SuperMira也到场，Mira2没出现，Lina还没确认。', result['text'])
        self.assertEqual([{'before': 'Mira', 'after': '小西', 'kind': 'reviewed_alias',
                           'reference': 'reviewed_person:0'}], result['repairs'])

    def test_reviewed_ascii_alias_casefold_and_same_person_conjunction(self):
        people = [{'name': '小西', 'aliases': ['Mira']}]
        for text in ('lina来了。', 'Mira或者小希来了。', 'Mira，也叫小希来了。'):
            result = ground_text(text, people, catalog={'version': 1, 'source': 'empty',
                                'entries': []}, readings=READINGS)
            if text == 'lina来了。':
                self.assertEqual(text, result['text'])
                self.assertEqual([], result['repairs'])
            else:
                self.assertTrue(result['text'].startswith('小西'))
                self.assertEqual(1, len(result['repairs']))
                self.assertEqual('reviewed_alias', result['repairs'][0]['kind'])

    def test_reviewed_ambiguous_conjunction_and_private_overlap_do_not_use_public_guess(self):
        text = 'Mira或者小希演唱会。'
        people = [{'name': '小西', 'aliases': ['Mira']},
                  {'name': '小希', 'aliases': ['Other']}]
        ambiguous = ground_text(text, people, catalog=catalog('嘉宁'), readings=READINGS)
        self.assertEqual(text, ambiguous['text'])
        self.assertEqual([], ambiguous['repairs'])
        self.assertTrue(ambiguous['ambiguous'])

        private = ground_text('看假宁演唱会。',
            [{'name': '小西', 'aliases': ['假宁']}],
            catalog=catalog('嘉宁'), readings=READINGS)
        self.assertEqual('看小西演唱会。', private['text'])
        self.assertEqual('reviewed_alias', private['repairs'][0]['kind'])

    def test_alias_colliding_with_another_canonical_or_shared_canonical_is_ambiguous(self):
        cases = [
            ('Shared', [{'name': '小西', 'aliases': ['Shared']},
                        {'name': 'Shared', 'aliases': ['Other']}]),
            ('Mira', [{'name': '小西', 'aliases': ['Mira']},
                      {'name': '小西', 'aliases': ['Other']}]),
        ]
        for text, people in cases:
            with self.subTest(text=text):
                result = ground_text(text, people,
                    catalog={'version': 1, 'source': 'empty', 'entries': []},
                    readings=READINGS)
                self.assertEqual(text, result['text'])
                self.assertEqual([], result['repairs'])
                self.assertTrue(result['ambiguous'])

    def test_public_grounding_only_replaces_source_spans_and_never_cascades(self):
        text = '看假宁演唱会，也提到嘉宁。'
        original = deepcopy(text)
        result = ground_text(text, [], catalog=catalog('嘉宁'), readings=READINGS)
        self.assertEqual('看嘉宁演唱会，也提到嘉宁。', result['text'])
        self.assertEqual(original, text)
        self.assertEqual('假宁', result['repairs'][0]['before'])

    def test_type_control_size_and_repair_caps_fail_closed(self):
        empty_catalog = {'version': 1, 'source': 'empty', 'entries': []}
        for text, people, data, readings in (
                (None, [], empty_catalog, READINGS),
                ('x' * (64 * 1024 + 1), [], empty_catalog, READINGS),
                ('bad\x00text', [], empty_catalog, READINGS),
                ('text', [{'name': 'x', 'aliases': []}] * 33, empty_catalog, READINGS),
                ('text', [], {'version': 2, 'source': 'x', 'entries': []}, READINGS),
                ('text', [], empty_catalog, {'嘉': ['jia3']})):
            with self.subTest(text=str(text)[:12]):
                with self.assertRaises(ValueError):
                    ground_text(text, people, catalog=data, readings=readings)

        crowded = '，'.join(['看假宁演唱会'] * 33)
        with self.assertRaises(ValueError):
            ground_text(crowded, [], catalog=catalog('嘉宁'), readings=READINGS)


if __name__ == '__main__':
    unittest.main()
