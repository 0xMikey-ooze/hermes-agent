"""
SkillEffectiveness — track how well each skill performs over time.

Records per-skill usage scores with time-decay weighting. Older scores
(> 30 days) count less toward the weighted average, so recent performance
dominates. Data is persisted to a JSON file so stats survive restarts.
"""
import json
import math
import time
from pathlib import Path
from typing import Dict, List, Optional


_DEFAULT_STORAGE = Path.home() / ".hermes" / "skill_effectiveness.json"
_SUCCESS_THRESHOLD = 0.7   # score >= this is counted as success
_MIN_USES_FOR_WORST = 3    # need at least this many uses to flag as worst
_DECAY_HALF_LIFE_DAYS = 30  # score weight halves every 30 days


def _decay_weight(ts: float) -> float:
    """Return a weight in (0, 1] based on age of the record.

    Uses exponential decay: weight = 0.5 ^ (age_days / half_life).
    A record from today has weight 1.0; one from 30 days ago has weight 0.5.
    """
    age_days = (time.time() - ts) / 86400
    return math.pow(0.5, age_days / _DECAY_HALF_LIFE_DAYS)


class SkillEffectiveness:
    """Track and persist skill usage scores.

    Args:
        storage_path: Path to JSON file for persistence. Defaults to
                      ~/.hermes/skill_effectiveness.json.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self._path = Path(storage_path) if storage_path else _DEFAULT_STORAGE
        self._data: Dict[str, List[Dict]] = {}
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────

    def _load(self):
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    # ── Recording ─────────────────────────────────────────────────────────

    def record_usage(self, skill_name: str, task: str, score: float):
        """Record a usage event for a skill.

        Args:
            skill_name: The skill identifier.
            task: Description of the task the skill was used for.
            score: Quality score in [0, 1] where 1.0 is perfect.
        """
        if skill_name not in self._data:
            self._data[skill_name] = []
        self._data[skill_name].append({
            "score": score,
            "task": task,
            "ts": time.time(),
        })
        self._save()

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_stats(self, skill_name: str) -> Dict:
        """Return stats for a skill.

        Returns:
            dict with keys: uses (int), avg_score (float), success_rate (float)
        """
        records = self._data.get(skill_name, [])
        if not records:
            return {"uses": 0, "avg_score": 0.0, "success_rate": 0.0}

        uses = len(records)

        # Weighted average with time decay
        total_weight = 0.0
        weighted_sum = 0.0
        successes = 0
        for rec in records:
            w = _decay_weight(rec["ts"])
            total_weight += w
            weighted_sum += rec["score"] * w
            if rec["score"] >= _SUCCESS_THRESHOLD:
                successes += 1

        avg_score = weighted_sum / total_weight if total_weight > 0 else 0.0
        success_rate = successes / uses if uses > 0 else 0.0

        return {
            "uses": uses,
            "avg_score": avg_score,
            "success_rate": success_rate,
        }

    def rank_skills(self, skill_names: List[str]) -> List[str]:
        """Return skill_names sorted by avg_score descending.

        Unrated skills (0 uses) are sorted last.
        """
        def sort_key(name):
            stats = self.get_stats(name)
            # Use -1 for unrated skills so they sort last
            if stats["uses"] == 0:
                return -1.0
            return stats["avg_score"]

        return sorted(skill_names, key=sort_key, reverse=True)

    def worst_skills(self, threshold: float = 0.5) -> List[str]:
        """Return skill names whose avg_score < threshold with >= min_uses uses.

        Skills with too few uses are excluded (unreliable data).
        """
        worst = []
        for skill_name, records in self._data.items():
            if len(records) < _MIN_USES_FOR_WORST:
                continue
            stats = self.get_stats(skill_name)
            if stats["avg_score"] < threshold:
                worst.append(skill_name)
        return worst
