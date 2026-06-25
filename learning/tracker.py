import json, os
from models.report import ExecutionReport

TRACKER_FILE = "data/learning_metrics.json"


class LearningTracker:
    """
    Records and reports the measurable learning signal.

    The primary signal: API calls per task.
    Why this metric:
    - Run 1: Planner has no context, may include redundant steps
    - Run 3+: Planner loads optimal sequence from execution memory,
              eliminates redundant steps → fewer API calls
    - Observable as a decreasing number in the learning report

    Secondary signal: tool reliability (success rate per tool).
    """

    def __init__(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(TRACKER_FILE):
            with open(TRACKER_FILE) as f:
                self._data = json.load(f)
        else:
            self._data = {"runs": [], "tool_stats": {}}

    def record(self, report: ExecutionReport) -> None:
        self._data["runs"].append({
            "timestamp": report.timestamp,
            "instruction": report.instruction,
            "total_api_calls": report.total_api_calls,
            "duration": report.total_duration_seconds,
            "success": report.success,
            "steps": len(report.steps),
        })
        for step in report.steps:
            t = step.tool
            if t not in self._data["tool_stats"]:
                self._data["tool_stats"][t] = {"success": 0, "failure": 0}
            if step.status.value == "success":
                self._data["tool_stats"][t]["success"] += 1
            elif step.status.value == "failed":
                self._data["tool_stats"][t]["failure"] += 1
        self._write()

    def print_report(self) -> None:
        """Print the before/after numbers. This is what you show on the call."""
        runs = self._data["runs"]
        if len(runs) < 2:
            print("[Learning] Need at least 2 runs to show improvement.")
            return
        print("\n" + "=" * 60)
        print("LEARNING REPORT — API Calls Per Run")
        print("=" * 60)
        for i, r in enumerate(runs, 1):
            bar = "█" * r["total_api_calls"]
            ok = "✓" if r["success"] else "✗"
            short = r["instruction"][:40] + "..." if len(r["instruction"]) > 40 else r["instruction"]
            print(f"Run {i:2d} {ok}  {bar:<15} {r['total_api_calls']} calls  {r['duration']:.1f}s")
        first = runs[0]["total_api_calls"]
        last = runs[-1]["total_api_calls"]
        if first > last:
            pct = round((first - last) / first * 100)
            print(f"\n→ Reduced by {pct}%: {first} calls on run 1 → {last} calls on run {len(runs)}")
        else:
            print(f"\n→ Consistent: {first} calls per run")
        print("\nTool reliability:")
        for tool, s in self._data["tool_stats"].items():
            total = s["success"] + s["failure"]
            if total:
                rate = round(s["success"] / total * 100)
                print(f"  {tool}: {rate}% ({total} total calls)")
        print("=" * 60)

    def get_data(self) -> dict:
        return self._data

    def _write(self):
        with open(TRACKER_FILE, "w") as f:
            json.dump(self._data, f, indent=2)