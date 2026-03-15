"""Tests for tools/skill_recommender.py."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_skills_dir(tmp_path: Path, skills: dict) -> Path:
    """Create a temp skills dir with SKILL.md files."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    for name, desc in skills.items():
        skill_dir = skills_dir / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f'---\nname: {name}\ndescription: "{desc}"\nversion: 1.0.0\n---\n# {name}\n'
        )
    return skills_dir


class TestSkillSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp)
        self.skills_dir = _make_skills_dir(self.tmp_path, {
            "hermes-deployment": "deploy applications to railway and cloud",
            "rag-engineer": "build RAG pipelines with embeddings",
            "react-components": "build React UI components",
        })

    def test_search_local_match(self):
        from tools.skill_recommender import SkillRecommender
        rec = SkillRecommender(self.skills_dir)
        results = rec.search("deploy to railway")
        names = [r["name"] for r in results]
        self.assertIn("hermes-deployment", names)

    def test_search_no_match(self):
        from tools.skill_recommender import SkillRecommender
        rec = SkillRecommender(self.skills_dir)
        results = rec.search("quantum teleportation")
        self.assertEqual(results, [])

    def test_search_github(self):
        from tools.skill_recommender import SkillRecommender
        mock_hub = MagicMock()
        mock_hub.search.return_value = [
            {"name": "react-testing", "description": "test React components"},
            {"name": "vitest-setup", "description": "vitest testing setup"},
        ]
        rec = SkillRecommender(self.skills_dir, hub=mock_hub)
        results = rec.search_github("react testing")
        mock_hub.search.assert_called_once_with("react testing")
        self.assertIsInstance(results, list)

    def test_search_github_returns_top5(self):
        from tools.skill_recommender import SkillRecommender
        mock_hub = MagicMock()
        mock_hub.search.return_value = [
            {"name": f"skill-{i}", "description": f"desc {i}"}
            for i in range(10)
        ]
        rec = SkillRecommender(self.skills_dir, hub=mock_hub)
        results = rec.search_github("anything")
        self.assertLessEqual(len(results), 5)

    def test_recommend_for_task(self):
        from tools.skill_recommender import SkillRecommender
        rec = SkillRecommender(self.skills_dir)
        results = rec.recommend("I need to build a RAG pipeline")
        self.assertIsInstance(results, list)
        # Should find rag-engineer
        names = [r["name"] for r in results]
        self.assertIn("rag-engineer", names)

    def test_recommend_filters_installed(self):
        from tools.skill_recommender import SkillRecommender
        mock_hub = MagicMock()
        mock_hub.search.return_value = [
            {"name": "hermes-deployment", "description": "deploy to railway"},
            {"name": "new-deploy-skill", "description": "deploy to cloud"},
        ]
        rec = SkillRecommender(self.skills_dir, hub=mock_hub)
        results = rec.recommend("deploy to railway")
        # hermes-deployment is already installed; new-deploy-skill from hub should appear
        remote_names = [r["name"] for r in results if not r.get("installed")]
        # The installed skill should not appear in remote results
        self.assertNotIn("hermes-deployment", remote_names)

    def test_recommend_empty_if_all_installed(self):
        from tools.skill_recommender import SkillRecommender
        mock_hub = MagicMock()
        mock_hub.search.return_value = []
        rec = SkillRecommender(self.skills_dir, hub=mock_hub)
        # Weird query that doesn't match anything
        results = rec.recommend("quantum teleportation")
        self.assertEqual(results, [])

    def test_install_skill(self):
        from tools.skill_recommender import SkillRecommender
        mock_hub = MagicMock()
        mock_hub.install.return_value = None  # success
        rec = SkillRecommender(self.skills_dir, hub=mock_hub)
        success = rec.install("new-skill", "https://github.com/foo/bar")
        self.assertTrue(success)
        mock_hub.install.assert_called_once_with("new-skill", "https://github.com/foo/bar")

    def test_install_skill_no_hub(self):
        from tools.skill_recommender import SkillRecommender
        rec = SkillRecommender(self.skills_dir, hub=None)
        success = rec.install("new-skill", "https://github.com/foo/bar")
        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main()
