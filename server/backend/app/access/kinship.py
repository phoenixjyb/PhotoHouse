"""Private, explicit-perspective kinship configuration. No household facts.

Graphs are read-only inputs, never an identity or library-access grant. Relative
names resolve through current reviewed catalog identities after authorization.
"""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import json
import os
import re
import stat

from . import discovery as d
from .private_storage import (require_private_directory, require_private_file,
                              stable_stat_identity)

MAX_BYTES = 128 * 1024
RELATIONS = frozenset(('mother', 'father', 'son', 'daughter', 'elder_daughter',
                      'younger_daughter', 'older_sister', 'younger_sister',
                      'eldest_sister', 'husband'))


class KinshipUnavailable(d.DiscoveryUnavailable):
    def __init__(self):
        Exception.__init__(self, 'Private kinship unavailable')


def require(value):
    if not value:
        raise KinshipUnavailable()


def label(value, maximum=256):
    require(type(value) is str and bool(value.strip()) and
            len(value.encode('utf-8')) <= maximum and not any(ord(c) < 32 for c in value))
    return value


def folded(value):
    return ' '.join(d.fold(value).split())


# Alternatives explicitly represent ambiguous routes; they are never reduced
# to the only known branch of an incomplete graph. Plurals allow several people.
SELECTORS = {}
def selector(aliases, paths, plural=False):
    for alias in aliases:
        SELECTORS[alias] = (paths, plural)


selector(('mother', 'mom', 'mum', 'mummy', '妈妈', '妈咪', '母亲'), (('mother',),))
selector(('father', 'dad', 'daddy', '爸爸', '父亲'), (('father',),))
selector(('parents', '父母', '爸爸妈妈'), (('mother',), ('father',)), True)
selector(('maternal grandmother', '外婆', '姥姥', '外祖母'), (('mother', 'mother'),))
selector(('maternal grandfather', '外公', '姥爷', '外祖父'), (('mother', 'father'),))
selector(('paternal grandmother', '奶奶', '祖母'), (('father', 'mother'),))
selector(('paternal grandfather', '爷爷', '祖父'), (('father', 'father'),))
selector(('grandmother', 'grandma'), (('mother', 'mother'), ('father', 'mother')))
selector(('grandfather', 'grandpa'), (('mother', 'father'), ('father', 'father')))
selector(('grandparents', '祖父母和外祖父母'),
         (('mother', 'mother'), ('mother', 'father'), ('father', 'mother'), ('father', 'father')), True)
selector(('older sister', 'elder sister', '姐姐'), (('older_sister',),))
selector(('younger sister', '妹妹'), (('younger_sister',),))
selector(('eldest sister', '大姐'), (('eldest_sister',),))
selector(('older brother', 'elder brother', '哥哥'), (('older_brother',),))
selector(('younger brother', '弟弟'), (('younger_brother',),))
selector(('sister', '姐妹'), (('sister',),))
selector(('siblings', '兄弟姐妹'), (('sibling',),), True)
selector(('elder daughter', 'older daughter', '大女儿'), (('elder_daughter',),))
selector(('younger daughter', '小女儿'), (('younger_daughter',),))
selector(('daughter', '女儿'), (('daughter',),))
selector(('daughters', '女儿们'), (('daughter',),), True)
selector(('son', '儿子'), (('son',),))
selector(('sons', '儿子们'), (('son',),), True)
selector(('children', '孩子们', '子女'), (('child',),), True)
selector(('husband', '丈夫', '老公'), (('husband',),))
selector(('wife', '妻子', '老婆'), (('wife',),))
selector(('spouse', '配偶'), (('spouse',),))


def names(person):
    values = [person['name_en'], person['name_zh'], *person['aliases']]
    return {part.strip() for value in values if value for part in (value, *value.split('/')) if part.strip()}


class KinshipGraph:
    def __init__(self, document):
        try:
            self._initialize(document)
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            raise KinshipUnavailable() from None

    @property
    def document(self):
        # A caller cannot mutate a loaded snapshot behind its digest.
        return deepcopy(self._document)

    def _initialize(self, document):
        require(type(document) is dict and set(document) == {
            'schema', 'graph_id', 'revision', 'perspective_id', 'scope', 'people', 'assertions'})
        require(type(document['schema']) is int and document['schema'] == 1)
        label(document['graph_id'], 128)
        revision = document['revision']
        require((type(revision) is int and 1 <= revision < 2**63) or
                (type(revision) is str and bool(label(revision, 128))))
        scope = document['scope']
        require(type(scope) is dict and set(scope) in (
            {'account_id', 'library_id'}, {'account_ids', 'library_id'}))
        accounts = ([scope['account_id']] if scope.get('account_id') is not None else []) if 'account_id' in scope else scope['account_ids']
        require(type(accounts) is list and len(accounts) <= 64)
        for account in accounts: label(account, 128)
        require(len(set(accounts)) == len(accounts))
        if accounts: require(scope['library_id'] is not None)
        if scope['library_id'] is not None: label(scope['library_id'], 128)
        self._account_ids = frozenset(accounts)
        self._library_id = scope['library_id']
        people = document['people']
        require(type(people) is list and 1 <= len(people) <= 256)
        self.people = {}; self._names = defaultdict(set)
        for person in people:
            require(type(person) is dict and set(person) == {
                'id', 'name_en', 'name_zh', 'aliases', 'catalog_binding'})
            pid = label(person['id'], 128); require(pid not in self.people)
            require(person['name_en'] is not None or person['name_zh'] is not None)
            for key in ('name_en', 'name_zh'):
                if person[key] is not None: label(person[key])
            require(type(person['aliases']) is list and len(person['aliases']) <= 16)
            for alias in person['aliases']: label(alias)
            require(len(set(map(folded, person['aliases']))) == len(person['aliases']))
            binding = person['catalog_binding']
            if binding is not None:
                require(type(binding) is dict and set(binding) == {'person_id', 'label'})
                d.identifier(binding['person_id']); label(binding['label'])
            self.people[pid] = deepcopy(person)
            for name in names(person): self._names[folded(name)].add(pid)
        self.perspective_id = document['perspective_id']
        require(type(self.perspective_id) is str and self.perspective_id in self.people)
        facts = document['assertions']
        require(type(facts) is list and len(facts) <= 2048)
        self._edges = defaultdict(lambda: defaultdict(set)); roles = defaultdict(set)
        seen_ids = set(); seen = set(); age = defaultdict(set)
        for fact in facts:
            require(type(fact) is dict and set(fact) == {'id', 'subject_id', 'relation', 'object_id', 'source'})
            fid = label(fact['id'], 128); require(fid not in seen_ids); seen_ids.add(fid)
            a, op, b = fact['subject_id'], fact['relation'], fact['object_id']
            require(a in self.people and b in self.people and a != b and op in RELATIONS and fact['source'] == 'user')
            require((a, op, b) not in seen); seen.add((a, op, b))
            if op in ('mother', 'daughter', 'elder_daughter', 'younger_daughter',
                      'older_sister', 'younger_sister', 'eldest_sister'): roles[b].add('female')
            if op in ('father', 'son', 'husband'): roles[b].add('male')
        require(all(len(value) == 1 for value in roles.values()))
        def add(a, op, b): self._edges[a][op].add(b)
        for fact in facts:
            a, op, b = fact['subject_id'], fact['relation'], fact['object_id']
            add(a, op, b)
            if op in ('mother', 'father'):
                add(a, 'parent', b); add(b, 'child', a)
            elif op in ('son', 'daughter', 'elder_daughter', 'younger_daughter'):
                add(a, 'child', b); add(b, 'parent', a)
                if op != 'son': add(a, 'daughter', b)
                if roles[a] == {'female'}: add(b, 'mother', a)
                elif roles[a] == {'male'}: add(b, 'father', a)
            elif op in ('older_sister', 'younger_sister', 'eldest_sister'):
                add(a, 'sister', b); add(a, 'sibling', b); add(b, 'sibling', a)
                if op in ('older_sister', 'eldest_sister'):
                    age[b].add(a); add(a, 'older_sister', b)
                    if roles[a]: add(b, 'younger_sister' if 'female' in roles[a] else 'younger_brother', a)
                else:
                    age[a].add(b)
                    if roles[a]: add(b, 'older_sister' if 'female' in roles[a] else 'older_brother', a)
            elif op == 'husband':
                add(a, 'spouse', b); add(b, 'spouse', a)
                if roles[a] == {'female'}: add(b, 'wife', a)
        for parent, edges in list(self._edges.items()):
            children = tuple(edges['child'])
            for child in children:
                if roles[child] == {'female'}: add(parent, 'daughter', child)
                elif roles[child] == {'male'}: add(parent, 'son', child)
                for sibling in children:
                    if sibling != child:
                        add(child, 'sibling', sibling)
                        if roles[sibling] == {'female'}: add(child, 'sister', sibling)
            for elder in edges['elder_daughter']:
                for younger in edges['younger_daughter']:
                    require(elder != younger); age[elder].add(younger)
                    add(younger, 'older_sister', elder); add(elder, 'younger_sister', younger)
        for pid, edges in list(self._edges.items()):
            for sibling in edges['sibling']:
                if roles[sibling] == {'female'}: add(pid, 'sister', sibling)
        def acyclic(edges):
            done = set(); active = set()
            def visit(pid):
                require(pid not in active)
                if pid in done: return
                active.add(pid)
                for target in edges.get(pid, ()): visit(target)
                active.remove(pid); done.add(pid)
            for pid in self.people: visit(pid)
        acyclic({pid: value['parent'] for pid, value in self._edges.items()})
        acyclic(age)
        for value in self._edges.values():
            require(len(value['mother']) <= 1 and len(value['father']) <= 1)
        self._document = deepcopy(document)
        self.digest = d.digest(document)

    def _apply(self, base, paths):
        result = set()
        for path in paths:
            current = set(base)
            for op in path:
                if not current or any(not self._edges[pid][op] for pid in current):
                    return set()
                current = set().union(*(self._edges[pid][op] for pid in current))
            result.update(current)
        return result

    def _resolve(self, phrase, base=None):
        phrase = folded(phrase).replace('’', "'")
        phrase = re.sub(r'^(?:my\s+|our\s+|我的?|我们的?)', '', phrase)
        if not phrase: return set(), False, None
        if phrase in self._names and phrase not in SELECTORS:
            return set(self._names[phrase]), False, None
        parts = [part.strip() for part in re.split(r"'s\s*|的", phrase) if part.strip()]
        current = {self.perspective_id} if base is None else set(base)
        if parts and parts[0] in self._names and parts[0] not in SELECTORS:
            current = set(self._names[parts.pop(0)])
            if len(current) != 1: return current, False, None
        plural = False; parent = None
        for part in parts:
            selection = SELECTORS.get(part)
            if selection is None: return set(), False, None
            paths, plural = selection; parent = set(current)
            current = self._apply(current, paths)
        return current, plural, parent

    def resolve(self, phrase):
        return self._resolve(phrase)[0]

    def allows(self, account_id, library_id):
        return account_id in self._account_ids and library_id == self._library_id

    def catalog_ids(self, targets, reviewed_people):
        reviewed_people = tuple(p for p in reviewed_people if p.library_id == self._library_id)
        found = set()
        for target in targets:
            require(target in self.people)
            person = self.people[target]; binding = person['catalog_binding']
            if binding is not None:
                candidates = [p.id for p in reviewed_people if p.id == binding['person_id'] and p.label == binding['label']]
            else:
                # A kinship nickname is not an identity join. Only explicit
                # proper-name aliases or a reviewed ID+label binding can link
                # this graph's person to the current catalog.
                requested = {folded(name) for name in names(person)
                             if re.sub(r'^(?:my |our |我的|我们的)', '', folded(name)) not in SELECTORS}
                candidates = []
                for p in reviewed_people:
                    candidates_names = {folded(part.strip()) for name in (p.label, *p.aliases)
                                        for part in (name, *name.split('/'))}
                    if requested & candidates_names: candidates.append(p.id)
            require(len(candidates) == 1)
            require(candidates[0] not in found)
            found.add(candidates[0])
        return found

    def mentions(self, words):
        def atom(values):
            parts = []
            for value in sorted(values, key=len, reverse=True):
                escaped = re.escape(value).replace(r'\ ', r'\s+')
                if value.isascii(): escaped = r'(?<![a-z0-9_])' + escaped + r'(?![a-z0-9_])'
                parts.append(escaped)
            return '(?:' + '|'.join(parts) + ')'
        anchors = atom(self._names)
        relative = atom(SELECTORS)
        connector = r"(?:['’]s\s*|的)"
        pattern = re.compile(r'(?:(?:' + anchors + connector + r'|my\s+|our\s+|我的?|我们的?))?'
                             + relative + '(?:' + connector + relative + '){0,5}', re.IGNORECASE)
        direct = re.compile(anchors, re.IGNORECASE)
        spans = []; targets = set(); ambiguous = False; previous_end = 0; parent = None
        for match in pattern.finditer(words):
            phrase = match.group(0)
            inherited = parent if re.fullmatch(r'\s*(?:and|or|和|与|及|或|、|，|,)\s*',
                                               words[previous_end:match.start()], re.IGNORECASE) else None
            result, plural, parent = self._resolve(phrase, inherited)
            ambiguous |= not result or (len(result) > 1 and not plural)
            targets.update(result)
            end = match.end()
            suffix = re.match(r"['’]s(?=\s+(?:photos?|videos?|pictures?|images?)\b)", words[end:], re.IGNORECASE)
            if suffix: end += suffix.end()
            spans.append((match.start(), end)); previous_end = end
        for match in direct.finditer(words):
            if any(start < match.end() and match.start() < end for start, end in spans): continue
            result = self._names.get(folded(match.group(0)), set())
            ambiguous |= len(result) != 1; targets.update(result)
            spans.append((match.start(), match.end()))
        return targets, [words[start:end] for start, end in sorted(spans)], bool(ambiguous)


def load_private_graph(path, source_root):
    try:
        path = Path(path); root = Path(source_root).resolve()
        require(path.is_absolute() and '..' not in path.parts and not path.is_relative_to(root))
        def check_path():
            for part in (*reversed(path.parents), path):
                info = part.lstat()
                require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400)
                if part.is_dir(): require(not (part / '.git').exists())
            require_private_directory(path.parent); require_private_file(path)
        check_path(); before = path.stat(); require(0 < before.st_size <= MAX_BYTES)
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno()); require(stat.S_ISREG(opened.st_mode))
            payload = stream.read(MAX_BYTES + 1); after = os.fstat(stream.fileno())
        check_path(); final = path.stat()
        require(stable_stat_identity(before) == stable_stat_identity(opened) ==
                stable_stat_identity(after) == stable_stat_identity(final) and len(payload) <= MAX_BYTES)
        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result); result[key] = value
            return result
        document = json.loads(payload.decode('utf-8'), object_pairs_hook=unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(KinshipUnavailable()))
        return KinshipGraph(document)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise KinshipUnavailable() from None


class PrivateKinshipProvider:
    def __init__(self, path, *, source_root):
        self.path, self.source_root = Path(path), Path(source_root)

    def get(self, account_id, library_id):
        graph = load_private_graph(self.path, self.source_root)
        return graph if graph.allows(account_id, library_id) else None
