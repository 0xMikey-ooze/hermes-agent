"""Lightweight metrics collection for hermes-agent observability.

Provides counters, gauges, and histograms with optional label support.
Can export in Prometheus text exposition format.

This is a zero-dependency implementation — no prometheus_client needed.
If you have Prometheus, use export_prometheus() to scrape; otherwise
call snapshot() for programmatic access.

Usage:
    from agent.metrics import metrics   # global singleton

    metrics.counter("messages_received")
    metrics.counter("tool_calls", labels={"tool": "web_search"})
    metrics.gauge("active_sessions", 5)
    metrics.histogram("llm_latency_seconds", 1.23)

    print(metrics.export_prometheus())
"""

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def _label_key(labels: Optional[Dict[str, str]]) -> str:
    """Convert labels dict to a deterministic hashable string key."""
    if not labels:
        return ""
    return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))


class MetricsRegistry:
    """Thread-safe metrics registry supporting counters, gauges, and histograms."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Counters: {(name, label_key): value}
        self._counters: Dict[Tuple[str, str], float] = defaultdict(float)
        # Gauges: {(name, label_key): value}
        self._gauges: Dict[Tuple[str, str], float] = {}
        # Histograms: {(name, label_key): list of observations}
        self._histograms: Dict[Tuple[str, str], List[float]] = defaultdict(list)

    def counter(
        self,
        name: str,
        value: float = 1,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a counter."""
        key = (name, _label_key(labels))
        with self._lock:
            self._counters[key] += value

    def gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge to a specific value."""
        key = (name, _label_key(labels))
        with self._lock:
            self._gauges[key] = value

    def histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a histogram observation."""
        key = (name, _label_key(labels))
        with self._lock:
            self._histograms[key].append(value)

    def get(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> float:
        """Get the current value of a counter or gauge."""
        key = (name, _label_key(labels))
        with self._lock:
            if key in self._counters:
                return self._counters[key]
            if key in self._gauges:
                return self._gauges[key]
            return 0

    def get_histogram_stats(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[str, float]:
        """Get summary statistics for a histogram."""
        key = (name, _label_key(labels))
        with self._lock:
            observations = list(self._histograms.get(key, []))
        if not observations:
            return {"count": 0, "sum": 0.0, "min": 0.0, "max": 0.0}
        return {
            "count": len(observations),
            "sum": sum(observations),
            "min": min(observations),
            "max": max(observations),
        }

    def snapshot(self) -> Dict[str, Any]:
        """Return a dict of all current metric values."""
        result: Dict[str, Any] = {}
        with self._lock:
            for (name, lk), value in self._counters.items():
                key = f"{name}{{{lk}}}" if lk else name
                result[key] = value
            for (name, lk), value in self._gauges.items():
                key = f"{name}{{{lk}}}" if lk else name
                result[key] = value
            for (name, lk), obs in self._histograms.items():
                key = f"{name}{{{lk}}}" if lk else name
                result[key] = {"count": len(obs), "sum": sum(obs)}
        return result

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text exposition format."""
        lines: List[str] = []
        with self._lock:
            for (name, lk), value in sorted(self._counters.items()):
                if lk:
                    lines.append(f"{name}{{{lk}}} {value}")
                else:
                    lines.append(f"{name} {value}")

            for (name, lk), value in sorted(self._gauges.items()):
                if lk:
                    lines.append(f"{name}{{{lk}}} {value}")
                else:
                    lines.append(f"{name} {value}")

            for (name, lk), obs in sorted(self._histograms.items()):
                suffix = f"{{{lk}}}" if lk else ""
                lines.append(f"{name}_count{suffix} {len(obs)}")
                lines.append(f"{name}_sum{suffix} {sum(obs)}")
        return "\n".join(lines) + "\n" if lines else ""


# Global singleton — import and use directly
metrics = MetricsRegistry()
