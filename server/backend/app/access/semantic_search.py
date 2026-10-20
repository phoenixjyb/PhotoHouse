"""Opt-in text-to-image search over current, hard-filtered library images.

The ordinary assistant wire stays literal. This explicit pilot shares its
authorization, reviewed metadata and hard-filter implementation, then ranks a
complete bounded cohort using a separately qualified joint text/image space.
"""
from dataclasses import asdict, dataclass
import math
from pathlib import Path
import re

from . import discovery as d
from .assistant_search import AssistantSearchReads
from .discovery_transport import DiscoveryRuntime
from .semantic_encoder import JointSpaceBinding, LocalSemanticEncoder, SemanticUnsupported, rank_semantic
from .service import AccessDenied, AccessService
from .search_exclusions import EXCLUSION_POLICY_VERSION, requires_semantic_clarification
from .visual_candidates import MAX_CANDIDATES, VectorRecord, _canonical_components, canonical_vector_checksum
from .visual_vector_artifacts import identity_sha256
from .visual_vector_loader import _COLUMNS, _checked_root, _read_vector, _validated_rows
from .visual_vector_schema import verify_visual_vector_schema
from .semantic_streaming import SemanticServingLimits, VECTOR_BATCH_SIZE, MAX_VECTOR_READ_BYTES, rank_semantic_batches


def _valid_pilot_owner_account_id(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9._-]{1,128}', value, re.ASCII) is not None


class SemanticSearchReads(AssistantSearchReads):
    def __init__(self, access, provider, budget, *, vector_root, encoder, query,
                 server_snapshot=None, serving_limits=None):
        super().__init__(access, provider, budget)
        self.vector_root, self.encoder, self.query = vector_root, encoder, query
        self._vector_rows = ()
        self._source_hashes = {}
        self._candidate_count = 0
        self._server_snapshot = server_snapshot
        self.serving_limits = serving_limits
        self._vector_read_bytes = 0

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
        return {**extra, 'semantic_policy': (4 if self.serving_limits else 3),
                **({'serving_limits': asdict(self.serving_limits)} if self.serving_limits else {}),
                'exclusion_policy': EXCLUSION_POLICY_VERSION,
                'joint_space_binding': self.encoder.binding.binding_sha256,
                'semantic_query': d.digest(self.query), 'image_vector_records': rows,
                'image_source_hashes': hashes}

    def _artifacts(self, found):
        check = self._check
        check()
        self._candidate_count = len(found)
        if len(found) > (self.serving_limits.candidate_limit if self.serving_limits else MAX_CANDIDATES):
            raise d.DiscoveryUnavailable()
        if not found:
            return None, ()
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
        return root, tuple(records.values())

    def _charge_vector_bytes(self, amount):
        self._check()
        if type(amount) is not int or amount <= 0:
            raise d.DiscoveryUnavailable()
        self._vector_read_bytes += amount
        if self._vector_read_bytes > MAX_VECTOR_READ_BYTES:
            raise d.DiscoveryUnavailable()

    def _vector_records(self, root, records):
        check = self._check
        for artifact in records:
            aid = artifact.asset_id
            check()
            if artifact.source_sha256 != self._source_hashes.get(aid):
                raise d.DiscoveryUnavailable()
            vector = (_read_vector(root, artifact, charge=self._charge_vector_bytes)
                      if self.serving_limits else _read_vector(root, artifact))
            check()
            if vector is None or canonical_vector_checksum(vector) != artifact.component_sha256:
                raise d.DiscoveryUnavailable()
            record = VectorRecord(aid, self.encoder.binding.image_identity,
                                  vector, artifact.component_sha256)
            try:
                _canonical_components(record, self.encoder.binding.image_identity)
            except (ValueError, TypeError, OverflowError):
                raise d.DiscoveryUnavailable() from None
            yield record

    def _vectors(self, found):
        root, records = self._artifacts(found)
        return list(self._vector_records(root, records))

    def _rank(self, found):
        # _run has already checked membership, filters and the current source
        # binding. Refuse before opening vectors, encoding, or restoring scores.
        if requires_semantic_clarification(self.query):
            raise SemanticUnsupported()
        check = self._check
        if self.serving_limits is None:
            vectors = self._vectors(found)
            root, artifacts = None, ()
        else:
            root, artifacts = self._artifacts(found)
            # Complete file validation precedes inference. Never hide a corrupt
            # tail behind top-k or invoke the provider on an incomplete cohort.
            for _record in self._vector_records(root, artifacts):
                check()
            if artifacts:
                del _record
            vectors = None
        if self._server_snapshot is not None:
            # Only the private workspace's validated server-owned summary can
            # supply this snapshot. Neither public API accepts a ranking. A
            # recovery verifies the complete current vector cohort without
            # repeating the model call or inventing scores for later pages.
            by_id = {item['id']: item for item in found}
            snapshot = self._server_snapshot
            if (len(snapshot) != min(20, len(found)) or
                    len({aid for aid, _score in snapshot}) != len(snapshot) or
                    any(aid not in by_id for aid, _score in snapshot)):
                raise d.DiscoveryChanged()
            selected = {aid for aid, _score in snapshot}
            return ([dict(by_id[aid], semantic_score=score) for aid, score in snapshot] +
                    [by_id[aid] for aid in sorted(set(by_id) - selected, key=int)])
        if not found:
            return []
        query_vector = self.encoder.encode(self.query, check=check)
        if self.serving_limits is None:
            ranked = rank_semantic(query_vector, self.encoder.binding, tuple(vectors), check=check)
        else:
            def batches():
                batch = []
                for record in self._vector_records(root, artifacts):
                    batch.append(record)
                    if len(batch) == VECTOR_BATCH_SIZE:
                        yield tuple(batch)
                        batch = []
                if batch:
                    yield tuple(batch)
            ranked = rank_semantic_batches(query_vector, self.encoder.binding, batches(),
                expected_count=len(found), candidate_limit=self.serving_limits.candidate_limit, check=check)
        by_id = {item['id']: item for item in found}
        check()
        return [dict(by_id[aid], semantic_score=score) for aid, score in ranked]


@dataclass(frozen=True)
class SemanticSearchRuntime:
    discovery: DiscoveryRuntime
    vector_root: Path
    encoder: LocalSemanticEncoder
    pilot_owner_account_id: str | None = None
    serving_limits: SemanticServingLimits | None = None

    def __post_init__(self):
        if (type(self.discovery) is not DiscoveryRuntime or
                not isinstance(self.vector_root, Path) or not self.vector_root.is_absolute() or
                '..' in self.vector_root.parts or type(self.encoder) is not LocalSemanticEncoder or
                type(self.encoder.binding) is not JointSpaceBinding):
            raise ValueError('Explicit discovery, vector root and qualified local encoder required')
        if (self.pilot_owner_account_id is not None and
                not _valid_pilot_owner_account_id(self.pilot_owner_account_id)):
            raise ValueError('Safe pilot owner account identifier required')
        if self.encoder.binding.image_identity.dimension == 768 and self.pilot_owner_account_id is None:
            raise ValueError('A pilot owner account is required for 768-dimensional semantic search')
        if self.serving_limits is not None and (type(self.serving_limits) is not SemanticServingLimits
                or self.pilot_owner_account_id is None):
            raise ValueError('Explicit serving limits require an exact pilot owner')

    @property
    def access(self):
        return self.discovery.access

    @property
    def budget(self):
        return (self.serving_limits.budget(self.discovery.budget)
                if self.serving_limits else self.discovery.budget)

    def authorize(self, token, library):
        if self.pilot_owner_account_id is None:
            self.discovery.authorize(token, library)
            return
        with self.access.connection_factory() as connection:
            access = AccessService(connection, clock=self.access.clock)
            with access._transaction():
                principal = access._require(token, library, 'library.members.manage')
                if principal['account_id'] != self.pilot_owner_account_id:
                    raise AccessDenied('Access denied')

    def call(self, operation, token, library, cancelled, values):
        return self._call(operation, token, library, cancelled, values)

    def _restore_server_snapshot(self, token, library, cancelled, values, snapshot):
        """Internal first-page recovery from trusted workspace state, not wire input."""
        d.require(type(snapshot) is tuple and values.get('page', 1) == 1
                  and values.get('page_size', 20) == 20)
        return self._call('search', token, library, cancelled, values, server_snapshot=snapshot)

    def _call(self, operation, token, library, cancelled, values, *, server_snapshot=None):
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
                self.discovery.provider, self.budget, vector_root=self.vector_root,
                encoder=self.encoder, query=query, server_snapshot=server_snapshot,
                serving_limits=self.serving_limits)
            binding = values.get('binding')
            if binding is None:
                # presentation intentionally omits the internal binding; use
                # the same authorized source read to obtain it directly.
                binding = reader._run(token, library, None,
                    lambda _index, _facts, context, _member, _check: context, bounded_cancelled)
            try:
                result = reader.search(token, library, binding=binding, filters=filters,
                    page=values.get('page', 1), page_size=values.get('page_size', 20),
                    fingerprint=values.get('fingerprint'), cancelled=bounded_cancelled)
            except SemanticUnsupported:
                # A refusal is meaningful only while this authorized cohort is
                # still current. Re-read after the provider transaction unwinds.
                reader._run(token, library, binding,
                    lambda _index, _facts, _context, _member, _check: None, bounded_cancelled)
                raise d.DiscoveryQueryUnsupported() from None
            # A provider call can outlive a concurrent membership or source
            # change. Re-read in a fresh transaction before releasing cards.
            reader._run(token, library, result['binding'],
                lambda _index, _facts, _context, _member, _check: None, bounded_cancelled)
            # The encoder runs outside the access transaction. Re-authorize the
            # configured principal and owner role after it completes, including
            # first-page recovery from a server-owned ranking snapshot.
            self.authorize(token, library)
            result.update(filters=filters, semantic={'mode': 'text_to_image',
                'score_kind': 'cosine', 'candidate_count': reader._candidate_count,
                'coverage': 'complete_eligible_images', 'needs_review': True})
            return result
