import json
import os
from typing import List, Optional, Dict
from models.report import ExecutionReport

MEMORY_FILE = "data/execution_memory.json"


class ExecutionMemory:
    """
    Episodic memory: stores what the agent has done.
    Persists as data/execution_memory.json between runs.

    Stored per execution:
    - instruction: the original user instruction
    - decomposition: the list of steps planned
    - execution_path: which tools ran in which order
    - api_calls: how many API calls were made
    - duration: how long it took
    - failures: which steps failed and why
    - success: overall outcome
    - lessons_learned: extracted patterns for future planning
    - discovered_constraints: runtime constraints found in this run

    Interview answer for "why not a vector DB?":
    A vector DB retrieves semantically similar text. We need structured
    retrieval of step sequences and API call counts — structured facts,
    not documents. Keyword overlap scoring retrieves relevant past runs
    without a dependency that obscures what we're doing.
    The planner gets useful context either way, but this approach is
    fully explainable and zero extra dependencies.
    """

    def __init__(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE) as f:
                self._data = json.load(f)
        else:
            self._data = {"executions": []}

    def save(self, report: ExecutionReport) -> None:
        """Persist an execution report with enriched metadata."""
        entry = report.to_dict()

        # Enrich with fields the to_dict() doesn't include natively
        entry["execution_path"] = [
            s["tool"] for s in entry["steps"] if s["status"] == "success"
        ]
        entry["failed_tools"] = [
            {"tool": s["tool"], "error": s["error"]}
            for s in entry["steps"] if s["status"] == "failed"
        ]
        entry["lessons_learned"] = self._extract_lessons(report)
        entry["discovered_constraints"] = self._extract_constraints(report)

        self._data["executions"].append(entry)

        # Trigger episodic memory compaction if count exceeds 5 runs
        if len(self._data["executions"]) >= 5:
            from memory.compactor import compact_memory
            original_len = len(self._data["executions"])
            compacted_execs, summary = compact_memory(self._data["executions"])
            if len(compacted_execs) < original_len:
                self._data["executions"] = compacted_execs
                report.compaction_occurred = True
                report.compaction_summary = summary
                entry["compaction_occurred"] = True
                entry["compaction_summary"] = summary
                print(f"          [Compaction] {summary}")

        self._write()

        # Confirm what was stored — shows the agent is actively writing memory
        step_seq = [s["tool"] for s in entry["steps"] if s["status"] == "success"]
        print(f"[ExecMem] Saved run #{self.count()}")
        print(f"          Instruction: '{entry['instruction'][:50]}'")
        print(f"          Result: {'SUCCESS' if entry['success'] else 'FAILED'}")
        print(f"          API calls: {entry['total_api_calls']}")
        print(f"          Step sequence stored: {step_seq}")

        # Check if this run was more efficient than past similar runs
        similar = self.get_similar(entry["instruction"], limit=10)
        successful_similar = [e for e in similar if e.get("success") and e != entry]
        if successful_similar:
            best_prev = min(successful_similar, key=lambda x: x.get("total_api_calls", 999))
            if entry["total_api_calls"] < best_prev["total_api_calls"]:
                saved = best_prev["total_api_calls"] - entry["total_api_calls"]
                print(f"          NEW BEST: saved {saved} API call(s) vs previous best run")

    def _extract_lessons(self, report: ExecutionReport) -> List[str]:
        """Extract reusable lessons from a completed execution."""
        lessons = []
        if report.success:
            tool_seq = [s.tool for s in report.steps if s.status.value == "success"]
            if tool_seq:
                lessons.append(f"Successful sequence for '{report.instruction[:60]}': {tool_seq}")
            if report.total_api_calls <= 2:
                lessons.append(f"Very efficient: completed in {report.total_api_calls} API calls")
        else:
            failed = [s for s in report.steps if s.status.value == "failed"]
            for s in failed:
                if s.error:
                    lessons.append(f"Tool '{s.tool}' failed: {s.error[:100]}")
        if report.synthesis_occurred:
            lessons.append(f"Synthesised new tool: {report.synthesised_tool_name}")
        return lessons

    def _extract_constraints(self, report: ExecutionReport) -> List[str]:
        """Extract runtime constraints discovered during this execution."""
        constraints = []
        for step in report.steps:
            if step.status.value == "failed" and step.error:
                e = step.error.lower()
                if "not found" in e or "404" in e:
                    constraints.append(f"Resource not found using {step.tool}")
                if "uuid" in e:
                    constraints.append("Node IDs must be UUID strings")
        return constraints

    def get_similar(self, instruction: str, limit: int = 5, min_jaccard: float = 0.3) -> List[dict]:
        """
        Retrieve past executions most similar to the given instruction.
        Uses Jaccard Similarity (intersection over union of keyword sets) after stop-word removal.
        Filters out matches with Jaccard index below min_jaccard.
        """
        STOP_WORDS = {"a", "an", "the", "and", "or", "in", "on", "at", "to", "for",
                      "of", "with", "by", "from", "up", "is", "it", "its", "all",
                      "me", "my", "give", "get", "then"}

        words = set(instruction.lower().split()) - STOP_WORDS
        scored = []
        for ex in self._data["executions"]:
            ex_words = set(ex["instruction"].lower().split()) - STOP_WORDS
            union_len = len(words | ex_words)
            if union_len > 0:
                jaccard = len(words & ex_words) / union_len
                if jaccard >= min_jaccard:
                    # Score is Jaccard similarity + success bonus to prefer successful executions
                    score = jaccard + (0.1 if ex.get("success") else 0)
                    scored.append((score, ex))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored[:limit]]

    def get_optimal_sequence(self, instruction: str) -> Optional[List[str]]:
        """
        Return the tool sequence from the most efficient successful run
        for a similar instruction.

        This is the core of the learning improvement: by run 3+, the planner
        receives the proven optimal sequence and uses it, reducing redundant steps.
        """
        similar = [ex for ex in self.get_similar(instruction, 10) if ex.get("success")]
        if not similar:
            return None
        # Pick the run with fewest API calls (most efficient)
        best = min(similar, key=lambda x: x.get("total_api_calls", 999))
        return best.get("execution_path") or [
            s["tool"] for s in best.get("steps", []) if s["status"] == "success"
        ]

    def get_api_call_trend(self, keyword: str) -> List[int]:
        """
        Returns API call counts in chronological order for similar instructions.
        This IS the measurable learning signal shown during the demo.
        Example: [5, 4, 4, 3, 2] proves the agent is improving.
        """
        similar = self.get_similar(keyword, 20)
        chronological = sorted(similar, key=lambda x: x.get("timestamp", ""))
        return [ex.get("total_api_calls", 0) for ex in chronological]

    def get_all_lessons(self) -> List[str]:
        """Aggregate all lessons learned across all executions."""
        lessons = []
        for ex in self._data["executions"]:
            lessons.extend(ex.get("lessons_learned", []))
        return list(set(lessons))  # deduplicate

    def get_constraints_summary(self) -> Dict[str, int]:
        """Count how often each constraint type was discovered."""
        summary: Dict[str, int] = {}
        for ex in self._data["executions"]:
            for c in ex.get("discovered_constraints", []):
                summary[c] = summary.get(c, 0) + 1
        return summary

    def count(self) -> int:
        return len(self._data["executions"])

    def _write(self) -> None:
        with open(MEMORY_FILE, "w") as f:
            json.dump(self._data, f, indent=2)