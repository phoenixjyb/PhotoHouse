"""Pure request validation for explicitly reviewed memoir editions.

Callers must supply a freshly authorized, same-library book bundle. This
module validates its target and uses it to validate manuscript chapters and
citations. It does not authorize identities, read storage, call a model, or
persist an edition.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
import uuid

from .memory_narrative import validate_narrative
from .transport import TransportError

MAX_BODY_BYTES = 128 * 1024
MAX_CHILDREN = 24
MAX_REVISION = 2**63 - 1

_REQUEST_KEYS = {
    'version', 'revision', 'mutation_id', 'job_id', 'job_result_sha256',
    'source_fingerprint', 'reviewed', 'children', 'manuscript',
}
_CHILD_KEYS = {'id', 'revision'}
_REVISION_RE = re.compile(r'[1-9][0-9]*\Z', re.ASCII)
_SHA256_RE = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)


@dataclass(frozen=True, slots=True)
class EditionChildRevision:
    id: str
    revision: str


@dataclass(frozen=True, slots=True)
class ReviewedManuscriptChapter:
    id: str
    narration: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewedManuscript:
    title: str
    chapters: tuple[ReviewedManuscriptChapter, ...]
    questions: tuple[str, ...]
    needs_review: bool


@dataclass(frozen=True, slots=True)
class ReviewedManuscriptRequest:
    version: int
    revision: str
    mutation_id: str
    job_id: str
    job_result_sha256: str
    source_fingerprint: str
    reviewed: bool
    children: tuple[EditionChildRevision, ...]
    manuscript: ReviewedManuscript
    _canonical_json: bytes = field(repr=False, compare=False)

    @property
    def canonical_json(self) -> bytes:
        """Stable strict-ASCII JSON; contains reviewed text and must not be logged."""
        return self._canonical_json

    @property
    def request_digest(self) -> str:
        return hashlib.sha256(self._canonical_json).hexdigest()


def _bad_request() -> None:
    raise TransportError(400, 'Invalid memoir edition request') from None


def _canonical_uuid(value: object) -> str:
    if type(value) is not str:
        _bad_request()
    try:
        if str(uuid.UUID(value)) != value:
            _bad_request()
    except (ValueError, AttributeError):
        _bad_request()
    return value


def _revision(value: object) -> str:
    if (type(value) is not str or _REVISION_RE.fullmatch(value) is None
            or len(value) > 19 or int(value) > MAX_REVISION):
        _bad_request()
    return value


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _bad_request()
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
            raise TransportError(400, 'Invalid memoir edition request') from None
    else:
        raise TransportError(400, 'Invalid memoir edition request') from None
    if len(encoded) > MAX_BODY_BYTES:
        raise TransportError(413, 'Memoir edition request too large') from None
    try:
        return json.loads(encoded.decode('utf-8', errors='strict'),
                          object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (json.JSONDecodeError, UnicodeError, ValueError, RecursionError):
        raise TransportError(400, 'Invalid memoir edition request') from None


def _exact_object(value: object, keys: set[str]) -> dict:
    if type(value) is not dict or set(value) != keys:
        _bad_request()
    return value


def _to_payload(request_fields: dict) -> bytes:
    try:
        return json.dumps(request_fields, sort_keys=True, ensure_ascii=True,
                          allow_nan=False, separators=(',', ':')).encode('ascii')
    except (TypeError, ValueError, UnicodeError):
        _bad_request()


def reviewed_edition_identity(raw: bytes | str) -> tuple[str, str]:
    """Bounded retry identity, without consulting vanished source text.

    This cannot authorize a new save. An existing actor-scoped receipt must
    match the whole canonical request digest before any receipt is returned.
    New requests still require parse_reviewed_edition against fresh evidence.
    """
    obj = _exact_object(_decode(raw), _REQUEST_KEYS)
    if type(obj['version']) is not int or obj['version'] != 1 or obj['reviewed'] is not True:
        _bad_request()
    mutation_id = _canonical_uuid(obj['mutation_id'])
    return mutation_id, hashlib.sha256(_to_payload(obj)).hexdigest()


def parse_reviewed_edition(raw: bytes | str, bundle: object) -> ReviewedManuscriptRequest:
    """Validate an exact v1 review/save request against an authorized bundle.

    The caller must separately verify that `children` exactly match the
    authorized book's ordered current child revisions. The bundle has composite
    chapter IDs and does not carry that ordered child/revision list. Narrative
    validation here does bind the manuscript's ordered chapters and source IDs
    to the supplied bundle.
    """
    value = _decode(raw)
    obj = _exact_object(value, _REQUEST_KEYS)
    if type(obj['version']) is not int or obj['version'] != 1:
        _bad_request()
    revision = _revision(obj['revision'])
    mutation_id = _canonical_uuid(obj['mutation_id'])
    job_id = _canonical_uuid(obj['job_id'])
    job_result_sha256 = _sha256(obj['job_result_sha256'])
    source_fingerprint = _sha256(obj['source_fingerprint'])
    if type(obj['reviewed']) is not bool or obj['reviewed'] is not True:
        _bad_request()

    raw_children = obj['children']
    if (type(raw_children) is not list or not 1 <= len(raw_children) <= MAX_CHILDREN):
        _bad_request()
    children = []
    for item in raw_children:
        child = _exact_object(item, _CHILD_KEYS)
        children.append(EditionChildRevision(
            id=_canonical_uuid(child['id']), revision=_revision(child['revision'])))
    clean_children = tuple(children)
    if len({child.id for child in clean_children}) != len(clean_children):
        _bad_request()

    if type(bundle) is not dict:
        raise TransportError(422, 'Authorized memoir context unavailable') from None
    target = bundle.get('target')
    if (type(target) is not dict or target.get('type') != 'book'
            or type(target.get('revision')) is not int):
        raise TransportError(422, 'Authorized memoir context unavailable') from None
    if target['revision'] != int(revision):
        raise TransportError(409, 'Memoir edition base revision changed') from None

    try:
        manuscript_value = validate_narrative(obj['manuscript'], bundle)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TransportError(422, 'Invalid reviewed memoir manuscript') from None

    manuscript = ReviewedManuscript(
        title=manuscript_value['title'],
        chapters=tuple(ReviewedManuscriptChapter(
            id=chapter['id'], narration=chapter['narration'],
            source_ids=tuple(chapter['source_ids']))
            for chapter in manuscript_value['chapters']),
        questions=tuple(manuscript_value['questions']),
        needs_review=manuscript_value['needs_review'],
    )
    fields = {
        'version': 1,
        'revision': revision,
        'mutation_id': mutation_id,
        'job_id': job_id,
        'job_result_sha256': job_result_sha256,
        'source_fingerprint': source_fingerprint,
        'reviewed': True,
        'children': [{'id': child.id, 'revision': child.revision}
                     for child in clean_children],
        'manuscript': {
            'version': manuscript_value['version'],
            'title': manuscript.title,
            'chapters': [{'id': chapter.id, 'narration': chapter.narration,
                          'source_ids': list(chapter.source_ids)}
                         for chapter in manuscript.chapters],
            'questions': list(manuscript.questions),
            'needs_review': manuscript.needs_review,
        },
    }
    return ReviewedManuscriptRequest(
        version=1,
        revision=revision,
        mutation_id=mutation_id,
        job_id=job_id,
        job_result_sha256=job_result_sha256,
        source_fingerprint=source_fingerprint,
        reviewed=True,
        children=clean_children,
        manuscript=manuscript,
        _canonical_json=_to_payload(fields),
    )
