"""Content-free dependency closure for a reviewed memoir edition.

The caller reauthorizes the book, resolves contribution ownership, and verifies
its job fingerprint. This pure helper includes every prompt source, even one
omitted from the model's citations. No source words or author labels are returned.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import uuid

from .memory_book_edition_contract import EditionChildRevision
from .memory_narrative import _validate_bundle
from .transport import TransportError


@dataclass(frozen=True, slots=True)
class EditionSourceDependency:
    source_id: str
    kind: str
    asset_id: str | None
    source_digest: str
    chapter_ids: tuple[str, ...]
    contribution_id: str | None
    contribution_story_id: str | None


@dataclass(frozen=True, slots=True)
class MemoirEditionProvenance:
    children: tuple[EditionChildRevision, ...]
    sources: tuple[EditionSourceDependency, ...]

    @property
    def closure_digest(self) -> str:
        metadata = {
            'children': [[child.id, child.revision] for child in self.children],
            'sources': [[source.source_id, source.kind, source.asset_id,
                         source.source_digest, list(source.chapter_ids),
                         source.contribution_id, source.contribution_story_id]
                        for source in self.sources],
        }
        return _digest(metadata)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
        allow_nan=False, separators=(',', ':')).encode('ascii')).hexdigest()


def _uuid(value):
    if type(value) is not str or str(uuid.UUID(value)) != value:
        raise ValueError()
    return value


def build_edition_provenance(bundle, children, *, contribution_owners):
    """Build closure from freshly authorized server data, never model citations.

    `children` is the current ordered book child/revision list. Ownership for all
    `contribution-*` sources must come from verified contribution rows, including
    sources not used by any chapter. Source IDs of other kinds are opaque; they
    are not silently treated as contribution or upload-original identities.
    Errors with server context return a bounded 503, without private details.
    """
    try:
        clean = _validate_bundle(bundle)
        if clean['target']['type'] != 'book' or clean['recent_turns']:
            raise ValueError()
        _uuid(clean['target']['id'])
        if type(children) is not tuple or not 1 <= len(children) <= 24:
            raise ValueError()
        for child in children:
            if type(child) is not EditionChildRevision:
                raise ValueError()
            _uuid(child.id)
            if (type(child.revision) is not str or len(child.revision) > 19 or
                    re.fullmatch(r'[1-9][0-9]*', child.revision, re.ASCII) is None or
                    int(child.revision) > 2**63 - 1):
                raise ValueError()
        child_ids = [child.id for child in children]
        if len(set(child_ids)) != len(child_ids) or type(contribution_owners) is not dict:
            raise ValueError()
        chapters_by_source = {source['id']: [] for source in clean['sources']}
        chapter_children = []
        chapter_owner = {}
        for chapter in clean['chapters']:
            matches = [child_id for child_id in child_ids if chapter['id'].startswith(child_id + '-')]
            if len(matches) != 1:
                raise ValueError()
            owner = matches[0]
            chapter_owner[chapter['id']] = owner
            if not chapter_children or chapter_children[-1] != owner:
                chapter_children.append(owner)
            for source_id in chapter['evidence_ids']:
                chapters_by_source[source_id].append(chapter['id'])
        if chapter_children != child_ids:
            raise ValueError()
        if any(sum(owner == child for owner in chapter_owner.values()) > 6 for child in child_ids):
            raise ValueError()
        if clean['version'] == 2:
            expected = [{'story_id': child.id, 'revision': child.revision} for child in children]
            if clean['book_editorial']['children'] != expected:
                raise ValueError()
        sources = []
        for source in clean['sources']:
            cid = owner = None
            if source['id'].startswith('contribution-'):
                cid = _uuid(source['id'][len('contribution-'):])
                owner = _uuid(contribution_owners.get(cid))
                if owner not in child_ids or source['kind'] not in {'family', 'transcript'}:
                    raise ValueError()
                if any(chapter_owner[chapter_id] != owner for chapter_id in chapters_by_source[source['id']]):
                    raise ValueError()
            sources.append(EditionSourceDependency(source['id'], source['kind'], source['asset_id'],
                _digest(source), tuple(chapters_by_source[source['id']]), cid, owner))
        return MemoirEditionProvenance(children, tuple(sources))
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise TransportError(503, 'Memoir edition provenance unavailable') from None
