from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Step:
    """
    One atomic unit of work the executor performs on n8n.
    The planner produces a list of these; the executor runs each one.

    Why a dataclass: typed, gives __repr__ for free, no boilerplate __init__.
    Why not a dict: we want type safety and IDE autocomplete during development.
    """
    id: str                              # e.g. "step_1"
    tool: str                            # e.g. "list_workflows"
    params: Dict[str, Any]               # passed directly to the tool function
    description: str                     # human-readable one-liner
    depends_on: list = field(default_factory=list)  # IDs of steps that must succeed first

    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    api_calls_made: int = 0              # learning signal
    duration_seconds: float = 0.0       # learning signal
    assigned_agent: Optional[str] = None
    confidence_score: float = 1.0
    confidence_reason: Optional[str] = None
    rollback_registered: bool = False