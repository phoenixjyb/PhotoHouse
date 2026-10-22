from __future__ import annotations

import builtins
import importlib.util
import itertools
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "app"
    / "access"
    / "selected_story_grammar.py"
)


def _load_module_without_optional_backend_imports():
    spec = importlib.util.spec_from_file_location("selected_story_grammar_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    original_import = builtins.__import__

    def restricted_import(name, *args, **kwargs):
        if name.startswith(("llama_cpp", "torch", "transformers")):
            raise AssertionError("optional backend imported during module load")
        return original_import(name, *args, **kwargs)

    builtins.__import__ = restricted_import
    try:
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        builtins.__import__ = original_import
    return module


grammar_module = _load_module_without_optional_backend_imports()


class _FakeSchemaConverter:
    def __init__(self, *, prop_order, allow_fetch, dotall, raw_pattern):
        self.init_options = (prop_order, allow_fetch, dotall, raw_pattern)
        self._rules = {"space": '" "?'}
        self.delegated = []

    def _add_rule(self, name, rule):
        key = name or "root"
        if key in self._rules and self._rules[key] != rule:
            suffix = 0
            while f"{key}{suffix}" in self._rules:
                suffix += 1
            key = f"{key}{suffix}"
        self._rules[key] = rule
        return key

    def _add_primitive(self, name, rule):
        result = self._add_rule(name, rule.content)
        for dependency in rule.deps:
            primitive = FAKE_BACKEND.PRIMITIVE_RULES[dependency]
            if dependency not in self._rules:
                self._add_primitive(dependency, primitive)
        return result

    def resolve_refs(self, schema, _base):
        assert self.init_options[1] is False
        return schema

    def visit(self, schema, name):
        self.delegated.append(schema)
        if type(schema) is dict and schema.get("type") == "object":
            for property_name in schema.get("properties", {}):
                self._add_rule(property_name, '"value"')
        return self._add_rule(name or "root", '"delegated"')

    def format_grammar(self):
        return "\n".join(f"{name} ::= {rule}" for name, rule in sorted(self._rules.items()))


FAKE_BACKEND = SimpleNamespace(
    SchemaConverter=_FakeSchemaConverter,
    RESERVED_NAMES={"root", "space"},
    PRIMITIVE_RULES={
        "char": type(
            "Primitive",
            (),
            {"content": r'[^"\\] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F])', "deps": []},
        )(),
    },
)


def _grammar_rules(grammar):
    return dict(line.split(" ::= ", 1) for line in grammar.splitlines())


def _length_intervals(rules, root):
    cache = {"char": ((1, 1),)}
    active = set()

    def merge(values):
        combined = []
        for lower, upper in sorted(values):
            if combined and lower <= combined[-1][1] + 1:
                combined[-1] = (combined[-1][0], max(combined[-1][1], upper))
            else:
                combined.append((lower, upper))
        return tuple(combined)

    def analyze(name):
        if name in cache:
            return cache[name]
        assert name not in active, f"nullable or recursive helper cycle: {name}"
        active.add(name)
        alternatives = []
        for alternative in rules[name].split("|"):
            lengths = ((0, 0),)
            for symbol in alternative.split():
                rhs = ((0, 0),) if symbol == '""' else analyze(symbol)
                lengths = merge(
                    (a + c, b + d)
                    for a, b in lengths
                    for c, d in rhs
                )
            alternatives.extend(lengths)
        active.remove(name)
        cache[name] = merge(alternatives)
        return cache[name]

    sequence = rules[root].split()
    delimiters = [index for index, token in enumerate(sequence) if token == r'"\""']
    assert len(delimiters) == 2
    lengths = ((0, 0),)
    for symbol in sequence[delimiters[0] + 1:delimiters[1]]:
        rhs = ((0, 0),) if symbol == '""' else analyze(symbol)
        lengths = merge((a + c, b + d) for a, b in lengths for c, d in rhs)
    return lengths


def _regex_for_rule(rules, root):
    cache = {}
    active = set()

    def compile_rule(name):
        if name in cache:
            return cache[name]
        assert name not in active
        active.add(name)
        source = rules[name]
        tokens = []
        index = 0
        while index < len(source):
            if source[index].isspace():
                index += 1
            elif source[index] in "|()?*+":
                tokens.append((source[index], source[index]))
                index += 1
            elif source[index] == '"':
                start = index
                index += 1
                while index < len(source):
                    if source[index] == "\\":
                        index += 2
                    elif source[index] == '"':
                        index += 1
                        break
                    else:
                        index += 1
                tokens.append(("literal", source[start:index]))
            elif source[index] == "[":
                start = index
                index += 1
                while index < len(source):
                    if source[index] == "\\":
                        index += 2
                    elif source[index] == "]":
                        index += 1
                        break
                    else:
                        index += 1
                tokens.append(("class", source[start:index]))
            elif source[index].isalnum() or source[index] in "_-":
                start = index
                while index < len(source) and (source[index].isalnum() or source[index] in "_-"):
                    index += 1
                tokens.append(("name", source[start:index]))
            else:
                raise AssertionError(f"unsupported grammar token {source[index]!r}")
        cursor = 0

        def alt():
            nonlocal cursor
            choices = [seq()]
            while cursor < len(tokens) and tokens[cursor][0] == "|":
                cursor += 1
                choices.append(seq())
            return "(?:" + "|".join(choices) + ")"

        def seq():
            nonlocal cursor
            pieces = []
            while cursor < len(tokens) and tokens[cursor][0] not in ("|", ")"):
                kind, value = tokens[cursor]
                cursor += 1
                if kind == "literal":
                    piece = re.escape(json.loads(value))
                elif kind == "class":
                    piece = value
                elif kind == "name":
                    piece = compile_rule(value)
                elif kind == "(":
                    piece = alt()
                    assert cursor < len(tokens) and tokens[cursor][0] == ")"
                    cursor += 1
                else:
                    raise AssertionError(kind)
                while cursor < len(tokens) and tokens[cursor][0] in ("?", "*", "+"):
                    suffix = tokens[cursor][0]
                    cursor += 1
                    piece = f"(?:{piece}){suffix}"
                pieces.append(piece)
            return "".join(pieces)

        expression = alt()
        assert cursor == len(tokens)
        active.remove(name)
        cache[name] = expression
        return expression

    return re.compile(compile_rule(root) + r"\Z")


def _prototype(schema):
    return grammar_module.bounded_schema_to_gbnf(json.dumps(schema), FAKE_BACKEND)


def _baseline_small_string_grammar(minimum, maximum):
    char = "char"

    def optional(n):
        if n == 0:
            return '""'
        if n == 1:
            return f"({char})?"
        return f"({char} {optional(n - 1)})?"

    required = " ".join([char] * minimum)
    optional_tail = optional(maximum - minimum)
    body = " ".join(part for part in (required, optional_tail) if part)
    return {
        "root": r'"\"" ' + body + r' "\"" space',
        "char": FAKE_BACKEND.PRIMITIVE_RULES["char"].content,
        "space": '" "?',
    }


def test_module_load_does_not_import_optional_model_packages():
    assert callable(grammar_module.bounded_schema_to_gbnf)


def test_bounded_string_uses_injected_backend_and_pinned_character_rule():
    schema = {"type": "string", "minLength": 1, "maxLength": 4}
    rules = _grammar_rules(_prototype(schema))
    assert rules["char"] == FAKE_BACKEND.PRIMITIVE_RULES["char"].content
    assert _length_intervals(rules, "root") == ((1, 4),)
    # The backend is instantiated with remote fetching and special pattern
    # modes disabled; the character grammar stays owned by that backend.
    assert "char" in rules


@pytest.mark.parametrize(
    "minimum,maximum",
    [(0, 0), (0, 1), (0, 7), (0, 8), (0, 9), (2, 5), (7, 9), (15, 17), (31, 33), (511, 513), (5999, 6000)],
)
def test_emitted_helper_language_has_exact_boundary_interval(minimum, maximum):
    grammar = _prototype({"type": "string", "minLength": minimum, "maxLength": maximum})
    intervals = _length_intervals(_grammar_rules(grammar), "root")
    assert intervals == ((minimum, maximum),)
    accepted = lambda count: any(low <= count <= high for low, high in intervals)
    for count, expected in [
        (minimum - 1, False),
        (minimum, True),
        (maximum, True),
        (maximum + 1, False),
    ]:
        if count >= 0:
            assert accepted(count) is expected


def test_small_serialized_json_strings_match_original_nested_grammar_language():
    tokens = ["x", "é", r'\"', r"\\", r"\/", r"\n", r"\u00e9"]
    payloads = [""] + ["".join(parts) for size in range(1, 5)
                            for parts in itertools.product(tokens, repeat=size)]
    payloads.extend([r"\ud83d\ude00", '"', r"\q"])
    for minimum, maximum in [(0, 0), (0, 1), (0, 4), (1, 3), (2, 5)]:
        generated = _regex_for_rule(
            _grammar_rules(_prototype({"type": "string", "minLength": minimum, "maxLength": maximum})),
            "root",
        )
        baseline = _regex_for_rule(_baseline_small_string_grammar(minimum, maximum), "root")
        for payload in payloads:
            encoded = f'"{payload}"'
            assert bool(generated.fullmatch(encoded)) == bool(baseline.fullmatch(encoded))


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "maxLength": True},
        {"type": "string", "maxLength": 1.5},
        {"type": "string", "minLength": -1, "maxLength": 2},
        {"type": "string", "minLength": 3, "maxLength": 2},
        {"type": "string", "maxLength": 65537},
    ],
)
def test_invalid_bounded_string_limits_fail_with_fixed_error(schema):
    with pytest.raises(ValueError, match="^invalid bounded string limits$"):
        _prototype(schema)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "minLength": 1, "maxLength": 4, "pattern": "^x+$"},
        {"type": "string", "minLength": 1, "maxLength": 4, "format": "date"},
        {"type": "string", "minLength": 1, "maxLength": 4, "const": "fixed"},
        {"type": "string", "minLength": 1, "maxLength": 4, "unknown": True},
        {"$ref": "https://invalid.example/schema"},
        {"type": "integer", "minimum": 0},
    ],
)
def test_special_or_unknown_forms_delegate_unchanged(schema):
    output = _prototype(schema)
    assert "root ::= \"delegated\"" in output


def test_schema_json_size_depth_nodes_and_nonstandard_scalars_are_capped():
    with pytest.raises(ValueError, match="^schema limits exceeded$"):
        grammar_module.bounded_schema_to_gbnf(" " * (grammar_module.MAX_SCHEMA_BYTES + 1), FAKE_BACKEND)
    deep = "[" * 33 + "0" + "]" * 33
    with pytest.raises(ValueError, match="^schema limits exceeded$"):
        grammar_module.bounded_schema_to_gbnf(deep, FAKE_BACKEND)
    wide = json.dumps([0] * grammar_module.MAX_SCHEMA_NODES)
    with pytest.raises(ValueError, match="^schema limits exceeded$"):
        grammar_module.bounded_schema_to_gbnf(wide, FAKE_BACKEND)
    with pytest.raises(ValueError, match="^invalid schema JSON$"):
        grammar_module.bounded_schema_to_gbnf('{"type":"string","maxLength":NaN}', FAKE_BACKEND)


def test_converter_rule_and_final_output_caps_are_enforced():
    properties = {f"p{index}": {} for index in range(1025)}
    schema = json.dumps({"type": "object", "properties": properties})
    with pytest.raises(ValueError, match="^schema rule limit exceeded$"):
        grammar_module.bounded_schema_to_gbnf(schema, FAKE_BACKEND)

    class HugeGrammarConverter(_FakeSchemaConverter):
        def format_grammar(self):
            return "x" * (grammar_module.MAX_GBNF_BYTES + 1)

    huge_backend = SimpleNamespace(
        SchemaConverter=HugeGrammarConverter,
        RESERVED_NAMES=FAKE_BACKEND.RESERVED_NAMES,
        PRIMITIVE_RULES=FAKE_BACKEND.PRIMITIVE_RULES,
    )
    with pytest.raises(ValueError, match="^grammar output limit exceeded$"):
        grammar_module.bounded_schema_to_gbnf('{"type":"string","maxLength":1}', huge_backend)
