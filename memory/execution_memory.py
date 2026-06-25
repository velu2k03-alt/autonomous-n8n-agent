import json, os
from typing import List, Optional
from models.report import ExecutionReport

MEMORY_FILE = "data/execution_memory.json"


class ExecutionMemory:
    """
    Episodic memory: stores what the agent has done.
    Persists as data/execution_memory.json between runs.

    Interview answer for "why not a vector DB?":
    A vector DB retrieves semantically similar text. We need structured
    retrieval of step sequences and API call counts — structured facts,
    not documents. Keyword overlap scoring retrieves relevant past runs
    without a dependency that obscures what we're doing.
    The planner gets useful context either way, but this version is
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
        self._data["executions"].append(report.to_dict())
        self._write()
        print(f"[ExecMem] Saved. Total: {self.count()}")

    def get_similar(self, instruction: str, limit: int = 5) -> List[dict]:
        """
        Retrieve past executions most similar to the given instruction.
        Uses keyword overlap (Jaccard-like) scoring.
        Higher overlap = more similar.
        """
        words = set(instruction.lower().split())
        scored = []
        for ex in self._data["executions"]:
            overlap = len(words & set(ex["instruction"].lower().split()))
            if overlap > 0:
                scored.append((overlap, ex))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored[:limit]]

    def get_optimal_sequence(self, instruction: str) -> Optional[List[str]]:
        """
        Return the tool sequence from the most efficient successful run
        for a similar instruction. Used by the planner to reuse proven paths.
        """
        similar = [ex for ex in self.get_similar(instruction, 10) if ex.get("success")]
        if not similar:
            return None
        best = min(similar, key=lambda x: x.get("total_api_calls", 999))
        return [s["tool"] for s in best.get("steps", []) if s["status"] == "success"]

    def get_api_call_trend(self, keyword: str) -> List[int]:
        """
        Returns API call counts in chronological order for similar instructions.
        This IS the measurable learning signal shown during the demo.
        Example: [5, 4, 4, 3, 2] proves the agent is improving.
        """
        similar = self.get_similar(keyword, 20)
        chronological = sorted(similar, key=lambda x: x.get("timestamp", ""))
        return [ex.get("total_api_calls", 0) for ex in chronological]

    def count(self) -> int:
        return len(self._data["executions"])

    def _write(self):
        with open(MEMORY_FILE, "w") as f:
            json.dump(self._data, f, indent=2)