"""Role-based tool presets for subagent scoping.

Each role defines a minimal set of tools appropriate for that role,
preventing subagents from accessing tools they don't need.

Usage:
    from agent.role_presets import get_tools_for_role, filter_tools_by_role

    # Get allowed tool names for a role
    tools = get_tools_for_role("researcher")  # frozenset or None

    # Filter OpenAI-format tool definitions by role
    filtered = filter_tools_by_role(tool_definitions, "coder")
"""

from typing import Dict, FrozenSet, List, Optional


ROLE_PRESETS: Dict[str, FrozenSet[str]] = {
    "researcher": frozenset({
        "web_search", "web_extract", "read_file", "search_files",
        "browser_navigate", "browser_snapshot", "browser_click",
        "browser_type", "browser_scroll", "browser_back",
        "browser_press", "browser_close", "browser_get_images",
        "browser_vision",
    }),
    "coder": frozenset({
        "read_file", "write_file", "patch", "search_files",
        "terminal", "process",
    }),
    "reviewer": frozenset({
        "read_file", "search_files", "web_search", "web_extract",
    }),
}


def get_tools_for_role(role: str) -> Optional[FrozenSet[str]]:
    """Return the tool set for a role, or None if role is unknown/default.

    None signals "no filtering" — the caller should allow all tools.
    """
    if role == "default":
        return None
    return ROLE_PRESETS.get(role)


def filter_tools_by_role(
    tool_definitions: List[dict],
    role: Optional[str],
) -> List[dict]:
    """Filter OpenAI-format tool definitions by role preset.

    If role is None, unknown, or "default", returns all tools unfiltered.
    """
    if not role:
        return tool_definitions

    allowed = get_tools_for_role(role)
    if allowed is None:
        return tool_definitions

    return [
        t for t in tool_definitions
        if t.get("function", {}).get("name") in allowed
    ]
