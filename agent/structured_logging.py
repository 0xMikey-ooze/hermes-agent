"""Structured JSON logging formatter for production observability.

Produces one JSON object per log line with standard fields:
    timestamp, level, logger, message, [session_id], [platform], [exception]

Usage:
    import logging
    from agent.structured_logging import StructuredFormatter

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    logging.getLogger().addHandler(handler)
"""

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Known extra fields that get promoted to top-level JSON keys.
_KNOWN_EXTRAS = frozenset({
    "session_id", "platform", "user_id", "trace_id",
    "tool_name", "operation", "latency_ms",
})

# Simple patterns for secret detection (kept lightweight on purpose).
_SECRET_PATTERNS = [
    "sk-",
    "ghp_",
    "ghs_",
    "xoxb-",
    "xoxp-",
    "AKIA",
]


def _redact_message(msg: str) -> str:
    """Best-effort redaction of common API key prefixes in log messages."""
    for pattern in _SECRET_PATTERNS:
        idx = msg.find(pattern)
        while idx != -1:
            # Find the end of the token (next whitespace or quote)
            end = idx + len(pattern)
            while end < len(msg) and msg[end] not in (' ', '"', "'", ',', '\n', '\t'):
                end += 1
            token = msg[idx:end]
            if len(token) > len(pattern) + 4:
                msg = msg.replace(token, f"{token[:len(pattern)+4]}***REDACTED***")
            idx = msg.find(pattern, end)
    return msg


class StructuredFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    Args:
        redact: If True, attempt to redact API keys from messages.
    """

    def __init__(self, redact: bool = False, **kwargs: Any):
        super().__init__()
        self._redact = redact

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if self._redact:
            message = _redact_message(message)

        entry: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }

        # Promote known extra fields to top-level keys
        for field in _KNOWN_EXTRAS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = "".join(
                traceback.format_exception(*record.exc_info)
            )

        return json.dumps(entry, default=str, ensure_ascii=False)
