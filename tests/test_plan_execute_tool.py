"""Tests for tools.plan_execute_tool — Architect/coder split tool.

Written test-first (RED phase) before implementation.
"""

import json
import pytest


class TestPlanStep:
    def test_create_plan_step(self):
        from tools.plan_execute_tool import PlanStep

        step = PlanStep(description="Research existing patterns")
        assert step.description == "Research existing patterns"
        assert step.status == "pending"
        assert step.substeps == []

    def test_create_step_with_substeps(self):
        from tools.plan_execute_tool import PlanStep

        step = PlanStep(
            description="Implement feature",
            substeps=["Write tests", "Write code", "Run tests"],
        )
        assert len(step.substeps) == 3


class TestExecutionPlan:
    def test_create_plan(self):
        from tools.plan_execute_tool import ExecutionPlan, PlanStep

        steps = [
            PlanStep(description="Research"),
            PlanStep(description="Implement"),
            PlanStep(description="Test"),
        ]
        plan = ExecutionPlan(goal="Build auth system", steps=steps)
        assert plan.goal == "Build auth system"
        assert len(plan.steps) == 3
        assert plan.current_step_index == 0

    def test_empty_plan(self):
        from tools.plan_execute_tool import ExecutionPlan

        plan = ExecutionPlan(goal="Nothing", steps=[])
        assert len(plan.steps) == 0
        assert plan.current_step_index == 0


class TestAdvancePlan:
    def test_advance_marks_current_done(self):
        from tools.plan_execute_tool import ExecutionPlan, PlanStep, advance_plan

        steps = [
            PlanStep(description="Step 1"),
            PlanStep(description="Step 2"),
        ]
        plan = ExecutionPlan(goal="test", steps=steps)
        new_plan = advance_plan(plan)
        assert new_plan.steps[0].status == "done"
        assert new_plan.current_step_index == 1

    def test_advance_sets_next_in_progress(self):
        from tools.plan_execute_tool import ExecutionPlan, PlanStep, advance_plan

        steps = [
            PlanStep(description="Step 1"),
            PlanStep(description="Step 2"),
        ]
        plan = ExecutionPlan(goal="test", steps=steps)
        new_plan = advance_plan(plan)
        assert new_plan.steps[1].status == "in_progress"

    def test_advance_last_step(self):
        from tools.plan_execute_tool import ExecutionPlan, PlanStep, advance_plan

        steps = [PlanStep(description="Only step")]
        plan = ExecutionPlan(goal="test", steps=steps)
        new_plan = advance_plan(plan)
        assert new_plan.steps[0].status == "done"
        assert new_plan.current_step_index == 1  # past the end

    def test_advance_empty_plan(self):
        from tools.plan_execute_tool import ExecutionPlan, advance_plan

        plan = ExecutionPlan(goal="test", steps=[])
        new_plan = advance_plan(plan)
        assert new_plan.current_step_index == 0  # no change


class TestIsPlanComplete:
    def test_complete_plan(self):
        from tools.plan_execute_tool import ExecutionPlan, PlanStep, is_plan_complete

        steps = [PlanStep(description="Done", status="done")]
        plan = ExecutionPlan(goal="test", steps=steps, current_step_index=1)
        assert is_plan_complete(plan) is True

    def test_incomplete_plan(self):
        from tools.plan_execute_tool import ExecutionPlan, PlanStep, is_plan_complete

        steps = [
            PlanStep(description="Done", status="done"),
            PlanStep(description="Pending"),
        ]
        plan = ExecutionPlan(goal="test", steps=steps, current_step_index=1)
        assert is_plan_complete(plan) is False

    def test_empty_plan_is_complete(self):
        from tools.plan_execute_tool import ExecutionPlan, is_plan_complete

        plan = ExecutionPlan(goal="test", steps=[])
        assert is_plan_complete(plan) is True

    def test_plan_with_failed_step(self):
        from tools.plan_execute_tool import ExecutionPlan, PlanStep, is_plan_complete

        steps = [PlanStep(description="Failed", status="failed")]
        plan = ExecutionPlan(goal="test", steps=steps, current_step_index=1)
        # A failed step still means the plan has been "processed"
        assert is_plan_complete(plan) is True


class TestGetRoleForPhase:
    def test_architect_phase(self):
        from tools.plan_execute_tool import get_role_for_phase

        assert get_role_for_phase("architect") == "researcher"

    def test_coder_phase(self):
        from tools.plan_execute_tool import get_role_for_phase

        assert get_role_for_phase("coder") == "coder"

    def test_unknown_phase_returns_default(self):
        from tools.plan_execute_tool import get_role_for_phase

        assert get_role_for_phase("unknown") == "default"


class TestToolRegistration:
    def test_plan_execute_schema(self):
        from tools.plan_execute_tool import PLAN_EXECUTE_SCHEMA

        assert PLAN_EXECUTE_SCHEMA["name"] == "plan_execute"
        assert "parameters" in PLAN_EXECUTE_SCHEMA

    def test_schema_has_goal_param(self):
        from tools.plan_execute_tool import PLAN_EXECUTE_SCHEMA

        props = PLAN_EXECUTE_SCHEMA["parameters"]["properties"]
        assert "goal" in props
