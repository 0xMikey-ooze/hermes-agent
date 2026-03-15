"""
SkillRecommender — finds relevant skills for a given task.

Searches locally installed skills (by keyword matching on SKILL.md frontmatter)
and optionally on a remote hub (GitHub skills marketplace).
"""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def _parse_frontmatter(text: str) -> Dict[str, str]:
    """Parse YAML-like frontmatter from a SKILL.md file."""
    result = {}
    in_front = False
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            in_front = True
            continue
        if in_front and line.strip() == "---":
            break
        if in_front and ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def _tokenize(text: str) -> List[str]:
    """Split text into lowercase tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _score_match(query_tokens: List[str], skill_text: str) -> int:
    """Return count of query tokens that appear in skill_text."""
    skill_tokens = set(_tokenize(skill_text))
    return sum(1 for t in query_tokens if t in skill_tokens)


class SkillRecommender:
    """Find and recommend skills for tasks.

    Args:
        skills_dir: Path to directory containing installed skill subdirectories.
        hub: Optional hub object with .search(query) -> list and .install(name, url) methods.
        effectiveness: Optional SkillEffectiveness instance for effectiveness-ranked results.
    """

    def __init__(self, skills_dir: Path, hub: Any = None, effectiveness: Any = None):
        self.skills_dir = Path(skills_dir)
        self.hub = hub
        self.effectiveness = effectiveness
        self._installed_cache: Optional[Dict[str, Dict]] = None

    def _load_installed(self) -> Dict[str, Dict]:
        """Load all locally installed skills from their SKILL.md files."""
        if self._installed_cache is not None:
            return self._installed_cache
        skills = {}
        if self.skills_dir.exists():
            for skill_dir in self.skills_dir.iterdir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    text = skill_md.read_text()
                    meta = _parse_frontmatter(text)
                    name = meta.get("name") or skill_dir.name
                    skills[name] = {
                        "name": name,
                        "description": meta.get("description", ""),
                        "installed": True,
                        "path": str(skill_dir),
                    }
        self._installed_cache = skills
        return skills

    def search(self, query: str, min_score: int = 1) -> List[Dict]:
        """Search locally installed skills by keyword matching.

        Returns list of matching skill dicts, sorted by relevance score descending.
        Each result includes a 'score' field with the keyword match count.
        """
        query_tokens = _tokenize(query)
        installed = self._load_installed()
        results = []
        for skill in installed.values():
            text = f"{skill['name']} {skill['description']}"
            score = _score_match(query_tokens, text)
            if score >= min_score:
                results.append({**skill, "score": score})
        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    def search_github(self, query: str, limit: int = 5) -> List[Dict]:
        """Search the remote hub for skills matching query.

        Returns at most `limit` results (default 5).
        """
        if not self.hub:
            return []
        results = self.hub.search(query)
        return results[:limit]

    def recommend(self, task: str) -> List[Dict]:
        """Recommend skills for a task.

        Returns locally installed matching skills (marked installed=True) plus
        remote hub results that are NOT already installed. Already-installed
        skills are filtered out of the remote results to avoid noise.

        When an effectiveness tracker is provided, results are sorted by
        effectiveness score descending, then keyword match score descending.
        Unrated skills (0 uses) are sorted after rated skills.
        """
        local_results = self.search(task)
        installed_names = {s["name"] for s in self._load_installed().values()}

        remote_results = []
        if self.hub:
            hub_results = self.search_github(task)
            for r in hub_results:
                if r["name"] not in installed_names:
                    remote_results.append({**r, "installed": False})

        combined = local_results + remote_results

        if self.effectiveness:
            # Sort by effectiveness score desc, then keyword score desc.
            # Unrated skills (uses=0) get avg_score=0.0 and sort after rated skills
            # by using -1.0 as the sort key so they reliably come last.
            def _sort_key(r):
                stats = self.effectiveness.get_stats(r["name"])
                if stats["uses"] == 0:
                    eff_score = -1.0
                else:
                    eff_score = stats["avg_score"]
                return (-eff_score, -r.get("score", 0))

            combined.sort(key=_sort_key)

        return combined[:5]

    def install(self, name: str, url: str) -> bool:
        """Install a skill from a remote URL via the hub.

        Returns True on success, False if no hub is configured.
        """
        if not self.hub:
            return False
        self.hub.install(name, url)
        # Invalidate cache so newly installed skill appears
        self._installed_cache = None
        return True
