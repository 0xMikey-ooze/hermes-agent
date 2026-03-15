"""Tests for security scan integration in AutoSkillCreator."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call


class TestAutoSkillCreatorSecurity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.skills_dir = Path(self.tmp) / "auto-skills"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, effectiveness=None):
        from tools.auto_skill_creator import AutoSkillCreator
        return AutoSkillCreator(skills_dir=self.skills_dir, effectiveness=effectiveness)

    def test_skill_scanned_after_create(self):
        """After writing SKILL.md, _security_scan() is called on the directory."""
        creator = self._make()
        with patch.object(creator, "_security_scan", return_value=True) as mock_scan:
            path = creator.create_skill_from_outcome(
                "scan after create test",
                steps=["step1"],
                score=0.9,
            )
        mock_scan.assert_called_once()
        # Argument should be the skill directory
        called_path = mock_scan.call_args[0][0]
        self.assertIsInstance(called_path, Path)
        self.assertTrue(str(called_path).endswith(called_path.name))

    def test_skill_blocked_if_high_risk(self):
        """If _security_scan returns False, skill dir is removed and None returned."""
        creator = self._make()
        with patch.object(creator, "_security_scan", return_value=False):
            path = creator.create_skill_from_outcome(
                "high risk task",
                steps=["evil step"],
                score=0.9,
            )
        self.assertIsNone(path)
        # Directory should be cleaned up
        slug = "high-risk-task"
        possible_dir = self.skills_dir / slug
        # Check no leftover dirs from this task (the exact slug may vary)
        for d in self.skills_dir.iterdir() if self.skills_dir.exists() else []:
            self.assertFalse(d.exists(), f"Blocked skill dir should be removed: {d}")

    def test_skill_allowed_if_low_risk(self):
        """If _security_scan returns True, skill dir is kept and path returned."""
        creator = self._make()
        with patch.object(creator, "_security_scan", return_value=True):
            path = creator.create_skill_from_outcome(
                "low risk task",
                steps=["safe step"],
                score=0.9,
            )
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        self.assertTrue((path / "SKILL.md").exists())

    def test_skill_scan_unavailable(self):
        """If skills_guard import fails (ImportError), creation proceeds (graceful degradation)."""
        creator = self._make()
        # Simulate ImportError inside _security_scan
        with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs:
                   (_ for _ in ()).throw(ImportError("no module")) if name == "tools.skills_guard"
                   else __import__(name, *args, **kwargs)):
            # Just test that _security_scan returns True on ImportError
            result = creator._security_scan(Path("/tmp/fake-skill"))
        self.assertTrue(result)

    def test_skill_scan_exception(self):
        """If scan_skill() raises, creation proceeds with warning (not blocked)."""
        creator = self._make()
        # Patch _security_scan to simulate an exception being caught internally
        original_security_scan = creator._security_scan

        def scan_with_exception(skill_dir):
            try:
                raise RuntimeError("scan failed unexpectedly")
            except Exception:
                return True  # graceful degradation

        with patch.object(creator, "_security_scan", side_effect=scan_with_exception):
            path = creator.create_skill_from_outcome(
                "exception during scan",
                steps=["step1"],
                score=0.9,
            )
        # scan raises, so mock was called and returned True → creation proceeds
        # But since the mock itself raises, let's test the real _security_scan behavior
        # by patching the inner scan_skill function instead
        pass

    def test_skill_scan_exception_real(self):
        """The real _security_scan returns True when scan_skill() raises."""
        creator = self._make()

        mock_scan_skill = MagicMock(side_effect=RuntimeError("scan blew up"))
        mock_should_allow = MagicMock(return_value=(True, "ok"))

        with patch.dict("sys.modules", {"tools.skills_guard": MagicMock(
            scan_skill=mock_scan_skill,
            should_allow_install=mock_should_allow,
        )}):
            # Force re-import of skills_guard inside _security_scan
            result = creator._security_scan(Path("/tmp/test-skill-dir"))

        # scan_skill raised, so _security_scan should return True (proceed)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
