"""Smoke tests for agi_tool registry import and function availability."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


class TestAgiToolImportable(unittest.TestCase):
    def test_agi_tool_importable(self):
        """`from tools.agi_tool import agi_health` does not raise."""
        from tools.agi_tool import agi_health
        self.assertTrue(callable(agi_health))

    def test_agi_health_in_registry(self):
        """After `import tools.agi_tool`, calling agi_health() returns dict."""
        import tools.agi_tool
        result = tools.agi_tool.agi_health()
        self.assertIsInstance(result, dict)

    def test_agi_goal_status_callable(self):
        """agi_goal_status() returns dict (mocked, no real server needed)."""
        os.environ.pop("AGI_SERVER_URL", None)
        import tools.agi_tool as agi
        result = agi.agi_goal_status()
        self.assertIsInstance(result, dict)

    def test_agi_worktree_create_callable(self):
        """agi_worktree_create('r1','t1','main') returns dict."""
        os.environ.pop("AGI_SERVER_URL", None)
        import tools.agi_tool as agi
        result = agi.agi_worktree_create("r1", "t1", "main")
        self.assertIsInstance(result, dict)

    def test_all_9_agi_functions_callable(self):
        """All 9 agi_* functions are importable and callable without crashing when AGI_SERVER_URL unset."""
        os.environ.pop("AGI_SERVER_URL", None)
        import tools.agi_tool as agi

        functions = [
            (agi.agi_health, []),
            (agi.agi_goal_status, []),
            (agi.agi_goal_decompose, ["build a feature"]),
            (agi.agi_goal_complete, ["task-1", {"result": "done"}]),
            (agi.agi_memory_search, ["query"]),
            (agi.agi_blackboard_post, ["topic", {"msg": "hello"}]),
            (agi.agi_worktree_create, ["run1", "team1", "main"]),
            (agi.agi_worktree_remove, ["run1", "team1"]),
            (agi.agi_worktree_list, ["run1"]),
        ]

        for func, args in functions:
            with self.subTest(func=func.__name__):
                result = func(*args)
                self.assertIsInstance(result, dict,
                    f"{func.__name__} should return dict, got {type(result)}")


class TestAgiToolRegistryEntry(unittest.TestCase):
    def test_agi_tools_registered_in_registry(self):
        """All agi_* tools appear in the registry after import."""
        import tools.agi_tool  # noqa: F401
        from tools.registry import registry

        expected = [
            "agi_health",
            "agi_goal_status",
            "agi_goal_decompose",
            "agi_goal_complete",
            "agi_memory_search",
            "agi_blackboard_post",
            "agi_worktree_create",
            "agi_worktree_remove",
            "agi_worktree_list",
        ]

        registered = registry.get_all_tool_names()
        for name in expected:
            self.assertIn(name, registered,
                f"Expected {name} to be registered in tool registry")


if __name__ == "__main__":
    unittest.main()
