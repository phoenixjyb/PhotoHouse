"""Bounded JSON Schema grammar conversion for the optional local worker.

The caller supplies its already-loaded grammar backend. This module intentionally
does not import optional model packages or patch their converter globally.
"""

from __future__ import annotations

import json
import math
from typing import Any


MAX_SCHEMA_BYTES = 128 * 1024
MAX_SCHEMA_DEPTH = 32
MAX_SCHEMA_NODES = 4096
MAX_CONVERTER_RULES = 1024
MAX_GBNF_BYTES = 256 * 1024
MAX_STRING_BOUND = 65_536
_BOUNDED_STRING_KEYS = frozenset({"type", "minLength", "maxLength"})


def _reject_json_constant(_value: str) -> None:
    raise ValueError("invalid schema JSON")


def _check_schema_tree(root: Any) -> None:
    """Apply structural caps iteratively before handing data to a converter."""
    pending = [(root, 1)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > MAX_SCHEMA_NODES or depth > MAX_SCHEMA_DEPTH:
            raise ValueError("schema limits exceeded")
        if type(value) is dict:
            for key, child in value.items():
                if type(key) is not str:
                    raise ValueError("invalid schema value")
                pending.append((child, depth + 1))
        elif type(value) is list:
            pending.extend((child, depth + 1) for child in value)
        elif value is None or type(value) in (str, bool, int):
            continue
        elif type(value) is float and math.isfinite(value):
            continue
        else:
            raise ValueError("invalid schema value")


def bounded_schema_to_gbnf(schema_json: str, backend_module: Any) -> str:
    """Convert a trusted worker schema with shallow bounded-string helper rules.

    Only schemas consisting solely of ``type``, ``minLength`` and
    ``maxLength`` override the supplied backend's string visitor. Every other
    schema form follows its original converter path. Counts preserve the supplied
    backend's serialized ``char`` tokens, including its surrogate-pair escape
    behavior; decoded character and byte limits remain the response validator
    authority. This is not a general JSON Schema implementation.
    """
    if type(schema_json) is not str:
        raise ValueError("invalid schema JSON")
    try:
        encoded = schema_json.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("invalid schema JSON") from exc
    if len(encoded) > MAX_SCHEMA_BYTES:
        raise ValueError("schema limits exceeded")
    try:
        schema = json.loads(schema_json, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("invalid schema JSON") from exc
    _check_schema_tree(schema)

    class _BoundedSchemaConverter(backend_module.SchemaConverter):
        def __init__(self):
            super().__init__(
                prop_order={},
                allow_fetch=False,
                dotall=False,
                raw_pattern=False,
            )
            self._bounded_power_rules = {}
            self._bounded_upto_rules = {}

        def _add_rule(self, name, rule):
            result = super()._add_rule(name, rule)
            if len(self._rules) > MAX_CONVERTER_RULES:
                raise ValueError("schema rule limit exceeded")
            return result

        def _rule_name(self, name):
            return name + "-" if name in backend_module.RESERVED_NAMES else name or "root"

        def _helper_name(self, name, kind, value):
            return f"{name or 'root'}-bounded-{kind}-{value}"

        def _power(self, name, exponent, char_rule):
            key = (name, exponent)
            if key in self._bounded_power_rules:
                return self._bounded_power_rules[key]
            rule_name = self._helper_name(name, "power", exponent)
            if exponent == 0:
                expression = char_rule
            else:
                previous = self._power(name, exponent - 1, char_rule)
                expression = f"{previous} {previous}"
            result = self._add_rule(rule_name, expression)
            self._bounded_power_rules[key] = result
            return result

        def _upto(self, name, count, char_rule):
            key = (name, count)
            if key in self._bounded_upto_rules:
                return self._bounded_upto_rules[key]
            rule_name = self._helper_name(name, "upto", count)
            if count == 0:
                expression = '""'
            else:
                power = 1 << (count.bit_length() - 1)
                exponent = power.bit_length() - 1
                shorter = self._upto(name, power - 1, char_rule)
                exact_block = self._power(name, exponent, char_rule)
                remainder = self._upto(name, count - power, char_rule)
                # The alternatives cover disjoint token lengths.
                expression = f"{shorter} | {exact_block} {remainder}"
            result = self._add_rule(rule_name, expression)
            self._bounded_upto_rules[key] = result
            return result

        def visit(self, schema_node, name):
            if (
                type(schema_node) is dict
                and set(schema_node).issubset(_BOUNDED_STRING_KEYS)
                and schema_node.get("type") == "string"
                and "maxLength" in schema_node
            ):
                minimum = schema_node.get("minLength", 0)
                maximum = schema_node["maxLength"]
                if (
                    type(minimum) is not int
                    or type(maximum) is not int
                    or minimum < 0
                    or maximum < minimum
                    or maximum > MAX_STRING_BOUND
                ):
                    raise ValueError("invalid bounded string limits")
                rule_name = self._rule_name(name)
                char_rule = self._add_primitive(
                    "char", backend_module.PRIMITIVE_RULES["char"]
                )
                pieces = []
                for exponent in range(minimum.bit_length() - 1, -1, -1):
                    if minimum & (1 << exponent):
                        pieces.append(self._power(name, exponent, char_rule))
                pieces.append(self._upto(name, maximum - minimum, char_rule))
                expression = (
                    r'"\"" ' + " ".join(pieces) + r' "\"" space'
                )
                return self._add_rule(rule_name, expression)
            return super().visit(schema_node, name)

    try:
        converter = _BoundedSchemaConverter()
        resolved = converter.resolve_refs(schema, "stdin")
        converter.visit(resolved, "")
        grammar = converter.format_grammar()
        if len(grammar.encode("utf-8", errors="strict")) > MAX_GBNF_BYTES:
            raise ValueError("grammar output limit exceeded")
        return grammar
    except ValueError as exc:
        # Preserve only this module's fixed public categories. Backend errors
        # may include schema text or paths, so do not expose their messages.
        message = str(exc)
        if message in {
            "schema rule limit exceeded",
            "invalid bounded string limits",
            "grammar output limit exceeded",
        }:
            raise
        raise ValueError("grammar conversion failed") from None
    except Exception:
        raise ValueError("grammar conversion failed") from None
