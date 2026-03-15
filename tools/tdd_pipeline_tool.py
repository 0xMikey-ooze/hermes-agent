"""Spec-first TDD pipeline tool.

Orchestrates the red-green-refactor cycle as a state machine:
  spec -> implement -> test -> fix -> test (loop until green or max_iterations)

Pure logic (state machine, test output parsing) is unit-testable.
The actual code generation and test execution are agent-loop-intercepted.

Usage:
    from tools.tdd_pipeline_tool import TDDState, advance_phase, parse_test_output
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TestSummary:
    """Parsed test execution results."""
    passed: int = 0
    failed: int = 0
    errors: int = 0
    output: str = ""


@dataclass
class TDDState:
    """State of the TDD pipeline."""
    spec: str
    phase: str = "spec"  # spec, implement, test, fix, done, max_iterations_reached
    code: Optional[str] = None
    test_results: Optional[TestSummary] = None
    iteration: int = 0
    max_iterations: int = 5


def advance_phase(state: TDDState) -> TDDState:
    """Advance the TDD state machine to the next phase.

    Returns a new TDDState (does not mutate the input).
    """
    if state.phase == "spec":
        return TDDState(
            spec=state.spec, phase="implement", code=state.code,
            test_results=state.test_results, iteration=state.iteration,
            max_iterations=state.max_iterations,
        )

    if state.phase == "implement":
        return TDDState(
            spec=state.spec, phase="test", code=state.code,
            test_results=state.test_results, iteration=state.iteration,
            max_iterations=state.max_iterations,
        )

    if state.phase == "test":
        results = state.test_results
        all_pass = results and results.failed == 0 and results.errors == 0 and results.passed > 0

        if all_pass:
            return TDDState(
                spec=state.spec, phase="done", code=state.code,
                test_results=state.test_results, iteration=state.iteration,
                max_iterations=state.max_iterations,
            )

        new_iteration = state.iteration + 1
        if new_iteration >= state.max_iterations:
            return TDDState(
                spec=state.spec, phase="max_iterations_reached", code=state.code,
                test_results=state.test_results, iteration=new_iteration,
                max_iterations=state.max_iterations,
            )

        return TDDState(
            spec=state.spec, phase="fix", code=state.code,
            test_results=state.test_results, iteration=new_iteration,
            max_iterations=state.max_iterations,
        )

    if state.phase == "fix":
        return TDDState(
            spec=state.spec, phase="test", code=state.code,
            test_results=state.test_results, iteration=state.iteration,
            max_iterations=state.max_iterations,
        )

    # done or max_iterations_reached — stay in place
    return TDDState(
        spec=state.spec, phase=state.phase, code=state.code,
        test_results=state.test_results, iteration=state.iteration,
        max_iterations=state.max_iterations,
    )


def parse_test_output(output: str) -> TestSummary:
    """Parse pytest-style output into a TestSummary."""
    passed = 0
    failed = 0
    errors = 0

    # Match patterns like "5 passed", "2 failed", "1 error"
    passed_match = re.search(r"(\d+)\s+passed", output)
    failed_match = re.search(r"(\d+)\s+failed", output)
    error_match = re.search(r"(\d+)\s+error", output)

    if passed_match:
        passed = int(passed_match.group(1))
    if failed_match:
        failed = int(failed_match.group(1))
    if error_match:
        errors = int(error_match.group(1))

    return TestSummary(passed=passed, failed=failed, errors=errors, output=output)


def tdd_pipeline(
    spec: Optional[str] = None,
    max_iterations: int = 5,
    parent_agent=None,
) -> str:
    """Run the TDD pipeline for a given spec.

    Agent-loop-intercepted: needs parent_agent for code generation and
    test execution.
    """
    if parent_agent is None:
        return json.dumps({"error": "tdd_pipeline requires a parent agent context."})

    if not spec or not spec.strip():
        return json.dumps({"error": "No spec provided."})

    state = TDDState(spec=spec, max_iterations=max(1, min(max_iterations, 10)))

    return json.dumps({
        "status": "pipeline_initialized",
        "spec": state.spec,
        "phase": state.phase,
        "max_iterations": state.max_iterations,
        "message": (
            "TDD pipeline initialized. The agent should now:\n"
            "1. Write test file based on the spec\n"
            "2. Run tests (expect RED)\n"
            "3. Implement code to make tests pass\n"
            "4. Run tests again (expect GREEN)\n"
            "5. Refactor if needed"
        ),
    })


# ---------------------------------------------------------------------------
# OpenAI Function-Calling Schema
# ---------------------------------------------------------------------------

TDD_PIPELINE_SCHEMA = {
    "name": "tdd_pipeline",
    "description": (
        "Initialize a spec-first TDD (Test-Driven Development) pipeline.\n\n"
        "The pipeline follows the red-green-refactor cycle:\n"
        "1. Write tests from the spec (RED - tests fail)\n"
        "2. Implement code to pass tests (GREEN)\n"
        "3. Refactor while keeping tests green\n\n"
        "WHEN TO USE:\n"
        "- When implementing new features that benefit from test-first approach\n"
        "- When the user explicitly requests TDD\n"
        "- For complex logic where having tests first prevents bugs\n\n"
        "Provide a clear spec describing the expected behavior."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "spec": {
                "type": "string",
                "description": (
                    "The specification describing expected behavior. "
                    "Be specific: include function signatures, expected inputs/outputs, "
                    "edge cases, and error handling requirements."
                ),
            },
            "max_iterations": {
                "type": "integer",
                "description": "Maximum fix iterations before giving up (1-10, default: 5).",
            },
        },
        "required": ["spec"],
    },
}


# --- Registry ---
from tools.registry import registry

registry.register(
    name="tdd_pipeline",
    toolset="tdd",
    schema=TDD_PIPELINE_SCHEMA,
    handler=lambda args, **kw: tdd_pipeline(
        spec=args.get("spec"),
        max_iterations=args.get("max_iterations", 5),
        parent_agent=kw.get("parent_agent"),
    ),
)
