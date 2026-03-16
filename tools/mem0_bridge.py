"""
Mem0Bridge — mem0 (mem-zero) memory integration for Hermes.

mem0 (https://github.com/mem0ai/mem0) is an intelligent memory layer for AI
agents. +26% accuracy over OpenAI Memory on LOCOMO benchmark, 91% faster than
full-context, 90% fewer tokens.

Configuration (env vars, all optional):
    MEM0_API_KEY     API key for Mem0 Platform (https://app.mem0.ai).
                     If set, uses managed cloud — no local setup needed.
    MEM0_USER_ID     User ID for memory scoping (default: hermes-{username}).
    MEM0_AGENT_ID    Agent ID for agent-level memory (default: "hermes").
    MEM0_LLM_PROVIDER  LLM provider for self-hosted (default: openai).
                       Supported: openai, anthropic, groq, ollama, etc.
                       Requires the matching API key in env (OPENAI_API_KEY etc).
    MEM0_TIMEOUT     Timeout in seconds for API calls (default: 5.0).

Quick start (self-hosted, no account needed):
    pip install mem0ai
    # mem0 uses your existing OPENAI_API_KEY by default

Quick start (cloud, zero infra):
    pip install mem0ai
    MEM0_API_KEY=your-key-from-app.mem0.ai

This module is zero-dependency at import time — silently skips if mem0ai
is not installed or not configured.
"""
import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MEM0_TIMEOUT = float(os.environ.get("MEM0_TIMEOUT", "5.0"))


def _get_client() -> Optional[Any]:
    """Return a configured mem0 Memory client or None if unavailable."""
    try:
        from mem0 import Memory, MemoryClient  # type: ignore
    except ImportError:
        logger.debug(
            "mem0ai not installed. Run: pip install mem0ai  to enable mem0 memory."
        )
        return None

    api_key = os.environ.get("MEM0_API_KEY")
    if api_key:
        # Cloud client — no local LLM needed
        try:
            return MemoryClient(api_key=api_key)
        except Exception as e:
            logger.warning("Failed to create mem0 MemoryClient (cloud): %s", e)
            return None
    else:
        # Self-hosted — needs an LLM configured (OPENAI_API_KEY etc.)
        llm_key = (
            os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("GROQ_API_KEY")
        )
        if not llm_key:
            logger.debug(
                "mem0 self-hosted requires an LLM API key "
                "(OPENAI_API_KEY / ANTHROPIC_API_KEY / GROQ_API_KEY) or MEM0_API_KEY for cloud."
            )
            return None
        try:
            return Memory()
        except Exception as e:
            logger.warning("Failed to create mem0 Memory (self-hosted): %s", e)
            return None


def _get_user_id() -> str:
    configured = os.environ.get("MEM0_USER_ID")
    if configured:
        return configured
    import getpass
    try:
        user = getpass.getuser()
    except Exception:
        user = "agent"
    return f"hermes-{user}"


def _get_agent_id() -> str:
    return os.environ.get("MEM0_AGENT_ID", "hermes")


def mem0_add(content: str, metadata: Optional[Dict] = None) -> bool:
    """
    Add a memory to mem0 (non-blocking).

    Args:
        content:  The fact, observation, or experience to store.
        metadata: Optional dict of metadata to tag the memory.

    Returns:
        True if successful, False otherwise.
    """
    client = _get_client()
    if client is None:
        return False

    user_id = _get_user_id()
    agent_id = _get_agent_id()
    result: List[bool] = []
    error: List[Exception] = []

    def _call():
        try:
            kwargs: Dict[str, Any] = {
                "messages": [{"role": "user", "content": content}],
                "user_id": user_id,
                "agent_id": agent_id,
            }
            if metadata:
                kwargs["metadata"] = metadata
            client.add(**kwargs)
            result.append(True)
        except Exception as e:
            error.append(e)

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    t.join(timeout=_MEM0_TIMEOUT)

    if t.is_alive():
        logger.warning("mem0 add timed out after %.1fs (non-critical)", _MEM0_TIMEOUT)
        return False
    if error:
        logger.debug("mem0 add failed (non-critical): %s", error[0])
        return False
    return bool(result)


def mem0_search(query: str, limit: int = 5) -> List[Dict]:
    """
    Search mem0 for relevant memories.

    Args:
        query: Natural language search query.
        limit: Maximum number of results to return.

    Returns:
        List of {"content": str, "source": "mem0", "score": float} dicts.
        Returns [] on any error or if mem0 is not configured.
    """
    client = _get_client()
    if client is None:
        return []

    user_id = _get_user_id()
    agent_id = _get_agent_id()
    results: List[Any] = []
    error: List[Exception] = []

    def _call():
        try:
            raw = client.search(
                query=query,
                user_id=user_id,
                agent_id=agent_id,
                limit=limit,
            )
            # mem0 returns {"results": [...]} or a list directly
            if isinstance(raw, dict):
                results.extend(raw.get("results", []))
            elif isinstance(raw, list):
                results.extend(raw)
        except Exception as e:
            error.append(e)

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    t.join(timeout=_MEM0_TIMEOUT)

    if t.is_alive():
        logger.warning("mem0 search timed out after %.1fs", _MEM0_TIMEOUT)
        return []
    if error:
        logger.debug("mem0 search failed: %s", error[0])
        return []

    # Normalize to the bridge's standard shape
    normalized = []
    for r in results:
        if isinstance(r, str):
            normalized.append({"content": r, "source": "mem0", "score": 0.8})
        elif isinstance(r, dict):
            normalized.append({
                "content": r.get("memory", r.get("content", str(r))),
                "source": "mem0",
                "score": float(r.get("score", 0.8)),
            })
        else:
            normalized.append({"content": str(r), "source": "mem0", "score": 0.8})

    return normalized[:limit]


def mem0_get_all() -> List[Dict]:
    """
    Retrieve all memories for the current user/agent.

    Returns:
        List of {"content": str, "source": "mem0", "score": float} dicts.
    """
    client = _get_client()
    if client is None:
        return []

    user_id = _get_user_id()
    agent_id = _get_agent_id()
    results: List[Any] = []
    error: List[Exception] = []

    def _call():
        try:
            raw = client.get_all(user_id=user_id, agent_id=agent_id)
            if isinstance(raw, dict):
                results.extend(raw.get("results", []))
            elif isinstance(raw, list):
                results.extend(raw)
        except Exception as e:
            error.append(e)

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    t.join(timeout=_MEM0_TIMEOUT)

    if t.is_alive():
        logger.warning("mem0 get_all timed out")
        return []
    if error:
        logger.debug("mem0 get_all failed: %s", error[0])
        return []

    return [
        {
            "content": r.get("memory", r.get("content", str(r))) if isinstance(r, dict) else str(r),
            "source": "mem0",
            "score": 1.0,
        }
        for r in results
    ]


def is_configured() -> bool:
    """Return True if mem0 is configured and the package is available."""
    return _get_client() is not None
