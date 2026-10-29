"""Local agent decisions using the existing private, owned model-process transport."""
from __future__ import annotations

import asyncio
import math

from .agent_decision import generation, validate_decision, validate_state
from .host_inference_admission import HostAdmissionError
from .memory_narrative import MAX_PROVIDER_BYTES, _json_bytes, _strict_loads
from .selected_story_native import NativeStoryOwnerError
from .selected_story_operations import PreparationScope
from .selected_story_process import ProcessSelectedStoryProvider, ProcessSelectedStoryError, _Exchange, MAX_REQUEST_BYTES


class ProcessAgentDecisionProvider(ProcessSelectedStoryProvider):
    """Shares launch, native Job, host admission and cleanup with story generation.

    The explicit launch must select the household worker, which accepts only the
    existing story packet or this separately versioned decision packet. No model,
    service, shell or tool is selected from model output.
    """

    async def decide(self, state, scope):
        self._bind()
        if not self.enabled:
            raise ProcessSelectedStoryError('disabled')
        if self._closed:
            raise ProcessSelectedStoryError('closed')
        if type(scope) is not PreparationScope:
            raise ProcessSelectedStoryError('invalid_input')
        if self._active is not None:
            raise ProcessSelectedStoryError('busy')
        try:
            self._check(scope)
            if type(state) is not dict or set(state) != {'turn', 'observations'}:
                raise ValueError('Invalid state')
            clean = validate_state(state['turn'], state['observations'])
            # Verify that the exact bounded canonical decision can be constructed
            # before taking a native permit or writing any private exchange.
            generation(clean, self.model)
            if (self._last_settled_scope is not None and
                    self._last_settled_scope.operation_id == scope.operation_id):
                raise ValueError('Reused operation')
            payload = _json_bytes({'version': 1, 'kind': 'agent_decision_v1',
                'operation_id': scope.operation_id, 'state': clean},
                'agent decision request', MAX_REQUEST_BYTES)
            remaining = min(self.timeout, scope.deadline_monotonic - scope._clock())
            if not math.isfinite(remaining) or remaining <= 0:
                raise ProcessSelectedStoryError('cancelled')
        except ProcessSelectedStoryError:
            raise
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            raise ProcessSelectedStoryError('invalid_input') from None
        call = _Exchange(scope)
        self._active = call
        try:
            async with asyncio.timeout(remaining):
                call.setup = asyncio.create_task(asyncio.to_thread(self._setup, call, payload))
                await asyncio.shield(call.setup)
                self._check(scope)
                await call.owner.begin(scope)
                await call.owner.wait_for_exit(scope)
                if await call.owner.stop_and_reconcile(scope) is not True:
                    raise ProcessSelectedStoryError('cleanup')
                self._check(scope)
                call.reading = asyncio.create_task(asyncio.to_thread(self._read, call))
                response = _strict_loads(await asyncio.shield(call.reading))
                if (type(response) is not dict or set(response) != {'version', 'operation_id', 'model', 'result'}
                        or type(response['version']) is not int or response['version'] != 1
                        or response['operation_id'] != scope.operation_id or response['model'] != self.model):
                    raise ValueError('Response binding')
                _json_bytes(response, 'agent decision response', MAX_PROVIDER_BYTES)
                result = validate_decision(response['result'], clean)
                self._check(scope)
                return result
        except (ProcessSelectedStoryError, HostAdmissionError):
            raise
        except TimeoutError:
            raise ProcessSelectedStoryError('cancelled') from None
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            raise ProcessSelectedStoryError('invalid_response') from None
        except NativeStoryOwnerError as error:
            raise ProcessSelectedStoryError('cancelled' if error.category == 'cancelled' else 'worker') from None
        except Exception:
            raise ProcessSelectedStoryError('worker') from None
        finally:
            call.settled.set()
