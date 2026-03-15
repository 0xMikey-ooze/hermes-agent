"""Tests for effectiveness-ranked SkillRecommender.recommend()."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock


def _make_skills_dir(tmp_path: Path, skills: dict) -> Path:
    """Create a temp skills dir with SKILL.md files."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    for name, desc in skills.items():
        skill_dir = skills_dir / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f'---\nname: {name}\ndescription: "{desc}"\nversion: 1.0.0\n---\n# {name}\n'
        )
    return skills_dir


def _make_effectiveness(scores: dict):
    """Create mock effectiveness tracker with given avg_scores."""
    mock = MagicMock()

    def get_stats(name):
        score = scores.get(name, None)
        if score is None:
            return {"uses": 0, "avg_score": 0.0, "success_rate": 0.0}
        return {"uses": 5, "avg_score": score, "success_rate": score}

    mock.get_stats.side_effect = get_stats
    return mock


class TestRecommendRanksByEffectiveness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)
        # Both skills match "deploy" query
        self.skills_dir = _make_skills_dir(self.tmp_path, {
            "low-skill": "deploy applications to server",
            "high-skill": "deploy apps to cloud",
        })

    def test_recommend_ranks_by_effectiveness(self):
        """Skill with avg_score=0.9 appears before skill with avg_score=0.2."""
        from tools.skill_recommender import SkillRecommender

        effectiveness = _make_effectiveness({
            "high-skill": 0.9,
            "low-skill": 0.2,
        })
        rec = SkillRecommender(self.skills_dir, effectiveness=effectiveness)
        results = rec.recommend("deploy application")
        names = [r["name"] for r in results]
        self.assertIn("high-skill", names)
        self.assertIn("low-skill", names)
        self.assertLess(names.index("high-skill"), names.index("low-skill"),
                        f"high-skill should appear before low-skill, got: {names}")

    def test_recommend_unrated_skills_last(self):
        """Skills with 0 uses appear after rated skills."""
        from tools.skill_recommender import SkillRecommender

        # high-skill has uses=5, unrated-skill has uses=0
        effectiveness = _make_effectiveness({
            "high-skill": 0.8,
            # low-skill: not in dict → uses=0
        })
        rec = SkillRecommender(self.skills_dir, effectiveness=effectiveness)
        results = rec.recommend("deploy application")
        names = [r["name"] for r in results]
        if "high-skill" in names and "low-skill" in names:
            self.assertLess(names.index("high-skill"), names.index("low-skill"),
                            "rated skill should appear before unrated skill")

    def test_recommend_no_effectiveness_tracker(self):
        """When no tracker provided, falls back to keyword-only ranking (no crash)."""
        from tools.skill_recommender import SkillRecommender

        rec = SkillRecommender(self.skills_dir, effectiveness=None)
        # Should not crash
        results = rec.recommend("deploy application")
        self.assertIsInstance(results, list)

    def test_recommend_ties_broken_by_keyword_score(self):
        """When effectiveness scores equal, higher keyword match wins."""
        from tools.skill_recommender import SkillRecommender

        # Add a more keyword-rich skill
        extra_skills_dir = _make_skills_dir(self.tmp_path / "extra", {
            "exact-deploy": "deploy deploy deploy apps to cloud services",  # high keyword score
            "vague-deploy": "deploy things",  # low keyword score
        })

        # Both have same effectiveness score
        effectiveness = _make_effectiveness({
            "exact-deploy": 0.5,
            "vague-deploy": 0.5,
        })
        rec = SkillRecommender(extra_skills_dir, effectiveness=effectiveness)
        results = rec.recommend("deploy apps to cloud services")
        names = [r["name"] for r in results]
        if "exact-deploy" in names and "vague-deploy" in names:
            self.assertLess(names.index("exact-deploy"), names.index("vague-deploy"),
                            "higher keyword match should win on ties")


if __name__ == "__main__":
    unittest.main()
