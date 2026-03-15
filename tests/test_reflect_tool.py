"""Tests for tools.reflect_tool — Reflection/critic loop tool.

Written test-first (RED phase) before implementation.
"""

import json
import pytest


class TestReflectionResult:
    def test_create_passing_result(self):
        from tools.reflect_tool import ReflectionResult

        r = ReflectionResult(passed=True, issues=[], suggestions=[], round_num=1)
        assert r.passed is True
        assert r.round_num == 1

    def test_create_failing_result(self):
        from tools.reflect_tool import ReflectionResult

        r = ReflectionResult(
            passed=False,
            issues=["Missing error handling", "No input validation"],
            suggestions=["Add try/except", "Validate params"],
            round_num=2,
        )
        assert r.passed is False
        assert len(r.issues) == 2
        assert len(r.suggestions) == 2


class TestParseCriteria:
    def test_parse_string_criteria(self):
        from tools.reflect_tool import parse_criteria

        result = parse_criteria("correctness, efficiency, readability")
        assert "correctness" in result
        assert "efficiency" in result
        assert "readability" in result

    def test_parse_list_criteria(self):
        from tools.reflect_tool import parse_criteria

        result = parse_criteria(["correctness", "efficiency"])
        assert result == ["correctness", "efficiency"]

    def test_parse_none_returns_defaults(self):
        from tools.reflect_tool import parse_criteria, DEFAULT_CRITERIA

        result = parse_criteria(None)
        assert result == DEFAULT_CRITERIA

    def test_parse_empty_string_returns_defaults(self):
        from tools.reflect_tool import parse_criteria, DEFAULT_CRITERIA

        result = parse_criteria("")
        assert result == DEFAULT_CRITERIA


class TestClampMaxRounds:
    def test_clamp_within_range(self):
        from tools.reflect_tool import clamp_max_rounds

        assert clamp_max_rounds(3) == 3

    def test_clamp_below_minimum(self):
        from tools.reflect_tool import clamp_max_rounds

        assert clamp_max_rounds(0) == 1

    def test_clamp_above_maximum(self):
        from tools.reflect_tool import clamp_max_rounds, MAX_REFLECTION_ROUNDS

        assert clamp_max_rounds(100) == MAX_REFLECTION_ROUNDS

    def test_clamp_negative(self):
        from tools.reflect_tool import clamp_max_rounds

        assert clamp_max_rounds(-5) == 1


class TestBuildReflectionPrompt:
    def test_prompt_contains_content(self):
        from tools.reflect_tool import build_reflection_prompt

        prompt = build_reflection_prompt("my code here", ["correctness"])
        assert "my code here" in prompt

    def test_prompt_contains_criteria(self):
        from tools.reflect_tool import build_reflection_prompt

        prompt = build_reflection_prompt("code", ["correctness", "efficiency"])
        assert "correctness" in prompt
        assert "efficiency" in prompt


class TestToolRegistration:
    def test_reflect_tool_registered(self):
        from tools.reflect_tool import REFLECT_SCHEMA

        assert REFLECT_SCHEMA["name"] == "reflect"
        assert "parameters" in REFLECT_SCHEMA

    def test_schema_has_required_params(self):
        from tools.reflect_tool import REFLECT_SCHEMA

        props = REFLECT_SCHEMA["parameters"]["properties"]
        assert "content" in props
        assert "criteria" in props
        assert "max_rounds" in props
