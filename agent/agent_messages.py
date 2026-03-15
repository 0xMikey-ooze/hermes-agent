"""Structured agent-to-agent communication messages.

Provides typed dataclasses for inter-agent communication, replacing
free-text returns with structured, serializable messages.

Usage:
    from agent.agent_messages import TaskRequest, TaskResult, FeedbackMessage
    from agent.agent_messages import serialize, deserialize

    req = TaskRequest(task_id="t1", description="search docs", role="researcher")
    data = serialize(req)       # dict with _type discriminator
    restored = deserialize(data)  # back to TaskRequest
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union

_VALID_STATUSES = {"success", "failure", "partial"}
_VALID_FEEDBACK_TYPES = {"revision", "approval", "rejection"}


@dataclass
class TaskRequest:
    """A request from a parent agent to a child agent."""
    task_id: str
    description: str
    role: str
    context: Optional[str] = None
    parent_trace_id: Optional[str] = None


@dataclass
class TaskResult:
    """A result returned from a child agent to its parent."""
    task_id: str
    status: str  # "success", "failure", "partial"
    result: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def __post_init__(self):
        if self.status not in _VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}'. Must be one of: {_VALID_STATUSES}"
            )


@dataclass
class FeedbackMessage:
    """Feedback from a parent agent about a child's work."""
    task_id: str
    feedback_type: str  # "revision", "approval", "rejection"
    content: str
    suggestions: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.feedback_type not in _VALID_FEEDBACK_TYPES:
            raise ValueError(
                f"Invalid feedback_type '{self.feedback_type}'. "
                f"Must be one of: {_VALID_FEEDBACK_TYPES}"
            )


_MESSAGE_TYPES = {
    "TaskRequest": TaskRequest,
    "TaskResult": TaskResult,
    "FeedbackMessage": FeedbackMessage,
}

AgentMessage = Union[TaskRequest, TaskResult, FeedbackMessage]


def serialize(msg: AgentMessage) -> Dict[str, Any]:
    """Serialize an agent message to a dict with a _type discriminator."""
    type_name = type(msg).__name__
    data = asdict(msg)
    data["_type"] = type_name
    return data


def deserialize(data: Dict[str, Any]) -> AgentMessage:
    """Deserialize a dict back to the appropriate message dataclass."""
    type_name = data.get("_type")
    cls = _MESSAGE_TYPES.get(type_name)
    if cls is None:
        raise ValueError(f"Unknown message type: {type_name}")
    fields = {k: v for k, v in data.items() if k != "_type"}
    return cls(**fields)
