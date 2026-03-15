"""Tests for tools/agi_tool.py — AGI tool registry wiring."""
import importlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


class TestAgiToolRegistered(unittest.TestCase):
    def test_agi_tool_registered(self):
        """agi_goal_status is in registry after importing agi_tool."""
        # Import agi_tool to trigger registry.register() calls
        import tools.agi_tool  # noqa: F401
        from tools.registry import registry
        names = registry.get_all_tool_names()
        self.assertIn("agi_goal_status", names)


class TestAgiToolNoUrl(unittest.TestCase):
    """All tools return error dict when AGI_SERVER_URL not set."""

    def setUp(self):
        # Ensure env var is not set
        os.environ.pop("AGI_SERVER_URL", None)
        # Re-import to pick up clean state
        if "tools.agi_tool" in sys.modules:
            del sys.modules["tools.agi_tool"]
        if "src.agi_client" in sys.modules:
            del sys.modules["src.agi_client"]

    def test_agi_health_no_url(self):
        import tools.agi_tool as agi
        result = agi.agi_health()
        self.assertIn("error", result)
        self.assertIn("AGI_SERVER_URL", result["error"])

    def test_agi_goal_status_no_url(self):
        import tools.agi_tool as agi
        result = agi.agi_goal_status()
        self.assertIn("error", result)

    def test_agi_memory_search_no_url(self):
        import tools.agi_tool as agi
        result = agi.agi_memory_search("query")
        self.assertIn("error", result)

    def test_agi_blackboard_post_no_url(self):
        import tools.agi_tool as agi
        result = agi.agi_blackboard_post("topic", {})
        self.assertIn("error", result)

    def test_agi_worktree_create_no_url(self):
        import tools.agi_tool as agi
        result = agi.agi_worktree_create("run1", "team1", "main")
        self.assertIn("error", result)

    def test_agi_worktree_remove_no_url(self):
        import tools.agi_tool as agi
        result = agi.agi_worktree_remove("run1", "team1")
        self.assertIn("error", result)


class TestAgiToolHealth(unittest.TestCase):
    def setUp(self):
        os.environ["AGI_SERVER_URL"] = "http://test-server:8080"
        # Clear cached modules
        for mod in ["tools.agi_tool", "src.agi_client"]:
            sys.modules.pop(mod, None)

    def tearDown(self):
        os.environ.pop("AGI_SERVER_URL", None)
        for mod in ["tools.agi_tool", "src.agi_client"]:
            sys.modules.pop(mod, None)

    def test_agi_health_ok(self):
        """agi_health() returns {"ok": True} when client.health() is True."""
        mock_client = MagicMock()
        mock_client.health.return_value = True
        with patch("tools.agi_tool._get_client", return_value=mock_client):
            import tools.agi_tool as agi
            result = agi.agi_health()
        self.assertEqual(result, {"ok": True})

    def test_agi_health_fail(self):
        """agi_health() returns {"ok": False, "error": ...} on failure."""
        mock_client = MagicMock()
        mock_client.health.return_value = False
        with patch("tools.agi_tool._get_client", return_value=mock_client):
            import tools.agi_tool as agi
            result = agi.agi_health()
        self.assertEqual(result["ok"], False)

    def test_agi_goal_status(self):
        """agi_goal_status() returns dict with pending/inProgress/completed."""
        mock_client = MagicMock()
        mock_client.goal_status.return_value = {
            "pending": 2, "inProgress": 1, "completed": 5
        }
        with patch("tools.agi_tool._get_client", return_value=mock_client):
            import tools.agi_tool as agi
            result = agi.agi_goal_status()
        self.assertIn("pending", result)
        self.assertIn("inProgress", result)
        self.assertIn("completed", result)

    def test_agi_memory_search(self):
        """agi_memory_search() returns list."""
        mock_client = MagicMock()
        mock_client.memory_search.return_value = [{"id": "1", "text": "foo"}]
        with patch("tools.agi_tool._get_client", return_value=mock_client):
            import tools.agi_tool as agi
            result = agi.agi_memory_search("foo")
        self.assertIsInstance(result, list)

    def test_agi_blackboard_post(self):
        """agi_blackboard_post() returns dict."""
        mock_client = MagicMock()
        mock_client.blackboard_post.return_value = {"ok": True}
        with patch("tools.agi_tool._get_client", return_value=mock_client):
            import tools.agi_tool as agi
            result = agi.agi_blackboard_post("topic", {"msg": "hi"})
        self.assertIsInstance(result, dict)

    def test_agi_worktree_create(self):
        """agi_worktree_create() returns dict with path."""
        mock_client = MagicMock()
        mock_client.worktree_create.return_value = {"path": "/tmp/wt/run1-team1"}
        with patch("tools.agi_tool._get_client", return_value=mock_client):
            import tools.agi_tool as agi
            result = agi.agi_worktree_create("run1", "team1", "main")
        self.assertIn("path", result)

    def test_agi_worktree_remove(self):
        """agi_worktree_remove() returns {"removed": bool}."""
        mock_client = MagicMock()
        mock_client.worktree_remove.return_value = True
        with patch("tools.agi_tool._get_client", return_value=mock_client):
            import tools.agi_tool as agi
            result = agi.agi_worktree_remove("run1", "team1")
        self.assertEqual(result, {"removed": True})


if __name__ == "__main__":
    unittest.main()
