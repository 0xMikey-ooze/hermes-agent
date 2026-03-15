"""Tests for agent.agent_messages — Structured agent-to-agent communication.

Written test-first (RED phase) before implementation.
"""

import pytest


class TestTaskRequest:
    def test_create_task_request(self):
        from agent.agent_messages import TaskRequest

        req = TaskRequest(
            task_id="task-001",
            description="Search for Python best practices",
            role="researcher",
        )
        assert req.task_id == "task-001"
        assert req.description == "Search for Python best practices"
        assert req.role == "researcher"
        assert req.context is None
        assert req.parent_trace_id is None

    def test_task_request_with_all_fields(self):
        from agent.agent_messages import TaskRequest

        req = TaskRequest(
            task_id="task-002",
            description="Fix the bug",
            role="coder",
            context="File: main.py, Line: 42",
            parent_trace_id="trace-abc123",
        )
        assert req.context == "File: main.py, Line: 42"
        assert req.parent_trace_id == "trace-abc123"


class TestTaskResult:
    def test_create_success_result(self):
        from agent.agent_messages import TaskResult

        result = TaskResult(
            task_id="task-001",
            status="success",
            result="Found 5 relevant articles",
        )
        assert result.status == "success"
        assert result.result == "Found 5 relevant articles"
        assert result.error is None
        assert result.artifacts == []

    def test_create_failure_result(self):
        from agent.agent_messages import TaskResult

        result = TaskResult(
            task_id="task-001",
            status="failure",
            error="API rate limit exceeded",
        )
        assert result.status == "failure"
        assert result.error == "API rate limit exceeded"

    def test_create_partial_result_with_artifacts(self):
        from agent.agent_messages import TaskResult

        result = TaskResult(
            task_id="task-001",
            status="partial",
            result="Found 2 of 5 items",
            artifacts=["file1.py", "file2.py"],
        )
        assert result.status == "partial"
        assert result.artifacts == ["file1.py", "file2.py"]

    def test_invalid_status_raises(self):
        from agent.agent_messages import TaskResult

        with pytest.raises(ValueError, match="status"):
            TaskResult(task_id="task-001", status="unknown")


class TestFeedbackMessage:
    def test_create_revision_feedback(self):
        from agent.agent_messages import FeedbackMessage

        fb = FeedbackMessage(
            task_id="task-001",
            feedback_type="revision",
            content="Please add error handling",
        )
        assert fb.feedback_type == "revision"
        assert fb.content == "Please add error handling"
        assert fb.suggestions == []

    def test_create_feedback_with_suggestions(self):
        from agent.agent_messages import FeedbackMessage

        fb = FeedbackMessage(
            task_id="task-001",
            feedback_type="revision",
            content="Code needs improvement",
            suggestions=["Add type hints", "Add docstrings"],
        )
        assert fb.suggestions == ["Add type hints", "Add docstrings"]

    def test_invalid_feedback_type_raises(self):
        from agent.agent_messages import FeedbackMessage

        with pytest.raises(ValueError, match="feedback_type"):
            FeedbackMessage(
                task_id="task-001",
                feedback_type="invalid",
                content="test",
            )


class TestSerialization:
    def test_serialize_task_request(self):
        from agent.agent_messages import TaskRequest, serialize

        req = TaskRequest(task_id="t1", description="do stuff", role="coder")
        data = serialize(req)
        assert data["_type"] == "TaskRequest"
        assert data["task_id"] == "t1"

    def test_serialize_task_result(self):
        from agent.agent_messages import TaskResult, serialize

        result = TaskResult(task_id="t1", status="success", result="done")
        data = serialize(result)
        assert data["_type"] == "TaskResult"
        assert data["status"] == "success"

    def test_serialize_feedback(self):
        from agent.agent_messages import FeedbackMessage, serialize

        fb = FeedbackMessage(task_id="t1", feedback_type="approval", content="LGTM")
        data = serialize(fb)
        assert data["_type"] == "FeedbackMessage"

    def test_deserialize_task_request(self):
        from agent.agent_messages import TaskRequest, serialize, deserialize

        original = TaskRequest(task_id="t1", description="test", role="reviewer")
        data = serialize(original)
        restored = deserialize(data)
        assert isinstance(restored, TaskRequest)
        assert restored.task_id == "t1"
        assert restored.role == "reviewer"

    def test_deserialize_task_result(self):
        from agent.agent_messages import TaskResult, serialize, deserialize

        original = TaskResult(task_id="t1", status="failure", error="oops")
        data = serialize(original)
        restored = deserialize(data)
        assert isinstance(restored, TaskResult)
        assert restored.status == "failure"
        assert restored.error == "oops"

    def test_deserialize_feedback(self):
        from agent.agent_messages import FeedbackMessage, serialize, deserialize

        original = FeedbackMessage(
            task_id="t1", feedback_type="rejection", content="Not good enough",
            suggestions=["Try again"],
        )
        data = serialize(original)
        restored = deserialize(data)
        assert isinstance(restored, FeedbackMessage)
        assert restored.suggestions == ["Try again"]

    def test_deserialize_unknown_type_raises(self):
        from agent.agent_messages import deserialize

        with pytest.raises(ValueError, match="Unknown message type"):
            deserialize({"_type": "UnknownMessage", "task_id": "t1"})

    def test_roundtrip_preserves_all_fields(self):
        from agent.agent_messages import TaskRequest, serialize, deserialize

        original = TaskRequest(
            task_id="t1", description="full test", role="coder",
            context="ctx", parent_trace_id="trace-123",
        )
        restored = deserialize(serialize(original))
        assert restored.task_id == original.task_id
        assert restored.description == original.description
        assert restored.role == original.role
        assert restored.context == original.context
        assert restored.parent_trace_id == original.parent_trace_id
