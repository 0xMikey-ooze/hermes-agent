"""
AutoSkillCreator — automatically codify successful task outcomes as skills.

When a task completes with a high score (>= 0.8), this module generates
a SKILL.md file capturing the approach so future tasks can reuse it.

Features:
  - Slugifies task descriptions to create skill directory names
  - Writes YAML frontmatter + step-by-step instructions to SKILL.md
  - Deduplicates: does not overwrite existing skills with the same slug
  - Optionally records the new skill with SkillEffectiveness
"""
import logging
import re
import time
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

_SCORE_THRESHOLD = 0.8  # minimum score to codify


def _slugify(text: str) -> str:
    """Convert a task description to a URL/filename-safe slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    # Truncate to 50 chars to keep directory names reasonable
    return text[:50].rstrip("-")


def _render_skill_md(name: str, description: str, steps: List[str], score: float) -> str:
    """Render a SKILL.md file with YAML frontmatter and step list."""
    steps_block = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))
    return (
        f"---\n"
        f"name: {name}\n"
        f'description: "{description}"\n'
        f"version: 1.0.0\n"
        f"score: {score}\n"
        f"auto_generated: true\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"Auto-generated skill from a successful task outcome (score: {score}).\n\n"
        f"## Steps\n\n"
        f"{steps_block}\n"
    )


class AutoSkillCreator:
    """Codify successful task outcomes as reusable skill files.

    Args:
        skills_dir: Directory where new skill subdirectories will be created.
        effectiveness: Optional SkillEffectiveness tracker — records the new
                       skill's initial usage when it is created.
    """

    def __init__(self, skills_dir: Path, effectiveness: Any = None):
        self.skills_dir = Path(skills_dir)
        self._effectiveness = effectiveness

    def create_skill_from_outcome(
        self,
        task: str,
        steps: List[str],
        score: float,
    ) -> Optional[Path]:
        """Create a skill from a completed task if the score is high enough.

        Args:
            task: Human-readable task description (used as skill name/description).
            steps: List of implementation steps to record.
            score: Outcome quality score in [0, 1].

        Returns:
            Path to the created (or existing) skill directory, or None if score
            is below the threshold.
        """
        if score < _SCORE_THRESHOLD:
            return None

        slug = _slugify(task)
        skill_dir = self.skills_dir / slug

        # Dedup: if the skill already exists, return existing path without overwriting
        if skill_dir.exists():
            return skill_dir

        # Create the skill directory and SKILL.md
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = _render_skill_md(
            name=slug,
            description=task,
            steps=steps,
            score=score,
        )
        (skill_dir / "SKILL.md").write_text(content)

        # Security scan — consistent with hub installs
        if not self._security_scan(skill_dir):
            import shutil
            shutil.rmtree(skill_dir, ignore_errors=True)
            logger.warning("Auto-skill %s blocked by security scan", slug)
            return None

        # Register with effectiveness tracker if provided
        if self._effectiveness is not None:
            self._effectiveness.record_usage(slug, task, score)

        return skill_dir

    def _security_scan(self, skill_dir: Path) -> bool:
        """Returns True if skill passes security check, False if blocked."""
        try:
            from tools.skills_guard import scan_skill, should_allow_install
            result = scan_skill(skill_dir, source="auto-generated")
            allowed, _reason = should_allow_install(result, force=False)
            return allowed
        except ImportError:
            return True  # guard unavailable — proceed
        except Exception as e:
            logger.warning("Security scan error (proceeding): %s", e)
            return True
