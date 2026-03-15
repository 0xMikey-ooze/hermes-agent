"""Tests for tools.tdd_pipeline_tool — Spec-first TDD pipeline.

Written test-first (RED phase) before implementation.
"""

import json
import pytest


class TestTDDState:
    def test_create_initial_state(self):
        from tools.tdd_pipeline_tool import TDDState

        state = TDDState(spec="test that add(1,2) returns 3")
        assert state.phase == "spec"
        assert state.spec == "test that add(1,2) returns 3"
        assert state.code is None
        assert state.test_results is None
        assert state.iteration == 0
        assert state.max_iterations == 5

    def test_create_with_custom_max_iterations(self):
        from tools.tdd_pipeline_tool import TDDState

        state = TDDState(spec="test", max_iterations=3)
        assert state.max_iterations == 3


class TestAdvancePhase:
    def test_spec_to_implement(self):
        from tools.tdd_pipeline_tool import TDDState, advance_phase

        state = TDDState(spec="test add function")
        new_state = advance_phase(state)
        assert new_state.phase == "implement"

    def test_implement_to_test(self):
        from tools.tdd_pipeline_tool import TDDState, advance_phase

        state = TDDState(spec="test", phase="implement", code="def add(a,b): return a+b")
        new_state = advance_phase(state)
        assert new_state.phase == "test"

    def test_test_with_failures_to_fix(self):
        from tools.tdd_pipeline_tool import TDDState, TestSummary, advance_phase

        state = TDDState(
            spec="test",
            phase="test",
            code="def add(a,b): return a",
            test_results=TestSummary(passed=1, failed=2, errors=0, output="FAILED"),
        )
        new_state = advance_phase(state)
        assert new_state.phase == "fix"
        assert new_state.iteration == 1

    def test_test_all_pass_to_done(self):
        from tools.tdd_pipeline_tool import TDDState, TestSummary, advance_phase

        state = TDDState(
            spec="test",
            phase="test",
            code="def add(a,b): return a+b",
            test_results=TestSummary(passed=3, failed=0, errors=0, output="PASSED"),
        )
        new_state = advance_phase(state)
        assert new_state.phase == "done"

    def test_fix_to_test(self):
        from tools.tdd_pipeline_tool import TDDState, advance_phase

        state = TDDState(spec="test", phase="fix", code="fixed code", iteration=1)
        new_state = advance_phase(state)
        assert new_state.phase == "test"

    def test_max_iterations_bail_out(self):
        from tools.tdd_pipeline_tool import TDDState, TestSummary, advance_phase

        state = TDDState(
            spec="test",
            phase="test",
            code="buggy",
            test_results=TestSummary(passed=0, failed=1, errors=0, output="FAILED"),
            iteration=5,
            max_iterations=5,
        )
        new_state = advance_phase(state)
        assert new_state.phase == "max_iterations_reached"

    def test_done_stays_done(self):
        from tools.tdd_pipeline_tool import TDDState, advance_phase

        state = TDDState(spec="test", phase="done")
        new_state = advance_phase(state)
        assert new_state.phase == "done"


class TestParseTestOutput:
    def test_parse_pytest_success(self):
        from tools.tdd_pipeline_tool import parse_test_output

        output = "===== 5 passed in 0.03s ====="
        result = parse_test_output(output)
        assert result.passed == 5
        assert result.failed == 0
        assert result.errors == 0

    def test_parse_pytest_failure(self):
        from tools.tdd_pipeline_tool import parse_test_output

        output = "===== 2 failed, 3 passed in 0.05s ====="
        result = parse_test_output(output)
        assert result.passed == 3
        assert result.failed == 2

    def test_parse_pytest_errors(self):
        from tools.tdd_pipeline_tool import parse_test_output

        output = "===== 1 error, 2 passed in 0.02s ====="
        result = parse_test_output(output)
        assert result.errors == 1
        assert result.passed == 2

    def test_parse_no_match_returns_zero(self):
        from tools.tdd_pipeline_tool import parse_test_output

        output = "some random output with no test results"
        result = parse_test_output(output)
        assert result.passed == 0
        assert result.failed == 0
        assert result.errors == 0
        assert result.output == output


class TestToolRegistration:
    def test_tdd_pipeline_schema(self):
        from tools.tdd_pipeline_tool import TDD_PIPELINE_SCHEMA

        assert TDD_PIPELINE_SCHEMA["name"] == "tdd_pipeline"
        assert "parameters" in TDD_PIPELINE_SCHEMA

    def test_schema_has_spec_param(self):
        from tools.tdd_pipeline_tool import TDD_PIPELINE_SCHEMA

        props = TDD_PIPELINE_SCHEMA["parameters"]["properties"]
        assert "spec" in props
        assert "max_iterations" in props
