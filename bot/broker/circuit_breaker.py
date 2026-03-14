"""Circuit breaker for exchange API calls."""

from __future__ import annotations

import asyncio
import enum
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CircuitBreakerOpen(Exception):
    """Raised when the circuit is open and calls are blocked."""

    def __init__(self, operation: str, remaining: float) -> None:
        self.operation = operation
        self.remaining = remaining
        super().__init__(
            f"Circuit breaker OPEN for '{operation}' – retry in {remaining:.1f}s"
        )


class CircuitState(enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class _OperationState:
    """Per-operation failure tracking."""

    __slots__ = (
        "consecutive_failures",
        "state",
        "opened_at",
        "current_timeout",
    )

    def __init__(self) -> None:
        self.consecutive_failures: int = 0
        self.state: CircuitState = CircuitState.CLOSED
        self.opened_at: float = 0.0
        self.current_timeout: float = 0.0


class CircuitBreaker:
    """Async-safe circuit breaker with per-operation tracking.

    Parameters
    ----------
    failure_threshold:
        Number of consecutive failures before opening the circuit.
    recovery_timeout:
        Seconds to wait before transitioning from OPEN to HALF_OPEN.
    max_timeout:
        Upper bound for the exponentially-doubled recovery timeout.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        max_timeout: float = 300.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._max_timeout = max_timeout
        self._ops: dict[str, _OperationState] = {}
        self._lock = asyncio.Lock()

    # ── Internal helpers ──────────────────────────────────

    def _get_op(self, operation: str) -> _OperationState:
        if operation not in self._ops:
            self._ops[operation] = _OperationState()
        return self._ops[operation]

    def _transition(self, op: _OperationState, operation: str, new_state: CircuitState) -> None:
        old = op.state
        op.state = new_state
        logger.info(
            "circuit_breaker_transition",
            operation=operation,
            old_state=old.value,
            new_state=new_state.value,
            consecutive_failures=op.consecutive_failures,
            current_timeout=op.current_timeout,
        )

    # ── Public API ────────────────────────────────────────

    async def pre_call(self, operation: str) -> None:
        """Check circuit state before executing a call.

        Raises ``CircuitBreakerOpen`` if the circuit is OPEN and the
        recovery timeout has not yet elapsed.
        """
        async with self._lock:
            op = self._get_op(operation)

            if op.state == CircuitState.CLOSED:
                return

            elapsed = time.monotonic() - op.opened_at

            if op.state == CircuitState.OPEN:
                if elapsed < op.current_timeout:
                    remaining = op.current_timeout - elapsed
                    raise CircuitBreakerOpen(operation, remaining)
                # Recovery timeout elapsed – allow one test request.
                self._transition(op, operation, CircuitState.HALF_OPEN)
                return

            # HALF_OPEN: allow the single test request through.
            return

    async def record_success(self, operation: str) -> None:
        """Record a successful call – close the circuit."""
        async with self._lock:
            op = self._get_op(operation)
            if op.state != CircuitState.CLOSED:
                self._transition(op, operation, CircuitState.CLOSED)
            op.consecutive_failures = 0
            op.current_timeout = 0.0

    async def record_failure(self, operation: str) -> None:
        """Record a failed call – possibly open the circuit."""
        async with self._lock:
            op = self._get_op(operation)
            op.consecutive_failures += 1

            if op.state == CircuitState.HALF_OPEN:
                # Test request failed – reopen with doubled timeout.
                op.current_timeout = min(op.current_timeout * 2, self._max_timeout)
                op.opened_at = time.monotonic()
                self._transition(op, operation, CircuitState.OPEN)
                return

            if (
                op.state == CircuitState.CLOSED
                and op.consecutive_failures >= self._failure_threshold
            ):
                op.current_timeout = self._recovery_timeout
                op.opened_at = time.monotonic()
                self._transition(op, operation, CircuitState.OPEN)

    # ── Introspection ─────────────────────────────────────

    def state_for(self, operation: str) -> CircuitState:
        """Return the current state for *operation*."""
        return self._get_op(operation).state

    @property
    def health_status(self) -> dict[str, Any]:
        """Return a snapshot of all tracked operations."""
        return {
            op_name: {
                "state": op.state.value,
                "consecutive_failures": op.consecutive_failures,
                "current_timeout": op.current_timeout,
            }
            for op_name, op in self._ops.items()
        }
