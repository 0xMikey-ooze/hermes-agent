"""Tests for tools/skill_effectiveness.py."""
import json
import tempfile
import time
import unittest
from pathlib import Path


class TestSkillEffectivenessBasics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.storage = Path(self.tmp) / "effectiveness.json"

    def _make(self):
        from tools.skill_effectiveness import SkillEffectiveness
        return SkillEffectiveness(storage_path=self.storage)

    def test_record_usage(self):
        se = self._make()
        se.record_usage("rag-engineer", task="build pipeline", score=0.8)
        stats = se.get_stats("rag-engineer")
        self.assertEqual(stats["uses"], 1)

    def test_get_stats_empty(self):
        se = self._make()
        stats = se.get_stats("unknown-skill")
        self.assertEqual(stats["uses"], 0)
        self.assertEqual(stats["avg_score"], 0.0)
        self.assertEqual(stats["success_rate"], 0.0)

    def test_get_stats_populated(self):
        se = self._make()
        se.record_usage("rag-engineer", "task1", 0.6)
        se.record_usage("rag-engineer", "task2", 0.8)
        se.record_usage("rag-engineer", "task3", 1.0)
        stats = se.get_stats("rag-engineer")
        self.assertEqual(stats["uses"], 3)
        # avg should be around 0.8 (with minor decay differences since all recent)
        self.assertGreater(stats["avg_score"], 0.7)
        self.assertLess(stats["avg_score"], 0.9)

    def test_success_rate(self):
        se = self._make()
        se.record_usage("skill-a", "t1", 0.9)  # success
        se.record_usage("skill-a", "t2", 0.7)  # success (boundary)
        se.record_usage("skill-a", "t3", 0.5)  # fail
        se.record_usage("skill-a", "t4", 0.3)  # fail
        stats = se.get_stats("skill-a")
        self.assertAlmostEqual(stats["success_rate"], 0.5, places=1)

    def test_rank_skills(self):
        se = self._make()
        se.record_usage("skill-low", "t", 0.3)
        se.record_usage("skill-high", "t", 0.9)
        se.record_usage("skill-mid", "t", 0.6)
        ranked = se.rank_skills(["skill-low", "skill-high", "skill-mid"])
        self.assertEqual(ranked[0], "skill-high")
        self.assertEqual(ranked[-1], "skill-low")

    def test_rank_skills_unrated_last(self):
        se = self._make()
        se.record_usage("rated", "t", 0.8)
        ranked = se.rank_skills(["unrated", "rated"])
        self.assertEqual(ranked[0], "rated")
        self.assertEqual(ranked[-1], "unrated")

    def test_worst_skills(self):
        se = self._make()
        for _ in range(3):
            se.record_usage("bad-skill", "t", 0.2)
        for _ in range(3):
            se.record_usage("good-skill", "t", 0.9)
        worst = se.worst_skills(threshold=0.5)
        self.assertIn("bad-skill", worst)
        self.assertNotIn("good-skill", worst)

    def test_worst_skills_requires_min_uses(self):
        """Skills with fewer than 3 uses are not flagged as worst."""
        se = self._make()
        se.record_usage("new-bad-skill", "t", 0.1)  # only 1 use
        worst = se.worst_skills(threshold=0.5)
        self.assertNotIn("new-bad-skill", worst)

    def test_persistence(self):
        """New SkillEffectiveness instance reads same data."""
        se1 = self._make()
        se1.record_usage("persist-skill", "task", 0.85)
        # Create new instance with same path
        se2 = self._make()
        stats = se2.get_stats("persist-skill")
        self.assertEqual(stats["uses"], 1)
        self.assertAlmostEqual(stats["avg_score"], 0.85, places=2)

    def test_recommend_over_alternative(self):
        """rank_skills returns higher-scoring skill first."""
        se = self._make()
        se.record_usage("skill-a", "t", 0.9)
        se.record_usage("skill-b", "t", 0.4)
        ranked = se.rank_skills(["skill-b", "skill-a"])
        self.assertEqual(ranked[0], "skill-a")

    def test_decay(self):
        """Scores older than 30 days are weighted less in avg_score calc."""
        se = self._make()
        # Manually insert an old record
        old_ts = time.time() - (31 * 86400)  # 31 days ago
        se._data["decay-skill"] = [
            {"score": 1.0, "task": "old", "ts": old_ts},
            {"score": 0.0, "task": "recent", "ts": time.time()},
        ]
        stats = se.get_stats("decay-skill")
        # With decay, old 1.0 score should be downweighted, bringing avg below 0.5
        # (if equal weight, avg would be 0.5; with decay old record < 0.5x weight)
        self.assertLess(stats["avg_score"], 0.5)


if __name__ == "__main__":
    unittest.main()
