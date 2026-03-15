"""Request tracing with correlation IDs for hermes-agent.

Provides a context-variable-based trace context that propagates through
async and sync code paths. Subagents inherit the parent trace ID.

Usage:
    from agent.tracing import TraceContext, get_current_trace, generate_trace_id

    with TraceContext(trace_id=generate_trace_id(), session_id="sess-123"):
        # All code in this block can access the trace
        ctx = get_current_trace()
        logger.info("Processing", extra={"trace_id": ctx.trace_id})

    # For subagents:
    with TraceContext(trace_id=generate_trace_id(), session_id="sess-123",
                      parent_trace_id=parent_ctx.trace_id):
        ...
"""

import contextvars
import logging
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class _TraceData:
    """Immutable trace context data."""
    trace_id: str
    session_id: Optional[str] = None
    parent_trace_id: Optional[str] = None
    platform: Optional[str] = None
    user_id: Optional[str] = None


# Context variable holding the current trace (None outside any TraceContext)
_current_trace: contextvars.ContextVar[Optional[_TraceData]] = contextvars.ContextVar(
    "_current_trace", default=None
)


def generate_trace_id() -> str:
    """Generate a unique trace ID (compact UUID4 hex)."""
    return uuid.uuid4().hex[:16]


def get_current_trace() -> Optional[_TraceData]:
    """Return the current trace context, or None if not in a trace."""
    return _current_trace.get()


class TraceContext:
    """Context manager that sets the active trace for its scope.

    Restores the previous trace on exit (supports nesting for subagents).
    """

    def __init__(
        self,
        trace_id: str,
        session_id: Optional[str] = None,
        parent_trace_id: Optional[str] = None,
        platform: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        self._data = _TraceData(
            trace_id=trace_id,
            session_id=session_id,
            parent_trace_id=parent_trace_id,
            platform=platform,
            user_id=user_id,
        )
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> _TraceData:
        self._token = _current_trace.set(self._data)
        return self._data

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._token is not None:
            _current_trace.reset(self._token)


class TraceLogFilter(logging.Filter):
    """Logging filter that injects trace_id and session_id into log records.

    Attach to a handler or logger:
        handler.addFilter(TraceLogFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _current_trace.get()
        if ctx is not None:
            record.trace_id = ctx.trace_id  # type: ignore[attr-defined]
            record.session_id = ctx.session_id  # type: ignore[attr-defined]
            record.parent_trace_id = ctx.parent_trace_id  # type: ignore[attr-defined]
        else:
            record.trace_id = None  # type: ignore[attr-defined]
            record.session_id = None  # type: ignore[attr-defined]
            record.parent_trace_id = None  # type: ignore[attr-defined]
        return True
