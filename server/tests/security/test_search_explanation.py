from __future__ import annotations

import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.search_explanation import (
    describe_empty_query, describe_filter_query, explain_filters, no_results_guidance,
    people_scope_notice,
)


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


def test_descriptive_explanation_names_required_clues_without_dumping_model_alternatives():
    filters = {'text': 'literal words', 'descriptive': {'version': 1, 'concepts': [
        {'surface': '玩雪', 'alternatives': ['private model alternative']},
        {'surface': 'red coat', 'alternatives': ['another model alternative']},
    ]}}
    for language in ('en', 'zh'):
        result = explain_filters(filters, {}, language)
        assert '玩雪' in result and 'red coat' in result and 'literal words' in result
        assert 'alternative' not in result
        assert len(result.encode('utf-8')) <= 600
    assert 'any description' in no_results_guidance({'descriptive': filters['descriptive']}, 'en')
    assert '不限描述' in no_results_guidance({'descriptive': filters['descriptive']}, 'zh')


def test_empty_result_question_recognition_is_closed_and_normalized():
    accepted = (
        'why no results',
        'WHY DID YOU FIND NOTHING?!',
        'why are there no results?',
        '为什么没找到',
        '怎么没有结果？',
        '为什么没有结果！',
        '为什么没有results？',
        '  PLEASE   why no results?! ',
        'please why did you find nothing please',
        '请 为什么没有结果？',
        '请为什么没找到请',
        '  为什么没有results！  ',
    )
    assert all(describe_empty_query(value) for value in accepted)
    rejected = (
        'why no results in the park',
        'why no results and open the first one',
        'tell me why no results',
        '"why no results"',
        'please explain why no results',
        '为什么没有结果并打开第一张',
        '为什么没有',
        '', None, 42,
    )
    assert all(not describe_empty_query(value) for value in rejected)


def test_empty_result_descriptive_relaxation_is_explicit_bounded_and_available_with_hard_filters():
    description = {'version': 1, 'concepts': [
        {'surface': 'PRIVATE SURFACE', 'alternatives': ['PRIVATE ALTERNATIVE']},
    ]}
    for hard in ({}, {'date': {'from': '2032-01-01', 'to': '2032-12-31'}},
                 {'text': 'PRIVATE LITERAL'}):
        filters = dict(hard, descriptive=description)
        before = copy.deepcopy(filters)
        english = no_results_guidance(filters, 'en')
        chinese = no_results_guidance(filters, 'zh')
        assert 'remove the "clue wording" clue' in english
        assert 'Other conditions stay active' in english
        assert '去掉“某条线索”线索' in chinese and '其余条件会保留' in chinese
        for reply in (english, chinese):
            assert 'PRIVATE' not in reply
            assert len(reply.encode('utf-8')) <= 600
        assert filters == before


def test_empty_result_guidance_uses_date_policy_before_text_and_keeps_other_filters():
    filters = {'date': {'from': '2025-01-01', 'to': '2025-01-31'},
               'text': 'private phrase', 'people': {'ids': ['private-person'], 'match': 'all'}}
    before = copy.deepcopy(filters)
    english = no_results_guidance(filters, 'en')
    chinese = no_results_guidance(filters, 'zh')
    assert 'recorded capture date' in english
    assert 'excluded from date searches' in english
    assert '"any date"' in english and 'only the date filter' in english
    assert 'any text' not in english
    assert '不限日期' in chinese and '仅移除日期筛选并保留其他条件' in chinese
    assert '不限内容' not in chinese
    assert 'private phrase' not in english and 'private-person' not in english
    assert 'private phrase' not in chinese and 'private-person' not in chinese
    assert filters == before


def test_empty_result_guidance_text_and_generic_branches_are_bounded_bilingual_and_non_speculative():
    filters = {'text': 'private phrase', 'people': {'ids': ['private-person'], 'match': 'any'}}
    before = copy.deepcopy(filters)
    english = no_results_guidance(filters, 'en')
    chinese = no_results_guidance(filters, 'zh')
    assert 'No matching photos or videos were found.' in english
    assert '"any text"' in english and 'only the text filter' in english
    assert '不限内容' in chinese and '仅移除内容筛选并保留其他条件' in chinese
    assert 'private phrase' not in english + chinese
    assert 'private-person' not in english + chinese
    assert filters == before

    generic_en = no_results_guidance({'people': {'ids': ['x'], 'match': 'any'}}, 'en')
    generic_zh = no_results_guidance({'people': {'ids': ['x'], 'match': 'any'}}, 'zh')
    assert 'what filters are active' in generic_en
    assert '现在筛选了哪些条件' in generic_zh
    assert 'any date' not in generic_en and 'any text' not in generic_en
    assert '不限日期' not in generic_zh and '不限内容' not in generic_zh

    for result in (english, chinese, generic_en, generic_zh,
                   no_results_guidance({'date': object(), 'text': object()}, 'en'),
                   no_results_guidance({'date': object(), 'text': object()}, 'zh')):
        assert len(result.encode('utf-8')) <= 600
        lowered = result.casefold()
        assert not any(term in lowered for term in ('event', 'no one', 'your fault'))
        assert '家人' not in result
    assert 'confirmed assignments only' in generic_en
    assert '人物检索只使用已确认的标注' in generic_zh


def test_people_notice_explains_reviewed_evidence_without_counts_names_or_absence_claims():
    for match in ('all', 'any'):
        filters = {'people': {'ids': ['PRIVATE ONE', 'PRIVATE TWO'], 'match': match}}
        before = copy.deepcopy(filters)
        en = people_scope_notice(filters, 'en')
        zh = people_scope_notice(filters, 'zh')
        assert 'confirmed assignments only' in en and 'may be missing' in en
        assert '已确认的标注' in zh and '可能遗漏' in zh
        assert ('same item' in en) == (match == 'all')
        assert ('同一项' in zh) == (match == 'all')
        assert 'PRIVATE' not in en + zh
        assert filters == before
    for filters in (None, {}, {'people': None}, {'people': {'ids': []}},
                    {'people': {'ids': 'PRIVATE'}}):
        assert people_scope_notice(filters, 'en') == ''
    assert 'same item' not in people_scope_notice({'people': {'ids': ['1'], 'match': 'all'}}, 'en')


def test_people_notice_survives_all_empty_search_guidance_combinations():
    import itertools
    people = {'ids': ['PRIVATE ONE', 'PRIVATE TWO'], 'match': 'all'}
    fields = [('date', {'from': '2032-01-01', 'to': '2032-12-31'}),
              ('text', 'PRIVATE LITERAL'),
              ('descriptive', {'version': 1, 'concepts': [
                  {'surface': 'PRIVATE CLUE', 'alternatives': ['PRIVATE ALTERNATIVE']}]} )]
    for enabled in itertools.product((False, True), repeat=len(fields)):
        filters = dict(pair for pair, active in zip(fields, enabled) if active)
        filters['people'] = people
        for language in ('en', 'zh'):
            reply = no_results_guidance(filters, language)
            assert people_scope_notice(filters, language) in reply
            assert 'PRIVATE' not in reply
            assert len(reply.encode('utf-8')) <= 600
            if 'date' in filters:
                assert ('any date' if language == 'en' else '不限日期') in reply


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
