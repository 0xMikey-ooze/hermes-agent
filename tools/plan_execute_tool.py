"""Architect/coder split tool.

Separates planning (architect phase) from implementation (coder phase),
preventing the agent from diving into code without a plan.

The architect uses the "researcher" role preset (read-only tools),
while the coder uses the "coder" role preset (file + terminal tools).

Pure logic (plan management, state transitions) is unit-testable.
Actual delegation is agent-loop-intercepted.

Usage:
    from tools.plan_execute_tool import (
        PlanStep, ExecutionPlan, advance_plan, is_plan_complete,
        get_role_for_phase,
    )
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    description: str
    status: str = "pending"  # pending, in_progress, done, failed
    substeps: List[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    """An ordered plan of steps to achieve a goal."""
    goal: str
    steps: List[PlanStep]
    current_step_index: int = 0


def advance_plan(plan: ExecutionPlan) -> ExecutionPlan:
    """Mark the current step as done and advance to the next.

    Returns a new ExecutionPlan (does not mutate the input).
    """
    if not plan.steps or plan.current_step_index >= len(plan.steps):
        return ExecutionPlan(
            goal=plan.goal,
            steps=[PlanStep(s.description, s.status, list(s.substeps)) for s in plan.steps],
            current_step_index=plan.current_step_index,
        )

    new_steps = [PlanStep(s.description, s.status, list(s.substeps)) for s in plan.steps]
    new_steps[plan.current_step_index].status = "done"

    new_index = plan.current_step_index + 1
    if new_index < len(new_steps):
        new_steps[new_index].status = "in_progress"

    return ExecutionPlan(goal=plan.goal, steps=new_steps, current_step_index=new_index)


def is_plan_complete(plan: ExecutionPlan) -> bool:
    """Check if all steps in the plan have been processed."""
    if not plan.steps:
        return True
    return plan.current_step_index >= len(plan.steps)


def get_role_for_phase(phase: str) -> str:
    """Map a plan/execute phase to a role preset name."""
    mapping = {
        "architect": "researcher",
        "coder": "coder",
        "reviewer": "reviewer",
    }
    return mapping.get(phase, "default")


def plan_execute(
    goal: Optional[str] = None,
    context: Optional[str] = None,
    parent_agent=None,
) -> str:
    """Initialize an architect/coder split workflow.

    Agent-loop-intercepted: needs parent_agent for delegation.
    """
    if parent_agent is None:
        return json.dumps({"error": "plan_execute requires a parent agent context."})

    if not goal or not goal.strip():
        return json.dumps({"error": "No goal provided."})

    return json.dumps({
        "status": "plan_execute_initialized",
        "goal": goal,
        "context": context,
        "phases": [
            {
                "phase": "architect",
                "role": "researcher",
                "description": "Research and create a detailed implementation plan",
            },
            {
                "phase": "coder",
                "role": "coder",
                "description": "Execute the plan step by step",
            },
        ],
        "message": (
            "Plan/Execute pipeline initialized. The agent should:\n"
            "1. ARCHITECT PHASE: Research the codebase and create a step-by-step plan "
            "(using researcher role - read-only tools)\n"
            "2. CODER PHASE: Execute each step of the plan "
            "(using coder role - file + terminal tools)\n"
            "3. Review the results against the original goal"
        ),
    })


# ---------------------------------------------------------------------------
# OpenAI Function-Calling Schema
# ---------------------------------------------------------------------------

PLAN_EXECUTE_SCHEMA = {
    "name": "plan_execute",
    "description": (
        "Split a complex task into architect (planning) and coder (execution) phases.\n\n"
        "Phase 1 - ARCHITECT: Uses researcher role (read-only tools) to:\n"
        "- Explore the codebase and understand existing patterns\n"
        "- Create a detailed, step-by-step implementation plan\n"
        "- Identify files to modify and potential risks\n\n"
        "Phase 2 - CODER: Uses coder role (file + terminal tools) to:\n"
        "- Execute each step of the architect's plan\n"
        "- Write code, run tests, and verify correctness\n\n"
        "WHEN TO USE:\n"
        "- Complex features requiring research before coding\n"
        "- Tasks where jumping straight to code leads to poor results\n"
        "- When you need to understand existing patterns before modifying code"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "The high-level goal to accomplish.",
            },
            "context": {
                "type": "string",
                "description": (
                    "Additional context: relevant file paths, constraints, "
                    "existing patterns to follow, etc."
                ),
            },
        },
        "required": ["goal"],
    },
}


# --- Registry ---
from tools.registry import registry

registry.register(
    name="plan_execute",
    toolset="plan_execute",
    schema=PLAN_EXECUTE_SCHEMA,
    handler=lambda args, **kw: plan_execute(
        goal=args.get("goal"),
        context=args.get("context"),
        parent_agent=kw.get("parent_agent"),
    ),
)
