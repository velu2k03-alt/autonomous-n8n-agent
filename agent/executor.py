import time
from typing import List, Callable, Optional
from models.step import Step, StepStatus
from models.report import ExecutionReport
from tools import get_tool
from tools.workflows import N8NAPIError


class Executor:
    """
    Runs a list of Steps sequentially.

    Key responsibilities:
    1. Check step dependencies before running each step
    2. Detect capability gaps (unknown tool names)
    3. Trigger synthesis callback when gap detected
    4. Handle partial failures — never silently ignore them
    5. Record API call counts and timing per step
    6. Build and return the full ExecutionReport
    """

    def _deps_ok(self, step: Step, done: dict) -> bool:
        return all(done.get(dep) == StepStatus.SUCCESS for dep in step.depends_on)

    def execute(self, steps: List[Step], instruction: str,
                on_capability_gap: Optional[Callable] = None) -> ExecutionReport:
        report = ExecutionReport(instruction=instruction, steps=steps)
        done = {}          # {step_id: StepStatus}
        t0 = time.time()

        for step in steps:
            # Check dependencies
            if step.depends_on and not self._deps_ok(step, done):
                step.status = StepStatus.SKIPPED
                step.error = f"Dependency not met: {step.depends_on}"
                done[step.id] = StepStatus.SKIPPED
                print(f"  [SKIP] {step.id}: {step.description}")
                continue

            # Look up tool
            fn = get_tool(step.tool)

            # Capability gap handling
            if fn is None:
                print(f"  [GAP]  Unknown tool: {step.tool}")
                if on_capability_gap:
                    synthesised = on_capability_gap(step)
                    if synthesised:
                        fn = get_tool(step.tool)
                        report.synthesis_occurred = True
                        report.synthesised_tool_name = step.tool

                if fn is None:
                    step.status = StepStatus.FAILED
                    step.error = f"No tool '{step.tool}' found. Synthesis also failed."
                    done[step.id] = StepStatus.FAILED
                    print(f"  [FAIL] {step.id}: capability gap — {step.tool}")
                    continue

            # Execute
            step.status = StepStatus.RUNNING
            ts = time.time()
            try:
                step.api_calls_made = 1
                step.result = fn(**step.params)
                step.status = StepStatus.SUCCESS
                done[step.id] = StepStatus.SUCCESS
                print(f"  [OK]   {step.id}: {step.description}")
                if isinstance(step.result, list):
                    print(f"         → {len(step.result)} items")
                elif isinstance(step.result, dict) and step.result.get("id"):
                    print(f"         → id: {step.result['id']}")
            except N8NAPIError as e:
                step.status = StepStatus.FAILED
                step.error = str(e)
                done[step.id] = StepStatus.FAILED
                print(f"  [FAIL] {step.id}: n8n error — {e}")
            except Exception as e:
                step.status = StepStatus.FAILED
                step.error = f"{type(e).__name__}: {e}"
                done[step.id] = StepStatus.FAILED
                print(f"  [FAIL] {step.id}: {e}")
            finally:
                step.duration_seconds = time.time() - ts

        report.total_api_calls = sum(s.api_calls_made for s in steps)
        report.total_duration_seconds = time.time() - t0
        report.success = all(
            s.status == StepStatus.SUCCESS
            for s in steps if s.status != StepStatus.SKIPPED
        )
        if not report.success:
            failed = [s for s in steps if s.status == StepStatus.FAILED]
            if failed:
                report.failure_reason = f"'{failed[0].id}' failed: {failed[0].error}"
        return report