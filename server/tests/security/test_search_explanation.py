from __future__ import annotations

import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.search_explanation import describe_filter_query, explain_filters


def test_filter_query_recognition_is_closed_and_normalized():
    accepted = (
        'what are we looking for',
        'WHAT ARE WE SEARCHING FOR?!',
        'what filters are active?',
        'describe the current search.',
        'explain the current search',
        '当前筛选条件是什么？',
        '现在筛选了哪些条件',
        '现在在找什么！',
        '解释当前查找条件。',
        '当前search条件是什么',
        'what are the 当前筛选条件？',
        '  PLEASE   WHAT ARE WE LOOKING FOR?! ',
        '请 解释当前查找条件。',
        '请解释当前查找条件。',
    )
    assert all(describe_filter_query(value) for value in accepted)
    rejected = (
        'what are we looking for in the park',
        'open the photo and explain the current search',
        '"what filters are active"',
        'what are we looking for then show the photos',
        'please explain the current search and open the first one',
        '请解释当前查找条件并打开第一张',
        '', None, 42,
    )
    assert all(not describe_filter_query(value) for value in rejected)


def test_empty_filters_have_explicit_bilingual_response():
    assert explain_filters({}, {}, 'en') == 'No search filters are active.'
    assert explain_filters({}, {}, 'zh') == '当前没有查找筛选条件。'


def test_summary_covers_every_filter_and_is_independent_of_result_count():
    filters = {
        'media': ['image', 'video'],
        'date': {'from': '2025-01-01', 'to': None},
        'people': {'ids': ['17', '23'], 'match': 'all'},
        'tags': {'ids': ['31'], 'match': 'any'},
        'locations': ['41'],
        'text': 'birthday lanterns',
    }
    interpretation = {
        'people': [{'id': '17', 'label': 'Mina'}, {'id': '23', 'label': 'Bo'}],
        'tags': [{'id': '31', 'label': 'birthday'}],
        'locations': [{'id': '41', 'label': 'Hangzhou'}],
        'perspective': {'label': 'Do not expose'},
        'items': [{'caption': 'private card text'}],
        'total': 0,
    }
    english = explain_filters(filters, interpretation, 'en')
    chinese = explain_filters(filters, interpretation, 'zh')
    for clause in ('Media kind:', 'Capture dates (inclusive):', 'People: all of 2',
                   'Tags: any of 1', 'Locations: 1', 'Text phrase:'):
        assert clause in english
    for clause in ('媒体类型：', '拍摄日期（含边界）：', '人物：全部匹配', '标签：任一匹配',
                   '地点：', '匹配文字：'):
        assert clause in chinese
    assert '2025-01-01' in english and 'no upper bound' in english
    assert 'Mina' in english and 'Bo' in english and 'Hangzhou' in english
    assert 'birthday lanterns' in english
    assert 'private card text' not in english and 'Do not expose' not in english
    interpretation_with_results = dict(interpretation, items=[], total=98)
    assert explain_filters(filters, interpretation_with_results, 'en') == english


def test_only_selected_label_rows_are_exposed_and_inputs_are_unchanged():
    filters = {
        'people': {'ids': ['2', '5', '8'], 'match': 'any'},
        'tags': {'ids': ['9'], 'match': 'all'},
        'locations': ['11'],
    }
    interpretation = {
        'people': [
            {'id': '1', 'label': 'FOREIGN PERSON'},
            {'id': '2', 'label': 'Selected "name"'},
            {'id': '5', 'label': 'second'},
            {'id': '8', 'label': 'third'},
        ],
        'tags': [{'id': '3', 'label': 'FOREIGN TAG'}, {'id': '9', 'label': 'selected tag'}],
        'locations': [{'id': '10', 'label': 'FOREIGN PLACE'}, {'id': '11', 'label': 'selected place'}],
        'roster': [{'id': '99', 'name': 'ROSTER SECRET'}],
    }
    before = copy.deepcopy((filters, interpretation))
    reply = explain_filters(filters, interpretation, 'en')
    assert 'Selected \\"name\\"' in reply
    assert '+1 more' in reply
    assert 'FOREIGN' not in reply and 'ROSTER SECRET' not in reply
    assert 'selected tag' in reply and 'selected place' in reply
    assert filters == before[0] and interpretation == before[1]


def test_ordinary_reviewed_bilingual_labels_are_not_needlessly_truncated():
    filters = {'people': {'ids': ['2'], 'match': 'any'}}
    interpretation = {'people': [{'id': '2', 'label': 'Sample Child / 示例儿童'}]}
    reply = explain_filters(filters, interpretation, 'en')
    assert '"Sample Child / 示例儿童"' in reply
    assert '…' not in reply


def test_labels_and_literal_text_are_json_quoted_as_data():
    filters = {'people': {'ids': ['7'], 'match': 'any'}, 'text': 'line\n"drop table"\x00'}
    interpretation = {'people': [{'id': '7', 'label': 'A\n"B"'}]}
    reply = explain_filters(filters, interpretation, 'en')
    assert '"A\\n\\"B\\""' in reply
    assert '"line\\n\\"drop table\\"\\u0000"' in reply
    assert 'drop table' in reply  # visible only inside the quoted literal filter


def test_all_slots_remain_bounded_with_many_labels_controls_and_unicode():
    names = [('长标签😀\x00\\"' * 12) + str(i) for i in range(20)]
    ids = [str(i) for i in range(20)]
    filters = {
        'media': ['image', 'video', 'other'],
        'date': {'from': None, 'to': '2026-12-31'},
        'people': {'ids': ids, 'match': 'all'},
        'tags': {'ids': ids, 'match': 'any'},
        'locations': ids,
        'text': ('😀\x01' * 64) + ('\x01' * 192),  # exactly 512 UTF-8 bytes
    }
    interpretation = {
        facet: [{'id': ident, 'label': name} for ident, name in zip(ids, names)]
        for facet in ('people', 'tags', 'locations')
    }
    for language in ('en', 'zh'):
        result = explain_filters(filters, interpretation, language)
        assert len(result.encode('utf-8')) <= 600
        result.encode('utf-8').decode('utf-8')
        assert '…' in result
        assert ('Text phrase: excerpt' in result if language == 'en' else '匹配文字：摘录' in result)
        for slot in ('media', 'date', 'people', 'tags', 'locations', 'text'):
            if language == 'en':
                marker = {'media': 'Media kind:', 'date': 'Capture dates (inclusive):',
                          'people': 'People:', 'tags': 'Tags:', 'locations': 'Locations:',
                          'text': 'Text phrase:'}[slot]
            else:
                marker = {'media': '媒体类型：', 'date': '拍摄日期（含边界）：', 'people': '人物：',
                          'tags': '标签：', 'locations': '地点：', 'text': '匹配文字：'}[slot]
            assert marker in result


def test_every_nonempty_media_combination_stays_bounded():
    ids = [str(i) for i in range(20)]
    filters = {
        'date': {'from': None, 'to': '2026-12-31'},
        'people': {'ids': ids, 'match': 'all'},
        'tags': {'ids': ids, 'match': 'any'},
        'locations': ids,
        'text': ('\x00😀' * 64) + ('\x01' * 192),
    }
    interpretation = {
        facet: [{'id': ident, 'label': '非常长的家庭地点标签😀\\"\x00' * 20}
                for ident in ids]
        for facet in ('people', 'tags', 'locations')
    }
    kinds = ('image', 'video', 'other')
    for mask in range(1, 1 << len(kinds)):
        filters['media'] = [kind for index, kind in enumerate(kinds) if mask & (1 << index)]
        for language in ('en', 'zh'):
            result = explain_filters(filters, interpretation, language)
            assert len(result.encode('utf-8')) <= 600
            assert 'excerpt' in result if language == 'en' else '摘录' in result
            assert 'Media kind:' in result if language == 'en' else '媒体类型：' in result


def test_missing_selected_labels_report_counts_without_falling_back_to_ids():
    filters = {'people': {'ids': ['private-id-1', 'private-id-2'], 'match': 'all'}}
    reply = explain_filters(filters, {'people': []}, 'en')
    assert 'People: all of 2' in reply
    assert 'names unavailable' in reply
    assert '+2 more' in reply
    assert 'private-id' not in reply
