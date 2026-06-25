from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from models.step import Step


@dataclass
class ExecutionReport:
    """
    The complete result of one agent run.
    Returned to the user AND written to execution memory.
    Same format serves both purposes.
    """
    instruction: str
    steps: List[Step] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    total_api_calls: int = 0
    total_duration_seconds: float = 0.0
    success: bool = False
    failure_reason: Optional[str] = None
    synthesis_occurred: bool = False
    synthesised_tool_name: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "instruction": self.instruction,
            "timestamp": self.timestamp,
            "total_api_calls": self.total_api_calls,
            "total_duration_seconds": self.total_duration_seconds,
            "success": self.success,
            "failure_reason": self.failure_reason,
            "synthesis_occurred": self.synthesis_occurred,
            "synthesised_tool_name": self.synthesised_tool_name,
            "steps": [
                {
                    "id": s.id,
                    "tool": s.tool,
                    "description": s.description,
                    "status": s.status.value,
                    "api_calls_made": s.api_calls_made,
                    "duration_seconds": s.duration_seconds,
                    "error": s.error,
                }
                for s in self.steps
            ],
        }

    def summary(self) -> str:
        succeeded = sum(1 for s in self.steps if s.status.value == "success")
        failed = sum(1 for s in self.steps if s.status.value == "failed")
        lines = [
            f"Instruction : {self.instruction}",
            f"Result      : {'SUCCESS' if self.success else 'FAILED'}",
            f"Steps       : {succeeded}/{len(self.steps)} succeeded, {failed} failed",
            f"API calls   : {self.total_api_calls}",
            f"Duration    : {self.total_duration_seconds:.2f}s",
        ]
        if self.failure_reason:
            lines.append(f"Reason      : {self.failure_reason}")
        if self.synthesis_occurred:
            lines.append(f"Synthesised : {self.synthesised_tool_name}")
        return "\n".join(lines)