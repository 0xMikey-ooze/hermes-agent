"""Tool dispatch logic extracted from run_agent.py.

Contains the decision logic for how to execute tool calls:
sequential vs concurrent, and the worker pool sizing.

This module is pure logic with no side effects — safe to import and test.
run_agent.py's _execute_tool_calls() delegates to this for the decision,
then uses its own methods for the actual execution.
"""

from typing import FrozenSet, List


# Maximum number of concurrent worker threads for parallel tool execution.
MAX_TOOL_WORKERS = 8

# Tools that must never run concurrently (interactive / user-facing).
DEFAULT_NEVER_PARALLEL: FrozenSet[str] = frozenset({"clarify"})


def choose_dispatch_mode(
    tool_names: List[str],
    never_parallel: FrozenSet[str] = DEFAULT_NEVER_PARALLEL,
) -> str:
    """Decide whether to run tool calls sequentially or concurrently.

    Returns "sequential" or "concurrent".

    Rules:
    - 0 or 1 tool calls → sequential (no benefit from concurrency)
    - Any tool in never_parallel → sequential (interactive tools)
    - Multiple non-interactive tools → concurrent
    """
    if len(tool_names) <= 1:
        return "sequential"

    if any(name in never_parallel for name in tool_names):
        return "sequential"

    return "concurrent"


def compute_worker_count(num_tools: int) -> int:
    """Compute the number of worker threads for concurrent execution.

    Capped at MAX_TOOL_WORKERS to prevent thread explosion.
    """
    return min(num_tools, MAX_TOOL_WORKERS)
