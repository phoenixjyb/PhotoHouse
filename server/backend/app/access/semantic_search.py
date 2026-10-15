"""Opt-in text-to-image search over current, hard-filtered library images.

The ordinary assistant wire stays literal. This explicit pilot shares its
authorization, reviewed metadata and hard-filter implementation, then ranks a
complete bounded cohort using a separately qualified joint text/image space.
"""
from dataclasses import dataclass
import math
from pathlib import Path

from . import discovery as d
from .assistant_search import AssistantSearchReads
from .discovery_transport import DiscoveryRuntime
from .semantic_encoder import JointSpaceBinding, LocalSemanticEncoder, rank_semantic
from .service import AccessService
from .visual_candidates import MAX_CANDIDATES, VectorRecord, _canonical_components, canonical_vector_checksum
from .visual_vector_artifacts import identity_sha256
from .visual_vector_loader import _COLUMNS, _checked_root, _read_vector, _validated_rows
from .visual_vector_schema import verify_visual_vector_schema


class SemanticSearchReads(AssistantSearchReads):
    def __init__(self, access, provider, budget, *, vector_root, encoder, query):
        super().__init__(access, provider, budget)
        self.vector_root, self.encoder, self.query = vector_root, encoder, query
        self._vector_rows = ()
        self._source_hashes = {}
        self._candidate_count = 0

    def _extra_source(self, index, source, read, check):
        extra = super()._extra_source(index, source, read, check)
        check()
        if not verify_visual_vector_schema(self.access.db):
            raise d.DiscoveryUnavailable()
        image_identity = self.encoder.binding.image_identity
        # Metadata participates in the same opaque source binding. Current
        # library scope and active status apply before any vector file is read.
        columns = ','.join('v.' + column for column in _COLUMNS.split(','))
        rows = read(f'''SELECT {columns} FROM image_vector_artifacts v
            JOIN assets a ON a.id=v.asset_id
            JOIN access_asset_libraries m ON m.asset_id=a.id
            WHERE m.library_id=? AND (a.status IS NULL OR a.status='active')
            AND a.mime GLOB 'image/*' AND v.status='ready' AND v.identity_sha256=?
            ORDER BY v.asset_id,v.record_id''', (index.library_id, identity_sha256(image_identity)))
        hashes = read('''SELECT a.id,a.hash_sha256 FROM assets a
            JOIN access_asset_libraries m ON m.asset_id=a.id WHERE m.library_id=?
            AND (a.status IS NULL OR a.status='active') AND a.mime GLOB 'image/*'
            ORDER BY a.id''', (index.library_id,))
        self._vector_rows = rows
        self._source_hashes = {str(aid): digest for aid, digest in hashes}
        return {**extra, 'semantic_policy': 1,
                'joint_space_binding': self.encoder.binding.binding_sha256,
                'semantic_query': d.digest(self.query), 'image_vector_records': rows,
                'image_source_hashes': hashes}

    def _rank(self, found):
        check = self._check
        check()
        self._candidate_count = len(found)
        if len(found) > MAX_CANDIDATES:
            raise d.DiscoveryUnavailable()
        if not found:
            return []
        ids = {item['id'] for item in found}
        selected = []
        for row in self._vector_rows:
            check()
            if str(row[1]) in ids:
                selected.append(row)
        records = _validated_rows(selected, self.encoder.binding.image_identity)
        # Missing, stale, duplicate or corrupt eligible vectors refuse the
        # whole search; top-k must not conceal incomplete candidate coverage.
        if set(records) != ids or len(selected) != len(ids):
            raise d.DiscoveryUnavailable()
        root = _checked_root(self.vector_root)
        if root is None:
            raise d.DiscoveryUnavailable()
        vectors = []
        for aid, artifact in records.items():
            check()
            if artifact.source_sha256 != self._source_hashes.get(aid):
                raise d.DiscoveryUnavailable()
            vector = _read_vector(root, artifact)
            check()
            if vector is None or canonical_vector_checksum(vector) != artifact.component_sha256:
                raise d.DiscoveryUnavailable()
            record = VectorRecord(aid, self.encoder.binding.image_identity,
                                  vector, artifact.component_sha256)
            try:
                _canonical_components(record, self.encoder.binding.image_identity)
            except (ValueError, TypeError, OverflowError):
                raise d.DiscoveryUnavailable() from None
            vectors.append(record)
        query_vector = self.encoder.encode(self.query, check=check)
        ranked = rank_semantic(query_vector, self.encoder.binding, tuple(vectors), check=check)
        by_id = {item['id']: item for item in found}
        check()
        return [dict(by_id[aid], semantic_score=score) for aid, score in ranked]


@dataclass(frozen=True)
class SemanticSearchRuntime:
    discovery: DiscoveryRuntime
    vector_root: Path
    encoder: LocalSemanticEncoder

    def __post_init__(self):
        if (type(self.discovery) is not DiscoveryRuntime or
                not isinstance(self.vector_root, Path) or not self.vector_root.is_absolute() or
                '..' in self.vector_root.parts or type(self.encoder) is not LocalSemanticEncoder or
                type(self.encoder.binding) is not JointSpaceBinding):
            raise ValueError('Explicit discovery, vector root and qualified local encoder required')

    @property
    def access(self):
        return self.discovery.access

    @property
    def budget(self):
        return self.discovery.budget

    def authorize(self, token, library):
        self.discovery.authorize(token, library)

    def call(self, operation, token, library, cancelled, values):
        # Authorization precedes query validation, metadata and provider I/O
        # for direct callers as well as the HTTP admission check.
        self.authorize(token, library)
        started = self.budget.clock()
        previous_clock = started
        def bounded_cancelled():
            nonlocal previous_clock
            current = self.budget.clock()
            if (not math.isfinite(started) or not math.isfinite(current) or current < previous_clock
                    or current - started > self.budget.search_seconds):
                raise d.DiscoveryUnavailable()
            previous_clock = current
            return cancelled()
        if bounded_cancelled():
            raise d.DiscoveryCancelled()
        d.require(operation == 'search')
        d.require(type(values) is dict and {'query', 'filters'} <= set(values)
                  and not set(values) - {'query', 'filters', 'binding', 'fingerprint', 'page', 'page_size'})
        query = d.text(values['query'], 512)
        d.require(not any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 for c in query))
        d.require(type(values.get('page_size', 20)) is int and 1 <= values.get('page_size', 20) <= 20)
        filters = values['filters']
        d.require(type(filters) is dict)
        d.require('media' not in filters or filters['media'] == ['image'])
        filters = {**filters, 'media': ['image']}
        with self.access.connection_factory() as connection:
            reader = SemanticSearchReads(AccessService(connection, clock=self.access.clock),
                self.discovery.provider, self.discovery.budget, vector_root=self.vector_root,
                encoder=self.encoder, query=query)
            binding = values.get('binding')
            if binding is None:
                # presentation intentionally omits the internal binding; use
                # the same authorized source read to obtain it directly.
                binding = reader._run(token, library, None,
                    lambda _index, _facts, context, _member, _check: context, bounded_cancelled)
            result = reader.search(token, library, binding=binding, filters=filters,
                page=values.get('page', 1), page_size=values.get('page_size', 20),
                fingerprint=values.get('fingerprint'), cancelled=bounded_cancelled)
            # A provider call can outlive a concurrent membership or source
            # change. Re-read in a fresh transaction before releasing cards.
            reader._run(token, library, result['binding'],
                lambda _index, _facts, _context, _member, _check: None, bounded_cancelled)
            result.update(filters=filters, semantic={'mode': 'text_to_image',
                'score_kind': 'cosine', 'candidate_count': reader._candidate_count,
                'coverage': 'complete_eligible_images', 'needs_review': True})
            return result
