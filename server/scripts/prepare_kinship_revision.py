#!/usr/bin/env python3
"""Create a new private kinship graph draft from reviewed assertion and alias edits.

The selected graph is never changed or activated. The patch must name the
expected canonical graph digest and may change assertions or one person's aliases.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / 'backend'))
sys.path.insert(0, str(SERVER / 'scripts'))

from app.access.kinship import KinshipGraph, KinshipUnavailable, MAX_BYTES, RELATIONS, load_private_graph
from check_private_search import (Refused, cases_file, private_bytes, selected,
                                  unique, write_report)
from app.access import discovery as d

SOURCE_ROOT = SERVER.parent
_DIGEST = re.compile(r'[0-9a-f]{64}')
_ASSERTION_FIELDS = {'id', 'subject_id', 'relation', 'object_id', 'source'}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused()


def _read_document(path):
    payload = private_bytes(path, MAX_BYTES)
    document = json.loads(payload.decode('utf-8'), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refused()))
    graph = load_private_graph(path, SOURCE_ROOT)
    if d.digest(document) != graph.digest:
        raise Refused()
    return payload, document, graph


def _assertion(value, people):
    if (type(value) is not dict or set(value) != _ASSERTION_FIELDS
            or type(value['id']) is not str or not value['id'].strip()
            or len(value['id'].encode('utf-8')) > 128
            or type(value['subject_id']) is not str or value['subject_id'] not in people
            or type(value['object_id']) is not str or value['object_id'] not in people
            or value['subject_id'] == value['object_id']
            or value['relation'] not in RELATIONS or value['source'] != 'user'):
        raise Refused()


def _apply_patch(document, patch):
    if (type(patch) is not dict
            or set(patch) != {'version', 'expected_graph_sha256', 'revision', 'operations'}
            or type(patch['version']) is not int or patch['version'] != 1
            or type(patch['expected_graph_sha256']) is not str
            or _DIGEST.fullmatch(patch['expected_graph_sha256']) is None
            or type(patch['operations']) is not list
            or not 1 <= len(patch['operations']) <= 64):
        raise Refused()

    base_graph = KinshipGraph(document)
    if patch['expected_graph_sha256'] != base_graph.digest:
        raise Refused()
    revision = patch['revision']
    if type(revision) is int:
        if type(document['revision']) is not int or revision <= document['revision']:
            raise Refused()
    elif type(revision) is str:
        if (type(document['revision']) is not str or revision == document['revision']
                or not revision.strip() or len(revision.encode('utf-8')) > 128
                or any(ord(char) < 32 for char in revision)):
            raise Refused()
    else:
        raise Refused()

    draft = deepcopy(document)
    people = {person['id']: person for person in draft['people']}
    assertions = list(document['assertions'])
    by_id = {item['id']: index for index, item in enumerate(assertions)}
    touched = set()
    touched_people = set()
    added = set()
    for operation in patch['operations']:
        if type(operation) is not dict or type(operation.get('op')) is not str:
            raise Refused()
        kind = operation['op']
        if kind == 'replace_aliases':
            ident, aliases = operation.get('person_id'), operation.get('aliases')
            if (set(operation) != {'op', 'person_id', 'aliases'} or type(ident) is not str
                    or ident not in people or ident in touched_people or type(aliases) is not list
                    or len(aliases) > 16 or aliases == people[ident]['aliases']):
                raise Refused()
            people[ident]['aliases'] = list(aliases)
            touched_people.add(ident)
        elif kind == 'add':
            if set(operation) != {'op', 'assertion'}:
                raise Refused()
            assertion = operation['assertion']
            _assertion(assertion, people)
            ident = assertion['id']
            if ident in by_id or ident in added or ident in touched:
                raise Refused()
            added.add(ident)
            assertions.append(deepcopy(assertion))
        elif kind in ('replace', 'remove'):
            expected = {'op', 'assertion_id', 'assertion'} if kind == 'replace' else {'op', 'assertion_id'}
            ident = operation.get('assertion_id')
            if (set(operation) != expected or type(ident) is not str
                    or ident not in by_id or ident in touched):
                raise Refused()
            touched.add(ident)
            index = by_id[ident]
            if kind == 'remove':
                assertions[index] = None
            else:
                assertion = operation['assertion']
                _assertion(assertion, people)
                if assertion['id'] != ident or assertion == assertions[index]:
                    raise Refused()
                assertions[index] = deepcopy(assertion)
        else:
            raise Refused()

    draft['revision'] = revision
    draft['assertions'] = [item for item in assertions if item is not None]
    validated = KinshipGraph(draft)
    return draft, validated


def main(argv=None):
    parser = Parser(allow_abbrev=False, description=__doc__)
    parser.add_argument('--graph', type=Path, required=True)
    parser.add_argument('--patch', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        selected(args.out, private=True, output=True)
        selected(args.graph, private=True)
        selected(args.patch, private=True)
        original_bytes, document, graph = _read_document(args.graph)
        patch = cases_file(args.patch)
        draft, validated = _apply_patch(document, patch)
        if (len(d.packed(draft)) + 1 > MAX_BYTES
                or graph.digest != patch['expected_graph_sha256']
                or private_bytes(args.graph, MAX_BYTES) != original_bytes
                or load_private_graph(args.graph, SOURCE_ROOT).digest != graph.digest):
            raise Refused()

        # The existing writer serializes a strict JSON document and creates the
        # destination once, owner-only; it refuses replacement or symlinks.
        output_sha256 = write_report(args.out, draft)
        reopened = load_private_graph(args.out, SOURCE_ROOT)
        if reopened.digest != validated.digest:
            raise Refused()
        print(json.dumps({'created': True, 'graph_sha256': reopened.digest,
                          'output_sha256': output_sha256},
                         sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print('Private kinship draft interrupted; inspect the new output before reuse.', file=sys.stderr)
        return 130
    except Exception:
        print('Private kinship draft refused or incomplete; inspect any new output before reuse.',
              file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
