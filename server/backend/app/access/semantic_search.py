"""Opt-in text-to-image search over current, hard-filtered library images.

The ordinary assistant wire stays literal. This explicit pilot shares its
authorization, reviewed metadata and hard-filter implementation, then ranks a
complete bounded cohort using a separately qualified joint text/image space.
"""
from dataclasses import asdict, dataclass
import hashlib
import math
import operator
from pathlib import Path
import re

from . import discovery as d
from .assistant_search import AssistantSearchReads
from .discovery_transport import DiscoveryRuntime
from .semantic_encoder import JointSpaceBinding, LocalSemanticEncoder, SemanticUnsupported, TextVector, rank_semantic
from .service import AccessDenied, AccessService
from .search_exclusions import EXCLUSION_POLICY_VERSION, requires_semantic_clarification
from .visual_candidates import MAX_CANDIDATES, VectorRecord, _canonical_components
from .visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256
from .visual_vector_loader import _COLUMNS, _checked_root, _read_vector, _validated_rows
from .visual_vector_schema import verify_visual_vector_schema
from .semantic_streaming import SemanticServingLimits, VECTOR_BATCH_SIZE, MAX_VECTOR_READ_BYTES, rank_semantic_batches
from .semantic_bulk_vectors import BulkVectorStore, BulkVectorUnavailable
from .semantic_eligibility import SemanticEligibilityStore, SemanticEligibilityUnavailable
from .semantic_request_snapshot import NativeSnapshotDatabase, create_request_source_snapshot


# The policy is reread on each source pass; an unbound first page derives its
# binding in the ranking pass and keeps the final fresh source check.
# Keep its private-file budget separate from the vector payload allowance.
MAX_POLICY_READ_BYTES = 64 * 1024 * 1024
SCORE_PRESENTATION_POLICY_VERSION = 1
_SCORE_PRESENTATION_ROUNDOFF = 16 * math.ulp(1.0)
_ARTIFACT_FIELDS = tuple(_COLUMNS.split(','))
_ARTIFACT_GETTER = operator.attrgetter(*_ARTIFACT_FIELDS)


def _present_semantic_score(score):
    """Bound only binary64 endpoint roundoff after ranking has completed."""
    if type(score) not in (int, float):
        raise d.DiscoveryUnavailable()
    try:
        if (not math.isfinite(score) or score < -1.0 - _SCORE_PRESENTATION_ROUNDOFF
                or score > 1.0 + _SCORE_PRESENTATION_ROUNDOFF):
            raise d.DiscoveryUnavailable()
    except (OverflowError, TypeError, ValueError):
        raise d.DiscoveryUnavailable() from None
    if score > 1.0:
        return 1.0
    if score < -1.0:
        return -1.0
    return score


def _typed_row_equal(current, previous):
    """Compare one SQL row without Python's bool/int equality aliasing."""
    return (type(current) is tuple and type(previous) is tuple
            and len(current) == len(previous)
            and all(type(left) is type(right) and left == right
                    for left, right in zip(current, previous)))


def _typed_rows_equal(rows, previous_rows, check):
    """Check a fresh ordered SQL cohort against one immutable prior snapshot."""
    if (type(rows) is not list or type(previous_rows) is not tuple
            or len(rows) != len(previous_rows)):
        return False
    for row, previous in zip(rows, previous_rows):
        check()
        if not _typed_row_equal(row, previous):
            return False
    return True


def _freeze_rows(rows, check):
    """Keep one ordered primitive snapshot, checking cancellation per row."""
    frozen = []
    for row in rows:
        check()
        frozen.append(tuple(row))
    return tuple(frozen)


def _freeze_artifacts(records, check):
    """Copy validated artifact fields into immutable, primitive-only tuples."""
    frozen = []
    for asset_id, record in records.items():
        check()
        frozen.append((asset_id, _ARTIFACT_GETTER(record)))
    return tuple(frozen)


def _thaw_artifacts(frozen_records, check):
    """Rebuild a private mapping; cached mutable dataclass instances are never reused."""
    records = {}
    for asset_id, values in frozen_records:
        check()
        if type(asset_id) is not str or type(values) is not tuple or len(values) != 16:
            return None
        record = ImmutableVectorArtifact(*values)
        if record.asset_id != asset_id or asset_id in records:
            return None
        records[asset_id] = record
    return records


def _valid_pilot_owner_account_id(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9._-]{1,128}', value, re.ASCII) is not None


class SemanticSearchReads(AssistantSearchReads):
    def __init__(self, access, provider, budget, *, vector_root, encoder, query,
                 server_snapshot=None, serving_limits=None, bulk_vectors=None, eligibility=None,
                 text_projection_required=True, media_only_facts=False):
        # This reader belongs to exactly one runtime call. Reuse derived facts
        # for an identical opaque binding during that call, while every _run
        # still reauthorizes and reads/validates the complete current source.
        # Never share this cache between readers, queries or requests.
        super().__init__(access, provider, budget, facts_cache={},
                         text_projection_required=text_projection_required)
        if type(media_only_facts) is not bool:
            raise d.DiscoveryInvalid()
        self._media_only_facts = media_only_facts
        self.vector_root, self.encoder, self.query = vector_root, encoder, query
        self._vector_rows = ()
        self._source_hashes = {}
        self._candidate_count = 0
        self._server_snapshot = server_snapshot
        self.serving_limits = serving_limits
        self.bulk_vectors = bulk_vectors
        self._bulk_artifacts = ()
        self._library_id = None
        self._vector_read_bytes = 0
        self.eligibility = eligibility
        self._eligibility_policy = None
        self._policy_read_bytes = 0
        self._matched_omitted_count = 0
        self._eligibility_bulk_generation = None
        self._eligibility_records_cache = None

    def _facts(self, index, source, people, places, check):
        """Build the minimal facts visible to an exact image-only query.

        Fresh reads and source binding have already completed. Keep asset
        conversion and reviewed-face/allow_zero checks, plus a poll for every
        indexed row. The semantic search action accepts absent rows and empty
        facets when its only filter is media.
        """
        if type(self._media_only_facts) is not bool:
            raise d.DiscoveryUnavailable()
        if not self._media_only_facts:
            return super()._facts(index, source, people, places, check)
        if self._text_projection_required is not False:
            raise d.DiscoveryUnavailable()

        assets = {}
        for row in source['assets']:
            check()
            fields = list(row[:6])
            try:
                d.text(fields[1], 256)
            except d.DiscoveryInvalid:
                fields[1] = None
            if d.taken_day(fields[5]) is None:
                fields[5] = None
            assets[str(row[0])] = d._asset(fields, index.library_id)

        faces = {str(row[0]): (str(row[1]), str(row[2]), row[3])
                 for row in source['faces']}
        approved = set()
        for assignment in index.assignments:
            check()
            if faces.get(assignment.id) != (
                    assignment.asset_id, assignment.person_id, assignment.source):
                raise d.DiscoveryChanged()
            approved.add(assignment.person_id)
        if any(person_id not in approved and not person.allow_zero
               for person_id, person in people.items()):
            raise d.DiscoveryUnavailable()

        for _asset_id in index.indexed_ids:
            check()
        return assets, {}, {'people': [], 'locations': [], 'tags': []}, {}

    def _search_action(self, library, binding, filters, page=1, page_size=50,
                       fingerprint=None, *, allow_unbound_first_page=False,
                       binding_observer=None):
        if type(self._media_only_facts) is not bool:
            raise d.DiscoveryUnavailable()
        if self._media_only_facts and not (
                type(filters) is dict and set(filters) == {'media'}
                and type(filters['media']) is list
                and filters['media'] == ['image']):
            raise d.DiscoveryUnavailable()
        return super()._search_action(
            library, binding, filters, page, page_size, fingerprint,
            allow_unbound_first_page=allow_unbound_first_page,
            binding_observer=binding_observer)

    def _extra_source(self, index, source, read, check):
        # A new generation belongs only to this exact fresh source read. Clear
        # it before any work so a failed read or policy check cannot leave an
        # earlier cohort available to _artifacts.
        self._eligibility_bulk_generation = None
        self._eligibility_policy = None
        self._bulk_artifacts = ()
        self._vector_rows = ()
        self._source_hashes = {}
        self._library_id = None
        try:
            return self._extra_source_fresh(index, source, read, check)
        except BaseException:
            self._eligibility_bulk_generation = None
            self._eligibility_policy = None
            self._eligibility_records_cache = None
            self._bulk_artifacts = ()
            self._vector_rows = ()
            self._source_hashes = {}
            self._library_id = None
            raise

    def _extra_source_fresh(self, index, source, read, check):
        extra = super()._extra_source(index, source, read, check)
        check()
        if not verify_visual_vector_schema(self.access.db):
            raise d.DiscoveryUnavailable()
        image_identity = self.encoder.binding.image_identity
        image_identity_digest = identity_sha256(image_identity)
        # Metadata participates in the same opaque source binding. Current
        # library scope and active status apply before any vector file is read.
        columns = ','.join('v.' + column for column in _COLUMNS.split(','))
        rows = read(f'''SELECT {columns} FROM image_vector_artifacts v
            JOIN assets a ON a.id=v.asset_id
            JOIN access_asset_libraries m ON m.asset_id=a.id
            WHERE m.library_id=? AND (a.status IS NULL OR a.status='active')
            AND a.mime GLOB 'image/*' AND v.status='ready' AND v.identity_sha256=?
            ORDER BY v.asset_id,v.record_id''', (index.library_id, image_identity_digest))
        hashes = read('''SELECT a.id,a.hash_sha256 FROM assets a
            JOIN access_asset_libraries m ON m.asset_id=a.id WHERE m.library_id=?
            AND (a.status IS NULL OR a.status='active') AND a.mime GLOB 'image/*'
            ORDER BY a.id''', (index.library_id,))
        self._vector_rows = rows
        self._library_id = index.library_id
        self._source_hashes = {str(aid): digest for aid, digest in hashes}
        if self.eligibility is not None:
            snapshot = None
            frozen_records = None
            if self.bulk_vectors is not None:
                cache = self._eligibility_records_cache
                cache_matches = (cache is not None and cache[0] == image_identity_digest
                                 and cache[1] == index.library_id
                                 and _typed_rows_equal(rows, cache[2], check))
                if cache_matches:
                    snapshot = cache[2]
                    frozen_records = cache[3]
                    records = _thaw_artifacts(frozen_records, check)
                    if records is None:
                        raise d.DiscoveryUnavailable()
                else:
                    snapshot = _freeze_rows(rows, check)
                    if self.bulk_vectors is not None:
                        try:
                            records = self.bulk_vectors._artifacts_from_current_sql(
                                snapshot, library_id=index.library_id,
                                identity=image_identity, check=check,
                            )
                        except BulkVectorUnavailable:
                            raise d.DiscoveryUnavailable() from None
                    else:
                        records = None
                    if records is None:
                        records = _validated_rows(rows, image_identity)
                    if len(records) != len(rows):
                        raise d.DiscoveryUnavailable()
                    # Capture only primitive values before passing artifact
                    # instances to policy validation or other callbacks.
                    frozen_records = _freeze_artifacts(records, check)
            else:
                records = _validated_rows(rows, image_identity)
                if len(records) != len(rows):
                    raise d.DiscoveryUnavailable()
            try:
                self._eligibility_policy = self.eligibility.read_and_validate(
                    self._source_hashes, records, library_id=index.library_id,
                    check=check, charge=self._charge_policy_bytes)
            except SemanticEligibilityUnavailable:
                raise d.DiscoveryUnavailable() from None
            if self.bulk_vectors is not None:
                # Only fresh SQL rows, current identity, and this library scope
                # select the immutable parsed values. Policy/source checks above
                # still run for every pass before this cache is refreshed.
                self._eligibility_records_cache = (
                    image_identity_digest, index.library_id, snapshot, frozen_records)
            self._bulk_artifacts = tuple(sorted(records.values(), key=lambda item: int(item.asset_id)))
            if self.bulk_vectors is not None:
                self._eligibility_bulk_generation = (
                    image_identity_digest, snapshot, records)
        return {**extra, 'semantic_policy': (6 if self.eligibility else 5 if self.bulk_vectors else 4 if self.serving_limits else 3),
                **({'semantic_eligibility': self.eligibility.descriptor} if self.eligibility else {}),
                **({'bulk_vectors': self.bulk_vectors.descriptor} if self.bulk_vectors else {}),
                **({'serving_limits': asdict(self.serving_limits)} if self.serving_limits else {}),
                'exclusion_policy': EXCLUSION_POLICY_VERSION,
                'score_presentation_policy': SCORE_PRESENTATION_POLICY_VERSION,
                'joint_space_binding': self.encoder.binding.binding_sha256,
                'semantic_query': d.digest(self.query), 'image_vector_records': rows,
                'image_source_hashes': hashes}

    def _charge_policy_bytes(self, amount):
        self._check()
        if type(amount) is not int or amount <= 0:
            raise d.DiscoveryUnavailable()
        self._policy_read_bytes += amount
        if self._policy_read_bytes > MAX_POLICY_READ_BYTES:
            raise d.DiscoveryUnavailable()

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
        generation = self._eligibility_bulk_generation
        generation_matches = generation is not None
        if generation_matches:
            try:
                current_identity = identity_sha256(self.encoder.binding.image_identity)
            except (ValueError, TypeError, AttributeError):
                raise d.DiscoveryUnavailable() from None
            if generation[0] != current_identity:
                raise d.DiscoveryUnavailable()
        if generation_matches and len(generation[1]) != len(self._vector_rows):
            generation_matches = False
        for position, row in enumerate(self._vector_rows):
            check()
            if self.bulk_vectors is not None or str(row[1]) in ids:
                selected.append(row)
                if generation_matches and (
                        position >= len(generation[1])
                        or not _typed_row_equal(tuple(row), generation[1][position])):
                    generation_matches = False
        if generation is not None and not generation_matches:
            # A cache miss means the rows or identity no longer match the
            # generation whose complete eligibility partition was checked.
            # Do not pair fresh rows with that older partition.
            raise d.DiscoveryUnavailable()
        records = (generation[2] if generation_matches else
                   _validated_rows(selected, self.encoder.binding.image_identity))
        if self.bulk_vectors is not None:
            # The explicit bulk artifact is authoritative for this complete
            # current library cohort. Old individual NPYs are build provenance.
            # Match every ready row and current source hash, even for a filter
            # that will score only a subset. No scope is inferred from the file.
            if (len(records) != len(selected) or not ids <= set(records)
                    or any(artifact.source_sha256 != self._source_hashes.get(aid)
                           for aid, artifact in records.items())):
                raise d.DiscoveryUnavailable()
            self._bulk_artifacts = tuple(sorted(records.values(), key=lambda item: int(item.asset_id)))
            return None, tuple(records[aid] for aid in sorted(ids, key=int))
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

    def _vector_records(self, root, records, *, validate_components=True):
        check = self._check
        for artifact in records:
            aid = artifact.asset_id
            check()
            if artifact.source_sha256 != self._source_hashes.get(aid):
                raise d.DiscoveryUnavailable()
            vector = (_read_vector(root, artifact, charge=self._charge_vector_bytes)
                      if self.serving_limits else _read_vector(root, artifact))
            check()
            if vector is None:
                raise d.DiscoveryUnavailable()
            record = VectorRecord(aid, self.encoder.binding.image_identity,
                                  vector, artifact.component_sha256)
            if validate_components:
                try:
                    _canonical_components(record, self.encoder.binding.image_identity)
                except (ValueError, TypeError, OverflowError):
                    raise d.DiscoveryUnavailable() from None
            yield record

    def _vectors(self, found):
        root, records = self._artifacts(found)
        return list(self._vector_records(root, records))

    def _bulk_snapshot(self):
        try:
            return self.bulk_vectors.snapshot(self._bulk_artifacts,
                library_id=self._library_id, check=self._check,
                charge=self._charge_vector_bytes)
        except BulkVectorUnavailable:
            raise d.DiscoveryUnavailable() from None

    def _rank(self, found):
        # _run has already checked membership, filters and the current source
        # binding. Refuse before opening vectors, encoding, or restoring scores.
        if requires_semantic_clarification(self.query):
            raise SemanticUnsupported()
        check = self._check
        bulk_snapshot = None
        if self._eligibility_policy is not None:
            self._matched_omitted_count = sum(
                item['id'] in self._eligibility_policy.omitted_ids for item in found)
            found = [item for item in found if item['id'] in self._eligibility_policy.eligible_ids]
        if self.bulk_vectors is not None:
            root, artifacts = self._artifacts(found)
            if artifacts or self.eligibility is not None:
                bulk_snapshot = self._bulk_snapshot()
            vectors = None
        elif self.serving_limits is None:
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
            return ([dict(by_id[aid], semantic_score=_present_semantic_score(score))
                     for aid, score in snapshot] +
                    [by_id[aid] for aid in sorted(set(by_id) - selected, key=int)])
        if not found:
            return []
        query_vector = self.encoder.encode(self.query, check=check)
        if self.bulk_vectors is not None:
            # Read/hash the pinned container again after provider execution.
            # Reusing canonical immutable bytes never bypasses current files.
            bulk_snapshot = self._bulk_snapshot()
            try:
                if (type(query_vector) is not TextVector
                        or query_vector.binding_sha256 != self.encoder.binding.binding_sha256
                        or query_vector.query_sha256 != hashlib.sha256(self.query.encode('utf-8')).hexdigest()):
                    raise ValueError('invalid_query_vector')
                query = _canonical_components(VectorRecord('1',
                    self.encoder.binding.text_identity, query_vector.vector,
                    query_vector.checksum_sha256), self.encoder.binding.text_identity)
            except (TypeError, ValueError, OverflowError):
                raise d.DiscoveryUnavailable() from None
            try:
                ranked = bulk_snapshot.rank(query,
                    tuple(artifact.asset_id for artifact in artifacts), check=check)
            except BulkVectorUnavailable:
                raise d.DiscoveryUnavailable() from None
        elif self.serving_limits is None:
            ranked = rank_semantic(query_vector, self.encoder.binding, tuple(vectors), check=check)
        else:
            def batches():
                batch = []
                # The ranker performs component checksum/norm validation for
                # every freshly re-read record. Retain the pre-inference pass
                # above without duplicating the ranker's second-pass work.
                for record in self._vector_records(root, artifacts, validate_components=False):
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
        return [dict(by_id[aid], semantic_score=_present_semantic_score(score))
                for aid, score in ranked]


@dataclass(frozen=True)
class SemanticSearchRuntime:
    discovery: DiscoveryRuntime
    vector_root: Path
    encoder: LocalSemanticEncoder
    pilot_owner_account_id: str | None = None
    serving_limits: SemanticServingLimits | None = None
    bulk_vectors: BulkVectorStore | None = None
    eligibility: SemanticEligibilityStore | None = None
    request_source_snapshot: bool = False

    def __post_init__(self):
        if type(self.request_source_snapshot) is not bool:
            raise ValueError('Explicit request snapshot flag required')
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
        if self.bulk_vectors is not None and (type(self.bulk_vectors) is not BulkVectorStore
                or self.serving_limits is None
                or self.bulk_vectors.identity != self.encoder.binding.image_identity):
            raise ValueError('Bulk vectors require explicit owner limits and matching image identity')
        if self.eligibility is not None and (type(self.eligibility) is not SemanticEligibilityStore
                or self.bulk_vectors is None
                or self.eligibility.library_id != self.bulk_vectors.library_id
                or self.eligibility.binding_sha256 != self.encoder.binding.binding_sha256
                or self.eligibility.bulk_sha256 != self.bulk_vectors.file_sha256):
            raise ValueError('Eligibility requires the exact owner bulk runtime and joint binding')

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
        # Keep one request-local limits view; repeated row checks must not copy
        # it. The view retains the discovery runtime's admission semaphore.
        budget = self.budget
        started = budget.clock()
        previous_clock = started
        def bounded_cancelled():
            nonlocal previous_clock
            current = budget.clock()
            if (not math.isfinite(started) or not math.isfinite(current) or current < previous_clock
                    or current - started > budget.search_seconds):
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
        supplied_filters = values['filters']
        d.require(type(supplied_filters) is dict)
        d.require('media' not in supplied_filters or supplied_filters['media'] == ['image'])
        filters = {**supplied_filters, 'media': ['image']}
        media_only_facts = (set(filters) == {'media'}
                            and type(filters['media']) is list
                            and filters['media'] == ['image'])
        snapshot = None
        factory = self.access.connection_factory
        from .runtime import ExistingDatabase
        snapshot_factory = None
        if self.request_source_snapshot and type(factory) is ExistingDatabase:
            snapshot = create_request_source_snapshot(library)
            snapshot_factory = factory.source_snapshot
        elif self.request_source_snapshot and type(factory) is NativeSnapshotDatabase:
            snapshot = create_request_source_snapshot(library)
            snapshot_factory = factory
        connection_context = snapshot_factory() if snapshot_factory is not None else factory()
        try:
            with connection_context as connection:
                if snapshot is not None:
                    snapshot.bind(connection)
                    budget = budget.with_request_source_snapshot(snapshot)
                reader = SemanticSearchReads(AccessService(connection, clock=self.access.clock),
                    self.discovery.provider, budget, vector_root=self.vector_root,
                    encoder=self.encoder, query=query, server_snapshot=server_snapshot,
                    serving_limits=self.serving_limits, bulk_vectors=self.bulk_vectors,
                    eligibility=self.eligibility,
                    text_projection_required=('text' in filters or 'descriptive' in filters),
                    media_only_facts=media_only_facts)
                binding = values.get('binding')
                page = values.get('page', 1)
                page_size = values.get('page_size', 20)
                fingerprint = values.get('fingerprint')
                unbound_first_page = (binding is None and type(page) is int and page == 1
                                      and fingerprint is None and server_snapshot is None)
                ranking_binding = None

                def observe_binding(context):
                    nonlocal ranking_binding
                    ranking_binding = context

                def validate_final(expected_binding):
                    if snapshot is not None:
                        snapshot.request_final_replay()
                    try:
                        reader._run(token, library, expected_binding,
                            lambda _index, _facts, _context, _member, _check: None,
                            bounded_cancelled)
                    except Exception:
                        if snapshot is None or not snapshot.consume_fallback_required():
                            raise
                        bounded_cancelled()
                        snapshot.stop_final_replay()
                        reader._run(token, library, expected_binding,
                            lambda _index, _facts, _context, _member, _check: None,
                            bounded_cancelled)
                    else:
                        if snapshot is not None and snapshot.consume_fallback_required():
                            snapshot.stop_final_replay()
                            reader._run(token, library, expected_binding,
                                lambda _index, _facts, _context, _member, _check: None,
                                bounded_cancelled)
                    finally:
                        if snapshot is not None:
                            snapshot.stop_final_replay()

                if binding is None and not unbound_first_page:
                    # presentation intentionally omits the internal binding; use
                    # an authorized source read to obtain it before pagination,
                    # fingerprint validation, or server-owned recovery.
                    binding = reader._run(token, library, None,
                        lambda _index, _facts, context, _member, _check: context, bounded_cancelled)
                try:
                    if unbound_first_page:
                        action = reader._search_action(library, None, filters, page, page_size,
                            fingerprint, allow_unbound_first_page=True,
                            binding_observer=observe_binding)
                        result = reader._run(token, library, None, action, bounded_cancelled)
                    else:
                        result = reader.search(token, library, binding=binding, filters=filters,
                            page=page, page_size=page_size, fingerprint=fingerprint,
                            cancelled=bounded_cancelled)
                except SemanticUnsupported:
                    # A refusal is meaningful only while this authorized cohort is
                    # still current. Re-read after the provider transaction unwinds.
                    expected_binding = ranking_binding if unbound_first_page else binding
                    if expected_binding is None:
                        raise d.DiscoveryUnavailable() from None
                    validate_final(expected_binding)
                    raise d.DiscoveryQueryUnsupported() from None
                # A provider call can outlive a concurrent membership or source
                # change. Re-read in a fresh transaction before releasing cards.
                validate_final(result['binding'])
                # The ranking transaction, including any encoder call, has committed.
                # Re-authorize the configured principal and owner role before release,
                # including first-page recovery from a server-owned ranking snapshot.
                self.authorize(token, library)
                result.update(filters=filters, semantic={'mode': 'text_to_image',
                    'score_kind': 'cosine', 'candidate_count': reader._candidate_count,
                    'coverage': 'complete_eligible_images', 'needs_review': True})
                if reader._eligibility_policy is not None:
                    result['semantic']['coverage_details'] = reader._eligibility_policy.coverage(
                        reader._matched_omitted_count)
                return result
        finally:
            if snapshot is not None:
                snapshot.close()
