"""
CostTracker — per-run token spend tracking with budget cap.

Prevents unbounded spend on agentic loops. Configure via env:
  MAX_COST_PER_RUN_USD=2.00   — stop loop when $2 spent this run

Pricing table matches agent/insights.py MODEL_PRICING.
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# USD per million tokens — must stay in sync with agent/insights.py
MODEL_PRICING = {
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "claude-haiku": {"input": 0.80, "output": 4.00},
    "gpt-5": {"input": 10.00, "output": 30.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gemini-3": {"input": 1.25, "output": 10.00},
}


def _match_model(model: str) -> Optional[dict]:
    """Fuzzy-match model name to pricing entry."""
    model_lower = model.lower()
    for key, pricing in MODEL_PRICING.items():
        if key in model_lower:
            return pricing
    return None


class CostTracker:
    """Track per-run token spend with optional budget cap.

    Args:
        budget_usd: Maximum spend in USD. None means unlimited.
    """

    def __init__(self, budget_usd: Optional[float] = None):
        self.budget_usd = budget_usd
        self.spent_usd = 0.0
        self._calls = 0

    @classmethod
    def from_env(cls) -> "CostTracker":
        """Create a CostTracker from the MAX_COST_PER_RUN_USD environment variable.

        Returns an unlimited tracker if the env var is not set.
        """
        raw = os.environ.get("MAX_COST_PER_RUN_USD")
        budget = float(raw) if raw else None
        return cls(budget_usd=budget)

    def record_tokens(self, input_tokens: int, output_tokens: int, model: str = "") -> float:
        """Record token usage and return the cost for this call.

        Returns 0.0 for unknown models (conservative — don't crash).
        """
        pricing = _match_model(model)
        if not pricing:
            return 0.0
        cost = (input_tokens / 1_000_000) * pricing["input"] + \
               (output_tokens / 1_000_000) * pricing["output"]
        self.spent_usd += cost
        self._calls += 1
        return cost

    def is_over_budget(self) -> bool:
        """Return True when spent >= budget. Always False for unlimited trackers."""
        if self.budget_usd is None:
            return False
        return self.spent_usd >= self.budget_usd

    def summary(self) -> dict:
        """Return a summary dict with spent_usd, budget_usd, remaining_usd, pct_used."""
        remaining = (
            None if self.budget_usd is None
            else max(0.0, self.budget_usd - self.spent_usd)
        )
        pct = (
            0.0 if self.budget_usd is None
            else min(100.0, (self.spent_usd / self.budget_usd) * 100)
        )
        return {
            "spent_usd": round(self.spent_usd, 6),
            "budget_usd": self.budget_usd,
            "remaining_usd": round(remaining, 6) if remaining is not None else None,
            "pct_used": round(pct, 1),
        }
