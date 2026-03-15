"""Tests for tools/auto_skill_creator.py."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock


class TestAutoSkillCreator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.skills_dir = Path(self.tmp) / "auto-skills"

    def _make(self, effectiveness=None):
        from tools.auto_skill_creator import AutoSkillCreator
        return AutoSkillCreator(skills_dir=self.skills_dir, effectiveness=effectiveness)

    def test_create_from_outcome(self):
        creator = self._make()
        path = creator.create_skill_from_outcome(
            "deploy to railway",
            steps=["Install Railway CLI", "Run railway up"],
            score=0.9,
        )
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        self.assertTrue((path / "SKILL.md").exists())

    def test_skip_low_score(self):
        creator = self._make()
        path = creator.create_skill_from_outcome(
            "deploy to railway",
            steps=["step1"],
            score=0.7,  # below 0.8 threshold
        )
        self.assertIsNone(path)

    def test_skill_name_generated(self):
        creator = self._make()
        path = creator.create_skill_from_outcome(
            "Deploy App to Railway Cloud",
            steps=["step1"],
            score=0.9,
        )
        self.assertIsNotNone(path)
        # Name should be slugified
        self.assertIn("deploy", path.name.lower())
        self.assertNotIn(" ", path.name)

    def test_skill_dedup(self):
        creator = self._make()
        path1 = creator.create_skill_from_outcome(
            "build REST API",
            steps=["step1"],
            score=0.9,
        )
        path2 = creator.create_skill_from_outcome(
            "build REST API",
            steps=["step1", "step2"],
            score=0.95,
        )
        # Should return same path (no overwrite on dedup)
        self.assertEqual(path1, path2)

    def test_skill_has_frontmatter(self):
        creator = self._make()
        path = creator.create_skill_from_outcome(
            "setup CI/CD pipeline",
            steps=["Configure GitHub Actions"],
            score=0.85,
        )
        content = (path / "SKILL.md").read_text()
        self.assertIn("name:", content)
        self.assertIn("description:", content)
        self.assertIn("version:", content)

    def test_skill_has_steps(self):
        creator = self._make()
        steps = ["Run tests", "Build Docker image", "Push to registry"]
        path = creator.create_skill_from_outcome(
            "containerize app",
            steps=steps,
            score=0.88,
        )
        content = (path / "SKILL.md").read_text()
        for step in steps:
            self.assertIn(step, content)

    def test_skill_has_score(self):
        creator = self._make()
        path = creator.create_skill_from_outcome(
            "optimize database queries",
            steps=["Add indexes", "Use EXPLAIN"],
            score=0.92,
        )
        content = (path / "SKILL.md").read_text()
        self.assertIn("0.92", content)

    def test_skill_registers_with_effectiveness(self):
        mock_eff = MagicMock()
        creator = self._make(effectiveness=mock_eff)
        creator.create_skill_from_outcome(
            "write GraphQL schema",
            steps=["Define types"],
            score=0.9,
        )
        mock_eff.record_usage.assert_called_once()

    def test_skill_no_effectiveness_ok(self):
        """Works fine without effectiveness tracker."""
        creator = self._make(effectiveness=None)
        path = creator.create_skill_from_outcome(
            "parse JSON config",
            steps=["Load file", "Validate schema"],
            score=0.85,
        )
        self.assertIsNotNone(path)

    def test_update_existing_skill_skips(self):
        """Dedup: creating same skill twice returns existing path."""
        creator = self._make()
        path1 = creator.create_skill_from_outcome(
            "write async Python",
            steps=["Use asyncio"],
            score=0.8,
        )
        # Second call with higher score should still return existing
        path2 = creator.create_skill_from_outcome(
            "write async Python",
            steps=["Use asyncio", "Add error handling"],
            score=0.95,
        )
        self.assertEqual(path1, path2)
        # Content should be from first write (not overwritten)
        content = (path1 / "SKILL.md").read_text()
        # Should have original score
        self.assertIn("0.8", content)


if __name__ == "__main__":
    unittest.main()
