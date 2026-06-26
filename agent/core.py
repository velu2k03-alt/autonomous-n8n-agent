from dotenv import load_dotenv
from agent.planner import Planner
from agent.executor import Executor
from memory.execution_memory import ExecutionMemory
from memory.capability_memory import CapabilityMemory
from synthesis.engine import SynthesisEngine
from learning.tracker import LearningTracker
from models.report import ExecutionReport

load_dotenv()


class AgentCore:
    """
    Facade that wires together all components.
    External code (main.py, api/server.py) only calls agent.run(instruction).

    Design pattern: Facade
    Why: Callers don't need to know internal component details.
         Keeps the external API clean and individually testable.

    Component responsibilities:
    - Planner: decomposes instruction -> Steps (LLM-powered, memory-informed)
    - Executor: runs each step, handles failures, retries, result chaining
    - ExecutionMemory: episodic store of what the agent has done
    - CapabilityMemory: semantic store of what the agent can do
    - SynthesisEngine: generates new tools when a capability gap is detected
    - LearningTracker: records metrics to show measurable improvement over runs
    """

    def __init__(self):
        self.execution_memory = ExecutionMemory()
        self.capability_memory = CapabilityMemory()
        self.planner = Planner()
        self.executor = Executor()
        self.synthesis_engine = SynthesisEngine()
        self.tracker = LearningTracker()

        print("[Agent] Ready.")
        print(f"[Agent] Known tools in capability memory : {len(self.capability_memory.get_all_tools())}")
        print(f"[Agent] Synthesised tools already loaded  : {len(self.capability_memory.get_synthesised_tools())}")
        print(f"[Agent] Past executions in memory         : {self.execution_memory.count()}")

    def run(self, instruction: str) -> ExecutionReport:
        """
        Full agent run lifecycle:

        1. Check if the instruction is a rollback request; if so, trigger rollback of last run.
        2. Load similar past executions from execution memory
        3. Planner decomposes instruction -> Steps (using memory as context)
        4. Executor runs each step (triggers synthesis if capability gap found)
        5. Both memory layers updated with results and lessons
        6. Learning tracker updated with API call count
        7. ExecutionReport returned and printed
        """
        # Check if this is an explicit rollback/undo instruction
        clean_instr = instruction.strip().lower()
        if clean_instr in ("undo", "rollback", "rollback last run", "rollback last action", "revert", "revert last execution"):
            print(f"\n{'='*60}")
            print(f"[Agent] Processing explicit Rollback request...")
            print('='*60)
            
            # Find the most recent run that has registered rollback actions and has not been rolled back yet
            target_run = None
            target_idx = -1
            for idx in reversed(range(len(self.execution_memory._data["executions"]))):
                ex = self.execution_memory._data["executions"][idx]
                if ex.get("rollback_actions") and not ex.get("rollback_occurred"):
                    target_run = ex
                    target_idx = idx
                    break
                    
            if not target_run:
                print("[Rollback] No rollbackable past execution found (either none exists or already rolled back).")
                report = ExecutionReport(instruction=instruction, steps=[])
                report.success = False
                report.failure_reason = "No rollbackable execution found."
                return report
                
            print(f"[Rollback] Found execution to undo: '{target_run['instruction']}' from {target_run.get('timestamp')}")
            
            # Reconstruct rollback journal
            self.executor.rollback_journal = []
            for act in target_run["rollback_actions"]:
                self.executor.rollback_journal.append({
                    "step_id": "rollback_step",
                    "action": act
                })
                
            # Create a report for this rollback run
            report = ExecutionReport(instruction=instruction, steps=[])
            self.executor._trigger_rollback(report)
            
            # Mark the original run as rolled back
            self.execution_memory._data["executions"][target_idx]["rollback_occurred"] = True
            self.execution_memory._data["executions"][target_idx]["rollback_log"] = report.rollback_log
            
            # Save the new rollback run to memory
            report.success = True
            self.execution_memory.save(report)
            
            print(f"\n{'='*60}")
            print(report.summary())
            print('='*60)
            
            return report

        print(f"\n{'='*60}")
        print(f"[Agent] {instruction}")
        print('='*60)

        # STEP 1: Load similar past executions BEFORE planning
        past = self.execution_memory.get_similar(instruction, limit=5)
        if past:
            print(f"[Memory] {len(past)} similar past run(s) found — using as context")
            for p in past[:2]:
                calls = p.get("total_api_calls", "?")
                seq = [s["tool"] for s in p.get("steps", []) if s.get("status") == "success"]
                print(f"         Past: {p['instruction'][:50]} → {calls} calls, seq: {seq}")
        else:
            print("[Memory] No similar past runs — planning from scratch")

        # STEP 2: Plan using memory context
        print("[Planner] Decomposing instruction...")
        
        # Query capability memory for global & tool constraints + strategies
        global_constraints = self.capability_memory.get_global_constraints()
        tool_constraints = []
        for name, tool_data in self.capability_memory.get_all_tools().items():
            for c in tool_data.get("discovered_constraints", []):
                tool_constraints.append(f"Tool {name}: {c}")
                
        reusable_strategies = self.capability_memory.get_reusable_strategies()
        
        steps = self.planner.plan(
            instruction,
            past_executions=past,
            global_constraints=global_constraints,
            tool_constraints=tool_constraints,
            reusable_strategies=reusable_strategies
        )
        print(f"[Planner] {len(steps)} step(s) created:")
        for s in steps:
            deps = f" (needs {s.depends_on})" if s.depends_on else ""
            print(f"  {s.id}: {s.description} → {s.tool}{deps}")

        # STEP 3: Execute
        print(f"\n[Executor] Running {len(steps)} step(s)...")

        def on_gap(step):
            return self.synthesis_engine.synthesise(
                step=step,
                capability_memory=self.capability_memory
            )

        report = self.executor.execute(steps, instruction, on_capability_gap=on_gap)

        # STEP 4: Save results to both memory layers
        self.execution_memory.save(report)
        self.capability_memory.update_from_report(report)
        self.tracker.record(report)

        # STEP 5: Print full report
        print(f"\n{'='*60}")
        print(report.summary())
        print('='*60)

        return report