import json
import os
from typing import Dict, List
from models.report import ExecutionReport

TRACKER_FILE = "data/learning_metrics.json"


class LearningTracker:
    """
    Records and reports the measurable learning signal.

    Primary signal: API calls per run (per instruction family).
    Why this metric:
    - Run 1: Planner has no context -> may include redundant steps
    - Run 3+: Planner loads optimal sequence from execution memory,
              eliminates redundant steps -> fewer API calls
    - Observable as a decreasing number in the learning report

    Secondary signal: tool reliability (success rate per tool).

    Improvement grouping:
    Runs are grouped by instruction "family" (first 5 significant words)
    so that mixing simple (1-call) and compound (5-call) instructions
    doesn't produce a misleading chart.
    """

    STOP_WORDS = {"a", "an", "the", "and", "or", "in", "on", "at", "to",
                  "for", "of", "with", "by", "from", "is", "it", "me", "my",
                  "all", "give", "get", "please", "can", "you"}

    def __init__(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(TRACKER_FILE):
            with open(TRACKER_FILE, encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {"runs": [], "tool_stats": {}}

    def _instruction_family(self, instruction: str) -> str:
        """
        Create a short identifier for an instruction family.
        Used to group similar instructions together in the improvement chart.
        """
        words = [w for w in instruction.lower().split() if w not in self.STOP_WORDS]
        return " ".join(words[:5])

    def record(self, report: ExecutionReport) -> None:
        """Record one run's metrics to disk."""
        self._data["runs"].append({
            "timestamp": report.timestamp,
            "instruction": report.instruction,
            "instruction_family": self._instruction_family(report.instruction),
            "total_api_calls": report.total_api_calls,
            "duration": round(report.total_duration_seconds, 3),
            "success": report.success,
            "steps": len(report.steps),
            "synthesis_occurred": report.synthesis_occurred,
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

    def get_improvement_for_family(self, family: str) -> Dict:
        """
        Return improvement stats for one instruction family.
        A family is a group of similar instructions (same first 5 words).
        """
        family_runs = [r for r in self._data["runs"] if r.get("instruction_family") == family]
        if len(family_runs) < 2:
            return {"family": family, "runs": len(family_runs), "improvement": None}
        successful = [r for r in family_runs if r["success"]]
        if len(successful) < 2:
            return {"family": family, "runs": len(family_runs), "improvement": None}
        first = successful[0]["total_api_calls"]
        last = successful[-1]["total_api_calls"]
        reduction_pct = round((first - last) / first * 100) if first > 0 else 0
        return {
            "family": family,
            "runs": len(family_runs),
            "first_calls": first,
            "last_calls": last,
            "reduction_pct": reduction_pct,
            "improving": last < first,
        }

    def print_report(self) -> None:
        runs = self._data["runs"]
        if not runs:
            print("[Learning] No runs recorded yet.")
            return
        if len(runs) < 2:
            print(f"[Learning] 1 run recorded. {runs[0]['total_api_calls']} API calls.")
            print("[Learning] Run at least 2 instructions to see improvement trend.")
            return

        print("\n" + "=" * 60)
        print("LEARNING REPORT — API Calls Per Run")
        print("=" * 60)

        for i, r in enumerate(runs, 1):
            bar = "█" * r["total_api_calls"]
            ok = "✓" if r["success"] else "✗"
            instr = r["instruction"][:35] + "..." if len(r["instruction"]) > 35 else r["instruction"]
            print(f"Run {i:2d} {ok}  {bar:<15}  {r['total_api_calls']} calls  {r['duration']:.1f}s  \"{instr}\"")

        # Group by instruction family
        families = {}
        for r in runs:
            fam = r.get("instruction_family")
            if fam not in families:
                families[fam] = []
            families[fam].append(r)

        print("\n" + "-" * 60)
        print("IMPROVEMENT BY INSTRUCTION FAMILY")
        print("-" * 60)
        for fam, fam_runs in families.items():
            successful_runs = [r for r in fam_runs if r["success"]]
            calls = [r["total_api_calls"] for r in fam_runs]
            success_status = [("✓" if r["success"] else "✗") for r in fam_runs]
            trend_str = " -> ".join(f"{c}({s})" for c, s in zip(calls, success_status))
            print(f"Family: \"{fam}...\"")
            print(f"  Runs: {len(fam_runs)} | API Calls: {trend_str}")
            if len(successful_runs) >= 2:
                first_calls = successful_runs[0]["total_api_calls"]
                last_calls = successful_runs[-1]["total_api_calls"]
                if last_calls < first_calls:
                    pct = round((first_calls - last_calls) / first_calls * 100)
                    print(f"  [LEARNING SIGNAL] ✓ IMPROVED: {first_calls} -> {last_calls} calls ({pct}% reduction)")
                elif last_calls == first_calls:
                    print(f"  [LEARNING SIGNAL] Stable: {first_calls} calls (optimal)")
                else:
                    print(f"  [LEARNING SIGNAL] Complexity changed or increased: {first_calls} -> {last_calls} calls")
            else:
                print(f"  [LEARNING SIGNAL] Need more runs to show trend")

        if self._data.get("tool_stats"):
            print("\nTool reliability:")
            for tool, s in self._data["tool_stats"].items():
                total = s["success"] + s["failure"]
                if total:
                    rate = round(s["success"] / total * 100)
                    bar = "█" * (rate // 10)
                    print(f"  {tool:<45} {bar:<10} {rate}%  ({total} calls)")

        print("=" * 60)
        print(f"\nTo show this during your demo: python main.py learning-report")
        print(f"This is your measurable learning signal for the Watermelon interview.\n")

    def get_data(self) -> dict:
        return self._data

    def _write(self) -> None:
        with open(TRACKER_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)