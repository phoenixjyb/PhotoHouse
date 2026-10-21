"""Private, opt-in timing observer for semantic runtime requests.

The observer patches only existing Python methods while its context is active.
It emits fixed phase names and numeric aggregates; request inputs, identifiers,
paths, provider payloads, SQL, exceptions and results are never retained.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import time


_PHASES = (
    "runtime_total", "authorization", "source_binding", "source_sql",
    "source_extra", "prepared_facts", "artifacts", "bulk_snapshot",
    "eligibility_validation", "canonical_hash", "encoder_roundtrip", "rank",
)
_MAX_REQUESTS = 256
_ACTIVE = ContextVar("semantic_request_profile_active", default=None)
_PATCH_LOCK = threading.Lock()

# source_sql measures the whole bounded read callback, including cancellation
# and budget checks, cursor fetching, row packing, and accounting. It is not an
# SQLite-engine-only duration.


class RequestObserver:
    """Thread-safe, bounded numeric measurements for one harness context."""

    def __init__(self):
        self._lock = threading.Lock()
        self._requests = []
        self._dropped = 0
        self._aggregate = {name: _empty_phase() for name in _PHASES}

    @property
    def request_count(self):
        """Total runtime calls seen, including calls beyond the sample cap."""
        with self._lock:
            return len(self._requests) + self._dropped

    def _start_request(self):
        with self._lock:
            if len(self._requests) >= _MAX_REQUESTS:
                self._dropped += 1
                return None
            request = {"phases": {name: _empty_phase() for name in _PHASES},
                       "total_ms": 0.0}
            self._requests.append(request)
            return request

    def _record(self, request, phase, elapsed_ns, error):
        elapsed_ms = max(0.0, elapsed_ns / 1_000_000)
        with self._lock:
            for target in (self._aggregate[phase], request["phases"][phase]):
                target["calls"] += 1
                target["inclusive_ms"] += elapsed_ms
                target["max_ms"] = max(target["max_ms"], elapsed_ms)
                target["errors"] += int(error)

    def _record_total(self, request, elapsed_ns, exclusive_ns, error):
        elapsed_ms = max(0.0, elapsed_ns / 1_000_000)
        with self._lock:
            request["total_ms"] = elapsed_ms
            phase = self._aggregate["runtime_total"]
            local = request["phases"]["runtime_total"]
            for target in (phase, local):
                target["calls"] += 1
                target["inclusive_ms"] += elapsed_ms
                target["exclusive_ms"] += max(0, exclusive_ns) / 1_000_000
                target["max_ms"] = max(target["max_ms"], elapsed_ms)
                target["errors"] += int(error)

    def _record_exclusive(self, request, phase, elapsed_ms):
        with self._lock:
            self._aggregate[phase]["exclusive_ms"] += elapsed_ms
            request["phases"][phase]["exclusive_ms"] += elapsed_ms

    def snapshot(self):
        """Return a detached JSON-safe report containing numeric fields only."""
        with self._lock:
            return {
                "schema": "photohouse.semantic_request_profile.v1",
                "diagnostic_only": True,
                "phases": {name: dict(values) for name, values in self._aggregate.items()},
                "requests": [
                    {"ordinal": ordinal,
                     "total_ms": record["total_ms"],
                     "phases": {name: dict(values) for name, values in record["phases"].items()}}
                    for ordinal, record in enumerate(self._requests, 1)
                ],
                "dropped_requests": self._dropped,
                "max_requests": _MAX_REQUESTS,
                "timings_are_nested": True,
                "observer_overhead_included": True,
                "transport_outside_runtime": True,
            }


def _empty_phase():
    return {"calls": 0, "inclusive_ms": 0.0, "exclusive_ms": 0.0,
            "max_ms": 0.0, "errors": 0}


def _safe_clock(clock):
    lock = threading.Lock()
    last = [None]

    def read():
        try:
            value = clock()
            if type(value) is not int:
                raise ValueError("clock must return integer nanoseconds")
        except BaseException:
            value = time.perf_counter_ns()
        with lock:
            if last[0] is not None and value < last[0]:
                value = last[0]
            last[0] = value
            return value
    return read


@contextmanager
def _span(phase):
    request = _ACTIVE.get()
    if request is None:
        yield
        return
    start = request.clock()
    frame = [phase, start, 0]
    request.stack.append(frame)
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        end = request.clock()
        elapsed = max(0, end - start)
        request.stack.pop()
        if request.stack:
            request.stack[-1][2] += elapsed
        request.observer._record(request.record, phase, elapsed, failed)
        exclusive = max(0, elapsed - frame[2]) / 1_000_000
        request.observer._record_exclusive(request.record, phase, exclusive)


def _span_wrapper(phase, function):
    def wrapped(self, *args, **kwargs):
        with _span(phase):
            return function(self, *args, **kwargs)
    wrapped.__name__ = getattr(function, "__name__", "profiled")
    wrapped.__doc__ = getattr(function, "__doc__", None)
    wrapped.__qualname__ = getattr(function, "__qualname__", wrapped.__name__)
    return wrapped


@contextmanager
def instrument_requests(*, clock=time.perf_counter_ns):
    """Patch semantic request phases for a private harness context.

    Only one instrumented context may patch the process at a time. Nested or
    overlapping contexts fail before changing any method. Calls beyond the
    256-request bound run normally and increment ``dropped_requests``.
    """
    observer = RequestObserver()
    if not callable(clock):
        raise ValueError("clock must be callable")
    clock = _safe_clock(clock)
    if not _PATCH_LOCK.acquire(blocking=False):
        raise ValueError("semantic request profiling is already active")
    patches = []

    def install(owner, name, replacement):
        descriptor = owner.__dict__.get(name, _MISSING)
        original = getattr(owner, name)
        wrapped = replacement(original)
        setattr(owner, name, wrapped)
        patches.append((owner, name, descriptor))

    def restore():
        for owner, name, descriptor in reversed(patches):
            if descriptor is _MISSING:
                delattr(owner, name)
            else:
                setattr(owner, name, descriptor)

    try:
        # Imports are intentionally inside the opt-in context. Importing this
        # module alone does not initialize a model, read files, or open sockets.
        from app.access import discovery as discovery_module
        from app.access.discovery import DiscoveryReads, ReadBudget
        from app.access.semantic_encoder import LocalSemanticEncoder
        from app.access.semantic_eligibility import SemanticEligibilityStore
        from app.access.semantic_search import SemanticSearchReads, SemanticSearchRuntime

        def profiled_call(original_call):
            def profiled(runtime, *args, **kwargs):
                if _ACTIVE.get() is not None:
                    with _span("runtime_total"):
                        return original_call(runtime, *args, **kwargs)
                record = observer._start_request()
                if record is None:
                    return original_call(runtime, *args, **kwargs)
                request = _RequestState(observer, record, clock)
                token = _ACTIVE.set(request)
                start = clock()
                root_frame = ["runtime_total", start, 0]
                request.stack.append(root_frame)
                failed = False
                try:
                    return original_call(runtime, *args, **kwargs)
                except BaseException:
                    failed = True
                    raise
                finally:
                    elapsed = max(0, clock() - start)
                    request.stack.pop()
                    observer._record_total(record, elapsed, elapsed - root_frame[2], failed)
                    _ACTIVE.reset(token)
            return profiled

        install(SemanticSearchRuntime, "_call", profiled_call)

        for owner, name, phase in (
            (SemanticSearchRuntime, "authorize", "authorization"),
            (DiscoveryReads, "_run", "source_binding"),
            (SemanticSearchReads, "_extra_source", "source_extra"),
            (SemanticSearchReads, "_prepared_facts", "prepared_facts"),
            (SemanticSearchReads, "_artifacts", "artifacts"),
            (SemanticSearchReads, "_bulk_snapshot", "bulk_snapshot"),
            (SemanticSearchReads, "_rank", "rank"),
            (discovery_module, "digest", "canonical_hash"),
            (LocalSemanticEncoder, "encode", "encoder_roundtrip"),
            (SemanticEligibilityStore, "read_and_validate", "eligibility_validation"),
        ):
            def wrap(original):
                if owner is DiscoveryReads:
                    profiled = _span_wrapper(phase, original)
                    def guarded(instance, *args, **kwargs):
                        if isinstance(instance, SemanticSearchReads):
                            return profiled(instance, *args, **kwargs)
                        return original(instance, *args, **kwargs)
                    return guarded
                return _span_wrapper(phase, original)

            install(owner, name, wrap)

        def wrap_attempt(original):
            @contextmanager
            def profiled_attempt(budget, *args, **kwargs):
                with original(budget, *args, **kwargs) as (check, read):
                    def profiled_read(*read_args, **read_kwargs):
                        with _span("source_sql"):
                            return read(*read_args, **read_kwargs)
                    yield check, profiled_read
            return profiled_attempt

        install(ReadBudget, "attempt", wrap_attempt)
        yield observer
    finally:
        restore()
        _PATCH_LOCK.release()


@contextmanager
def request_profile(*, enabled=False, clock=time.perf_counter_ns):
    """Compatibility-friendly harness entry point; disabled mode is inert."""
    if type(enabled) is not bool:
        raise ValueError("enabled must be bool")
    if not enabled:
        yield RequestObserver()
        return
    with instrument_requests(clock=clock) as observer:
        yield observer


class _RequestState:
    __slots__ = ("observer", "record", "clock", "stack")

    def __init__(self, observer, record, clock):
        self.observer, self.record, self.clock = observer, record, clock
        self.stack = []


_MISSING = object()
