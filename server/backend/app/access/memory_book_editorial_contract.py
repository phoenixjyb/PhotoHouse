"""Pure strict parsing and validation for versioned memoir editorial sidecars.

This module validates a request against current book/child revisions and source
identities supplied by a trusted caller. It does not authorize a user, read a
database, or decide whether a source may be used; callers must construct the
eligible identity set only after same-library authorization and consent checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import re
import uuid
from typing import AbstractSet, Sequence

MAX_BODY_BYTES = 65_536
MAX_CHILDREN = 24
MAX_REFS_PER_SECTION = 12
MAX_REFS_TOTAL = 96
MAX_TRANSITION_BYTES = 6_000
MAX_CHAPTER_ID_BYTES = 128
MAX_REVISION = 2**63 - 1

_REQUEST_KEYS = {
    'version', 'revision', 'mutation_id', 'children',
    'introduction_source_refs', 'transitions',
}
_CHILD_KEYS = {'story_id', 'revision'}
_SOURCE_KEYS = {'story_id', 'story_revision', 'chapter_id', 'contribution_id'}
_TRANSITION_KEYS = {'left_story_id', 'right_story_id', 'text', 'source_refs'}
_REVISION_RE = re.compile(r'[1-9][0-9]*\Z')


class ContractCode(str, Enum):
    INVALID_JSON = 'invalid_json'
    INVALID_SHAPE = 'invalid_shape'
    UNSUPPORTED_VERSION = 'unsupported_version'
    INVALID_IDENTIFIER = 'invalid_identifier'
    TOO_LARGE = 'too_large'
    CHILD_LIMIT = 'child_limit'
    REVISION_CONFLICT = 'revision_conflict'
    SOURCE_CHANGED = 'source_changed'
    INVALID_TRANSITION = 'invalid_transition'
    INVALID_REFERENCE = 'invalid_reference'
    INVALID_CONTEXT = 'invalid_context'


class EditorialContractError(ValueError):
    """Bounded validation error; never includes request or source values."""

    def __init__(self, code: ContractCode):
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class ChildRevision:
    story_id: str
    revision: str


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    story_id: str
    story_revision: str
    chapter_id: str
    contribution_id: str


@dataclass(frozen=True, slots=True)
class EditorialTransition:
    left_story_id: str
    right_story_id: str
    text: str
    source_refs: tuple[SourceIdentity, ...]


@dataclass(frozen=True, slots=True)
class EditorialMutation:
    expected_revision: str
    mutation_id: str
    children: tuple[ChildRevision, ...]
    introduction_source_refs: tuple[SourceIdentity, ...]
    transitions: tuple[EditorialTransition, ...]


def _fail(code: ContractCode) -> None:
    raise EditorialContractError(code) from None


def _canonical_uuid(value: object) -> str:
    if type(value) is not str:
        _fail(ContractCode.INVALID_IDENTIFIER)
    try:
        if str(uuid.UUID(value)) != value:
            _fail(ContractCode.INVALID_IDENTIFIER)
    except (ValueError, AttributeError):
        _fail(ContractCode.INVALID_IDENTIFIER)
    return value


def _revision(value: object) -> str:
    if (type(value) is not str or _REVISION_RE.fullmatch(value) is None
            or len(value) > 19):
        _fail(ContractCode.INVALID_IDENTIFIER)
    if int(value) > MAX_REVISION:
        _fail(ContractCode.INVALID_IDENTIFIER)
    return value


def _chapter_id(value: object) -> str:
    if type(value) is not str or not value or '\x00' in value:
        _fail(ContractCode.INVALID_IDENTIFIER)
    try:
        if len(value.encode('utf-8', errors='strict')) > MAX_CHAPTER_ID_BYTES:
            _fail(ContractCode.INVALID_IDENTIFIER)
    except UnicodeError:
        _fail(ContractCode.INVALID_IDENTIFIER)
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError('nonstandard number')


def _decode(raw: bytes | str) -> object:
    if type(raw) is bytes:
        encoded = raw
    elif type(raw) is str:
        try:
            encoded = raw.encode('utf-8', errors='strict')
        except UnicodeError:
            _fail(ContractCode.INVALID_JSON)
    else:
        _fail(ContractCode.INVALID_JSON)
    if len(encoded) > MAX_BODY_BYTES:
        _fail(ContractCode.TOO_LARGE)
    try:
        text = encoded.decode('utf-8', errors='strict')
        return json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (json.JSONDecodeError, UnicodeError, ValueError, RecursionError):
        _fail(ContractCode.INVALID_JSON)


def _exact_object(value: object, keys: set[str]) -> dict:
    if type(value) is not dict or set(value) != keys:
        _fail(ContractCode.INVALID_SHAPE)
    return value


def _source_ref(value: object) -> SourceIdentity:
    obj = _exact_object(value, _SOURCE_KEYS)
    return SourceIdentity(
        story_id=_canonical_uuid(obj['story_id']),
        story_revision=_revision(obj['story_revision']),
        chapter_id=_chapter_id(obj['chapter_id']),
        contribution_id=_canonical_uuid(obj['contribution_id']),
    )


def _source_list(value: object, *, child_revisions: dict[str, str],
                 eligible_sources: AbstractSet[SourceIdentity],
                 allowed_stories: set[str] | None = None) -> tuple[SourceIdentity, ...]:
    if type(value) is not list or len(value) > MAX_REFS_PER_SECTION:
        _fail(ContractCode.INVALID_REFERENCE)
    refs = tuple(_source_ref(item) for item in value)
    if len(set(refs)) != len(refs):
        _fail(ContractCode.INVALID_REFERENCE)
    for ref in refs:
        if (ref.story_id not in child_revisions
                or child_revisions[ref.story_id] != ref.story_revision
                or (allowed_stories is not None and ref.story_id not in allowed_stories)
                or ref not in eligible_sources):
            _fail(ContractCode.INVALID_REFERENCE)
    return refs


def parse_mutation(raw: bytes | str, *, current_book_revision: str,
                   current_children: Sequence[ChildRevision],
                   eligible_sources: AbstractSet[SourceIdentity]) -> EditorialMutation:
    """Parse an exact v1 mutation and bind it to trusted current state.

    `eligible_sources` must be prefiltered by the caller for authorization,
    selected library, accepted/consented state, chapter compatibility, and
    current story revision. The result is immutable. This function performs no
    I/O and cannot authorize or reauthorize any identity on its own.
    """
    try:
        book_revision = _revision(current_book_revision)
        if (type(current_children) not in (tuple, list)
                or not 1 <= len(current_children) <= MAX_CHILDREN):
            _fail(ContractCode.INVALID_CONTEXT)
        clean_current = tuple(
            ChildRevision(_canonical_uuid(child.story_id), _revision(child.revision))
            for child in current_children
            if type(child) is ChildRevision)
        if len(clean_current) != len(current_children):
            _fail(ContractCode.INVALID_CONTEXT)
        if len({child.story_id for child in clean_current}) != len(clean_current):
            _fail(ContractCode.INVALID_CONTEXT)
        if type(eligible_sources) not in (set, frozenset):
            _fail(ContractCode.INVALID_CONTEXT)
        if any(type(source) is not SourceIdentity for source in eligible_sources):
            _fail(ContractCode.INVALID_CONTEXT)

        value = _decode(raw)
        obj = _exact_object(value, _REQUEST_KEYS)
        if type(obj['version']) is not int or obj['version'] != 1:
            _fail(ContractCode.UNSUPPORTED_VERSION)
        expected_revision = _revision(obj['revision'])
        if expected_revision != book_revision:
            _fail(ContractCode.REVISION_CONFLICT)
        mutation_id = _canonical_uuid(obj['mutation_id'])

        raw_children = obj['children']
        if type(raw_children) is not list or not 1 <= len(raw_children) <= MAX_CHILDREN:
            _fail(ContractCode.CHILD_LIMIT)
        children = []
        for item in raw_children:
            child = _exact_object(item, _CHILD_KEYS)
            children.append(ChildRevision(
                _canonical_uuid(child['story_id']), _revision(child['revision'])))
        child_tuple = tuple(children)
        if len({child.story_id for child in child_tuple}) != len(child_tuple):
            _fail(ContractCode.INVALID_IDENTIFIER)
        if child_tuple != clean_current:
            _fail(ContractCode.SOURCE_CHANGED)

        child_revisions = {child.story_id: child.revision for child in child_tuple}
        introduction_refs = _source_list(
            obj['introduction_source_refs'], child_revisions=child_revisions,
            eligible_sources=eligible_sources)
        total_refs = len(introduction_refs)

        raw_transitions = obj['transitions']
        if (type(raw_transitions) is not list
                or len(raw_transitions) != len(child_tuple) - 1):
            _fail(ContractCode.INVALID_TRANSITION)
        transitions = []
        for index, item in enumerate(raw_transitions):
            transition = _exact_object(item, _TRANSITION_KEYS)
            left = _canonical_uuid(transition['left_story_id'])
            right = _canonical_uuid(transition['right_story_id'])
            if (left != child_tuple[index].story_id
                    or right != child_tuple[index + 1].story_id):
                _fail(ContractCode.INVALID_TRANSITION)
            text = transition['text']
            if type(text) is not str or '\x00' in text:
                _fail(ContractCode.INVALID_TRANSITION)
            try:
                text_size = len(text.encode('utf-8', errors='strict'))
            except UnicodeError:
                _fail(ContractCode.INVALID_TRANSITION)
            if text_size > MAX_TRANSITION_BYTES:
                _fail(ContractCode.INVALID_TRANSITION)
            refs = _source_list(
                transition['source_refs'], child_revisions=child_revisions,
                eligible_sources=eligible_sources, allowed_stories={left, right})
            if text.strip():
                if not refs:
                    _fail(ContractCode.INVALID_TRANSITION)
            elif refs:
                _fail(ContractCode.INVALID_TRANSITION)
            total_refs += len(refs)
            transitions.append(EditorialTransition(left, right, text, refs))
        if total_refs > MAX_REFS_TOTAL:
            _fail(ContractCode.INVALID_REFERENCE)

        return EditorialMutation(expected_revision, mutation_id, child_tuple,
                                 introduction_refs, tuple(transitions))
    except EditorialContractError:
        raise
    except (AttributeError, TypeError, ValueError, UnicodeError, RecursionError):
        # Never include untrusted values or standard-library parser messages.
        _fail(ContractCode.INVALID_SHAPE)
