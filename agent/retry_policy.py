"""Centralized retry policy for hermes-agent.

Replaces scattered manual retry loops with a single decorator that
provides exponential backoff with jitter.

Usage:
    from agent.retry_policy import with_retry

    @with_retry(max_attempts=3, base_delay=1.0)
    def call_api():
        ...

    @with_retry(max_attempts=5, retry_on=(ConnectionError, TimeoutError))
    async def async_call():
        ...
"""

import asyncio
import functools
import logging
import random
import time
from typing import Any, Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)

# Default exception types to retry on
_DEFAULT_RETRY_ON: Tuple[Type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def _compute_delay(
    attempt: int,
    base_delay: float,
    jitter: bool = True,
    max_delay: float = 60.0,
) -> float:
    """Compute the delay for a given retry attempt.

    Uses exponential backoff: base_delay * 2^attempt, capped at max_delay.
    If jitter is True, adds random variation (0.5x to 1.5x) to prevent
    thundering herd.
    """
    delay = base_delay * (2 ** attempt)
    delay = min(delay, max_delay)
    if jitter:
        delay *= 0.5 + random.random()  # 0.5x to 1.5x
    return delay


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retry_on: Optional[Tuple[Type[BaseException], ...]] = None,
) -> Callable:
    """Decorator that adds retry with exponential backoff.

    Works with both sync and async functions. Detects async automatically.

    Args:
        max_attempts: Total number of attempts (including the first).
        base_delay: Initial delay in seconds before first retry.
        max_delay: Maximum delay cap in seconds.
        jitter: Add random jitter to prevent thundering herd.
        retry_on: Exception types to retry on. Defaults to
                  (ConnectionError, TimeoutError, OSError).
    """
    exceptions = retry_on or _DEFAULT_RETRY_ON

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_err: Optional[BaseException] = None
                for attempt in range(max_attempts):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_err = e
                        if attempt < max_attempts - 1:
                            delay = _compute_delay(
                                attempt, base_delay, jitter, max_delay
                            )
                            logger.debug(
                                "Retry %d/%d for %s after %.2fs: %s",
                                attempt + 1, max_attempts, func.__name__,
                                delay, e,
                            )
                            await asyncio.sleep(delay)
                        else:
                            raise
                raise last_err  # type: ignore[misc]
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_err: Optional[BaseException] = None
                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_err = e
                        if attempt < max_attempts - 1:
                            delay = _compute_delay(
                                attempt, base_delay, jitter, max_delay
                            )
                            logger.debug(
                                "Retry %d/%d for %s after %.2fs: %s",
                                attempt + 1, max_attempts, func.__name__,
                                delay, e,
                            )
                            time.sleep(delay)
                        else:
                            raise
                raise last_err  # type: ignore[misc]
            return sync_wrapper
    return decorator
