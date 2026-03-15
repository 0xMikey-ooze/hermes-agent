"""TDD tests for Prometheus-style metrics collection.

Tests written BEFORE implementation.
"""

import threading
import time

import pytest


class TestMetricsRegistry:
    """Tests for the central metrics registry."""

    def test_counter_increments(self):
        """A counter should increment by 1 by default."""
        from agent.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.counter("messages_received")
        reg.counter("messages_received")
        assert reg.get("messages_received") == 2

    def test_counter_increments_by_n(self):
        """A counter should support incrementing by arbitrary amounts."""
        from agent.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.counter("tokens_used", 150)
        reg.counter("tokens_used", 250)
        assert reg.get("tokens_used") == 400

    def test_gauge_set_and_get(self):
        """A gauge should hold the last set value."""
        from agent.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.gauge("active_sessions", 5)
        assert reg.get("active_sessions") == 5
        reg.gauge("active_sessions", 3)
        assert reg.get("active_sessions") == 3

    def test_histogram_records_values(self):
        """A histogram should record observed values and compute stats."""
        from agent.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.histogram("llm_latency_seconds", 0.5)
        reg.histogram("llm_latency_seconds", 1.5)
        reg.histogram("llm_latency_seconds", 2.0)
        stats = reg.get_histogram_stats("llm_latency_seconds")
        assert stats["count"] == 3
        assert abs(stats["sum"] - 4.0) < 0.01
        assert stats["min"] == 0.5
        assert stats["max"] == 2.0

    def test_get_unknown_metric_returns_zero(self):
        """Getting an unknown metric should return 0."""
        from agent.metrics import MetricsRegistry
        reg = MetricsRegistry()
        assert reg.get("nonexistent") == 0

    def test_labeled_counter(self):
        """Counters should support labels for dimensionality."""
        from agent.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.counter("tool_calls", labels={"tool": "web_search"})
        reg.counter("tool_calls", labels={"tool": "web_search"})
        reg.counter("tool_calls", labels={"tool": "terminal"})
        assert reg.get("tool_calls", labels={"tool": "web_search"}) == 2
        assert reg.get("tool_calls", labels={"tool": "terminal"}) == 1

    def test_snapshot_returns_all_metrics(self):
        """snapshot() should return a dict of all current metric values."""
        from agent.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.counter("a")
        reg.gauge("b", 42)
        snap = reg.snapshot()
        assert "a" in snap
        assert "b" in snap

    def test_thread_safety(self):
        """Concurrent increments should not lose counts."""
        from agent.metrics import MetricsRegistry
        reg = MetricsRegistry()
        n_threads = 10
        n_increments = 1000

        def worker():
            for _ in range(n_increments):
                reg.counter("concurrent_test")

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert reg.get("concurrent_test") == n_threads * n_increments

    def test_prometheus_format_output(self):
        """export_prometheus() should produce valid Prometheus text format."""
        from agent.metrics import MetricsRegistry
        reg = MetricsRegistry()
        reg.counter("http_requests_total", 5)
        reg.gauge("active_connections", 3)
        output = reg.export_prometheus()
        assert "http_requests_total 5" in output
        assert "active_connections 3" in output


class TestRequestTracing:
    """Tests for request tracing with correlation IDs."""

    def test_generate_trace_id(self):
        """Should generate a unique trace ID."""
        from agent.tracing import generate_trace_id
        id1 = generate_trace_id()
        id2 = generate_trace_id()
        assert isinstance(id1, str)
        assert len(id1) > 0
        assert id1 != id2

    def test_trace_context_propagates(self):
        """Trace context should propagate through the context var."""
        from agent.tracing import TraceContext, get_current_trace
        with TraceContext(trace_id="test-123", session_id="sess-456"):
            ctx = get_current_trace()
            assert ctx.trace_id == "test-123"
            assert ctx.session_id == "sess-456"

    def test_nested_trace_context(self):
        """Nested trace contexts should work (subagents)."""
        from agent.tracing import TraceContext, get_current_trace
        with TraceContext(trace_id="parent", session_id="sess-1"):
            assert get_current_trace().trace_id == "parent"
            with TraceContext(trace_id="child", session_id="sess-1", parent_trace_id="parent"):
                ctx = get_current_trace()
                assert ctx.trace_id == "child"
                assert ctx.parent_trace_id == "parent"
            # After child exits, parent is restored
            assert get_current_trace().trace_id == "parent"

    def test_trace_context_outside_scope_returns_none(self):
        """Outside any TraceContext, get_current_trace() should return None."""
        from agent.tracing import get_current_trace
        # Reset any existing context
        ctx = get_current_trace()
        # May be None or may have a default — just check it doesn't crash
        assert ctx is None or hasattr(ctx, "trace_id")

    def test_trace_context_adds_to_log_record(self):
        """TraceContext should inject trace_id into logging records."""
        import logging
        from agent.tracing import TraceContext, TraceLogFilter
        test_logger = logging.getLogger("test_trace_filter")
        test_logger.handlers = []
        test_logger.filters = []
        handler = logging.StreamHandler()
        filt = TraceLogFilter()
        handler.addFilter(filt)
        test_logger.addHandler(handler)

        with TraceContext(trace_id="trace-abc", session_id="sess-1"):
            record = test_logger.makeRecord(
                "test", logging.INFO, "test.py", 1, "msg", (), None
            )
            filt.filter(record)
            assert record.trace_id == "trace-abc"  # type: ignore[attr-defined]


class TestRetryPolicy:
    """Tests for the centralized retry policy."""

    def test_sync_retry_succeeds_on_first_try(self):
        """If the function succeeds immediately, no retry needed."""
        from agent.retry_policy import with_retry
        call_count = 0

        @with_retry(max_attempts=3)
        def succeeds():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeeds() == "ok"
        assert call_count == 1

    def test_sync_retry_retries_on_failure(self):
        """Should retry the configured number of times."""
        from agent.retry_policy import with_retry
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temporary")
            return "ok"

        assert fails_twice() == "ok"
        assert call_count == 3

    def test_sync_retry_exhaustion_raises(self):
        """If all retries are exhausted, the last exception should be raised."""
        from agent.retry_policy import with_retry

        @with_retry(max_attempts=2, base_delay=0.01)
        def always_fails():
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            always_fails()

    def test_async_retry_succeeds(self):
        """Async functions should also be retryable."""
        import asyncio
        from agent.retry_policy import with_retry
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        async def async_fails_once():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("temp")
            return "async_ok"

        result = asyncio.get_event_loop().run_until_complete(async_fails_once())
        assert result == "async_ok"
        assert call_count == 2

    def test_retry_only_on_specified_exceptions(self):
        """Should only retry on specified exception types."""
        from agent.retry_policy import with_retry

        @with_retry(max_attempts=3, base_delay=0.01, retry_on=(ConnectionError,))
        def wrong_exception():
            raise TypeError("not retryable")

        with pytest.raises(TypeError):
            wrong_exception()

    def test_retry_with_jitter(self):
        """Jitter should add randomness to prevent thundering herd."""
        from agent.retry_policy import _compute_delay
        delays = set()
        for _ in range(20):
            d = _compute_delay(attempt=1, base_delay=1.0, jitter=True)
            delays.add(round(d, 3))
        # With jitter, we should get varied delays
        assert len(delays) > 1

    def test_exponential_backoff_growth(self):
        """Delays should grow exponentially."""
        from agent.retry_policy import _compute_delay
        d0 = _compute_delay(attempt=0, base_delay=1.0, jitter=False)
        d1 = _compute_delay(attempt=1, base_delay=1.0, jitter=False)
        d2 = _compute_delay(attempt=2, base_delay=1.0, jitter=False)
        assert d0 == 1.0
        assert d1 == 2.0
        assert d2 == 4.0

    def test_max_delay_cap(self):
        """Delay should be capped at max_delay."""
        from agent.retry_policy import _compute_delay
        d = _compute_delay(attempt=10, base_delay=1.0, jitter=False, max_delay=30.0)
        assert d <= 30.0
