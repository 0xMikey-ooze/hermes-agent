"""Tests for tools/cost_tracker.py — CostTracker budget cap."""
import os
import unittest


class TestCostTrackerInit(unittest.TestCase):
    def test_cost_tracker_init(self):
        """CostTracker(budget_usd=1.0) initializes with zero spent."""
        from tools.cost_tracker import CostTracker
        tracker = CostTracker(budget_usd=1.0)
        self.assertEqual(tracker.spent_usd, 0.0)
        self.assertEqual(tracker.budget_usd, 1.0)

    def test_cost_tracker_no_budget(self):
        """CostTracker(budget_usd=None) never returns over_budget (unlimited)."""
        from tools.cost_tracker import CostTracker
        tracker = CostTracker(budget_usd=None)
        # Record a huge amount
        tracker.record_tokens(input_tokens=10_000_000, output_tokens=10_000_000, model="claude-opus-4")
        self.assertFalse(tracker.is_over_budget())


class TestCostTrackerRecord(unittest.TestCase):
    def test_cost_tracker_record(self):
        """record_tokens updates spent_usd for a known model."""
        from tools.cost_tracker import CostTracker
        tracker = CostTracker(budget_usd=10.0)
        cost = tracker.record_tokens(input_tokens=1000, output_tokens=500, model="claude-opus-4-6")
        # claude-opus-4 pricing: $15/M input, $75/M output
        # expected: 1000/1M * 15 + 500/1M * 75 = 0.015 + 0.0375 = 0.0000525
        # (model="claude-opus-4-6" should fuzzy-match "claude-opus-4")
        self.assertGreater(tracker.spent_usd, 0.0)
        self.assertAlmostEqual(cost, tracker.spent_usd, places=8)

    def test_cost_tracker_unknown_model(self):
        """Unknown model charges $0 (conservative — don't crash)."""
        from tools.cost_tracker import CostTracker
        tracker = CostTracker(budget_usd=1.0)
        cost = tracker.record_tokens(input_tokens=1000, output_tokens=500, model="unknown-model-xyz")
        self.assertEqual(cost, 0.0)
        self.assertEqual(tracker.spent_usd, 0.0)


class TestCostTrackerBudget(unittest.TestCase):
    def test_cost_tracker_under_budget(self):
        """is_over_budget() returns False when spent < budget."""
        from tools.cost_tracker import CostTracker
        tracker = CostTracker(budget_usd=100.0)
        tracker.record_tokens(input_tokens=100, output_tokens=50, model="claude-haiku")
        self.assertFalse(tracker.is_over_budget())

    def test_cost_tracker_over_budget(self):
        """is_over_budget() returns True when spent >= budget."""
        from tools.cost_tracker import CostTracker
        tracker = CostTracker(budget_usd=0.000001)  # $0.000001 — tiny budget
        tracker.record_tokens(input_tokens=1_000_000, output_tokens=1_000_000, model="claude-opus-4")
        self.assertTrue(tracker.is_over_budget())


class TestCostTrackerFromEnv(unittest.TestCase):
    def setUp(self):
        os.environ.pop("MAX_COST_PER_RUN_USD", None)

    def tearDown(self):
        os.environ.pop("MAX_COST_PER_RUN_USD", None)

    def test_cost_tracker_from_env(self):
        """CostTracker.from_env() reads MAX_COST_PER_RUN_USD env var."""
        os.environ["MAX_COST_PER_RUN_USD"] = "2.50"
        from tools.cost_tracker import CostTracker
        tracker = CostTracker.from_env()
        self.assertAlmostEqual(tracker.budget_usd, 2.50)

    def test_cost_tracker_from_env_unset(self):
        """CostTracker.from_env() returns unlimited tracker when env unset."""
        # Ensure unset
        os.environ.pop("MAX_COST_PER_RUN_USD", None)
        from tools.cost_tracker import CostTracker
        tracker = CostTracker.from_env()
        self.assertIsNone(tracker.budget_usd)
        self.assertFalse(tracker.is_over_budget())


class TestCostTrackerSummary(unittest.TestCase):
    def test_cost_tracker_summary(self):
        """summary() returns { spent_usd, budget_usd, remaining_usd, pct_used }."""
        from tools.cost_tracker import CostTracker
        tracker = CostTracker(budget_usd=1.0)
        tracker.record_tokens(input_tokens=1_000_000, output_tokens=0, model="gpt-4o")
        # gpt-4o: $2.50/M input → spent = $0.0025
        summary = tracker.summary()
        self.assertIn("spent_usd", summary)
        self.assertIn("budget_usd", summary)
        self.assertIn("remaining_usd", summary)
        self.assertIn("pct_used", summary)
        self.assertAlmostEqual(summary["budget_usd"], 1.0)
        self.assertGreater(summary["spent_usd"], 0.0)
        self.assertLess(summary["remaining_usd"], 1.0)
        self.assertGreater(summary["pct_used"], 0.0)

    def test_cost_tracker_summary_no_budget(self):
        """summary() with unlimited budget has None for remaining_usd."""
        from tools.cost_tracker import CostTracker
        tracker = CostTracker(budget_usd=None)
        summary = tracker.summary()
        self.assertIsNone(summary["budget_usd"])
        self.assertIsNone(summary["remaining_usd"])
        self.assertEqual(summary["pct_used"], 0.0)


if __name__ == "__main__":
    unittest.main()
