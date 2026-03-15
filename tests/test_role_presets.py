"""Tests for agent.role_presets — Role-based tool scoping for subagents.

Written test-first (RED phase) before implementation.
"""

import pytest


class TestRolePresets:
    """Test ROLE_PRESETS mapping and get_tools_for_role()."""

    def test_researcher_role_has_read_only_tools(self):
        from agent.role_presets import get_tools_for_role

        tools = get_tools_for_role("researcher")
        assert "web_search" in tools
        assert "web_extract" in tools
        assert "read_file" in tools
        assert "search_files" in tools
        # Researcher should NOT have write tools
        assert "write_file" not in tools
        assert "patch" not in tools
        assert "terminal" not in tools

    def test_coder_role_has_file_and_terminal_tools(self):
        from agent.role_presets import get_tools_for_role

        tools = get_tools_for_role("coder")
        assert "read_file" in tools
        assert "write_file" in tools
        assert "patch" in tools
        assert "search_files" in tools
        assert "terminal" in tools
        assert "process" in tools

    def test_reviewer_role_has_read_only_tools(self):
        from agent.role_presets import get_tools_for_role

        tools = get_tools_for_role("reviewer")
        assert "read_file" in tools
        assert "search_files" in tools
        # Reviewer should NOT have write or terminal tools
        assert "write_file" not in tools
        assert "terminal" not in tools

    def test_unknown_role_returns_none(self):
        from agent.role_presets import get_tools_for_role

        result = get_tools_for_role("nonexistent_role")
        assert result is None

    def test_default_role_returns_none(self):
        """Default means 'no filtering' — returns None to signal all tools allowed."""
        from agent.role_presets import get_tools_for_role

        result = get_tools_for_role("default")
        assert result is None

    def test_all_presets_return_frozensets(self):
        from agent.role_presets import ROLE_PRESETS

        for role_name, tools in ROLE_PRESETS.items():
            assert isinstance(tools, frozenset), f"{role_name} should be a frozenset"

    def test_presets_are_nonempty(self):
        from agent.role_presets import ROLE_PRESETS

        for role_name, tools in ROLE_PRESETS.items():
            assert len(tools) > 0, f"{role_name} should not be empty"


class TestFilterToolsByRole:
    """Test filter_tools_by_role() which filters tool definition lists."""

    def test_filter_keeps_matching_tools(self):
        from agent.role_presets import filter_tools_by_role

        tool_defs = [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "write_file"}},
            {"type": "function", "function": {"name": "web_search"}},
        ]
        filtered = filter_tools_by_role(tool_defs, "researcher")
        names = [t["function"]["name"] for t in filtered]
        assert "read_file" in names
        assert "web_search" in names
        assert "write_file" not in names

    def test_filter_with_none_role_returns_all(self):
        from agent.role_presets import filter_tools_by_role

        tool_defs = [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "write_file"}},
        ]
        filtered = filter_tools_by_role(tool_defs, None)
        assert len(filtered) == 2

    def test_filter_with_unknown_role_returns_all(self):
        from agent.role_presets import filter_tools_by_role

        tool_defs = [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "write_file"}},
        ]
        filtered = filter_tools_by_role(tool_defs, "nonexistent")
        assert len(filtered) == 2

    def test_filter_with_empty_list(self):
        from agent.role_presets import filter_tools_by_role

        filtered = filter_tools_by_role([], "coder")
        assert filtered == []
