"""Graceful shutdown helpers for the gateway.

Provides timeout-bounded adapter disconnection to prevent the gateway
from hanging indefinitely when an adapter is stuck.
"""

import asyncio
import logging
from typing import Any, List

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10.0  # seconds


async def shutdown_with_timeout(
    adapters: List[Any],
    timeout: float = _DEFAULT_TIMEOUT,
) -> bool:
    """Disconnect all adapters with a timeout.

    Each adapter's disconnect() is called concurrently. If any adapter
    fails to disconnect within the timeout, it is cancelled and logged.

    Returns True when shutdown completes (even if some adapters timed out).
    """
    if not adapters:
        return True

    async def _safe_disconnect(adapter: Any) -> None:
        name = getattr(adapter, "platform_name", type(adapter).__name__)
        try:
            coro = adapter.disconnect()
            if asyncio.iscoroutine(coro) or asyncio.isfuture(coro):
                await asyncio.wait_for(coro, timeout=timeout)
            logger.info("Adapter %s disconnected cleanly", name)
        except asyncio.TimeoutError:
            logger.warning(
                "Adapter %s did not disconnect within %.1fs — forcing shutdown",
                name, timeout,
            )
        except Exception:
            logger.exception("Error disconnecting adapter %s", name)

    await asyncio.gather(
        *[_safe_disconnect(a) for a in adapters],
        return_exceptions=True,
    )
    return True
