"""
SkillGapDetector — detect when Hermes lacks skills for a task category.

Monitors task failures and fires a "gap" alert when a category accumulates
3+ consecutive failures. Integrates with SkillRecommender to suggest fixes
and posts gap events to the shared blackboard.

Categories are keyword-based: a task matches a category if any keyword
appears in the task description.
"""
from typing import Any, Callable, Dict, List, Optional


# Map of category name -> keywords that trigger that category
CATEGORIES: Dict[str, List[str]] = {
    "ml": ["machine learning", "ml", "training", "neural", "embedding", "model", "pytorch", "tensorflow"],
    "deploy": ["deploy", "deployment", "railway", "docker", "kubernetes", "k8s", "container", "cloud"],
    "testing": ["test", "tests", "tdd", "unit test", "pytest", "jest", "vitest", "coverage"],
    "frontend": ["react", "vue", "angular", "ui", "frontend", "css", "html", "component"],
    "database": ["database", "sql", "postgres", "mysql", "mongo", "migration", "query", "orm"],
    "api": ["api", "rest", "graphql", "endpoint", "http", "grpc", "openapi"],
    "security": ["security", "auth", "authentication", "authorization", "oauth", "jwt", "crypto"],
    "infra": ["infrastructure", "terraform", "ansible", "ci", "cd", "pipeline", "github actions"],
}

_GAP_THRESHOLD = 3  # failures before a gap is declared


def _detect_categories(task: str) -> List[str]:
    """Return list of category names that match the task description."""
    task_lower = task.lower()
    matched = []
    for cat, keywords in CATEGORIES.items():
        if any(kw in task_lower for kw in keywords):
            matched.append(cat)
    return matched


class SkillGapDetector:
    """Detect skill gaps from repeated task failures.

    Args:
        recommender: Optional SkillRecommender — called when a gap fires.
        blackboard_fn: Optional callable(topic, message) for posting to blackboard.
    """

    def __init__(
        self,
        recommender: Any = None,
        blackboard_fn: Optional[Callable] = None,
    ):
        self._recommender = recommender
        self._blackboard_fn = blackboard_fn
        # category -> failure count
        self._failures: Dict[str, int] = {}
        # categories that have already fired (to avoid repeat callbacks)
        self._fired: set = set()

    def _get_categories(self, task: str) -> List[str]:
        return _detect_categories(task)

    def register_failure(self, task: str):
        """Record a task failure; fires gap callback if threshold reached."""
        categories = self._get_categories(task)
        for cat in categories:
            self._failures[cat] = self._failures.get(cat, 0) + 1
            if self._failures[cat] >= _GAP_THRESHOLD and cat not in self._fired:
                self._fired.add(cat)
                self._on_gap_detected(cat, task)

    def register_success(self, task: str):
        """Record a task success; resets failure counts for its categories."""
        categories = self._get_categories(task)
        for cat in categories:
            self._failures[cat] = 0
            self._fired.discard(cat)

    def detect_gap(self, task: str) -> Optional[Dict]:
        """Check if there is a currently active gap for the task's categories.

        Returns a dict like {"gap": category_name} if a gap exists, else None.
        """
        categories = self._get_categories(task)
        for cat in categories:
            if self._failures.get(cat, 0) >= _GAP_THRESHOLD:
                return {"gap": cat}
        return None

    def _on_gap_detected(self, category: str, task: str):
        """Internal callback when a gap threshold is crossed."""
        gap_info = {
            "gap": category,
            "task": task,
            "failures": self._failures.get(category, 0),
        }

        # Ask recommender for skill suggestions
        if self._recommender:
            suggestions = self._recommender.recommend(task)
            gap_info["suggestions"] = suggestions

        # Post to blackboard
        if self._blackboard_fn:
            self._blackboard_fn("swarm/skill-gaps", gap_info)
