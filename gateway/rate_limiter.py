"""Per-user rate limiter for the gateway.

Uses a sliding window algorithm to limit the number of messages
a single user can send within a time window. Prevents a single
user from DOSing the agent with unlimited messages.
"""

import threading
import time
from collections import defaultdict
from typing import Dict, List


class RateLimiter:
    """Thread-safe sliding-window rate limiter keyed by user ID.

    Args:
        max_messages: Maximum messages allowed per window.
        window_seconds: Size of the sliding window in seconds.
    """

    def __init__(self, max_messages: int = 10, window_seconds: float = 60.0):
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self._timestamps: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, user_id: str, now: float) -> None:
        """Remove timestamps outside the current window."""
        cutoff = now - self.window_seconds
        timestamps = self._timestamps[user_id]
        # Find the first timestamp within the window
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

    def allow(self, user_id: str) -> bool:
        """Check if a message from this user should be allowed.

        Returns True if the message is allowed, False if rate-limited.
        """
        now = time.monotonic()
        with self._lock:
            self._prune(user_id, now)
            if len(self._timestamps[user_id]) >= self.max_messages:
                return False
            self._timestamps[user_id].append(now)
            return True

    def remaining(self, user_id: str) -> int:
        """Return the number of remaining messages allowed in the current window."""
        now = time.monotonic()
        with self._lock:
            self._prune(user_id, now)
            return max(0, self.max_messages - len(self._timestamps[user_id]))
