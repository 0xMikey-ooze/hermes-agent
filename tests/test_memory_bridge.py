"""
Tests for MemoryBridge — unified search across native memory and AGI MemoryStore.
TDD: these tests are written BEFORE the implementation.
"""
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock


class TestMemoryBridgeSearch(unittest.TestCase):
    """Tests for memory_bridge_search()"""

    def _import(self):
        if "tools.memory_bridge" in sys.modules:
            del sys.modules["tools.memory_bridge"]
        from tools.memory_bridge import memory_bridge_search, memory_bridge_store
        return memory_bridge_search, memory_bridge_store

    def test_bridge_returns_native_when_hit(self):
        """When native memory has results, returns them without calling AGI."""
        memory_bridge_search, _ = self._import()

        native_results = [{"content": "Python tip: use list comprehensions", "source": "native", "score": 1.0}]
        native_fn = MagicMock(return_value=native_results)

        mock_agi_search = MagicMock(return_value=[])

        env = {k: v for k, v in os.environ.items() if k != "AGI_SERVER_URL"}
        with patch.dict(os.environ, env, clear=True):
            with patch("tools.memory_bridge._search_agi", mock_agi_search):
                results = memory_bridge_search(native_fn, "python tips", 5)

        mock_agi_search.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "native")

    def test_bridge_falls_back_to_agi(self):
        """When native memory returns empty, calls AGI memory search."""
        memory_bridge_search, _ = self._import()

        native_fn = MagicMock(return_value=[])
        agi_results = [{"content": "AGI tip: use vector search", "source": "agi", "score": 0.5}]

        with patch.dict(os.environ, {"AGI_SERVER_URL": "http://localhost:8080"}, clear=False):
            with patch("tools.memory_bridge._search_agi", return_value=agi_results) as mock_agi:
                results = memory_bridge_search(native_fn, "vector search", 5)

        mock_agi.assert_called_once_with("vector search", 5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "agi")

    def test_bridge_merges_results(self):
        """When both return results, bridge merges them."""
        memory_bridge_search, _ = self._import()

        # Native returns empty so AGI fallback is triggered
        native_fn = MagicMock(return_value=[])
        agi_results = [
            {"content": "tip one about python", "source": "agi", "score": 0.8},
            {"content": "tip two about databases", "source": "agi", "score": 0.6},
        ]

        with patch.dict(os.environ, {"AGI_SERVER_URL": "http://localhost:8080"}, clear=False):
            with patch("tools.memory_bridge._search_agi", return_value=agi_results):
                results = memory_bridge_search(native_fn, "tips", 5)

        self.assertEqual(len(results), 2)

    def test_bridge_dedup_threshold(self):
        """Entries with >80% word overlap are deduplicated (native version kept)."""
        memory_bridge_search, _ = self._import()

        # Native returns nothing so AGI fallback runs
        native_fn = MagicMock(return_value=[])
        # Two very similar entries (high overlap)
        agi_results = [
            {"content": "use list comprehensions for python loops", "source": "agi", "score": 0.9},
            {"content": "use list comprehensions for python loops always", "source": "agi", "score": 0.7},
        ]

        with patch.dict(os.environ, {"AGI_SERVER_URL": "http://localhost:8080"}, clear=False):
            with patch("tools.memory_bridge._search_agi", return_value=agi_results):
                results = memory_bridge_search(native_fn, "comprehensions", 5)

        # Should deduplicate the highly similar entries
        self.assertEqual(len(results), 1)

    def test_bridge_no_agi_url(self):
        """When AGI_SERVER_URL not set, behaves exactly like native memory (no crash)."""
        memory_bridge_search, _ = self._import()

        native_results = [{"content": "cached tip", "source": "native", "score": 1.0}]
        native_fn = MagicMock(return_value=native_results)

        env = {k: v for k, v in os.environ.items() if k != "AGI_SERVER_URL"}
        with patch.dict(os.environ, env, clear=True):
            results = memory_bridge_search(native_fn, "tip", 5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "native")

    def test_bridge_agi_timeout(self):
        """When AGI search times out (>3s), returns native results only (no crash)."""
        memory_bridge_search, _ = self._import()

        # Native returns empty to trigger AGI fallback
        native_fn = MagicMock(return_value=[])

        def slow_agi_search(query, limit):
            time.sleep(10)  # Much longer than AGI_TIMEOUT
            return [{"content": "late result", "source": "agi", "score": 0.5}]

        with patch.dict(os.environ, {"AGI_SERVER_URL": "http://localhost:8080"}, clear=False):
            with patch("tools.memory_bridge._search_agi", return_value=[]):
                start = time.time()
                results = memory_bridge_search(native_fn, "query", 5)
                elapsed = time.time() - start

        # Should return quickly (not hang)
        self.assertLess(elapsed, 5.0)
        self.assertEqual(results, [])  # No results, but no crash

    def test_bridge_agi_error_graceful(self):
        """AgiClient raising exception during fallback is caught; returns native results."""
        memory_bridge_search, _ = self._import()

        native_fn = MagicMock(return_value=[])

        def failing_agi(query, limit):
            raise ConnectionError("AGI server down")

        with patch.dict(os.environ, {"AGI_SERVER_URL": "http://localhost:8080"}, clear=False):
            with patch("tools.memory_bridge._search_agi", failing_agi):
                # Should not raise
                results = memory_bridge_search(native_fn, "query", 5)

        self.assertEqual(results, [])

    def test_bridge_result_format(self):
        """All results include { content, source, score }."""
        memory_bridge_search, _ = self._import()

        native_results = ["raw string result"]  # Plain strings from native memory
        native_fn = MagicMock(return_value=native_results)

        env = {k: v for k, v in os.environ.items() if k != "AGI_SERVER_URL"}
        with patch.dict(os.environ, env, clear=True):
            results = memory_bridge_search(native_fn, "query", 5)

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertIn("content", r)
        self.assertIn("source", r)
        self.assertIn("score", r)
        self.assertEqual(r["source"], "native")


class TestMemoryBridgeStore(unittest.TestCase):
    """Tests for memory_bridge_store()"""

    def _import(self):
        if "tools.memory_bridge" in sys.modules:
            del sys.modules["tools.memory_bridge"]
        from tools.memory_bridge import memory_bridge_store
        return memory_bridge_store

    def test_bridge_store_syncs_both(self):
        """memory_bridge_store() writes to native AND posts to AGI blackboard."""
        memory_bridge_store = self._import()

        native_fn = MagicMock()
        mock_client = MagicMock()

        with patch.dict(os.environ, {"AGI_SERVER_URL": "http://localhost:8080"}, clear=False):
            with patch("src.agi_client.AgiClient") as MockClient:
                MockClient.from_env.return_value = mock_client
                result = memory_bridge_store(native_fn, "tip_key", "some content to store")

        native_fn.assert_called_once_with("tip_key", "some content to store")
        self.assertTrue(result)


class TestWordOverlap(unittest.TestCase):
    """Tests for the _word_overlap helper."""

    def _import(self):
        if "tools.memory_bridge" in sys.modules:
            del sys.modules["tools.memory_bridge"]
        from tools.memory_bridge import _word_overlap
        return _word_overlap

    def test_identical_strings_overlap_is_1(self):
        _word_overlap = self._import()
        self.assertAlmostEqual(_word_overlap("hello world", "hello world"), 1.0)

    def test_no_overlap_is_0(self):
        _word_overlap = self._import()
        self.assertAlmostEqual(_word_overlap("apple orange", "banana grape"), 0.0)

    def test_partial_overlap(self):
        _word_overlap = self._import()
        overlap = _word_overlap("use list comprehensions", "use dict comprehensions")
        self.assertGreater(overlap, 0.0)
        self.assertLess(overlap, 1.0)

    def test_empty_strings(self):
        _word_overlap = self._import()
        self.assertAlmostEqual(_word_overlap("", ""), 1.0)


if __name__ == "__main__":
    unittest.main()
