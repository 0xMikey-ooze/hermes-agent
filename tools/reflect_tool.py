"""Reflection/critic loop tool for self-review.

Provides pure-logic helpers for building reflection prompts and parsing
results. The actual LLM call is handled by the agent loop (this tool is
agent-loop-intercepted and needs parent_agent).

Usage:
    # Pure logic (unit-testable):
    from tools.reflect_tool import (
        ReflectionResult, parse_criteria, clamp_max_rounds,
        build_reflection_prompt,
    )

    # Tool is registered as "reflect" in the tool registry.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


MAX_REFLECTION_ROUNDS = 5

DEFAULT_CRITERIA = ["correctness", "completeness", "clarity"]


@dataclass
class ReflectionResult:
    """Result of a single reflection round."""
    passed: bool
    issues: List[str]
    suggestions: List[str]
    round_num: int


def parse_criteria(criteria: Union[str, List[str], None]) -> List[str]:
    """Parse criteria into a list of strings.

    Accepts comma-separated string, list, or None (returns defaults).
    """
    if criteria is None or (isinstance(criteria, str) and not criteria.strip()):
        return DEFAULT_CRITERIA
    if isinstance(criteria, list):
        return criteria
    return [c.strip() for c in criteria.split(",") if c.strip()]


def clamp_max_rounds(n: int) -> int:
    """Clamp max_rounds to [1, MAX_REFLECTION_ROUNDS]."""
    return max(1, min(n, MAX_REFLECTION_ROUNDS))


def build_reflection_prompt(content: str, criteria: List[str]) -> str:
    """Build the reflection/critic prompt for the LLM."""
    criteria_str = ", ".join(criteria)
    return (
        f"Review the following content against these criteria: {criteria_str}\n\n"
        f"CONTENT TO REVIEW:\n{content}\n\n"
        "Respond with a JSON object:\n"
        '{"passed": true/false, "issues": ["..."], "suggestions": ["..."]}\n\n'
        "If all criteria are met, set passed=true with empty issues. "
        "Otherwise list specific issues and actionable suggestions."
    )


def reflect(
    content: Optional[str] = None,
    criteria: Optional[Union[str, List[str]]] = None,
    max_rounds: int = 3,
    parent_agent=None,
) -> str:
    """Run the reflection/critic loop.

    This tool is agent-loop-intercepted: it needs parent_agent to call
    the LLM for critique. Without parent_agent, returns an error.
    """
    if parent_agent is None:
        return json.dumps({"error": "reflect requires a parent agent context."})

    if not content or not content.strip():
        return json.dumps({"error": "No content provided to reflect on."})

    parsed_criteria = parse_criteria(criteria)
    rounds = clamp_max_rounds(max_rounds)

    results = []
    current_content = content

    for round_num in range(1, rounds + 1):
        prompt = build_reflection_prompt(current_content, parsed_criteria)

        # Delegate to parent agent's LLM for the actual critique
        try:
            response = _call_parent_llm(parent_agent, prompt)
            parsed = _parse_reflection_response(response, round_num)
        except Exception as e:
            logger.warning("Reflection round %d failed: %s", round_num, e)
            parsed = ReflectionResult(
                passed=False,
                issues=[f"Reflection failed: {e}"],
                suggestions=[],
                round_num=round_num,
            )

        results.append({
            "round": parsed.round_num,
            "passed": parsed.passed,
            "issues": parsed.issues,
            "suggestions": parsed.suggestions,
        })

        if parsed.passed:
            break

    return json.dumps({
        "reflection_rounds": results,
        "final_passed": results[-1]["passed"] if results else False,
        "total_rounds": len(results),
    })


def _call_parent_llm(parent_agent, prompt: str) -> str:
    """Call the parent agent's LLM for a single reflection critique."""
    # Use the parent agent's simple completion method if available
    if hasattr(parent_agent, "simple_completion"):
        return parent_agent.simple_completion(prompt)
    # Fallback: return empty to signal no LLM available
    return "{}"


def _parse_reflection_response(response: str, round_num: int) -> ReflectionResult:
    """Parse the LLM's JSON response into a ReflectionResult."""
    try:
        data = json.loads(response)
        return ReflectionResult(
            passed=bool(data.get("passed", False)),
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
            round_num=round_num,
        )
    except (json.JSONDecodeError, TypeError):
        return ReflectionResult(
            passed=False,
            issues=["Could not parse reflection response"],
            suggestions=[],
            round_num=round_num,
        )


# ---------------------------------------------------------------------------
# OpenAI Function-Calling Schema
# ---------------------------------------------------------------------------

REFLECT_SCHEMA = {
    "name": "reflect",
    "description": (
        "Self-review content against specified criteria using a critic loop. "
        "Runs up to max_rounds of reflection, stopping early if all criteria pass.\n\n"
        "WHEN TO USE:\n"
        "- After generating code, text, or plans that need quality review\n"
        "- When you want to verify your work before presenting to the user\n"
        "- For iterative improvement of complex outputs\n\n"
        "The tool returns a structured summary of each reflection round, "
        "including issues found and suggestions for improvement."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The content to reflect on (code, text, plan, etc.)",
            },
            "criteria": {
                "type": "string",
                "description": (
                    "Comma-separated evaluation criteria. "
                    "Default: 'correctness, completeness, clarity'. "
                    "Examples: 'security, performance', 'readability, test coverage'"
                ),
            },
            "max_rounds": {
                "type": "integer",
                "description": "Maximum reflection rounds (1-5, default: 3). Stops early if all criteria pass.",
            },
        },
        "required": ["content"],
    },
}


# --- Registry ---
from tools.registry import registry

registry.register(
    name="reflect",
    toolset="reflection",
    schema=REFLECT_SCHEMA,
    handler=lambda args, **kw: reflect(
        content=args.get("content"),
        criteria=args.get("criteria"),
        max_rounds=args.get("max_rounds", 3),
        parent_agent=kw.get("parent_agent"),
    ),
)
