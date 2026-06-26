from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
from datetime import datetime
from models.step import Step


@dataclass
class ExecutionReport:
    """
    The complete result of one agent run.

    Returned to the user via CLI and API AND written to execution memory.
    Using the same format for both purposes ensures the stored record is
    always complete and contains everything the planner needs on future runs.

    Fields map to the assignment's execution memory requirements:
    - instruction: the original user input
    - steps: full decomposition with tool, status, timing per step
    - timestamp: when the run occurred (ISO 8601 UTC)
    - total_api_calls: learning signal — should decrease over repeated runs
    - total_duration_seconds: end-to-end wall time including LLM planning
    - success: True only if all non-skipped steps succeeded
    - failure_reason: structured failure description (not just first failure)
    - synthesis_occurred: whether a new tool was generated during this run
    - synthesised_tool_name: name of the tool that was synthesised (if any)
    """
    instruction: str
    steps: List[Step] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    total_api_calls: int = 0
    total_duration_seconds: float = 0.0
    success: bool = False
    failure_reason: Optional[str] = None
    synthesis_occurred: bool = False
    synthesised_tool_name: Optional[str] = None
    rollback_occurred: bool = False
    rollback_log: List[str] = field(default_factory=list)
    rollback_actions: List[Dict[str, Any]] = field(default_factory=list)
    compaction_occurred: bool = False
    compaction_summary: Optional[str] = None

    @property
    def final_result(self) -> Optional[Any]:
        """Find the last successful step that returned a result."""
        for s in reversed(self.steps):
            if s.status.value == "success" and s.result is not None:
                return s.result
        return None

    def to_dict(self) -> dict:
        """
        Serialise to a dict suitable for:
        - Writing to execution_memory.json
        - Returning from FastAPI endpoints
        - Displaying in the React UI
        """
        return {
            "instruction": self.instruction,
            "timestamp": self.timestamp,
            "total_api_calls": self.total_api_calls,
            "total_duration_seconds": self.total_duration_seconds,
            "success": self.success,
            "failure_reason": self.failure_reason,
            "synthesis_occurred": self.synthesis_occurred,
            "synthesised_tool_name": self.synthesised_tool_name,
            "rollback_occurred": self.rollback_occurred,
            "rollback_log": self.rollback_log,
            "rollback_actions": self.rollback_actions,
            "compaction_occurred": self.compaction_occurred,
            "compaction_summary": self.compaction_summary,
            "final_result": self.final_result,
            "steps": [
                {
                    "id": s.id,
                    "tool": s.tool,
                    "description": s.description,
                    "status": s.status.value,
                    "api_calls_made": s.api_calls_made,
                    "duration_seconds": s.duration_seconds,
                    "error": s.error,
                    "params": s.params,
                    "result": s.result,
                    "result_summary": _summarise_result(s.result),
                    "assigned_agent": s.assigned_agent,
                    "confidence_score": s.confidence_score,
                    "confidence_reason": s.confidence_reason,
                    "rollback_registered": s.rollback_registered,
                }
                for s in self.steps
            ],
        }

    def summary(self) -> str:
        """Human-readable summary for CLI output."""
        succeeded = sum(1 for s in self.steps if s.status.value == "success")
        failed = sum(1 for s in self.steps if s.status.value == "failed")
        skipped = sum(1 for s in self.steps if s.status.value == "skipped")

        # Compute average confidence
        valid_confidences = [s.confidence_score for s in self.steps if s.confidence_score is not None]
        avg_confidence = sum(valid_confidences) / len(valid_confidences) if valid_confidences else 1.0

        lines = [
            f"Instruction : {self.instruction}",
            f"Result      : {'v SUCCESS' if self.success else 'x FAILED'}",
            f"Confidence  : {avg_confidence*100:.1f}%",
            f"Steps       : {succeeded}/{len(self.steps)} succeeded"
            + (f", {failed} failed" if failed else "")
            + (f", {skipped} skipped" if skipped else ""),
            f"API calls   : {self.total_api_calls}",
            f"Duration    : {self.total_duration_seconds:.2f}s",
        ]
        if self.failure_reason:
            lines.append(f"Failure     : {self.failure_reason}")
        if self.synthesis_occurred:
            lines.append(f"Synthesised : [SYNTH] {self.synthesised_tool_name}")
        if self.rollback_occurred:
            lines.append(f"Rollback    : ACTIVE (Undid {len(self.rollback_log)} state changes)")
            for rlog in self.rollback_log:
                lines.append(f"              - {rlog}")
        if self.compaction_occurred:
            lines.append(f"Compaction  : {self.compaction_summary}")
        
        # Details on agent assignment
        lines.append("Agent Steps :")
        for s in self.steps:
            agent_str = f"[{s.assigned_agent}]" if s.assigned_agent else "[Coordinator]"
            conf_str = f"({s.confidence_score*100:.0f}% conf)"
            lines.append(f"  - {s.id} {agent_str}: {s.tool} -> {s.status.value} {conf_str}")
        
        final_res = self.final_result
        if final_res is not None:
            import json
            try:
                # If list/dict, pretty print it
                if isinstance(final_res, (dict, list)):
                    # Limit long lists to avoid huge scrolling logs
                    if isinstance(final_res, list) and len(final_res) > 10:
                        lines.append(f"Final Result (showing first 10 of {len(final_res)} items):\n"
                                     + json.dumps(final_res[:10], indent=2))
                    else:
                        lines.append(f"Final Result:\n{json.dumps(final_res, indent=2)}")
                else:
                    lines.append(f"Final Result: {final_res}")
            except Exception:
                lines.append(f"Final Result: {final_res}")

        return "\n".join(lines)


def _summarise_result(result) -> str:
    """Convert actual API result into a human-readable summary for display."""
    if result is None:
        return ""
    if isinstance(result, list):
        if not result:
            return "empty list"
        first = result[0]
        if isinstance(first, dict) and "name" in first:
            names = [str(item.get("name", "?")) for item in result[:3]]
            more = f" +{len(result)-3} more" if len(result) > 3 else ""
            return f"{len(result)} items: {', '.join(names)}{more}"
        return f"{len(result)} items"
    if isinstance(result, dict):
        name = result.get("name", "")
        wf_id = str(result.get("id", ""))[:8]
        active = result.get("active", "")
        status = result.get("status", "")
        if name:
            return f"'{name}' id={wf_id} active={active}"
        if status:
            return f"status={status}"
        if wf_id:
            return f"id={wf_id}"
    return str(result)[:120]