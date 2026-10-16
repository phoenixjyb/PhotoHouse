#!/usr/bin/env python3
"""Build a private, offline source-and-wording review page from one canary capture."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
from html import escape
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server' / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools'))
import run_memoir_quality_canary as canary
from review_model_qualification import ReviewError, _write_exclusive
from app.access.model_deployment import DeploymentError, _load_private_document
from app.access.memory_narrative import validate_companion, validate_narrative
from app.access.story_titles import validate_suggestions


class PageError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(canary._canonical(value)).hexdigest()


def _read(path):
    try:
        return _load_private_document(path, source_root=ROOT)
    except DeploymentError:
        raise PageError('private_capture_unavailable') from None


def load_review(directory: Path):
    """Validate canonical content and current contracts, without asserting execution."""
    record = _read(directory / 'record.json')
    bundle = _read(directory / 'input-bundle.json')
    output = _read(directory / 'output.json')
    try:
        fields = {'schema', 'status', 'case_id', 'role', 'task', 'input_sha256',
                  'output_sha256', 'configuration_identity_sha256', 'provider_configuration',
                  'started_at', 'ended_at', 'duration_seconds', 'timeout_seconds', 'quality',
                  'quality_evaluated', 'activation_performed', 'resource_limits_verified'}
        record_fields = fields | ({'ollama_metrics'} if type(record) is dict and
                                   'ollama_metrics' in record else set())
        if (type(record) is not dict or set(record) != record_fields or
                type(record['schema']) is not int or record['schema'] != 1 or
                record['status'] != 'captured_for_human_review'):
            raise ValueError()
        if 'ollama_metrics' in record:
            from app.access.memory_narrative import _clean_ollama_metrics
            metrics = record['ollama_metrics']
            clean_metrics = _clean_ollama_metrics(metrics)
            if (type(metrics) is not dict or not metrics or clean_metrics != metrics or
                    any(type(value) is not int for value in metrics.values())):
                raise ValueError()
        case, criteria = canary._case_plan(record['case_id'])
        role, task = canary.CASE_BINDINGS[record['case_id']]
        if (record['role'] != role or record['task'] != task or
                digest(bundle) != case['bundle_sha256'] or
                record['input_sha256'] != digest(bundle) or
                record['output_sha256'] != digest(output) or
                record['configuration_identity_sha256'] != digest(record['provider_configuration']) or
                record['quality'] != dict.fromkeys(criteria, 'unreviewed') or
                any(record[field] is not False for field in
                    ('quality_evaluated', 'activation_performed', 'resource_limits_verified'))):
            raise ValueError()
        for field in ('duration_seconds', 'timeout_seconds'):
            number = record[field]
            if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
                raise ValueError()
        if not 0 < record['timeout_seconds'] <= canary.COLD_START_MAX_TIMEOUT_SECONDS:
            raise ValueError()
        start, end = (datetime.strptime(record[key], '%Y-%m-%dT%H:%M:%SZ')
                      for key in ('started_at', 'ended_at'))
        configuration = record['provider_configuration']
        if (start > end or type(configuration) is not dict or set(configuration) !=
                {'ollama_url', 'ollama_model', 'timeout_seconds'} or
                configuration['timeout_seconds'] != record['timeout_seconds']):
            raise ValueError()
        validator = {'narrative': validate_narrative, 'companion': validate_companion,
                     'suggest': validate_suggestions}[task]
        clean = validator(output, bundle)
        if clean != output:
            raise ValueError()
        rubric = json.loads((ROOT / 'models' / 'quality-cases.json').read_text())['criteria']
        definitions = [(criterion, rubric[criterion]) for criterion in criteria]
    except (KeyError, TypeError, ValueError, canary.CanaryError, OSError, RecursionError):
        raise PageError('capture_contract_mismatch') from None
    # Detect replaced content across the three independently stable reads.
    for name, value in (('record.json', record), ('input-bundle.json', bundle), ('output.json', output)):
        if digest(_read(directory / name)) != digest(value):
            raise PageError('capture_changed')
    return {'case': case, 'bundle': bundle, 'output': clean, 'criteria': definitions,
            'record_sha256': digest(record), 'input_sha256': digest(bundle),
            'output_sha256': digest(output), 'configuration_sha256': record['configuration_identity_sha256'],
            'review_context_sha256': digest({'case': case, 'criteria': definitions})}


STYLE = '''
:root{color-scheme:light;--ink:#302d29;--muted:#746c61;--line:#dfd8cb;--accent:#9c4935}
*{box-sizing:border-box}html{scroll-padding-top:1rem}body{margin:0;background:#f6f3ed;color:var(--ink);font:1rem/1.75 system-ui,sans-serif;overflow-wrap:anywhere}
main{max-width:1440px;margin:auto;padding:clamp(1rem,3vw,3rem)}h1{font-size:clamp(1.8rem,4vw,2.7rem);line-height:1.3;margin:.4rem 0 1rem}h2{font-size:1.35rem}h3{font-size:1.1rem}
p{margin:.6rem 0}.eyebrow,.meta{color:var(--muted);font-size:.9rem}.notice{border-left:4px solid var(--accent);padding:.8rem 1rem;background:#eee7db;margin:1.2rem 0 2rem}
.layout{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:1.4rem;align-items:start}.card{background:#fffcf7;border:1px solid var(--line);border-radius:16px;padding:clamp(1rem,2vw,1.8rem);margin:0 0 1rem;min-width:0}
.words{white-space:pre-wrap;overflow-wrap:anywhere}a{color:var(--accent);text-underline-offset:.2em;overflow-wrap:anywhere}a:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:4px}
.references{display:flex;flex-wrap:wrap;gap:.4rem .8rem;margin:.9rem 0}a{min-height:44px;display:inline-flex;align-items:center}nav a{margin-right:1rem}summary{cursor:pointer;min-height:44px;display:flex;align-items:center}
.source:target,.chapter:target{outline:3px solid var(--accent);outline-offset:3px}.source h3{margin:.2rem 0}.original{border-top:1px solid var(--line);margin-top:1rem;padding-top:.8rem}
ol,ul{padding-left:1.4rem}li{margin:.6rem 0}code{overflow-wrap:anywhere;word-break:break-all;font-size:.82em}small{color:var(--muted)}.empty{color:var(--muted);font-style:italic}
@media(max-width:800px){.layout{grid-template-columns:1fr}main{padding:1rem}.card{border-radius:12px}}@media print{body{background:white}.layout{display:block}.card{break-inside:avoid}a{color:inherit}}
'''


def render_review(review):
    case, bundle, output = review['case'], review['bundle'], review['output']
    sources = {source['id']: (index, source) for index, source in enumerate(bundle['sources'], 1)}
    e = lambda value: escape(str(value), quote=True)

    def refs(ids):
        if not ids:
            return '<p class="empty">没有引用来源；请核对是否应澄清或不作建议。</p>'
        return '<div class="references" aria-label="引用来源">' + ''.join(
            f'<a href="#source-{sources[ident][0]}">来源 {sources[ident][0]}</a>' for ident in ids) + '</div>'

    def narrative(result):
        chapters = []
        for index, (proposed, original) in enumerate(zip(result['chapters'], bundle['chapters']), 1):
            chapters.append(f'<article class="card chapter" id="chapter-{index}">'
                            f'<p class="meta">章节 {index} · AI 建议，尚未采纳</p>'
                            f'<h3>{e(original["title"])}</h3><p class="words">{e(proposed["narration"])}</p>'
                            + refs(proposed['source_ids']) + '<details class="original"><summary>对照输入章节原文</summary>'
                            f'<p class="words">{e(original["narration"])}</p>'
                            + refs(original['evidence_ids']) + '</details></article>')
        return f'<h2 class="words">{e(result["title"])}</h2>' + ''.join(chapters)

    task = case['task']
    if task == 'suggest':
        proposed = ''.join(f'<article class="card"><p class="meta">标题建议 {i}</p><h2 class="words">{e(title["text"])}</h2>'
                           + refs(title['source_ids']) + '</article>' for i, title in enumerate(output['titles'], 1))
        proposed = proposed or '<p class="card empty">没有标题建议。空来源时应保留这一结果，不补造标题。</p>'
        questions = []
    elif task == 'companion':
        kind = {'answer': '回答', 'clarification': '澄清', 'proposal': '叙事建议'}[output['kind']]
        proposed = f'<article class="card"><p class="meta">{kind} · 尚待人工核对</p><p class="words">{e(output["reply"])}</p>' + refs(output['source_ids']) + '</article>'
        if output['proposal'] is not None:
            proposed += narrative(output['proposal'])
        questions = output['questions'] + (output['proposal']['questions'] if output['proposal'] else [])
    else:
        proposed, questions = narrative(output), output['questions']
    if questions:
        proposed += '<section class="card"><h3>模型提出的问题</h3><ul>' + ''.join(f'<li class="words">{e(q)}</li>' for q in questions) + '</ul></section>'
    kinds = {'family': '家人记录', 'transcript': '录音转写', 'metadata': '元数据：查看来源说明',
             'ai': 'AI 观察，需核对', 'draft': '输入草稿'}
    source_html = ''
    for index, source in sources.values():
        kind = source.get('kind', source.get('source'))
        author = source.get('author')
        attribution = f'<p class="meta">记录中的作者标签：{e(author)}</p>' if author else ''
        source_html += f'<article class="card source" id="source-{index}"><h3>来源 {index}</h3><p class="meta">{e(kinds.get(kind, kind))}</p>{attribution}<p class="words">{e(source["text"])}</p></article>'
    source_html = source_html or '<p class="card empty">本案例没有来源材料。</p>'
    expectations = ''.join(f'<li><strong>{e(key)}</strong><p class="words">{e(value)}</p></li>'
                           for key, value in case['human_review_expectations'].items())
    rubric = ''.join(f'<li><strong>{e(criterion)}</strong> · 未评审<p class="words">{e(definition)}</p></li>'
                    for criterion, definition in review['criteria'])
    history = bundle.get('recent_turns', [])
    context = ('<section class="card"><h3>本次输入要求</h3>'
               f'<p class="words">主题：{e(bundle["theme"])}</p>'
               f'<p class="words">{e(bundle.get("instructions", "标题候选，保留人工选择。"))}</p></section>')
    if history:
        context += '<section class="card"><h3>最近对话：不是已确认来源</h3>' + ''.join(
            f'<p class="words"><strong>用户：</strong>{e(turn["user"])}</p><p class="words"><strong>助手：</strong>{e(turn["assistant"])}</p>' for turn in history) + '</section>'
    hashes = ''.join(f'<li>{e(key)}<br><code>{e(review[key])}</code></li>'
                     for key in ('record_sha256', 'input_sha256', 'output_sha256', 'configuration_sha256', 'review_context_sha256'))
    css_hash = base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
    csp = f"default-src 'none'; style-src 'sha256-{css_hash}'; script-src 'none'; base-uri 'none'; form-action 'none'"
    return ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="Content-Security-Policy" content="{e(csp)}">'
            f'<title>PhotoHouse · 故事质量审阅</title><style>{STYLE}</style></head><body><main>'
            '<header><p class="eyebrow">PHOTOHOUSE · 私密离线审阅</p><h1>故事与来源审阅</h1>'
            f'<p class="meta">合成案例 · {e(case["case_id"])} · {e(task)}</p></header>'
            '<div class="notice">结构与引用检查通过；故事质量尚未评审。</div>'
            '<nav aria-label="审阅导航"><a href="#wording">建议文字</a><a href="#sources">原始来源</a><a href="#review">评审要点</a></nav>'
            f'<div class="layout"><section id="wording"><h2>建议文字</h2>{proposed}</section>'
            f'<aside id="sources" aria-label="原始来源"><h2>原始来源</h2>{source_html}{context}</aside></div>'
            f'<section id="review" class="card"><h2>当前源码评审要点 · 全部未评审</h2><p>逐项对照来源、事件、归属和不确定之处。人工评审记录仍使用独立的模型评审工作表。</p><ol>{rubric}</ol>'
            f'<details><summary>查看本案例的具体预期</summary><ul>{expectations}</ul></details></section>'
            '<details class="card"><summary>查看检查范围与内容哈希</summary>'
            '<p>本页只检查规范化文件内容、当前结构和引用约束。哈希与引用不证明事实正确、'
            '模型确实执行或资源合格。本页不会保存、采纳、发布或启用模型。</p>'
            f'<ul>{hashes}</ul></details>'
            '</main></body></html>')


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise PageError('arguments_invalid')


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--capture-directory', type=Path, required=True)
        parser.add_argument('--output', type=Path, required=True)
        args = parser.parse_args(argv)
        if args.output.suffix.lower() != '.html':
            raise PageError('output_location')
        review = load_review(args.capture_directory)
        payload = render_review(review).encode('utf-8')
        if len(payload) > 1024 * 1024:
            raise PageError('review_page_too_large')
        _write_exclusive(args.output, payload, ROOT)
        result = dict(status='private_review_page_written', case_id=review['case']['case_id'],
                      task=review['case']['task'], page_sha256=hashlib.sha256(payload).hexdigest(),
                      quality_evaluated=False, activation_performed=False, provider_contacted=False)
        code = 0
    except (PageError, ReviewError) as error:
        result, code = dict(status='refused', error_code=str(error)), 2
    except Exception:
        result, code = dict(status='refused', error_code='review_page_unavailable'), 2
    print(json.dumps(result, separators=(',', ':')))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
