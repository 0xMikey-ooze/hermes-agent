"""Tests for tools/skill_gap_detector.py."""
import unittest
from unittest.mock import MagicMock


class TestSkillGapDetector(unittest.TestCase):
    def _make(self, recommender=None, blackboard_fn=None):
        from tools.skill_gap_detector import SkillGapDetector
        return SkillGapDetector(recommender=recommender, blackboard_fn=blackboard_fn)

    def test_no_gap_initial(self):
        detector = self._make()
        result = detector.detect_gap("build RAG pipeline")
        self.assertIsNone(result)

    def test_gap_detected(self):
        detector = self._make()
        # 3 failures on ML task
        for _ in range(3):
            detector.register_failure("train a machine learning model")
        gap = detector.detect_gap("train a machine learning model")
        self.assertIsNotNone(gap)
        self.assertIn("gap", gap)

    def test_gap_threshold(self):
        detector = self._make()
        detector.register_failure("deploy to docker")
        detector.register_failure("deploy to docker")
        # Only 2 failures — no gap yet
        gap = detector.detect_gap("deploy to docker")
        self.assertIsNone(gap)
        # 3rd failure — gap fires
        detector.register_failure("deploy to docker")
        gap = detector.detect_gap("deploy to docker")
        self.assertIsNotNone(gap)

    def test_gap_clears(self):
        detector = self._make()
        for _ in range(3):
            detector.register_failure("deploy to kubernetes")
        # Confirm gap is there
        self.assertIsNotNone(detector.detect_gap("deploy to kubernetes"))
        # One success clears it
        detector.register_success("deploy to kubernetes")
        self.assertIsNone(detector.detect_gap("deploy to kubernetes"))

    def test_gap_categories(self):
        detector = self._make()
        for _ in range(3):
            detector.register_failure("run machine learning training job")
        gap = detector.detect_gap("run machine learning training job")
        self.assertIsNotNone(gap)
        self.assertEqual(gap["gap"], "ml")

    def test_on_failure_callback(self):
        detector = self._make()
        detector.register_failure("write tests with TDD")
        from tools.skill_gap_detector import CATEGORIES
        cats = [cat for cat, kws in CATEGORIES.items()
                if any(kw in "write tests with TDD".lower() for kw in kws)]
        for cat in cats:
            self.assertEqual(detector._failures[cat], 1)

    def test_on_success_callback(self):
        detector = self._make()
        for _ in range(2):
            detector.register_failure("write unit tests")
        detector.register_success("write unit tests")
        # Failure count should be reset
        gap = detector.detect_gap("write unit tests")
        self.assertIsNone(gap)

    def test_gap_triggers_recommender(self):
        mock_rec = MagicMock()
        mock_rec.recommend.return_value = [{"name": "ml-engineer", "description": "ML"}]
        detector = self._make(recommender=mock_rec)
        for _ in range(3):
            detector.register_failure("train embedding model")
        # recommend should have been called when gap fired
        mock_rec.recommend.assert_called()

    def test_gap_reports_to_blackboard(self):
        mock_blackboard = MagicMock()
        detector = self._make(blackboard_fn=mock_blackboard)
        for _ in range(3):
            detector.register_failure("train neural network")
        mock_blackboard.assert_called_with("swarm/skill-gaps", unittest.mock.ANY)


if __name__ == "__main__":
    unittest.main()
