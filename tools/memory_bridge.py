"""
MemoryBridge — unified search across Hermes native memory and AGI MemoryStore.

Does NOT modify memory_tool.py. Instead, provides a drop-in augmentation:
  from tools.memory_bridge import memory_bridge_search, memory_bridge_store

When native memory returns results → return them immediately (fast path).
When native memory returns nothing → fall back to AGI MemoryStore.
When both return results → merge, deduplicate by content similarity.

This means:
- Skills/sessions that used Hermes native memory: still work
- Skills/sessions that used AGI MemoryStore: still work
- Cross-session search works: native miss → AGI fallback finds it

Store path: memory_bridge_store() writes to native memory AND posts the
content to AGI MemoryStore via blackboard so the next AGI server can index it.
"""
import logging
import os
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

AGI_TIMEOUT = 3.0  # seconds before falling back


def _word_overlap(a: str, b: str) -> float:
    """Jaccard word overlap between two strings."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _dedup(results: List[Dict], threshold: float = 0.8) -> List[Dict]:
    """Remove near-duplicate entries by content similarity."""
    deduped: List[Dict] = []
    for item in results:
        content = item.get("content", "")
        is_dup = any(
            _word_overlap(content, d.get("content", "")) >= threshold
            for d in deduped
        )
        if not is_dup:
            deduped.append(item)
    return deduped


def _search_agi(query: str, limit: int = 5) -> List[Dict]:
    """Search AGI MemoryStore with timeout. Returns [] on any failure."""
    agi_url = os.environ.get("AGI_SERVER_URL")
    if not agi_url:
        return []
    try:
        from src.agi_client import AgiClient

        client = AgiClient.from_env()

        results: List[Any] = []
        error: List[Exception] = []

        def _call():
            try:
                results.extend(client.memory_search(query, limit))
            except Exception as e:
                error.append(e)

        t = threading.Thread(target=_call, daemon=True)
        t.start()
        t.join(timeout=AGI_TIMEOUT)

        if t.is_alive():
            logger.warning("AGI memory search timed out after %.1fs", AGI_TIMEOUT)
            return []
        if error:
            logger.warning("AGI memory search error: %s", error[0])
            return []
        return [{"content": str(r), "source": "agi", "score": 0.5} for r in results]
    except ImportError:
        return []
    except Exception as e:
        logger.warning("AGI memory fallback failed: %s", e)
        return []


def memory_bridge_search(
    native_search_fn: Callable,
    query: str,
    limit: int = 5,
) -> List[Dict]:
    """
    Search native memory first; fall back to AGI MemoryStore if empty.

    Args:
        native_search_fn: Callable that accepts (query, limit) and returns list
        query: Search query
        limit: Max results

    Returns:
        List of { content, source, score } dicts
    """
    # Fast path: try native memory
    try:
        native = native_search_fn(query, limit) or []
    except Exception as e:
        logger.warning("Native memory search error: %s", e)
        native = []

    # Normalize native results
    native_norm = [
        {
            "content": r if isinstance(r, str) else r.get("content", str(r)),
            "source": "native",
            "score": 1.0,
        }
        for r in native
    ]

    if native_norm:
        return native_norm[:limit]

    # Fallback: try AGI MemoryStore
    try:
        agi = _search_agi(query, limit)
    except Exception as e:
        logger.warning("AGI memory fallback raised: %s", e)
        agi = []
    merged = _dedup(native_norm + agi)
    return merged[:limit]


def memory_bridge_store(
    native_store_fn: Callable,
    key: str,
    content: str,
) -> bool:
    """
    Store in native memory AND sync to AGI MemoryStore via blackboard.

    Args:
        native_store_fn: Callable that accepts (key, content)
        key: Memory key
        content: Content to store

    Returns:
        True if native store succeeded
    """
    # Always write to native first
    try:
        native_store_fn(key, content)
        native_ok = True
    except Exception as e:
        logger.error("Native memory store failed: %s", e)
        native_ok = False

    # Best-effort: also post to AGI blackboard as a learning signal
    agi_url = os.environ.get("AGI_SERVER_URL")
    if agi_url:
        try:
            from src.agi_client import AgiClient

            client = AgiClient.from_env()
            client.blackboard_post("memory/learnings", {"key": key, "content": content})
        except Exception as e:
            logger.debug("AGI memory sync failed (non-critical): %s", e)

    return native_ok
